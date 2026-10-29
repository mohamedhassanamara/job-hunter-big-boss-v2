"""The browser extension's API (docs/LINKEDIN_EXTENSION_DESIGN.md §2.4-2.5).

Two groups:
- `/linkedin/extension*`: Settings → LinkedIn creates / revokes the token (no token needed: it is
  the app's own UI talking to its own backend).
- `/ext/*`: what the extension calls, always with `Authorization: Bearer <token>`. These routes use
  the REAL workspace only (the tour sandbox never involves the extension) and never request
  linkedin.com.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from app.api.deps import SessionDep, WorkspaceDep
from app.api.linkedin import CaptureIn, CaptureOut, PasteIn
from app.config import get_settings
from app.db import engine, workspace_of
from app.models import Contact, Job, LinkedInOutreach
from app.services import ext_auth, linkedin

router = APIRouter()

# ------------------------------------------------------------- Settings → LinkedIn (no token)


class TokenStatusOut(BaseModel):
    available: bool  # False in the tour sandbox: the extension only works on the real workspace
    exists: bool
    created_at: str | None
    last_used_at: str | None
    extension_ids: list[str]


class TokenOut(BaseModel):
    token: str  # shown once; only its hash is stored


class TokenIn(BaseModel):
    """A JSON body is required on purpose: a plain cross-site form post cannot rotate the token."""

    label: str = ""


def _real_only(workspace: str) -> None:
    if workspace == "demo":
        raise HTTPException(409, "The extension works on your real workspace, not the tour sandbox")


@router.get("/linkedin/extension", response_model=TokenStatusOut)
def extension_status(session: SessionDep, workspace: WorkspaceDep) -> TokenStatusOut:
    ids = get_settings().extension_ids
    if workspace == "demo":
        return TokenStatusOut(available=False, exists=False, created_at=None, last_used_at=None,
                              extension_ids=ids)
    return TokenStatusOut(available=True, **ext_auth.status(session), extension_ids=ids)


@router.post("/linkedin/extension/token", response_model=TokenOut)
def create_token(_: TokenIn, session: SessionDep, workspace: WorkspaceDep) -> TokenOut:
    """A new token; the previous one stops working. The plain text is returned only here."""
    _real_only(workspace)
    return TokenOut(token=ext_auth.create(session))


@router.delete("/linkedin/extension/token", status_code=204)
def revoke_token(session: SessionDep, workspace: WorkspaceDep) -> None:
    _real_only(workspace)
    ext_auth.revoke(session)


# ------------------------------------------------------------------ /ext/* (token required)


def _ext_session(request: Request, authorization: Annotated[str | None, Header()] = None):  # noqa: ANN202
    if workspace_of(request) == "demo":
        raise HTTPException(400, "The extension never uses the tour sandbox")
    scheme, _, token = (authorization or "").partition(" ")
    with Session(engine) as session:
        if scheme.lower() != "bearer" or not ext_auth.verify(session, token.strip()):
            # same answer for "no token", "wrong token" and "revoked": nothing to probe
            raise HTTPException(401, "Invalid or missing extension token",
                                headers={"WWW-Authenticate": "Bearer"})
        yield session


ExtSession = Annotated[Session, Depends(_ext_session)]
ext = APIRouter(prefix="/ext", tags=["extension"])


class PingOut(BaseModel):
    ok: bool
    app: str
    jobs_captured_today: int
    people_total: int


@ext.get("/ping", response_model=PingOut)
def ping(session: ExtSession) -> PingOut:
    ext_auth.touch(session)
    midnight = linkedin.local_midnight()
    today = session.exec(select(func.count()).select_from(Job).where(
        col(Job.linkedin_job_id).is_not(None), Job.discovered_at >= midnight)).one()
    people = session.exec(select(func.count()).select_from(LinkedInOutreach)).one()
    return PingOut(ok=True, app="job-hunter-v2", jobs_captured_today=today, people_total=people)


class StatusOut(BaseModel):
    saved: bool
    job_id: int | None = None
    title: str | None = None
    company: str | None = None
    contact_id: int | None = None
    full_name: str | None = None


@ext.get("/status", response_model=StatusOut)
def saved_status(session: ExtSession, linkedin_job_id: str = "", profile: str = "") -> StatusOut:
    """Already saved? Keys come from the URL only (a job id, or the /in/<slug>)."""
    if linkedin_job_id:
        job = session.exec(select(Job).where(Job.linkedin_job_id == linkedin_job_id)).first()
        if job is None:
            return StatusOut(saved=False)
        return StatusOut(saved=True, job_id=job.id, title=job.title)
    if profile and "/" not in profile:
        url = linkedin.profile_url(f"https://www.linkedin.com/in/{profile}/")
        found = session.exec(
            select(Contact).where(col(Contact.linkedin_url).like(f"{url}%"))).first()
        if found is not None:
            return StatusOut(saved=True, contact_id=found.id, full_name=found.full_name)
    return StatusOut(saved=False)


class ExtJobOut(BaseModel):
    saved: bool  # False: a required field is missing, nothing was saved
    missing: list[str]
    warnings: list[str]
    job_id: int | None = None
    application_id: int | None = None
    created: bool = False
    duplicate_of: dict[str, Any] | None = None
    matched_track: str | None = None
    scoring: str = ""


@ext.post("/job", response_model=ExtJobOut)
def capture_job(body: CaptureIn, session: ExtSession) -> ExtJobOut:
    """Validate the captured fields and save the job in one call. A missing required field saves
    nothing and says which (the panel then asks for it)."""
    try:
        c = linkedin.validate(body.model_dump())
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    if c.missing:
        return ExtJobOut(saved=False, missing=c.missing, warnings=c.warnings)
    done = linkedin.import_job(engine, c, workspace="real")
    return ExtJobOut(saved=True, missing=[], warnings=done.warnings, job_id=done.job_id,
                     application_id=done.application_id, created=done.created,
                     duplicate_of=done.duplicate_of, matched_track=done.matched_track,
                     scoring=done.scoring)


@ext.post("/paste", response_model=CaptureOut)
def paste(body: PasteIn, session: ExtSession) -> CaptureOut:
    """The fallback: a pasted URL + listing text becomes the same editable preview as a capture."""
    try:
        c = linkedin.validate(linkedin.from_paste(body.url, body.text))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    return CaptureOut(**vars(c), existing=linkedin.existing(session, c))


router.include_router(ext)
