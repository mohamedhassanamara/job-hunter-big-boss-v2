"""The Get contact step (Phase 9): Contacts to get, per-job view, verify / found / edit, nobody
found / never look up, paste parsing, and Try Hunter (a click, never automatic)."""

from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.api.deps import SessionDep, WorkspaceDep, get_or_404
from app.models import Application, AppSetting, Company, Contact, Job
from app.models.base import utcnow
from app.models.enums import ContactSearch, ContactSource
from app.providers.registry import hunter as hunter_provider
from app.schemas.get_contact import (
    ContactEdit,
    ContactSearchIn,
    FoundIn,
    GetContactView,
    HunterCredits,
    HunterFindIn,
    HunterFindOut,
    HunterVerifyIn,
    HunterVerifyOut,
    PasteIn,
    PasteOut,
    ToGetItem,
    ToGetQueue,
    VerifyIn,
)
from app.services import contact_paste, contacts, get_contact
from app.services.pipeline import stage_label
from app.services.views import fit_brief, latest_fits

router = APIRouter(tags=["get-contact"])


def _view(s: Session, app: Application) -> GetContactView:
    return GetContactView.model_validate(get_contact.view(s, app), from_attributes=True)


def queue_out(session: Session, limit: int | None = None) -> ToGetQueue:
    rows = get_contact.queue(session)
    total = len(rows)
    rows = rows[:limit] if limit else rows
    fits = latest_fits(session, [r.job.id for r in rows])
    days = get_contact.verify_days(session)
    return ToGetQueue(
        items=[ToGetItem(application_id=r.app.id, job_id=r.job.id, job_title=r.job.title,
                         company_id=r.company.id, company_name=r.company.name,
                         stage=r.app.stage, stage_label=stage_label(r.app.stage),
                         fit=fit_brief(fits.get(r.job.id)), state=r.state,
                         nobody_found=r.nobody_found,
                         contact_name=r.contact.full_name if r.contact else None,
                         stale=bool(r.contact and r.contact.verified_at
                                    and not get_contact.is_current(r.contact, days)))
               for r in rows],
        total=total, found_today=contacts.found_today(session),
        daily_limit=contacts.daily_cap(session))


@router.get("/contacts/to-get", response_model=ToGetQueue)
def to_get(session: SessionDep) -> ToGetQueue:
    """Contacts to get: jobs past New that need a contact or a verification, best fit first."""
    return queue_out(session)


@router.get("/applications/{app_id}/get-contact", response_model=GetContactView)
def get_contact_view(app_id: int, session: SessionDep) -> GetContactView:
    return _view(session, get_or_404(session, Application, app_id, "Application"))


@router.post("/applications/{app_id}/contact/verify", response_model=GetContactView)
def verify(app_id: int, body: VerifyIn, session: SessionDep) -> GetContactView:
    """Still there (verified today) / left / wrong person (never picked again)."""
    app = get_or_404(session, Application, app_id, "Application")
    try:
        get_contact.verify(session, app, body.action)
    except get_contact.GetContactError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    session.refresh(app)
    return _view(session, app)


@router.post("/applications/{app_id}/contact/found", response_model=GetContactView)
def found(app_id: int, body: FoundIn, session: SessionDep) -> GetContactView:
    """Someone you found (Apollo extension or Hunter): saved verified, set on the job."""
    app = get_or_404(session, Application, app_id, "Application")
    source = ContactSource.hunter if body.via == "hunter" else ContactSource.found
    try:
        get_contact.found(session, app, full_name=body.full_name, title=body.title,
                          email=body.email, linkedin_url=body.linkedin_url, source=source)
    except get_contact.GetContactError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    session.refresh(app)
    return _view(session, app)


@router.patch("/contacts/{contact_id}", response_model=GetContactView | None)
def edit_contact(contact_id: int, body: ContactEdit, session: SessionDep,
                 application_id: int | None = None) -> GetContactView | None:
    """Edit details. A new email counts as a new entry (verified today)."""
    contact = get_or_404(session, Contact, contact_id, "Contact")
    try:
        get_contact.edit(session, contact, **body.model_dump(exclude_unset=True))
    except get_contact.GetContactError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    if application_id is None:
        return None
    return _view(session, get_or_404(session, Application, application_id, "Application"))


@router.post("/companies/{company_id}/contact-search", response_model=GetContactView | None)
def set_contact_search(company_id: int, body: ContactSearchIn,
                       session: SessionDep) -> GetContactView | None:
    """Nobody found / never look up (a job board: web apply only) / undo (none)."""
    get_or_404(session, Company, company_id, "Company")
    try:
        status = ContactSearch(body.status)
    except ValueError as exc:
        raise HTTPException(422, "status is none, not_found or never") from exc
    contacts.set_contact_search(session, company_id, status, body.notes)
    session.commit()
    if body.application_id is None:
        return None
    return _view(session, get_or_404(session, Application, body.application_id, "Application"))


