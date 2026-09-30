"""The Get contact step: the first step of every job's Outreach track (Phase 9).

Contacts are found by hand with the Apollo Chrome extension (no Apollo API on the free plan);
this guides it and gates drafting. Per job:
- get: nobody yet (or the contact left / has no email): "Who to look for", links, the entry form.
- verify: a contact exists (e.g. from a CSV import) but you haven't confirmed they're still there,
  or the confirmation is older than Settings → Contacts `verify_days` (30).
- ready: a contact you verified recently, with an email. Only then can an email be drafted (and
  the company researched).
- never: the company is never looked up (a job board): web apply only.

Anyone you enter counts as verified. "Still there" also dismisses the automatic "may have left"
alerts. "Left or wrong person" is permanent for that contact (never picked again).
No network, no model calls.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlmodel import Session, col, select

from app.models import (
    Application,
    Company,
    Contact,
    ContactImport,
    Job,
    OutreachDraft,
)
from app.models.base import utcnow
from app.models.enums import ContactSearch, ContactSource, DraftStatus, Stage
from app.services import contacts as contacts_svc

DEFAULT_VERIFY_DAYS = 30
# Past New and not closed: the jobs whose Outreach track is open.
QUEUE_STAGES = (Stage.shortlisted, Stage.cv_ready, Stage.ready, Stage.done)
_EMAIL_DONE = (DraftStatus.sent, DraftStatus.queued, DraftStatus.failed)


class GetContactError(ValueError):
    pass


def verify_days(s: Session) -> int:
    value = contacts_svc._setting(s, "contacts", {}) or {}
    return int(value.get("verify_days") or DEFAULT_VERIFY_DAYS)


def is_current(contact: Contact, days: int) -> bool:
    if contact.verified_at is None:
        return False
    when = contact.verified_at if contact.verified_at.tzinfo else \
        contact.verified_at.replace(tzinfo=utcnow().tzinfo)
    return utcnow() - when <= timedelta(days=days)


def state_of(contact: Contact | None, company: Company | None, days: int) -> str:
    if contact is None or contact.left_at is not None:
        if company is not None and company.contact_search == ContactSearch.never:
            return "never"
        return "get"
    if not contact.email or not is_current(contact, days):
        return "verify"
    return "ready"


def state(s: Session, app: Application) -> str:
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id) if job else None
    return state_of(contact, company, verify_days(s))


def require_ready(s: Session, app: Application) -> Contact:
    """The gate before a new email (and its company research)."""
    st = state(s, app)
    if st == "ready":
        return s.get(Contact, app.contact_id)
    if st == "never":
        raise GetContactError("This company is never looked up (a job board): apply on the web")
    if st == "get":
        raise GetContactError("Get the contact first (Outreach → Contacts to get)")
    contact = s.get(Contact, app.contact_id)
    if not contact.email:
        raise GetContactError(f"{contact.full_name} has no email yet: add it in Get contact")
    raise GetContactError(f"Verify {contact.full_name} first: still at the company? "
                          "(Outreach → Contacts to get)")


# ------------------------------------------------------------------------------- where from


def provenance(s: Session, contact: Contact) -> dict[str, Any]:
    """Where and when the contact came from, in words: an import file, you, or Hunter."""
    if contact.source == ContactSource.apollo_dump:
        run = None
        if contact.imported_batch and contact.imported_batch.isdigit():
            run = s.get(ContactImport, int(contact.imported_batch))
        if run is not None:
            return {"kind": "import", "label": run.filename, "at": run.started_at}
        return {"kind": "import", "label": contact.imported_batch or "an import",
                "at": contact.created_at}
    label = {ContactSource.found: "you, with the Apollo extension",
             ContactSource.hunter: "Hunter (you confirmed it)",
             ContactSource.manual: "you, by hand"}.get(ContactSource(contact.source), "you")
    return {"kind": str(contact.source), "label": label, "at": contact.created_at}


# ---------------------------------------------------------------------------------- actions


def verify(s: Session, app: Application, action: str) -> Application:
    """still_there: verified today (alerts dismissed). left / wrong_person: never picked again,
    and the job moves to the next contact by the ranking (or back to Get contact)."""
    from app.models.enums import EventKind
    from app.services import contact_check, pipeline

    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    if contact is None:
        raise GetContactError("This job has no contact to verify")
    now = utcnow()
    if action == "still_there":
        if not contact.email:
            raise GetContactError(f"Add {contact.full_name}'s email first (Edit details)")
        contact.verified_at, contact.verified_how = now, "still_there"
        for alert in contact_check.active(s, contact.id):
            contact_check.dismiss(s, alert)
        s.add(contact)
        pipeline.log_event(s, app, EventKind.contact_resolved,
                           f"Contact verified: {contact.full_name} is still there",
                           contact_id=contact.id, verified=True)
        return app
    if action not in ("left", "wrong_person"):
        raise GetContactError(f"Unknown action {action!r}")
    contact.left_at, contact.left_reason = now, action
    s.add(contact)
    what = "left the company" if action == "left" else "wrong person"
    pipeline.log_event(s, app, EventKind.contact_resolved, f"{contact.full_name}: {what}",
                       contact_id=contact.id, left=action)
    s.flush()
    contacts_svc.clear_contact(s, app)  # re-resolves: the next by the ranking, or to get
    for other in s.exec(select(Application).where(Application.contact_id == contact.id)).all():
        if other.id != app.id:  # every other job written to them moves on too
            contacts_svc.clear_contact(s, other)
    return app


def found(s: Session, app: Application, *, full_name: str, title: str | None,
          email: str | None, linkedin_url: str | None,
          source: ContactSource = ContactSource.found) -> Contact:
    """Someone you found (Apollo extension, or Hunter): created verified and set on the job.
    An email that's already a contact at this company updates that contact instead."""
    job = s.get(Job, app.job_id)
    email_n = (email or "").strip().lower() or None
    if not email_n:
        raise GetContactError("An email is needed to write to them")
    existing = s.exec(select(Contact).where(Contact.email_normalized == email_n)).first()
    if existing is not None and existing.company_id != job.company_id:
        raise GetContactError(f"{email_n} is already a contact at another company "
                              f"({existing.full_name})")
    if existing is not None:
        existing.full_name = " ".join(full_name.split()) or existing.full_name
        existing.title = (title or "").strip() or existing.title
        existing.linkedin_url = (linkedin_url or "").strip() or existing.linkedin_url
        existing.verified_at, existing.verified_how = utcnow(), "entered"
        existing.left_at = existing.left_reason = None
        s.add(existing)
        contact = existing
    else:
        try:
            contact = contacts_svc.add_contact(s, job.company_id, full_name=full_name,
                                               title=title, email=email,
                                               linkedin_url=linkedin_url, source=source)
        except contacts_svc.ContactError as exc:
            raise GetContactError(str(exc)) from exc
    company = s.get(Company, job.company_id)
    if company.contact_search == ContactSearch.not_found:
        company.contact_search, company.contact_search_at = ContactSearch.none, None
        s.add(company)
    contacts_svc.set_contact(s, app, contact)
    s.flush()
    contacts_svc.resolve_company(s, job.company_id)  # the company's other jobs get them too
    return contact


