import os

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, select

from app.api.deps import SessionDep
from app.config import get_settings
from app.db import engine
from app.models import AppSetting, SearchProfile, SourceRun
from app.models.enums import RemotePolicy
from app.providers.registry import job_sources
from app.schemas.settings import (
    DiscoveryResult,
    SearchProfileIO,
    SettingsOut,
    SettingValue,
    SourceRunOut,
)
from app.services.discovery import RunInProgress, enabled_sources, run_discovery

router = APIRouter(tags=["settings"])

EDITABLE_KEYS = {"sources", "models", "smtp", "schedule", "lookup", "profile"}


def run_out(r: SourceRun) -> SourceRunOut:
    return SourceRunOut.model_validate(r, from_attributes=True)


def last_runs(session: Session) -> list[SourceRunOut]:
    latest: dict[str, SourceRun] = {}
    for r in session.exec(select(SourceRun).order_by(col(SourceRun.started_at))).all():
        latest[r.source] = r
    return [run_out(r) for r in sorted(latest.values(), key=lambda r: r.source)]


@router.get("/settings", response_model=SettingsOut)
def get_settings_view(session: SessionDep) -> SettingsOut:
    values = {s.key: s.value for s in session.exec(select(AppSetting)).all()}
    return SettingsOut(
        values=values,
        smtp_password_configured=bool(os.environ.get("SMTP_APP_PASSWORD")),
        database_path=get_settings().database_url.removeprefix("sqlite:///"),
        last_runs=last_runs(session),
    )


@router.put("/settings/{key}", response_model=SettingsOut)
def put_setting(key: str, body: SettingValue, session: SessionDep) -> SettingsOut:
    if key not in EDITABLE_KEYS:
        raise HTTPException(404, f"Unknown setting {key}")
    row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if row is None:
        row = AppSetting(key=key, value={})
    row.value = body.value
    session.add(row)
    session.commit()
    return get_settings_view(session)


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


@router.put("/search-profile", response_model=SearchProfileIO)
def put_profile(body: SearchProfileIO, session: SessionDep) -> SearchProfileIO:
    try:
        RemotePolicy(body.remote_policy)
    except ValueError as exc:
        raise HTTPException(422, f"Unknown remote policy {body.remote_policy}") from exc
    if not 0 <= body.min_fit_score <= 100:
        raise HTTPException(422, "min_fit_score must be between 0 and 100")
    profile = _profile(session)
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    session.add(profile)
    session.commit()
    return get_profile(session)


@router.post("/discovery/run", response_model=DiscoveryResult)
def discovery_run(session: SessionDep) -> DiscoveryResult:
    try:
        run_id = run_discovery(engine, job_sources(enabled_sources(session)))
    except RunInProgress as exc:
        raise HTTPException(409, str(exc)) from exc
    runs = session.exec(select(SourceRun).where(SourceRun.discovery_run_id == run_id)).all()
    return DiscoveryResult(runs=[run_out(r) for r in runs], new_jobs=sum(r.new_count for r in runs))


@router.post("/dev/reset", status_code=204)
def reset_demo(empty: bool = False) -> None:
    """Dev aid: reset the DB to the demo dataset, or to an empty workspace (to see empty states)."""
    from app.db import engine
    from app.seed.seed import seed

    seed(engine, empty=empty)