@router.post("/companies/{company_id}/not-aggregator", response_model=GetContactView | None)
def not_aggregator(company_id: int, session: SessionDep,
                   application_id: int | None = None) -> GetContactView | None:
    """You checked the "looks like a job board" suggestion: it's a real employer."""
    company = get_or_404(session, Company, company_id, "Company")
    company.aggregator_reviewed = True
    session.add(company)
    session.commit()
    if application_id is None:
        return None
    return _view(session, get_or_404(session, Application, application_id, "Application"))


@router.post("/contacts/parse", response_model=PasteOut)
def parse_paste(body: PasteIn) -> PasteOut:
    """Fields from a pasted block (Apollo extension, LinkedIn, a signature). Nothing is saved."""
    return PasteOut(**contact_paste.parse(body.text[:20000]).dict())


# ------------------------------------------------------------------------------- Hunter


def _credits(workspace: str) -> HunterCredits:
    from app.providers.hunter import HunterError

    try:
        c = hunter_provider(mock=True if workspace == "demo" else None).account()
    except HunterError as exc:
        configured = "HUNTER_API_KEY" not in str(exc)
        return HunterCredits(configured=configured, error=str(exc))
    return HunterCredits(configured=True, plan=c.plan, searches_left=c.searches_left,
                         searches_available=c.searches_available,
                         verifications_left=c.verifications_left,
                         verifications_available=c.verifications_available,
                         reset_date=c.reset_date)


def _log(s: Session, kind: str, detail: dict[str, Any]) -> None:
    row = s.exec(select(AppSetting).where(AppSetting.key == "hunter_log")).first()
    entries = list((row.value if row else {}).get("calls") or [])[-199:]
    entries.append({"at": utcnow().isoformat(), "kind": kind, **detail})
    if row is None:
        row = AppSetting(key="hunter_log", value={"calls": entries})
    else:
        row.value = {"calls": entries}
    s.add(row)


@router.get("/hunter/credits", response_model=HunterCredits)
def hunter_credits(workspace: WorkspaceDep) -> HunterCredits:
    """What's left this month (free: no credit used)."""
    return _credits(workspace)


@router.post("/hunter/find", response_model=HunterFindOut)
def hunter_find(body: HunterFindIn, session: SessionDep, workspace: WorkspaceDep) -> HunterFindOut:
    """One Hunter search for this person at the job's company (1 credit). The email fills the
    form; nothing is saved until you do."""
    from app.providers.hunter import HunterError
    from app.services import research

    app = get_or_404(session, Application, body.application_id, "Application")
    company = session.get(Company, session.get(Job, app.job_id).company_id)
    site = research.company_site(session, company)
    domain = company.domain or (urlsplit(site).netloc.removeprefix("www.") if site else "")
    parts = body.full_name.split()
    if not domain:
        raise HTTPException(422, f"No domain known for {company.name}: add its website first")
    if len(parts) < 2 or len(parts[-1].strip(".")) < 2:
        raise HTTPException(422, "Hunter needs a first and a last name (not an initial)")
    try:
        f = hunter_provider(mock=True if workspace == "demo" else None).find(
            domain, parts[0], " ".join(parts[1:]))
    except HunterError as exc:
        raise HTTPException(422, str(exc)) from exc
    _log(session, "find", {"domain": domain, "found": bool(f.email)})
    session.commit()
    name = " ".join(x for x in (f.first_name, f.last_name) if x) or body.full_name
    return HunterFindOut(email=f.email, score=f.score, full_name=name, position=f.position,
                         linkedin_url=f.linkedin_url, status=f.status, credits=_credits(workspace))


@router.post("/hunter/verify", response_model=HunterVerifyOut)
def hunter_verify(body: HunterVerifyIn, session: SessionDep,
                  workspace: WorkspaceDep) -> HunterVerifyOut:
    """One Hunter verification of an email that looks wrong (1 credit)."""
    from app.providers.hunter import HunterError

    try:
        v = hunter_provider(mock=True if workspace == "demo" else None).verify(body.email.strip())
    except HunterError as exc:
        raise HTTPException(422, str(exc)) from exc
    _log(session, "verify", {"result": v.result})
    session.commit()
    return HunterVerifyOut(email=v.email, result=v.result, status=v.status, score=v.score,
                           credits=_credits(workspace))
