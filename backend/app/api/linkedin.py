"""LinkedIn section: daily search links (built in code), and the one-click import of a job
page you capture with the bookmark. Nothing here requests linkedin.com."""

from datetime import date
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


class RegenerateIn(BaseModel):
    feedback: str = ""  # "What should change?" (optional)


class RestoreIn(BaseModel):
    kind: str  # note | followup | inmail
    index: int  # into the message's `history`


class PersonOut(BaseModel):
    id: int
    contact_id: int
    full_name: str
    title: str | None
    linkedin_url: str | None
    group: str  # the note's angle: recruiter | lead | alumni | other (detected, overridable)
    alumni: bool
    hiring_team: bool  # they posted this job
    # The claim verifier on the current text: passed | failed | error | stale | none.
    note_verification_state: str = "none"
    followup_verification_state: str = "none"
    inmail_verification_state: str = "none"
    status: str
    note: dict[str, Any] | None
    followup: dict[str, Any] | None
    inmail: dict[str, Any] | None = None  # {subject, text, violations, verification, ...}
    inmail_sent_at: Any = None
    inmail_refunded_at: Any = None  # the credit came back (they replied within 90 days)
    source: str = "manual"  # manual | captured | viewed_profile
    reason: str = ""  # for you only: "viewed my profile on 20 Oct"
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
    company_id: int
    school: str | None
    max_chars: int
    inmail_max_chars: int = 1000
    credits: dict[str, Any] = {}  # InMail credits this month (Premium)
    requests_today: int
    daily_limit: int
    groups: list[GroupOut]
    people: list[PersonOut]
    agency: list[str]  # why the company looks like a recruiting agency (employer not named)
    order_hint: list[dict[str, Any]]  # apply → LinkedIn request today → email 1-2 days later


class PersonIn(BaseModel):
    full_name: str
    title: str | None = None
    linkedin_url: str | None = None
    group: str | None = None  # empty: detected from the title
    alumni: bool = False
    hiring_team: bool = False


class PersonPatch(BaseModel):
    note: str | None = None
    followup: str | None = None
    inmail_text: str | None = None
    inmail_subject: str | None = None
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
                     hiring_team=row.hiring_team,
                     status=row.status, note=row.note, followup=row.followup, inmail=row.inmail,
                     inmail_sent_at=row.inmail_sent_at, inmail_refunded_at=row.inmail_refunded_at,
                     source=row.source, reason=row.reason,
                     critique=row.critique, sent_at=row.sent_at, accepted_at=row.accepted_at,
                     messaged_at=row.messaged_at, replied_at=row.replied_at,
                     gap_hint=lt.gap_hint(s, c.id),
                     note_verification_state=_vstate(row.note),
                     followup_verification_state=_vstate(row.followup),
                     inmail_verification_state=_vstate(row.inmail, "inmail"))


def _vstate(message: dict | None, kind: str = "note") -> str:
    from app.services import verifier
    from app.services.linkedin_check import inmail_text

    if not message or not message.get("text"):
        return "none"
    text = inmail_text(message) if kind == "inmail" else message["text"]
    return verifier.state(message.get("verification"), text)


def _panel(s, app) -> PanelOut:  # noqa: ANN001
    from app.models import Company, Job
    from app.services import agency, tracks
    from app.services import linkedin_track as lt
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
                    company=s.get(Company, job.company_id).name, company_id=job.company_id,
                    school=lt.school(load_pool(s))[0], max_chars=int(cfg["note_max_chars"]),
                    inmail_max_chars=int(cfg["inmail_max_chars"]), credits=lt.credits(s),
                    requests_today=lt.requests_today(s), daily_limit=int(cfg["daily_requests"]),
                    groups=[GroupOut(**g) for g in lt.suggestions(s, app)],
                    people=[_person(s, r) for r in people], order_hint=order,
                    agency=agency.signals(s.get(Company, job.company_id), job))


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
               linkedin_url=body.linkedin_url,
               group=LinkedInGroup(body.group) if body.group else None,
               alumni=body.alumni, hiring_team=body.hiring_team)
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
    if body.inmail_text is not None or body.inmail_subject is not None:
        if not row.inmail:
            raise HTTPException(409, "Draft the InMail first")
        lt.edit(session, row, "inmail", body.inmail_text, body.inmail_subject)
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
    # Sending needs the exact text verified (moving back never does).
    gates = {(LinkedInStatus.to_contact, LinkedInStatus.sent): ("note", row.note),
             (LinkedInStatus.accepted, LinkedInStatus.messaged): ("follow-up", row.followup)}
    if gate := gates.get((LinkedInStatus(row.status), status)):
        label, message = gate
        if message and _vstate(message) != "passed":
            raise HTTPException(409, f"Verify the {label} first: every claim must hold before "
                                     "you send it")
    lt.set_status(session, row, status)
    session.commit()
    session.refresh(row)
    return _person(session, row)


