
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.api.deps import SessionDep
from app.config import get_settings
from app.db import engine
from app.models import AppSetting, SearchProfile, SourceRun
from app.models.enums import RemotePolicy, RemoteScope
from app.providers.sources.boards import ATS_KINDS
from app.schemas.settings import (
    CountryOut,
    SearchProfileIO,
    SettingsOut,
    SettingValue,
    SourceRunOut,
)
from app.seed.seed import reset_sandbox, seed
from app.services import contacts, scheduler
from app.services.discovery import is_running
from app.services.geo import country_catalog
from app.services.roles import all_titles, suggest_variants, with_suggested_variants
from app.services.scoring import recompute_all

router = APIRouter(tags=["settings"])

EDITABLE_KEYS = {
    "sources", "models", "smtp", "schedule", "lookup", "profile", "scoring", "company_boards",
    "cv", "tracking", "contacts", "outreach",
}


def run_out(r: SourceRun) -> SourceRunOut:
    return SourceRunOut.model_validate(r, from_attributes=True)


def last_runs(session: Session) -> list[SourceRunOut]:
    latest: dict[str, SourceRun] = {}
    rows = session.exec(
        select(SourceRun)
        .where(col(SourceRun.status).not_in(["pending", "running"]))
        .order_by(col(SourceRun.started_at))
    ).all()
    for r in rows:
        if not (r.details or {}).get("dry_run"):
            latest[r.source] = r
    return [run_out(r) for r in sorted(latest.values(), key=lambda r: r.source)]


@router.get("/settings", response_model=SettingsOut)
def get_settings_view(session: SessionDep) -> SettingsOut:
    values = {s.key: s.value for s in session.exec(select(AppSetting)).all()}
    return SettingsOut(
        values=values,
        smtp_password_configured=bool(get_settings().smtp_app_password),
        database_path=get_settings().database_url.removeprefix("sqlite:///"),
        last_runs=last_runs(session),
        next_run_at=scheduler.next_run_at(),
    )


def _check_cv(value: dict) -> None:
    from app.services.cv_templates import validate

    name = value.get("default_template") or "default"
    try:
        status = validate(name)
    except KeyError as exc:
        raise HTTPException(422, f"Unknown template {name}") from exc
    if not status.valid:
        raise HTTPException(422, f"Template {name} isn't valid yet: {status.error}")
    pattern = str(value.get("filename_pattern") or "")
    if pattern and "{" in pattern:
        import string

        fields = {f for _, f, _, _ in string.Formatter().parse(pattern) if f}
        if unknown := fields - {"full_name", "company", "job_title", "version"}:
            raise HTTPException(422, f"Unknown filename fields: {', '.join(sorted(unknown))}")


def _check_boards(value: dict) -> None:
    rows = value.get("boards")
    if not isinstance(rows, list):
        raise HTTPException(422, "company_boards needs a 'boards' list")
    for i, row in enumerate(rows, 1):
        if str(row.get("ats", "")).lower() not in ATS_KINDS:
            raise HTTPException(422, f"Board {i}: ats must be one of {', '.join(ATS_KINDS)}")
        if not str(row.get("token", "")).strip():
            raise HTTPException(422, f"Board {i}: the board token is empty")


@router.put("/settings/{key}", response_model=SettingsOut)
def put_setting(key: str, body: SettingValue, session: SessionDep) -> SettingsOut:
    if key not in EDITABLE_KEYS:
        raise HTTPException(404, f"Unknown setting {key}")
    if key == "company_boards":
        _check_boards(body.value)
    if key == "cv":
        _check_cv(body.value)
    if key == "tracking":
        days = body.value.get("followup_days")
        ghost = body.value.get("ghost_after_days")
        if not isinstance(days, list) or not all(isinstance(d, int) and 0 < d <= 365 for d in days):
            raise HTTPException(422, "followup_days must be a list of days between 1 and 365")
        if not isinstance(ghost, int) or not 1 <= ghost <= 365:
            raise HTTPException(422, "ghost_after_days must be between 1 and 365")
    if key == "contacts":
        _check_contacts(body.value)
    if key == "outreach":
        _check_outreach(body.value)
    if key == "lookup":
        cap = body.value.get("daily_cap")
        if not isinstance(cap, int) or not 1 <= cap <= 100:
            raise HTTPException(422, "daily_cap must be between 1 and 100")
        body.value = {"daily_cap": cap}  # "used today" is computed, never stored
    row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if row is None:
        row = AppSetting(key=key, value={})
    row.value = body.value
    session.add(row)
    session.commit()
    if key == "contacts":
        contacts.rerank_all(session)
        contacts.match_all(session)  # a new ranking can change who each job is written to
        session.commit()
    if key == "schedule":
        scheduler.configure(body.value)
    if key in ("scoring", "profile"):
        # Weights, the hard-flag cap and work authorization only change arithmetic: recompute
        # every stored score from its sub-scores (no LLM). Profile edits also make scores stale.
        recompute_all(session.get_bind())  # type: ignore[arg-type]
    return get_settings_view(session)


