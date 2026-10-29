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
from app.models import Contact, Job, LinkedInOutreach, LinkedInProfile
from app.services import capture_review, ext_auth, linkedin, linkedin_page, linkedin_people

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
    parsed: dict[str, str] = {}  # what was read, so the panel can show / correct it
    sources: dict[str, str] = {}  # where each field came from (title, page, you, missing…)
    flags: list[dict[str, str]] = []  # capture_review: worth a look in the app
    undo: bool = False  # this click created the job: Undo (dismiss) is on offer
    description_chars: int = 0
    description_level: str = ""


class ExtJobIn(CaptureIn):
    """What the extension sends: the page `payload` (read here), plus `fields` the user typed in the
    panel for anything the page did not give. Plain capture fields still work too."""

    payload: dict[str, Any] | None = None
    fields: dict[str, Any] | None = None


_OVERRIDABLE = ("title", "company", "description", "location", "workplace", "company_url", "url")


def _job_fields(body: ExtJobIn) -> dict[str, Any]:
    data = linkedin_page.parse_job(body.payload) if body.payload else {}
    flat = body.model_dump(exclude={"payload", "fields"})
    typed = {k: v for k, v in (body.fields or {}).items() if k in _OVERRIDABLE and str(v).strip()}
    data = {**data, **{k: v for k, v in flat.items() if v not in ("", None, {}, [])}, **typed}
    sources = {**(data.get("sources") or {}), **{k: "you" for k in typed}}
    return {**data, "sources": sources}


@ext.post("/job", response_model=ExtJobOut)
def capture_job(body: ExtJobIn, session: ExtSession) -> ExtJobOut:
    """Read the page payload, validate, and save the job in one call. A missing required field
    saves nothing and says which (the panel then asks for it)."""
    try:
        c = linkedin.validate(_job_fields(body))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    if c.missing:
        return ExtJobOut(saved=False, missing=c.missing, warnings=c.warnings,
                         parsed={k: getattr(c, k) for k in ("title", "company", "location",
                                                            "workplace")})
    done = linkedin.import_job(engine, c, workspace="real")
    return ExtJobOut(saved=True, missing=[], warnings=done.warnings, job_id=done.job_id,
                     application_id=done.application_id, created=done.created,
                     duplicate_of=done.duplicate_of, matched_track=done.matched_track,
                     scoring=done.scoring, flags=done.flags, undo=done.created,
                     sources=c.sources, description_chars=len(c.description),
                     description_level=str(c.description_level),
                     parsed={k: getattr(c, k) for k in ("title", "company", "location",
                                                        "workplace")})


@ext.post("/paste", response_model=CaptureOut)
def paste(body: PasteIn, session: ExtSession) -> CaptureOut:
    """The fallback: a pasted URL + listing text becomes the same editable preview as a capture."""
    try:
        c = linkedin.validate(linkedin.from_paste(body.url, body.text))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    return CaptureOut(**vars(c), existing=linkedin.existing(session, c))


class PersonIn(BaseModel):
    payload: dict[str, Any] | None = None  # the extension's profile read
    paste: str | None = None  # the fallback: pasted profile text
    url: str = ""
    company: str | None = None  # typed in the panel when the page did not give it
    persona: str | None = None  # recruiter | lead | peer (a chip you picked)
    alumni: bool | None = None
    job_id: int | None = None  # None: best open job at the company; 0: keep as a contact only
    extension_version: str = ""


class ExtPersonOut(BaseModel):
    saved: bool
    flags: list[dict[str, str]] = []  # capture_review: worth a look in the app
    undo: bool = False  # this click created the person: Undo is on offer
    missing: list[str]
    warnings: list[str]
    name: str
    headline: str
    location: str
    current_title: str
    current_company: str
    degree: int | None
    persona: str
    persona_reasons: list[str]
    persona_source: str
    alumni: bool
    school: str | None
    education: list[str | None]
    job: dict[str, Any] | None
    existing: bool
    contact_id: int | None
    do_not_contact: str | None


class PersonPatch(BaseModel):
    persona: str | None = None
    alumni: bool | None = None
    job_id: int | None = None


def _person_args(body: PersonIn) -> dict[str, Any]:
    return {"payload": body.payload, "paste": body.paste, "url": body.url,
            "company": body.company, "persona": body.persona, "alumni": body.alumni,
            "job_id": body.job_id}


@ext.post("/person/preview", response_model=ExtPersonOut)
def preview_person(body: PersonIn, session: ExtSession) -> ExtPersonOut:
    """What saving this profile would do (role and why, alum, the job it joins). Writes nothing."""
    try:
        out = linkedin_people.preview(session, **_person_args(body))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.rollback()
    return ExtPersonOut(**out)


