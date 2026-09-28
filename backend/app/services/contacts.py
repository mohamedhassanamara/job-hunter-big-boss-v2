"""Contact resolution: who to write to for each job, in three tiers.

1. An imported contact at the job's company, the most relevant role first (Settings → Contacts).
2. None imported: the company joins the manual Apollo-extension lookup queue (one row per company).
3. The lookup found nobody: "No contact", and the job stays on the web-apply route.

Never overrides a contact you picked by hand, and never touches jobs already applied to or closed.
No network, no model calls.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, col, select

from app.models import (
    Application,
    ApplicationEvent,
    AppSetting,
    Company,
    CompanyLookup,
    Contact,
    Job,
)
from app.models.base import utcnow
from app.models.enums import ContactSource, ContactTier, EventKind, LookupStatus, Stage
from app.services import pipeline
from app.services.dedupe import _ascii_words
from app.services.views import latest_fits

# Ordered: the first group is the most relevant person to write to. Editable in Settings.
DEFAULT_ROLE_RANKING: list[dict[str, Any]] = [
    {"label": "CTO", "keywords": [
        "cto", "chief technology officer", "chief technical officer", "directeur technique",
        "directrice technique", "director tecnico", "directora tecnica", "technischer direktor",
        "direttore tecnico", "chief product technology officer"]},
    {"label": "VP / Head of Engineering", "keywords": [
        "vp engineering", "vp of engineering", "vice president engineering",
        "vice president of engineering", "head of engineering", "director of engineering",
        "engineering director", "head of technology", "head of tech", "directeur de l ingenierie",
        "responsable engineering", "director de ingenieria", "head of software",
        "head of development", "leiter softwareentwicklung", "head of it", "it director",
        "directeur informatique", "dsi"]},
    {"label": "Head of Data / AI / ML", "keywords": [
        "head of data", "head of ai", "head of ml", "head of machine learning",
        "chief data officer", "cdo", "director of data", "data director", "vp data",
        "head of analytics", "directeur data", "responsable data", "director de datos",
        "head of mobile", "head of platform"]},
    {"label": "Engineering Manager", "keywords": [
        "engineering manager", "software engineering manager", "development manager",
        "manager engineering", "manager ingenierie", "responsable technique",
        "responsable developpement", "jefe de desarrollo"]},
    {"label": "Tech Lead", "keywords": [
        "tech lead", "technical lead", "lead engineer", "lead developer", "staff engineer",
        "principal engineer", "lead software engineer", "architect", "lead dev",
        "responsable d equipe", "team lead", "teamlead", "engineering lead", "data lead",
        "ml lead", "ai lead", "platform lead", "mobile lead", "backend lead", "dev lead"]},
    {"label": "HR / Talent", "keywords": [
        "talent", "recruiter", "recruiting", "recruitment", "hr", "human resources",
        "people", "rrhh", "recursos humanos", "reclutamiento", "recrutement", "recruteur",
        "recruteuse", "charge de recrutement", "rh", "ressources humaines", "personal"]},
    {"label": "Founder / CEO", "keywords": [
        "founder", "co founder", "cofounder", "ceo", "chief executive officer", "fondateur",
        "fondatrice", "fundador", "fundadora", "gerente", "managing director", "geschaftsfuhrer"]},
]
DEFAULT_LOOKUP = {"daily_cap": 10}
UNRANKED = 999
FROZEN_STAGES = (Stage.done, Stage.interview, Stage.closed)


def fold(text: str | None) -> list[str]:
    return _ascii_words(text or "")


def normalize_person(name: str | None) -> str:
    return " ".join(fold(name))


def _contains(words: list[str], phrase: list[str]) -> bool:
    n = len(phrase)
    return n > 0 and any(words[i:i + n] == phrase for i in range(len(words) - n + 1))


def rank(title: str | None, ranking: list[dict[str, Any]]) -> tuple[int, str | None]:
    """(position of the first matching group, its label); (UNRANKED, None) when nothing matches."""
    words = fold(title)
    for i, group in enumerate(ranking):
        if any(_contains(words, fold(k)) for k in group.get("keywords") or []):
            return i, group.get("label")
    return UNRANKED, None


def _setting(s: Session, key: str, default: Any) -> Any:
    row = s.exec(select(AppSetting).where(AppSetting.key == key)).first()
    return row.value if row else default


def role_ranking(s: Session) -> list[dict[str, Any]]:
    value = _setting(s, "contacts", {})
    return (value or {}).get("role_ranking") or DEFAULT_ROLE_RANKING


def daily_cap(s: Session) -> int:
    return int((_setting(s, "lookup", DEFAULT_LOOKUP) or {}).get("daily_cap", 10))


def rerank_all(s: Session) -> int:
    """Re-derive every contact's cached role_rank (after the ranking setting changes)."""
    ranking = role_ranking(s)
    changed = 0
    for c in s.exec(select(Contact)).all():
        r = rank(c.title, ranking)[0]
        if r != c.role_rank:
            c.role_rank = r
            s.add(c)
            changed += 1
    return changed