def _check_outreach(value: dict) -> None:
    from pathlib import Path

    words = value.get("max_words", 150)
    if not isinstance(words, int) or not 50 <= words <= 400:
        raise HTTPException(422, "max_words must be between 50 and 400")
    banned = value.get("banned_phrases", [])
    if not isinstance(banned, list) or not all(isinstance(b, str) for b in banned):
        raise HTTPException(422, "banned_phrases must be a list of phrases")
    sig = value.get("signature") or {}
    if not isinstance(sig, dict) or not all(isinstance(v, str) for v in sig.values()):
        raise HTTPException(422, "signature fields must be text")
    photo = (sig.get("photo_path") or "").strip()
    if photo and not Path(photo).expanduser().is_file():
        raise HTTPException(422, f"Signature photo not found: {photo}")
    lang = value.get("language", "auto")
    if lang != "auto" and not (isinstance(lang, str) and len(lang) == 2):
        raise HTTPException(422, "language must be auto or a 2-letter code (en, fr…)")


def _check_contacts(value: dict) -> None:
    ranking = value.get("role_ranking")
    if not isinstance(ranking, list) or not ranking:
        raise HTTPException(422, "role_ranking must be a non-empty list")
    for group in ranking:
        keywords = group.get("keywords") if isinstance(group, dict) else None
        if not isinstance(group.get("label"), str) or not group["label"].strip():
            raise HTTPException(422, "Every ranking group needs a label")
        if not isinstance(keywords, list) or not keywords or \
                not all(isinstance(k, str) and k.strip() for k in keywords):
            raise HTTPException(422, f"“{group['label']}” needs at least one keyword")
    labels = {g["label"] for g in ranking}
    for key in ("small_order", "large_order"):
        order = value.get(key)
        if order is None:
            continue
        if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
            raise HTTPException(422, f"{key} must be a list of group labels")
        unknown = [x for x in order if x not in labels]
        if unknown:
            raise HTTPException(422, f"{key}: unknown group {', '.join(unknown)}")
    threshold = value.get("small_company_threshold")
    if threshold is not None and (not isinstance(threshold, int) or not 1 <= threshold <= 100_000):
        raise HTTPException(422, "small_company_threshold must be a number of employees")


def _profile(session: Session) -> SearchProfile:
    profile = session.exec(select(SearchProfile).where(SearchProfile.is_active)).first()
    if profile is None:
        profile = SearchProfile(name="Default")
        session.add(profile)
        session.flush()
    return profile


@router.get("/search-profile", response_model=SearchProfileIO)
def get_profile(session: SessionDep) -> SearchProfileIO:
    return SearchProfileIO.model_validate(_profile(session), from_attributes=True)


@router.get("/countries", response_model=list[CountryOut])
def countries() -> list[CountryOut]:
    """Countries the location parser recognises (the Settings picker offers exactly these)."""
    return [CountryOut(**c) for c in country_catalog()]


@router.put("/search-profile", response_model=SearchProfileIO)
def put_profile(body: SearchProfileIO, session: SessionDep) -> SearchProfileIO:
    try:
        RemotePolicy(body.remote_policy)
    except ValueError as exc:
        raise HTTPException(422, f"Unknown remote policy {body.remote_policy}") from exc
    try:
        RemoteScope(body.remote_scope)
    except ValueError as exc:
        raise HTTPException(422, f"Unknown remote scope {body.remote_scope}") from exc
    known = {c["code"] for c in country_catalog()}
    if unknown := [c for c in body.locations if c not in known]:
        raise HTTPException(422, f"Unknown country codes: {', '.join(unknown)}")
    if not 0 <= body.min_fit_score <= 100:
        raise HTTPException(422, "min_fit_score must be between 0 and 100")
    if not 1 <= body.max_age_days <= 365:
        raise HTTPException(422, "max_age_days must be between 1 and 365")
    tracks = with_suggested_variants([t.model_dump() for t in body.tracks])
    names = [t["name"].lower() for t in tracks]
    if any(not n for n in names) and len(tracks) > 1:
        raise HTTPException(422, "Every track needs a name")
    if len(set(names)) != len(names):
        raise HTTPException(422, "Track names must be unique")
    profile = _profile(session)
    for key, value in body.model_dump(exclude={"tracks", "roles"}).items():
        setattr(profile, key, value)
    profile.tracks = tracks
    profile.roles = all_titles(tracks)  # flat list for code that only needs titles
    session.add(profile)
    session.commit()
    return get_profile(session)


class SuggestIn(BaseModel):
    title: str


@router.post("/roles/suggest", response_model=dict[str, list[str]])
def suggest(body: SuggestIn) -> dict[str, list[str]]:
    """Common equivalents of a job title per language (the user edits them before saving)."""
    return suggest_variants(body.title)


class EraseIn(BaseModel):
    confirm: str


@router.post("/sandbox/reset", status_code=204)
def reset_sandbox_endpoint() -> None:
    """Rebuild the tour sandbox from fixtures (called at every tour start)."""
    reset_sandbox()


@router.post("/workspace/erase", status_code=204)
def erase_workspace(body: EraseIn) -> None:
    """Erase ALL real data (jobs, contacts, CVs, drafts, experience). Keeps profile + settings
    defaults. Requires typing ERASE."""
    if body.confirm != "ERASE":
        raise HTTPException(422, 'Type "ERASE" to confirm')
    if is_running():
        raise HTTPException(409, "A discovery run is in progress")
    seed(engine, empty=True)
