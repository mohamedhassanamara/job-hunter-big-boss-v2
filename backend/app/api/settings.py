
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
from app.services import contacts, model_choice, scheduler
from app.services.discovery import is_running
from app.services.geo import country_catalog
from app.services.roles import all_titles, suggest_variants, with_suggested_variants
from app.services.scoring import recompute_all

router = APIRouter(tags=["settings"])

EDITABLE_KEYS = {
    "sources", "models", "smtp", "schedule", "lookup", "profile", "scoring", "company_boards",
    "cv", "tracking", "contacts", "outreach", "cover_letter", "writing", "research", "linkedin",
    "motivation", "providers", "generation", "gemini", "usage_log",
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
    from app.services.cv_rules import structure
    from app.services.cv_service import cv_settings

    cv = cv_settings(session)  # defaults for keys added by newer versions (guide, structure…)
    values["cv"] = {**cv, "structure": structure(cv)}
    from app.services.cover_letter import letter_settings

    values["cover_letter"] = letter_settings(session)
    from app.services.cover_letter import writing_settings

    values["writing"] = writing_settings(session)
    from app.services.research import research_settings

    values["research"] = research_settings(session)
    from app.services.linkedin import linkedin_settings

    values["linkedin"] = linkedin_settings(session)
    from app.services import motivation

    values["motivation"] = motivation.settings(session)
    from app.services import generation

    values["generation"] = generation.settings(session)
    from app.services import usage

    values["usage_log"] = usage.settings(session)
    from app.services import gemini_keys

    values["gemini"] = gemini_keys.config(session)
    values["smtp"] = {"gap_min_minutes": 4, "gap_max_minutes": 7, "max_per_queue": 20,
                      **{k: v for k, v in (values.get("smtp") or {}).items()
                         if k != "interval_minutes"}}
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
    _check_cv_structure(value)


def _check_smtp(value: dict) -> dict:
    """The random gap between sends: whole or decimal minutes, minimum at least 1, minimum not
    above the maximum. The old fixed `interval_minutes` is dropped."""
    lo, hi = value.get("gap_min_minutes", 4), value.get("gap_max_minutes", 7)
    if isinstance(lo, bool) or isinstance(hi, bool) or not all(
            isinstance(x, int | float) for x in (lo, hi)):
        raise HTTPException(422, "The gap between sends must be numbers of minutes")
    if lo < 1:
        raise HTTPException(422, "The minimum gap must be at least 1 minute")
    if lo > hi:
        raise HTTPException(422, "The minimum gap can't be above the maximum")
    if hi > 240:
        raise HTTPException(422, "The maximum gap is 240 minutes")
    return {**{k: v for k, v in value.items() if k != "interval_minutes"},
            "gap_min_minutes": lo, "gap_max_minutes": hi}


def _check_cv_structure(value: dict) -> None:
    from app.services.cv_rules import DEFAULT_STRUCTURE, parse_merges

    guide = value.get("writing_guide")
    if guide is not None and (not isinstance(guide, str) or len(guide) > 4000):
        raise HTTPException(422, "The writing guide must be text (at most 4000 characters)")
    rules = value.get("structure")
    if rules is not None:
        if not isinstance(rules, dict):
            raise HTTPException(422, "structure must be an object")
        for key, v in rules.items():
            default = DEFAULT_STRUCTURE.get(key)
            if default is None:
                raise HTTPException(422, f"Unknown structure rule {key}")
            if isinstance(default, list):
                if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v)
                        and 0 <= v[0] <= v[1] <= 8):
                    raise HTTPException(422, f"{key} must be [min, max] bullets (0-8)")
            elif key == "fill_min":
                if not isinstance(v, int | float) or not 0.5 <= v <= 1:
                    raise HTTPException(422, "fill_min must be between 0.5 and 1")
            elif not isinstance(v, int) or not 0 <= v <= 400:
                raise HTTPException(422, f"{key} must be a whole number")
    q = value.get("qualifiers")
    if q is not None and (not isinstance(q, list) or not all(isinstance(x, str) for x in q)):
        raise HTTPException(422, "qualifiers must be a list of words")
    for name in ("skill_display", "skill_keep"):
        table = value.get(name)
        if table is None:
            continue
        inner = str if name == "skill_display" else list
        if not isinstance(table, dict) or not all(
                isinstance(v, dict) and all(isinstance(x, inner) for x in v.values())
                for v in table.values()):
            raise HTTPException(422, f"{name} must map a track to {{category: "
                                f"{'name' if inner is str else 'list of skills'}}}")
    banned = value.get("banned_phrases")
    if banned is not None and (not isinstance(banned, list)
                               or not all(isinstance(b, str) for b in banned)):
        raise HTTPException(422, "banned_phrases must be a list of phrases")
    merges = value.get("skill_merges")
    if merges is not None:
        if not isinstance(merges, list) or not all(isinstance(m, str) for m in merges):
            raise HTTPException(422, "skill_merges must be a list of lines")
        bad = [m for m in merges if m.strip() and not parse_merges([m])]
        if bad:
            raise HTTPException(422, f"Can't read merge rule “{bad[0]}” (use “Parent: A, B”, "
                                     "“A + B” or “A / B”)")


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
    if key == "providers":
        _check_providers(body.value)
    if key == "profile":
        _check_profile(body.value)
    if key == "outreach":
        _check_outreach(body.value)
    if key == "cover_letter":
        _check_cover_letter(body.value)
    if key == "linkedin":
        for name, lo, hi in (("note_max_chars", 100, 300), ("daily_requests", 1, 100),
                             ("followup_days", 1, 60), ("gap_days", 0, 30),
                             ("inmail_monthly_credits", 0, 200), ("inmail_max_chars", 300, 1900),
                             ("premium_remind_days", 0, 120)):
            v = body.value.get(name)
            if v is not None and (not isinstance(v, int) or not lo <= v <= hi):
                raise HTTPException(422, f"{name} must be between {lo} and {hi}")
        end = body.value.get("premium_end_date")
        if end:
            from datetime import date

            try:
                date.fromisoformat(str(end))
            except ValueError as exc:
                raise HTTPException(422, "premium_end_date must be a date (YYYY-MM-DD)") from exc
        geos = body.value.get("geo_ids")
        if geos is not None:
            if not isinstance(geos, dict):
                raise HTTPException(422, "geo_ids must map country codes to {id, verified}")
            for code, g in geos.items():
                gid = str((g or {}).get("id") or "").strip() if isinstance(g, dict) else None
                if gid is None or (gid and not gid.isdigit()) or len(code) != 2:
                    raise HTTPException(422, f"{code}: a geoId is digits only (or empty)")
    if key == "smtp":
        body.value = _check_smtp(body.value)
    if key == "models":
        try:
            model_choice.check(body.value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if key == "generation":
        for name in ("auto_cv", "auto_email"):
            if not isinstance(body.value.get(name, False), bool):
                raise HTTPException(422, f"{name} must be true or false")
        body.value = {"auto_cv": bool(body.value.get("auto_cv", True)),
                      "auto_email": bool(body.value.get("auto_email", True))}
    if key == "usage_log":
        if not isinstance(body.value.get("enabled", True), bool):
            raise HTTPException(422, "enabled must be true or false")
        body.value = {"enabled": bool(body.value.get("enabled", True))}
    if key == "gemini":
        for name, lo, hi in (("max_keys", 1, 5), ("daily_cap", 10, 1000)):
            v = body.value.get(name)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool)
                                  or not lo <= v <= hi):
                raise HTTPException(422, f"{name} must be a whole number between {lo} and {hi}")
        # the pause switch and its reason are written by the app, never through this form
        from app.services import gemini_keys

        cur = gemini_keys.config(session)
        body.value = {"max_keys": body.value.get("max_keys", cur["max_keys"]),
                      "daily_cap": body.value.get("daily_cap", cur["daily_cap"]),
                      "paused": cur["paused"], "paused_reason": cur["paused_reason"],
                      "paused_at": cur["paused_at"]}
    if key == "motivation":
        _check_motivation(session, body.value)
    if key == "research":
        days = body.value.get("refresh_days", 30)
        if not isinstance(days, int) or not 1 <= days <= 365:
            raise HTTPException(422, "refresh_days must be between 1 and 365")
    if key == "writing" and body.value.get("work_authorization") not in ("never", "if_asked"):
        raise HTTPException(422, "work_authorization must be never or if_asked")
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