def best_contact(contacts: list[Contact]) -> Contact | None:
    """Most relevant role first; then one with an email; then the most recently imported."""
    if not contacts:
        return None
    return sorted(contacts, key=lambda c: (c.role_rank, c.email is None,
                                           -(c.created_at.timestamp() if c.created_at else 0),
                                           -(c.id or 0)))[0]


def _manual(s: Session, app: Application) -> bool:
    """A contact you set by hand is never replaced by matching."""
    if app.contact_id is None:
        return False
    contact = s.get(Contact, app.contact_id)
    if contact is not None and contact.source == ContactSource.manual:
        return True
    events = s.exec(select(ApplicationEvent).where(
        ApplicationEvent.application_id == app.id,
        ApplicationEvent.kind == EventKind.contact_resolved)).all()
    return any((e.payload or {}).get("manual") for e in events)


# -------------------------------------------------------------------------------- resolution


@dataclass
class Resolution:
    changed: bool
    tier: str
    contact_id: int | None


def _apply(s: Session, app: Application, contact: Contact | None, tier: ContactTier,
           message: str) -> bool:
    new_id = contact.id if contact else None
    if app.contact_id == new_id and app.contact_tier == tier:
        return False
    app.contact_id = new_id
    app.contact_tier = tier
    s.add(app)
    pipeline.log_event(s, app, EventKind.contact_resolved, message, tier=tier,
                       contact_id=new_id)
    return True


def _drop_pending_lookup(s: Session, company_id: int) -> None:
    """The company has contacts now (e.g. a later import): it no longer needs a lookup."""
    row = s.exec(select(CompanyLookup).where(CompanyLookup.company_id == company_id)).first()
    if row is not None and row.status in (LookupStatus.queued, LookupStatus.skipped):
        s.delete(row)
        s.flush()


def _lookup_for(s: Session, company_id: int, priority: int) -> CompanyLookup:
    row = s.exec(select(CompanyLookup).where(CompanyLookup.company_id == company_id)).first()
    if row is None:
        row = CompanyLookup(company_id=company_id, priority=priority)
        s.add(row)
        s.flush()
    elif row.status == LookupStatus.queued and priority > row.priority:
        row.priority = priority
        s.add(row)
    return row


def resolve(s: Session, app: Application, *, contacts: list[Contact] | None = None,
            priority: int = 0) -> Resolution:
    """Resolve one application. `contacts` (the company's) can be passed in by batch callers."""
    if Stage(app.stage) in FROZEN_STAGES or _manual(s, app):
        return Resolution(False, app.contact_tier, app.contact_id)
    job = s.get(Job, app.job_id)
    if job is None:
        return Resolution(False, app.contact_tier, app.contact_id)
    if contacts is None:
        contacts = list(s.exec(select(Contact).where(Contact.company_id == job.company_id)).all())
    best = best_contact(contacts)
    if best is not None:
        _drop_pending_lookup(s, job.company_id)
        tier = (ContactTier.lookup_found if best.source == ContactSource.apollo_lookup
                else ContactTier.apollo_dump)
        role = f" ({best.title})" if best.title else ""
        changed = _apply(s, app, best, tier, f"Contact found: {best.full_name}{role}")
        return Resolution(changed, tier, best.id)
    lookup = _lookup_for(s, job.company_id, priority)
    if lookup.status == LookupStatus.not_found:
        changed = _apply(s, app, None, ContactTier.none,
                         "No contact: the Apollo lookup found nobody")
        return Resolution(changed, ContactTier.none, None)
    if lookup.status == LookupStatus.found:  # found earlier but the contact is gone: ask again
        lookup.status, lookup.resolved_at = LookupStatus.queued, None
        s.add(lookup)
    changed = _apply(s, app, None, ContactTier.lookup_queued, "Queued for an Apollo lookup")
    return Resolution(changed, ContactTier.lookup_queued, None)


def _open_apps(s: Session, company_ids: set[int] | None = None,
               job_ids: list[int] | None = None) -> list[tuple[Application, Job]]:
    stmt = (select(Application, Job).join(Job, col(Job.id) == col(Application.job_id))
            .where(col(Application.stage).not_in(list(FROZEN_STAGES))))
    if company_ids is not None:
        stmt = stmt.where(col(Job.company_id).in_(company_ids))
    if job_ids is not None:
        stmt = stmt.where(col(Job.id).in_(job_ids))
    return list(s.exec(stmt).all())