def edit(s: Session, contact: Contact, **fields: Any) -> Contact:
    """Edit details. A new email is a new entry: verified now."""
    email = fields.pop("email", None)
    for k in ("full_name", "title", "linkedin_url"):
        if fields.get(k) is not None:
            setattr(contact, k, (fields[k] or "").strip() or (None if k != "full_name"
                                                                else contact.full_name))
    if email is not None and (email or "").strip().lower() != (contact.email_normalized or ""):
        email_n = email.strip().lower() or None
        if email_n:
            other = s.exec(select(Contact).where(Contact.email_normalized == email_n,
                                                 Contact.id != contact.id)).first()
            if other is not None:
                raise GetContactError(f"{email_n} is already a contact ({other.full_name})")
        contact.email, contact.email_normalized = email.strip() or None, email_n
        if email_n:
            contact.verified_at, contact.verified_how = utcnow(), "entered"
    contact.normalized_name = contacts_svc.normalize_person(contact.full_name)
    contact.role_rank = contacts_svc.rank(contact.title, contacts_svc.role_ranking(s))[0]
    s.add(contact)
    return contact


# ------------------------------------------------------------------------------------ queue


@dataclass
class QueueRow:
    app: Application
    job: Job
    company: Company
    contact: Contact | None
    state: str
    fit: int | None
    nobody_found: bool