@router.post("/linkedin/people/{row_id}/verify", response_model=PersonOut)
def verify_message(row_id: int, session: SessionDep, workspace: WorkspaceDep,
                   kind: str = "note") -> PersonOut:
    """Check every claim of the note (or follow-up) with Claude: Copy unlocks when it passes."""
    from app.services import verifier

    if kind not in ("note", "followup", "inmail"):
        raise HTTPException(422, "kind is note, followup or inmail")
    row = _row(session, row_id)
    try:
        verifier.code_checks_first(({"note": row.note, "followup": row.followup,
                                     "inmail": row.inmail}[kind] or {}).get("violations"))
        verifier.verify_linkedin(session, row, kind, verifier.for_workspace(session, workspace))
    except verifier.VerifyError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    session.refresh(row)
    return _person(session, row)


def _drafter(workspace: str):  # noqa: ANN202
    from app.providers.registry import linkedin_drafter

    return linkedin_drafter(mock=True if workspace == "demo" else None)


@router.post("/linkedin/people/{row_id}/note", response_model=PersonOut)
def draft_note(row_id: int, session: SessionDep, engine: EngineDep, workspace: WorkspaceDep,
               body: RegenerateIn | None = None) -> PersonOut:
    """Claude drafts the connection note (claude -p, your subscription), checked in code. With
    feedback ("What should change?") it edits the current note toward it."""
    from app.services import linkedin_track as lt

    _row(session, row_id)
    try:
        row = lt.draft_note(engine, row_id, _drafter(workspace),
                           (body or RegenerateIn()).feedback)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return _person(session, _row(session, row.id))


@router.post("/linkedin/people/{row_id}/followup", response_model=PersonOut)
def draft_followup(row_id: int, session: SessionDep, engine: EngineDep, workspace: WorkspaceDep,
                   body: RegenerateIn | None = None) -> PersonOut:
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
                                fetcher=SampleFetcher() if demo else None,
                                feedback=(body or RegenerateIn()).feedback)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return _person(session, _row(session, row.id))


@router.post("/linkedin/people/{row_id}/inmail", response_model=PersonOut)
def draft_inmail(row_id: int, session: SessionDep, engine: EngineDep, workspace: WorkspaceDep,
                 body: RegenerateIn | None = None) -> PersonOut:
    """Claude drafts a LinkedIn Premium InMail (subject + body, claude -p on your subscription),
    checked in code like the note. You send it yourself."""
    from app.services import linkedin_track as lt

    _row(session, row_id)
    try:
        row = lt.draft_inmail(engine, row_id, _drafter(workspace),
                             (body or RegenerateIn()).feedback)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return _person(session, _row(session, row.id))


@router.post("/linkedin/people/{row_id}/restore", response_model=PersonOut)
def restore_version(row_id: int, body: RestoreIn, session: SessionDep) -> PersonOut:
    """Go back to an earlier version of the note, follow-up or InMail (its `history`)."""
    from app.services import linkedin_track as lt

    row = _row(session, row_id)
    try:
        lt.restore_version(session, row, body.kind, body.index)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _person(session, _row(session, row_id))