def _check_motivation(session: Session, value: dict) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from app.services import motivation

    for name, lo, hi in (("daily_goal", 1, 50), ("chest_goal", 1, 1000),
                         ("max_upload_mb", 1, 2000)):
        v = value.get(name)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise HTTPException(422, f"{name} must be between {lo} and {hi}")
    for name in ("enabled", "count_emails", "count_linkedin"):
        if not isinstance(value.get(name), bool):
            raise HTTPException(422, f"{name} must be true or false")
    try:
        ZoneInfo(str(value.get("timezone") or ""))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, "Unknown timezone (e.g. Africa/Tunis)") from exc
    # When chests started counting is set once: never moved by a settings save.
    value["chests_since"] = motivation.settings(session)["chests_since"]


def _check_outreach(value: dict) -> None:
    from pathlib import Path

    words = value.get("max_words", 150)
    if not isinstance(words, int) or not 50 <= words <= 400:
        raise HTTPException(422, "max_words must be between 50 and 400")
    banned = value.get("banned_phrases", [])
    if not isinstance(banned, list) or not all(isinstance(b, str) for b in banned):
        raise HTTPException(422, "banned_phrases must be a list of phrases")
    sig = value.get("signature") or {}
    if not isinstance(sig, dict) or not all(isinstance(v, bool) if k in ("show_phone",
                                                                         "show_contacts")
                                            else isinstance(v, str) for k, v in sig.items()):
        raise HTTPException(422, "signature fields must be text (show_phone: true or false)")
    photo = (sig.get("photo_path") or "").strip()
    if photo and not Path(photo).expanduser().is_file():
        raise HTTPException(422, f"Signature photo not found: {photo}")
    lang = value.get("language", "auto")
    if lang != "auto" and not (isinstance(lang, str) and len(lang) == 2):
        raise HTTPException(422, "language must be auto or a 2-letter code (en, fr…)")