def queue(s: Session) -> list[QueueRow]:
    """Contacts to get: every open job past New whose email isn't sent or queued and whose
    contact is missing or unverified. Best fit first; companies where you found nobody last;
    never-look-up companies left out."""
    from app.services.views import latest_fits

    rows = s.exec(select(Application, Job, Company)
                  .join(Job, col(Job.id) == col(Application.job_id))
                  .join(Company, col(Company.id) == col(Job.company_id))
                  .where(col(Application.stage).in_(list(QUEUE_STAGES)),
                         Company.contact_search != ContactSearch.never)).all()
    if not rows:
        return []
    app_ids = [a.id for a, _, _ in rows]
    done = set(s.exec(select(OutreachDraft.application_id).where(
        col(OutreachDraft.application_id).in_(app_ids),
        col(OutreachDraft.status).in_(list(_EMAIL_DONE)))).all())
    contact_ids = {a.contact_id for a, _, _ in rows if a.contact_id}
    people = {c.id: c for c in s.exec(select(Contact).where(
        col(Contact.id).in_(contact_ids))).all()} if contact_ids else {}
    fits = latest_fits(s, [j.id for _, j, _ in rows])
    days = verify_days(s)
    out = []
    for app, job, company in rows:
        if app.id in done:
            continue
        contact = people.get(app.contact_id) if app.contact_id else None
        st = state_of(contact, company, days)
        if st not in ("get", "verify"):
            continue
        fit = fits.get(job.id)
        out.append(QueueRow(app, job, company, contact, st,
                            fit.score if fit is not None and fit.prompt_version else None,
                            company.contact_search == ContactSearch.not_found and contact is None))
    out.sort(key=lambda r: (r.nobody_found, -(r.fit or -1),
                            -(r.app.stage_changed_at.timestamp() if r.app.stage_changed_at
                              else 0), r.app.id))
    return out


# ------------------------------------------------------------------------------------- view

STEPS = [
    "Open a profile from the LinkedIn search (the roles above, in this order).",
    "Open the Apollo extension on the profile and reveal the email.",
    "Copy the extension's panel (or the profile header) and paste it below, or type the fields.",
    "Check the fields and save: the contact counts as verified today.",
]


def links(s: Session, company: Company, contact: Contact | None,
          who: dict[str, Any]) -> dict[str, str | None]:
    """One-click links: the company's LinkedIn page, the people search for the roles, the
    website, and the contact's profile (or a name search)."""
    from urllib.parse import quote

    from app.services import research

    profile = None
    if contact is not None:
        profile = contact.linkedin_url or (
            "https://www.linkedin.com/search/results/people/?keywords="
            + quote(f'"{contact.full_name}" "{company.name}"'))
    return {
        "company_linkedin": company.linkedin_url
        or "https://www.linkedin.com/search/results/companies/?keywords=" + quote(company.name),
        "people_search": who.get("linkedin_url"),
        "website": research.company_site(s, company),
        "profile": profile,
    }


def view(s: Session, app: Application) -> dict[str, Any]:
    """Everything the Get contact panel shows for one job."""
    from app.services import aggregators, contact_check
    from app.services.views import contact_out

    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    days = verify_days(s)
    st = state_of(contact, company, days)
    who = contacts_svc.who_to_contact(s, job, company)
    ranking = contacts_svc.ranking_settings(s)
    people = contacts_svc.ranked(
        [c for c in s.exec(select(Contact).where(Contact.company_id == company.id)).all()
         if c.left_at is None and c.id != app.contact_id], ranking.order_for(company))
    alerts = contact_check.active(s, contact.id) if contact else []
    jobs = list(s.exec(select(Job).where(Job.company_id == company.id)).all())
    return {
        "application_id": app.id, "job_id": job.id, "job_title": job.title, "state": st,
        "company": {"id": company.id, "name": company.name, "domain": company.domain,
                    "contact_search": company.contact_search,
                    "contact_search_notes": company.contact_search_notes,
                    "aggregator": [] if company.aggregator_reviewed
                    else aggregators.signals(company, jobs)},
        "contact": contact_out(contact, ranking.groups) if contact else None,
        "provenance": provenance(s, contact) if contact else None,
        "verified_at": contact.verified_at if contact else None,
        "verified_how": contact.verified_how if contact else None,
        "verify_days": days,
        "stale": bool(contact and contact.verified_at and not is_current(contact, days)),
        "who": {**who, "steps": STEPS},
        "links": links(s, company, contact, who),
        "alerts": alerts,
        "next_contact": contact_out(nxt, ranking.groups)
        if alerts and (nxt := contact_check.next_contact(s, app)) else None,
        "others": [contact_out(c, ranking.groups) for c in people[:5]],
        "found_today": contacts_svc.found_today(s),
        "daily_limit": contacts_svc.daily_cap(s),
    }