@ext.post("/person", response_model=ExtPersonOut)
def save_person(body: PersonIn, session: ExtSession) -> ExtPersonOut:
    try:
        out = linkedin_people.save(session, extension_version=body.extension_version,
                                   **_person_args(body))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ExtPersonOut(**out)


@ext.patch("/person/{contact_id}")
def patch_person(contact_id: int, body: PersonPatch, session: ExtSession) -> dict[str, Any]:
    try:
        return linkedin_people.update(session, contact_id, persona=body.persona,
                                      alumni=body.alumni, job_id=body.job_id)
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc


@ext.delete("/job/{job_id}")
def undo_job(job_id: int, session: ExtSession) -> dict[str, bool]:
    """Undo a capture that just created this job: it is dismissed, not deleted."""
    try:
        linkedin_people.undo_job(session, job_id)
    except linkedin.CaptureError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"undone": True}


@ext.delete("/person/{contact_id}")
def undo_person(contact_id: int, session: ExtSession) -> dict[str, bool]:
    """Undo a capture that just created this person (refused once you worked on them)."""
    try:
        linkedin_people.undo(session, contact_id)
    except linkedin.CaptureError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"undone": True}


# ------------------------------------------------------ the app's People list (no token)


class CapturedPersonOut(BaseModel):
    contact_id: int
    full_name: str
    headline: str
    current_title: str
    company: str
    company_id: int
    persona: str
    alumni: bool
    degree: int | None
    profile_url: str
    captured_at: Any
    jobs: list[dict[str, Any]]
    do_not_contact: bool
    flags: list[dict[str, str]] = []
    reviewed_at: str | None = None


class PeopleOut(BaseModel):
    items: list[CapturedPersonOut]
    total: int


@router.get("/linkedin/profiles", response_model=PeopleOut)
def captured_people(session: SessionDep) -> PeopleOut:
    """People captured with the extension: with a job, and the ones waiting for one."""
    items = linkedin_people.listing(session)
    return PeopleOut(items=[CapturedPersonOut(**x) for x in items], total=len(items))


class CapturedJobReview(BaseModel):
    job_id: int
    flags: list[dict[str, str]]
    reviewed_at: str | None
    needs_review: bool


class CapturedJobsOut(BaseModel):
    items: list[CapturedJobReview]
    total: int
    needs_review: int


@router.get("/linkedin/captured/jobs", response_model=CapturedJobsOut)
def captured_jobs(session: SessionDep) -> CapturedJobsOut:
    """The review state of every job captured from LinkedIn (the cards come from GET /jobs)."""
    rows = session.exec(select(Job.id, Job.capture).where(
        col(Job.linkedin_job_id).is_not(None))).all()
    items = []
    for job_id, cap in rows:
        review = (cap or {}).get("review") or {}
        items.append(CapturedJobReview(
            job_id=job_id, flags=review.get("flags", []), reviewed_at=review.get("reviewed_at"),
            needs_review=capture_review.needs_review(review)))
    return CapturedJobsOut(items=items, total=len(items),
                           needs_review=sum(i.needs_review for i in items))


@router.post("/linkedin/captured/jobs/{job_id}/reviewed", status_code=204)
def job_reviewed(job_id: int, session: SessionDep) -> None:
    job = session.get(Job, job_id)
    if job is None or not job.linkedin_job_id:
        raise HTTPException(404, "Not a job captured from LinkedIn")
    job.capture = {**(job.capture or {}),
                   "review": capture_review.mark_reviewed((job.capture or {}).get("review"))}
    session.add(job)
    session.commit()


@router.post("/linkedin/profiles/{contact_id}/reviewed", status_code=204)
def profile_reviewed(contact_id: int, session: SessionDep) -> None:
    try:
        linkedin_people.mark_reviewed(session, contact_id)
    except linkedin.CaptureError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/linkedin/profiles/{contact_id}")
def edit_profile(contact_id: int, body: PersonPatch, session: SessionDep) -> dict[str, Any]:
    """Change a captured person's role / alum flag (the app's own copy of PATCH /ext/person)."""
    try:
        return linkedin_people.update(session, contact_id, persona=body.persona,
                                      alumni=body.alumni, job_id=body.job_id)
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/linkedin/profiles/{contact_id}", status_code=204)
def delete_snapshot(contact_id: int, session: SessionDep) -> None:
    """Forget the captured profile fields. The contact and its LinkedIn messages stay."""
    prof = session.exec(select(LinkedInProfile).where(
        LinkedInProfile.contact_id == contact_id)).first()
    if prof is None:
        raise HTTPException(404, "No captured profile for this person")
    session.delete(prof)
    session.commit()


router.include_router(ext)