def _fit_score(fit: Any) -> int:
    return fit.score if fit is not None and fit.score is not None and fit.prompt_version else 0


def resolve_many(s: Session, pairs: list[tuple[Application, Job]]) -> int:
    """Batch resolution: contacts loaded once per company, lookup priority = best fit there."""
    company_ids = {j.company_id for _, j in pairs}
    by_company: dict[int, list[Contact]] = defaultdict(list)
    for c in s.exec(select(Contact).where(col(Contact.company_id).in_(company_ids))).all():
        by_company[c.company_id].append(c)
    fits = latest_fits(s, [j.id for _, j in pairs])
    priority: dict[int, int] = defaultdict(int)
    for _, j in pairs:
        priority[j.company_id] = max(priority[j.company_id], _fit_score(fits.get(j.id)))
    changed = 0
    for app, job in pairs:
        r = resolve(s, app, contacts=by_company.get(job.company_id, []),
                    priority=priority[job.company_id])
        changed += r.changed
    return changed


def resolve_jobs(s: Session, job_ids: list[int]) -> int:
    """After discovery: resolve the new/changed jobs."""
    return resolve_many(s, _open_apps(s, job_ids=job_ids)) if job_ids else 0


def resolve_after_discovery(engine: Any, job_ids: list[int]) -> int:
    with Session(engine) as s:
        changed = resolve_jobs(s, job_ids)
        s.commit()
        return changed


def resolve_company(s: Session, company_id: int) -> int:
    return resolve_many(s, _open_apps(s, company_ids={company_id}))


# ---------------------------------------------------------------------------------- report


