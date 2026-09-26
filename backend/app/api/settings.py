import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.api.deps import SessionDep
from app.config import get_settings
from app.db import engine
from app.models import AppSetting, SearchProfile, SourceRun
from app.models.enums import RemotePolicy
from app.schemas.settings import (
    SearchProfileIO,
    SettingsOut,
    SettingValue,
    SourceRunOut,
)
from app.seed.seed import reset_sandbox, seed
from app.services import scheduler
from app.services.discovery import is_running

router = APIRouter(tags=["settings"])

EDITABLE_KEYS = {"sources", "models", "smtp", "schedule", "lookup", "profile"}


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
        smtp_password_configured=bool(os.environ.get("SMTP_APP_PASSWORD")),
        database_path=get_settings().database_url.removeprefix("sqlite:///"),
        last_runs=last_runs(session),
        next_run_at=scheduler.next_run_at(),
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
    if key == "schedule":
        scheduler.configure(body.value)
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
    if not 1 <= body.max_age_days <= 365:
        raise HTTPException(422, "max_age_days must be between 1 and 365")
    profile = _profile(session)
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    session.add(profile)
    session.commit()
    return get_profile(session)


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
