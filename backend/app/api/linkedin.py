"""LinkedIn section: daily search links (built in code), and the one-click import of a job
page you capture with the bookmark. Nothing here requests linkedin.com."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import EngineDep, SessionDep, WorkspaceDep
from app.services import linkedin

router = APIRouter(tags=["linkedin"])


class LinkOut(BaseModel):
    key: str
    role: str
    country: str
    country_name: str
    geo_id: str
    verified: bool
    url: str
    opened_today: bool


class LinkGroupOut(BaseModel):
    track: str
    role: str
    links: list[LinkOut]


class LinksOut(BaseModel):
    groups: list[LinkGroupOut]
    total: int
    opened: int
    missing_geo: list[dict[str, str]]  # target countries with no geoId: no link


class OpenIn(BaseModel):
    key: str


class CaptureIn(BaseModel):
    """What the bookmarklet sends (or the import window, after your edits)."""

    url: str = ""
    job_id: str | None = None
    title: str = ""
    company: str = ""
    company_url: str | None = None
    location: str = ""
    workplace: str = ""
    description: str = ""
    poster: dict[str, Any] | None = None
    sources: dict[str, str] = {}


class PasteIn(BaseModel):
    url: str = ""
    text: str


class CaptureOut(BaseModel):
    url: str
    job_id: str | None
    title: str
    company: str
    company_url: str | None
    location: str
    workplace: str
    description: str
    poster: dict[str, str] | None
    sources: dict[str, str]
    missing: list[str]
    warnings: list[str]
    existing: dict[str, Any] | None


class ImportOut(BaseModel):
    job_id: int
    application_id: int
    created: bool
    duplicate_of: dict[str, Any] | None
    matched_track: str | None
    warnings: list[str]
    scoring: str


@router.get("/linkedin/links", response_model=LinksOut)
def links(session: SessionDep, remote: bool = False, easy: bool = False) -> LinksOut:
    """One LinkedIn job search per role × target country, past 24 hours, newest first."""
    found = linkedin.search_links(session, remote=remote, easy=easy)
    out = [LinkGroupOut(track=g.track, role=g.role,
                        links=[LinkOut(**vars(x)) for x in g.links]) for g in found.groups]
    every = [x for g in found.groups for x in g.links]
    return LinksOut(groups=out, total=len(every), opened=sum(x.opened_today for x in every),
                    missing_geo=found.missing_geo)


@router.post("/linkedin/links/open", status_code=204)
def open_link(body: OpenIn, session: SessionDep) -> None:
    """You opened a search link today (the mark resets tomorrow)."""
    linkedin.mark_opened(session, body.key)
    session.commit()


def _capture_out(session, c: linkedin.Capture) -> CaptureOut:  # noqa: ANN001
    return CaptureOut(**vars(c), existing=linkedin.existing(session, c))


@router.post("/linkedin/capture", response_model=CaptureOut)
def check_capture(body: CaptureIn, session: SessionDep) -> CaptureOut:
    """The import window's preview: every field, how it was found, what's missing, and whether
    the job is already in your list. Nothing is saved."""
    try:
        return _capture_out(session, linkedin.validate(body.model_dump()))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/linkedin/paste", response_model=CaptureOut)
def check_paste(body: PasteIn, session: SessionDep) -> CaptureOut:
    """The fallback when the capture fails: a pasted URL and listing."""
    try:
        return _capture_out(session, linkedin.validate(linkedin.from_paste(body.url, body.text)))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/linkedin/import", response_model=ImportOut)
def import_job(body: CaptureIn, engine: EngineDep, workspace: WorkspaceDep) -> ImportOut:
    """Save the job (source LinkedIn): deduped, its track matched, scored on its own now."""
    try:
        c = linkedin.validate(body.model_dump())
        result = linkedin.import_job(engine, c, workspace=workspace)
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ImportOut(**vars(result))


# ------------------------------------------------------------------- the LinkedIn messages track


class PersonOut(BaseModel):
    id: int
    contact_id: int
    full_name: str
    title: str | None
    linkedin_url: str | None
    group: str
    alumni: bool
    status: str
    note: dict[str, Any] | None
    followup: dict[str, Any] | None
    critique: dict[str, Any] | None
    sent_at: Any = None
    accepted_at: Any = None
    messaged_at: Any = None
    replied_at: Any = None
    gap_hint: str | None  # "Emailed on 1 Oct: request after 4 Oct"


class GroupOut(BaseModel):
    group: str
    label: str
    why: str
    search: str | None
    titles: list[str] = []


class PanelOut(BaseModel):
    application_id: int
    job_id: int
    company: str
    school: str | None
    max_chars: int
    requests_today: int
    daily_limit: int
    groups: list[GroupOut]
    people: list[PersonOut]
    order_hint: list[dict[str, Any]]  # apply → LinkedIn request today → email 1-2 days later


class PersonIn(BaseModel):
    full_name: str
    title: str | None = None
    linkedin_url: str | None = None
    group: str = "other"
    alumni: bool = False


class PersonPatch(BaseModel):
    note: str | None = None
    followup: str | None = None
    group: str | None = None
    alumni: bool | None = None


class StatusIn(BaseModel):
    status: str  # to_contact | sent | accepted | messaged | replied


def _person(s, row) -> PersonOut:  # noqa: ANN001
    from app.models import Contact
    from app.services import linkedin_track as lt

    c = s.get(Contact, row.contact_id)
    return PersonOut(id=row.id, contact_id=c.id, full_name=c.full_name, title=c.title,
                     linkedin_url=c.linkedin_url, group=row.group, alumni=row.alumni,
                     status=row.status, note=row.note, followup=row.followup,
                     critique=row.critique, sent_at=row.sent_at, accepted_at=row.accepted_at,
                     messaged_at=row.messaged_at, replied_at=row.replied_at,
                     gap_hint=lt.gap_hint(s, c.id))


def _panel(s, app) -> PanelOut:  # noqa: ANN001
    from app.models import Company, Job
    from app.services import linkedin_track as lt
    from app.services import tracks
    from app.services.cv_pool import load_pool

    job = s.get(Job, app.job_id)
    cfg = linkedin.linkedin_settings(s)
    people = lt.rows(s, app)
    t = tracks.for_app(s, app)
    order = [{"step": "Apply on the website", "done": t.application == "applied"},
             {"step": "LinkedIn request, the same day", "done": t.linkedin not in ("none",
                                                                                   "to_contact")},
             {"step": "Email, 1-2 days later", "done": t.outreach in ("queued", "sent")}]
    return PanelOut(application_id=app.id, job_id=job.id,
                    company=s.get(Company, job.company_id).name,
                    school=lt.school(load_pool(s))[0], max_chars=int(cfg["note_max_chars"]),
                    requests_today=lt.requests_today(s), daily_limit=int(cfg["daily_requests"]),
                    groups=[GroupOut(**g) for g in lt.suggestions(s, app)],
                    people=[_person(s, r) for r in people], order_hint=order)


def _app(session, app_id: int):  # noqa: ANN001, ANN202
    from app.api.deps import get_or_404
    from app.models import Application

    return get_or_404(session, Application, app_id, "Application")


def _row(session, row_id: int):  # noqa: ANN001, ANN202
    from app.api.deps import get_or_404
    from app.models import LinkedInOutreach

    return get_or_404(session, LinkedInOutreach, row_id, "Person")


@router.get("/applications/{app_id}/linkedin", response_model=PanelOut)
def panel(app_id: int, session: SessionDep) -> PanelOut:
    """Who to message (with search links), the people you added, their notes and statuses."""
    return _panel(session, _app(session, app_id))


@router.post("/applications/{app_id}/linkedin/people", response_model=PanelOut)
def add_person(app_id: int, body: PersonIn, session: SessionDep) -> PanelOut:
    from app.models.enums import LinkedInGroup
    from app.services import linkedin_track as lt

    app = _app(session, app_id)
    try:
        lt.add(session, app, full_name=body.full_name, title=body.title,
               linkedin_url=body.linkedin_url, group=LinkedInGroup(body.group),
               alumni=body.alumni)
    except (lt.LinkedInError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _panel(session, app)


@router.patch("/linkedin/people/{row_id}", response_model=PersonOut)
def patch_person(row_id: int, body: PersonPatch, session: SessionDep) -> PersonOut:
    """Edit the note or follow-up (checked again), or the group / alumni flag."""
    from app.models.enums import LinkedInGroup
    from app.services import linkedin_track as lt

    row = _row(session, row_id)
    if body.group is not None:
        row.group = LinkedInGroup(body.group)
    if body.alumni is not None:
        row.alumni = body.alumni
    if body.note is not None:
        lt.edit(session, row, "note", body.note)
    if body.followup is not None:
        lt.edit(session, row, "followup", body.followup)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _person(session, row)


@router.delete("/linkedin/people/{row_id}", status_code=204)
def remove_person(row_id: int, session: SessionDep) -> None:
    session.delete(_row(session, row_id))
    session.commit()


@router.post("/linkedin/people/{row_id}/status", response_model=PersonOut)
def set_status(row_id: int, body: StatusIn, session: SessionDep) -> PersonOut:
    """You did it on LinkedIn (sent, accepted, messaged, replied): recorded here."""
    from app.models.enums import LinkedInStatus
    from app.services import linkedin_track as lt

    row = _row(session, row_id)
    try:
        status = LinkedInStatus(body.status)
    except ValueError as exc:
        raise HTTPException(422, "Unknown status") from exc
    lt.set_status(session, row, status)
    session.commit()
    session.refresh(row)
    return _person(session, row)


def _drafter(workspace: str):  # noqa: ANN202
    from app.providers.registry import linkedin_drafter

    return linkedin_drafter(mock=True if workspace == "demo" else None)


@router.post("/linkedin/people/{row_id}/note", response_model=PersonOut)
def draft_note(row_id: int, session: SessionDep, engine: EngineDep,
               workspace: WorkspaceDep) -> PersonOut:
    """Claude drafts the connection note (claude -p, your subscription), checked in code."""
    from app.services import linkedin_track as lt

    _row(session, row_id)
    try:
        row = lt.draft_note(engine, row_id, _drafter(workspace))
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return _person(session, _row(session, row.id))


@router.post("/linkedin/people/{row_id}/followup", response_model=PersonOut)
def draft_followup(row_id: int, session: SessionDep, engine: EngineDep,
                   workspace: WorkspaceDep) -> PersonOut:
    """After they accept: one proof and one direct ask (company research reused, or run here
    if the company has none)."""
    from app.api.outreach import _research_models
    from app.providers.registry import researcher as research_provider
    from app.services import linkedin_track as lt
    from app.services.research import SampleFetcher

    _row(session, row_id)
    model, fallback = _research_models(session)
    demo = workspace == "demo"
    try:
        row = lt.draft_followup(engine, row_id, _drafter(workspace),
                                researcher=research_provider(mock=True if demo else None,
                                                             model=model, fallback=fallback),
                                fetcher=SampleFetcher() if demo else None)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return _person(session, _row(session, row.id))


@router.get("/linkedin/summary")
def linkedin_summary(session: SessionDep) -> dict[str, Any]:
    """Searches not opened today, imports to decide on, requests to send, follow-ups due."""
    from app.services import linkedin_track as lt

    return jsonable(lt.summary(session))


def jsonable(value: Any) -> Any:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(value)