def report(s: Session) -> dict[str, Any]:
    """Jobs with a contact / queued for lookup / no contact, overall and by track and country."""
    rows = _open_apps(s)
    empty = {"jobs": 0, "with_contact": 0, "queued": 0, "no_contact": 0}

    def bucket(app: Application) -> str:
        if app.contact_id is not None:
            return "with_contact"
        return "queued" if app.contact_tier == ContactTier.lookup_queued else "no_contact"

    totals = dict(empty)
    by_track: dict[str, dict[str, int]] = defaultdict(lambda: dict(empty))
    by_country: dict[str, dict[str, int]] = defaultdict(lambda: dict(empty))
    for app, job in rows:
        b = bucket(app)
        for target in (totals, by_track[job.matched_track or "(none)"],
                       by_country[job.country or "(remote)"]):
            target["jobs"] += 1
            target[b] += 1

    def table(d: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        return sorted(({"group": k, **v} for k, v in d.items()), key=lambda x: -x["jobs"])

    queued = s.exec(select(CompanyLookup).where(
        CompanyLookup.status == LookupStatus.queued)).all()
    return {
        "totals": totals,
        "by_track": table(by_track),
        "by_country": table(by_country),
        "lookup_queue": len(queued),
        "contacts": len(s.exec(select(Contact.id)).all()),
        "companies_with_contacts": len(set(s.exec(select(Contact.company_id)).all())),
        "at": utcnow().isoformat(),
    }


def match_all(s: Session) -> dict[str, Any]:
    """Resolve every open application, then report. Stored for the Contacts screen."""
    changed = resolve_many(s, _open_apps(s))
    out = {**report(s), "changed": changed}
    row = s.exec(select(AppSetting).where(AppSetting.key == "contacts_last_match")).first()
    if row is None:
        row = AppSetting(key="contacts_last_match", value=out)
    else:
        row.value = out
    s.add(row)
    return out


# --------------------------------------------------------------------------------- lookups


def local_midnight(now: datetime | None = None) -> datetime:
    local = (now or utcnow()).astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def used_today(s: Session, now: datetime | None = None) -> int:
    since = local_midnight(now)
    return len(s.exec(select(CompanyLookup.id).where(
        col(CompanyLookup.status).in_([LookupStatus.found, LookupStatus.not_found]),
        col(CompanyLookup.resolved_at) >= since)).all())


@dataclass
class QueueRow:
    lookup: CompanyLookup
    company: Company
    open_jobs: int
    best_job_id: int | None
    best_job_title: str | None
    best_fit: int | None


@dataclass
class LookupQueueView:
    daily_cap: int
    used_today: int
    total: int
    rows: list[QueueRow] = field(default_factory=list)


def lookup_queue(s: Session, now: datetime | None = None, limit: int = 100) -> LookupQueueView:
    now = now or utcnow()
    lookups = [lk for lk in s.exec(select(CompanyLookup).where(col(CompanyLookup.status).in_(
        [LookupStatus.queued, LookupStatus.skipped]))).all()
        if lk.status == LookupStatus.queued or not lk.snoozed_until or lk.snoozed_until <= now]
    lookups.sort(key=lambda lk: (-lk.priority, lk.queued_at))
    shown = lookups[:limit]
    pairs = _open_apps(s, company_ids={lk.company_id for lk in shown})
    fits = latest_fits(s, [j.id for _, j in pairs])
    jobs_by_company: dict[int, list[Job]] = defaultdict(list)
    for _, j in pairs:
        jobs_by_company[j.company_id].append(j)
    rows = []
    for lk in shown:
        jobs = jobs_by_company.get(lk.company_id, [])
        best = max(jobs, key=lambda j: _fit_score(fits.get(j.id)), default=None)
        company = s.get(Company, lk.company_id)
        if company is None:
            continue
        best_fit = _fit_score(fits.get(best.id)) if best else 0
        rows.append(QueueRow(lk, company, len(jobs), best.id if best else None,
                             best.title if best else None, best_fit or None))
    return LookupQueueView(daily_cap(s), used_today(s, now), len(lookups), rows)


class ContactError(ValueError):
    pass


def lookup_for_company(s: Session, company_id: int) -> CompanyLookup:
    row = s.exec(select(CompanyLookup).where(CompanyLookup.company_id == company_id)).first()
    if row is None:
        row = CompanyLookup(company_id=company_id)
        s.add(row)
        s.flush()
    return row


def add_contact(s: Session, company_id: int, *, full_name: str, title: str | None,
                email: str | None, linkedin_url: str | None, source: ContactSource,
                notes: str = "") -> Contact:
    name = " ".join(full_name.split())
    if not name:
        raise ContactError("A name is required")
    email_n = (email or "").strip().lower() or None
    if email_n:
        existing = s.exec(select(Contact).where(Contact.email_normalized == email_n)).first()
        if existing is not None:
            raise ContactError(f"{email_n} is already a contact ({existing.full_name})")
    parts = name.split(" ", 1)
    contact = Contact(company_id=company_id, full_name=name, first_name=parts[0],
                      last_name=parts[1] if len(parts) > 1 else None,
                      normalized_name=normalize_person(name), title=(title or "").strip() or None,
                      email=(email or "").strip() or None, email_normalized=email_n,
                      linkedin_url=(linkedin_url or "").strip() or None, source=source,
                      role_rank=rank(title, role_ranking(s))[0], notes=notes)
    s.add(contact)
    s.flush()
    return contact


def lookup_found(s: Session, company_id: int, **contact: Any) -> Contact:
    c = add_contact(s, company_id, source=ContactSource.apollo_lookup, **contact)
    row = lookup_for_company(s, company_id)
    row.status, row.resolved_at, row.snoozed_until = LookupStatus.found, utcnow(), None
    s.add(row)
    resolve_company(s, company_id)
    return c


def lookup_not_found(s: Session, company_id: int, notes: str = "") -> CompanyLookup:
    row = lookup_for_company(s, company_id)
    row.status, row.resolved_at, row.snoozed_until = LookupStatus.not_found, utcnow(), None
    row.notes = notes.strip()
    s.add(row)
    resolve_company(s, company_id)
    return row


def lookup_skip(s: Session, company_id: int, now: datetime | None = None) -> CompanyLookup:
    """Not today: hidden until tomorrow (local midnight)."""
    row = lookup_for_company(s, company_id)
    row.status = LookupStatus.skipped
    row.snoozed_until = local_midnight(now) + timedelta(days=1)
    s.add(row)
    return row


# ------------------------------------------------------------------------------- per job


def set_contact(s: Session, app: Application, contact: Contact) -> Application:
    """Your choice for this job; matching never replaces it."""
    tier = (ContactTier.lookup_found if contact.source == ContactSource.apollo_lookup
            else ContactTier.apollo_dump)
    app.contact_id, app.contact_tier = contact.id, tier
    s.add(app)
    pipeline.log_event(s, app, EventKind.contact_resolved, f"Contact set: {contact.full_name}",
                       tier=tier, contact_id=contact.id, manual=True)
    return app


def clear_contact(s: Session, app: Application) -> Application:
    """Back to automatic matching."""
    app.contact_id = None
    s.add(app)
    pipeline.log_event(s, app, EventKind.contact_resolved, "Contact cleared (automatic matching)",
                       manual=False, cleared=True)
    s.flush()
    for e in s.exec(select(ApplicationEvent).where(
            ApplicationEvent.application_id == app.id,
            ApplicationEvent.kind == EventKind.contact_resolved)).all():
        if (e.payload or {}).get("manual"):
            e.payload = {**e.payload, "manual": False}
            s.add(e)
    s.flush()
    resolve(s, app)
    return app