def _check_cover_letter(value: dict) -> None:
    import string

    lo, hi = value.get("min_words", 250), value.get("max_words", 350)
    if not (isinstance(lo, int) and isinstance(hi, int) and 20 <= lo <= hi <= 600):
        raise HTTPException(422, "The word range must be between 20 and 600 (min ≤ max)")
    flo, fhi = value.get("form_min_words", 80), value.get("form_max_words", 220)
    if not (isinstance(flo, int) and isinstance(fhi, int) and 20 <= flo <= fhi <= 600):
        raise HTTPException(422, "The form text range must be between 20 and 600 (min ≤ max)")
    jargon = value.get("jargon", [])
    if not isinstance(jargon, list) or not all(isinstance(j, str) for j in jargon):
        raise HTTPException(422, "jargon must be a list of phrases")
    if value.get("language", "auto") not in ("auto", "fr", "en"):
        raise HTTPException(422, "language must be auto, fr or en")
    guide = value.get("guide", "")
    if not isinstance(guide, str) or len(guide) > 4000:
        raise HTTPException(422, "The writing guide must be text (at most 4000 characters)")
    for key in ("banned_phrases", "salutation", "closing"):
        per_language = value.get(key) or {}
        if not isinstance(per_language, dict) or set(per_language) - {"fr", "en"}:
            raise HTTPException(422, f"{key} must have fr and en entries")
        for v in per_language.values():
            ok = (isinstance(v, list) and all(isinstance(x, str) for x in v)) if \
                key == "banned_phrases" else isinstance(v, str)
            if not ok:
                raise HTTPException(422, f"{key}: wrong value type")
    pattern = str(value.get("filename_pattern") or "")
    fields = {f for _, f, _, _ in string.Formatter().parse(pattern) if f}
    if unknown := fields - {"full_name", "company", "job_title", "version"}:
        raise HTTPException(422, f"Unknown filename fields: {', '.join(sorted(unknown))}")


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
    exclude = value.get("exclude_keywords")
    if exclude is not None and (not isinstance(exclude, list)
                                or not all(isinstance(x, str) and x.strip() for x in exclude)):
        raise HTTPException(422, "exclude_keywords must be a list of words")
    days = value.get("verify_days")
    if days is not None and (not isinstance(days, int) or not 1 <= days <= 365):
        raise HTTPException(422, "verify_days must be between 1 and 365")
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


def _check_providers(value: dict) -> None:
    days = value.get("max_age_days")
    if days is not None and (not isinstance(days, int) or not 1 <= days <= 730):
        raise HTTPException(422, "max_age_days must be between 1 and 730")
    reveals = value.get("max_reveals")
    if reveals is not None and (not isinstance(reveals, int) or not 0 <= reveals <= 5):
        raise HTTPException(422, "max_reveals must be between 0 and 5")
    limits = value.get("limits")
    if limits is not None:
        if not isinstance(limits, dict) or set(limits) - {"hunter", "prospeo", "apollo", "apify"}:
            raise HTTPException(422, "limits must map hunter/prospeo/apollo/apify to numbers")
        if not all(isinstance(v, (int, float)) and 0 <= v <= 100_000 for v in limits.values()):
            raise HTTPException(422, "A monthly limit is a number between 0 and 100000")


def _check_profile(value: dict) -> None:
    from app.services import glossary

    entries = value.get("glossary")
    if entries is None:
        return
    if not isinstance(entries, list) or len(entries) > glossary.MAX_ENTRIES:
        raise HTTPException(422, f"The glossary is a list of at most {glossary.MAX_ENTRIES} terms")
    seen: set[str] = set()
    for i, e in enumerate(entries, 1):
        src = " ".join(str((e or {}).get("from") or "").split()) if isinstance(e, dict) else ""
        dst = " ".join(str(e.get("to") or "").split()) if isinstance(e, dict) else ""
        if not src or not dst:
            raise HTTPException(422, f"Glossary term {i} needs both words")
        if len(src) > glossary.MAX_TERM or len(dst) > glossary.MAX_TERM \
                or len(str(e.get("note") or "")) > glossary.MAX_NOTE:
            raise HTTPException(422, f"Glossary term {i} is too long")
        if src.lower() == dst.lower() or src.lower() in seen:
            raise HTTPException(422, f"Glossary term {i} repeats a word or a term already there")
        seen.add(src.lower())