@router.post("/linkedin/people/{row_id}/inmail/sent", response_model=PersonOut)
def inmail_sent(row_id: int, session: SessionDep) -> PersonOut:
    """You sent the InMail on LinkedIn: it uses a credit. Needs the exact text verified."""
    from app.services import linkedin_track as lt

    row = _row(session, row_id)
    if _vstate(row.inmail, "inmail") != "passed":
        raise HTTPException(409, "Verify the InMail first: every claim must hold before you "
                                 "send it")
    try:
        lt.send_inmail(session, row)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    session.refresh(row)
    return _person(session, row)


@router.post("/linkedin/people/{row_id}/inmail/unsent", response_model=PersonOut)
def inmail_unsent(row_id: int, session: SessionDep) -> PersonOut:
    """Undo "I sent the InMail": the credit comes back."""
    from app.services import linkedin_track as lt

    row = _row(session, row_id)
    try:
        lt.unsend_inmail(session, row)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    session.refresh(row)
    return _person(session, row)


@router.get("/linkedin/credits")
def linkedin_credits(session: SessionDep) -> dict[str, Any]:
    """InMail credits this month and the Premium end-date reminder (Settings → LinkedIn)."""
    from app.services import linkedin_track as lt

    return jsonable({"credits": lt.credits(session), "premium": lt.premium(session)})


class ViewerIn(BaseModel):
    full_name: str
    title: str | None = None
    company: str
    linkedin_url: str | None = None
    viewed_on: date | None = None  # default: today


class LinkIn(BaseModel):
    application_id: int


@router.post("/linkedin/viewers")
def add_viewer(body: ViewerIn, session: SessionDep) -> dict[str, Any]:
    """Quick-add someone who viewed your profile: a person in the LinkedIn track with the reason
    "viewed my profile on <date>", linked to your best open job at their company, or kept as a
    lead until a job at that company exists. The reason is for you; drafts never mention it."""
    from app.services import linkedin_track as lt

    try:
        result = lt.add_viewer(session, full_name=body.full_name, title=body.title,
                               company=body.company, linkedin_url=body.linkedin_url,
                               viewed_on=body.viewed_on)
    except (lt.LinkedInError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return jsonable(result)


@router.get("/linkedin/leads")
def linkedin_leads(session: SessionDep) -> list[dict[str, Any]]:
    """Viewer leads still waiting for a job at their company (those whose company now has one are
    linked first)."""
    from app.services import linkedin_track as lt

    out = lt.leads(session)
    session.commit()
    return jsonable(out)


@router.post("/linkedin/leads/{lead_id}/link")
def link_lead(lead_id: int, body: LinkIn, session: SessionDep) -> dict[str, Any]:
    from app.api.deps import get_or_404
    from app.models import LinkedInLead
    from app.services import linkedin_track as lt

    lead = get_or_404(session, LinkedInLead, lead_id, "Lead")
    try:
        row = lt.link_lead(session, lead, body.application_id)
    except lt.LinkedInError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"row_id": row.id, "application_id": body.application_id}


@router.delete("/linkedin/leads/{lead_id}", status_code=204)
def remove_lead(lead_id: int, session: SessionDep) -> None:
    from app.api.deps import get_or_404
    from app.models import LinkedInLead

    session.delete(get_or_404(session, LinkedInLead, lead_id, "Lead"))
    session.commit()


@router.get("/linkedin/summary")
def linkedin_summary(session: SessionDep) -> dict[str, Any]:
    """Searches not opened today, imports to decide on, requests to send, follow-ups due."""
    from app.services import linkedin_track as lt

    return jsonable(lt.summary(session))


def jsonable(value: Any) -> Any:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(value)


class CritiqueIn(BaseModel):
    kind: str  # cv | letter | email | linkedin_note | linkedin_followup
    id: int


@router.post("/critique")
def run_critique(body: CritiqueIn, session: SessionDep, workspace: WorkspaceDep) -> dict[str, Any]:
    """What's still weak in this document from the reader's side (one Claude call, no rewrite)."""
    from app.providers.registry import critic
    from app.services import critique

    try:
        result = critique.critique(session, body.kind, body.id,
                                   critic(mock=True if workspace == "demo" else None))
    except critique.CritiqueError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return result
