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
# Who to write to first depends on company size (labels of the groups above).
DEFAULT_SMALL_ORDER = ["CTO", "Founder / CEO", "VP / Head of Engineering", "Head of Data / AI / ML",
                       "Engineering Manager", "Tech Lead", "HR / Talent"]
DEFAULT_LARGE_ORDER = ["HR / Talent", "Engineering Manager", "CTO", "VP / Head of Engineering",
                       "Head of Data / AI / ML", "Tech Lead", "Founder / CEO"]
DEFAULT_SMALL_THRESHOLD = 200  # employees; "under 200" (Apollo lists) counts as small
DEFAULT_LOOKUP = {"daily_cap": 10}
UNRANKED = 999
FROZEN_STAGES = (Stage.closed,)  # both routes: an applied job still gets a contact to email


def _email_started(s: Session, app: Application) -> bool:
    """A draft exists (not rejected): that email's contact is never swapped automatically."""
    from app.models import OutreachDraft
    from app.models.enums import DraftStatus

    return s.exec(select(OutreachDraft.id).where(
        OutreachDraft.application_id == app.id,
        OutreachDraft.status != DraftStatus.rejected)).first() is not None


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


@dataclass
class Ranking:
    """The role groups plus the order to use at small and at large (or unknown-size) companies."""

    groups: list[dict[str, Any]]
    small: list[int]  # group indices, most relevant first
    large: list[int]
    threshold: int

    def order_for(self, company: Company | None) -> list[int]:
        return self.small if is_small(company, self.threshold) else self.large

    def position(self, contact: Contact, order: list[int]) -> int:
        return order.index(contact.role_rank) if contact.role_rank in order else UNRANKED

    def label(self, group: int) -> str | None:
        return self.groups[group].get("label") if 0 <= group < len(self.groups) else None


def _order(labels: list[str] | None, groups: list[dict[str, Any]],
           default: list[str]) -> list[int]:
    by_label = {g.get("label"): i for i, g in enumerate(groups)}
    wanted = [by_label[x] for x in (labels or default) if x in by_label]
    return wanted + [i for i in range(len(groups)) if i not in wanted]  # unlisted groups last


def ranking_settings(s: Session) -> Ranking:
    value = _setting(s, "contacts", {}) or {}
    groups = value.get("role_ranking") or DEFAULT_ROLE_RANKING
    return Ranking(groups, _order(value.get("small_order"), groups, DEFAULT_SMALL_ORDER),
                   _order(value.get("large_order"), groups, DEFAULT_LARGE_ORDER),
                   int(value.get("small_company_threshold") or DEFAULT_SMALL_THRESHOLD))


def is_small(company: Company | None, threshold: int) -> bool:
    """Exact headcount below the threshold, or an upper bound at or below it ("under 200").
    Unknown size counts as large."""
    if company is None:
        return False
    if company.employees is not None:
        return company.employees < threshold
    return company.employees_max is not None and company.employees_max <= threshold


def size_label(company: Company) -> str:
    if company.employees is not None:
        return f"{company.employees} employees"
    if company.employees_max is not None:
        return f"under {company.employees_max} employees"
    return "size unknown"


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


def ranked(contacts: list[Contact], order: list[int] | None = None) -> list[Contact]:
    """Most relevant role first (by the company's size order); then one with an email; then the
    most recently imported. Without an order, the groups' own order."""
    def pos(c: Contact) -> int:
        if order is None:
            return c.role_rank
        return order.index(c.role_rank) if c.role_rank in order else UNRANKED

    return sorted(contacts, key=lambda c: (pos(c), c.email is None,
                                           -(c.created_at.timestamp() if c.created_at else 0),
                                           -(c.id or 0)))


def best_contact(contacts: list[Contact], order: list[int] | None = None) -> Contact | None:
    return ranked(contacts, order)[0] if contacts else None


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
            priority: int = 0, ranking: Ranking | None = None) -> Resolution:
    """Resolve one application. `contacts` (the company's) and `ranking` can be passed in by
    batch callers."""
    if Stage(app.stage) in FROZEN_STAGES or _manual(s, app) or _email_started(s, app):
        return Resolution(False, app.contact_tier, app.contact_id)
    job = s.get(Job, app.job_id)
    if job is None:
        return Resolution(False, app.contact_tier, app.contact_id)
    if contacts is None:
        contacts = list(s.exec(select(Contact).where(Contact.company_id == job.company_id)).all())
    never = s.exec(select(CompanyLookup).where(CompanyLookup.company_id == job.company_id,
                                               CompanyLookup.status == LookupStatus.never)).first()
    if never is not None:  # a job board: nobody there to write to about this job
        changed = _apply(s, app, None, ContactTier.none,
                         "No contact: never looked up (job board or aggregator)")
        return Resolution(changed, ContactTier.none, None)
    ranking = ranking or ranking_settings(s)
    best = best_contact(contacts, ranking.order_for(s.get(Company, job.company_id)))
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
    ranking = ranking_settings(s)
    changed = 0
    for app, job in pairs:
        r = resolve(s, app, contacts=by_company.get(job.company_id, []),
                    priority=priority[job.company_id], ranking=ranking)
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


ACTIVE_STAGES = (Stage.shortlisted, Stage.cv_ready, Stage.ready)


@dataclass
class QueueRow:
    lookup: CompanyLookup
    company: Company
    open_jobs: int
    shortlisted: int  # open jobs you shortlisted (or later)
    best_job_id: int | None
    best_job_title: str | None
    best_fit: int | None
    newest_at: datetime | None
    reason: str  # why this company sits at this position
    aggregator: list[str]  # signals it looks like a job board (a suggestion; you confirm)


@dataclass
class LookupQueueView:
    daily_cap: int
    used_today: int
    total: int
    rows: list[QueueRow] = field(default_factory=list)


def _age(at: datetime | None, now: datetime) -> str:
    if at is None:
        return "no date"
    days = (now - at).days
    return "today" if days <= 0 else "1 day ago" if days == 1 else f"{days} days ago"


def lookup_queue(s: Session, now: datetime | None = None, limit: int = 100) -> LookupQueueView:
    """Shortlisted jobs first, then the highest fit, then the newest job; each row says why."""
    from app.services.aggregators import signals

    now = now or utcnow()
    lookups = [lk for lk in s.exec(select(CompanyLookup).where(col(CompanyLookup.status).in_(
        [LookupStatus.queued, LookupStatus.skipped]))).all()
        if lk.status == LookupStatus.queued or not lk.snoozed_until or lk.snoozed_until <= now]
    pairs = _open_apps(s, company_ids={lk.company_id for lk in lookups})
    fits = latest_fits(s, [j.id for _, j in pairs])
    by_company: dict[int, list[tuple[Application, Job]]] = defaultdict(list)
    for a, j in pairs:
        by_company[j.company_id].append((a, j))

    def facts(lk: CompanyLookup) -> tuple[int, int, datetime | None, Job | None]:
        rows = by_company.get(lk.company_id, [])
        shortlisted = sum(1 for a, _ in rows if Stage(a.stage) in ACTIVE_STAGES)
        best = max((j for _, j in rows), key=lambda j: _fit_score(fits.get(j.id)), default=None)
        newest = max((j.discovered_at for _, j in rows if j.discovered_at), default=None)
        return shortlisted, _fit_score(fits.get(best.id)) if best else 0, newest, best

    scored = [(lk, *facts(lk)) for lk in lookups]
    scored.sort(key=lambda x: (-(x[1] > 0), -x[2], -(x[3].timestamp() if x[3] else 0),
                               x[0].queued_at))
    rows = []
    companies = {c.id: c for c in s.exec(select(Company).where(col(Company.id).in_(
        [x[0].company_id for x in scored[:limit]]))).all()}
    for i, (lk, shortlisted, fit, newest, best) in enumerate(scored[:limit]):
        company = companies.get(lk.company_id)
        if company is None:
            continue
        prev = scored[i - 1] if i else None
        if shortlisted:
            reason = f"{shortlisted} shortlisted job{'s' if shortlisted > 1 else ''}"
        elif prev is None or prev[1] > 0 or prev[2] != fit:
            reason = f"Best fit {fit}" if fit else "Not scored yet"
        else:  # same fit as the row above: the newer job wins the tie
            reason = f"Fit {fit}, newest job {_age(newest, now)}"
        jobs = [j for _, j in by_company.get(lk.company_id, [])]
        rows.append(QueueRow(lk, company, len(jobs), shortlisted, best.id if best else None,
                             best.title if best else None, fit or None, newest, reason,
                             [] if company.aggregator_reviewed else signals(company, jobs)))
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


def lookup_never(s: Session, company_id: int) -> CompanyLookup:
    """A job board or aggregator: never looked up; its jobs go to web apply."""
    row = lookup_for_company(s, company_id)
    row.status, row.resolved_at, row.snoozed_until = LookupStatus.never, None, None
    s.add(row)
    resolve_company(s, company_id)
    return row


def lookup_again(s: Session, company_id: int) -> CompanyLookup:
    """Undo "never" / "nobody found": back in the queue."""
    row = lookup_for_company(s, company_id)
    row.status, row.resolved_at, row.snoozed_until = LookupStatus.queued, None, None
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


# ----------------------------------------------------------------------------- who to contact

# Apollo seniority filters that match a ranking group, by its label's words.
_SENIORITY = {"cto": "c_suite", "ceo": "c_suite", "founder": "founder", "vp": "vp",
              "head": "head", "manager": "manager", "lead": "senior", "hr": "manager",
              "talent": "manager"}


def _titles(group: dict[str, Any], n: int = 3) -> list[str]:
    """Search titles for a ranking group: its keywords as people write them."""
    out = []
    for k in group.get("keywords") or []:
        title = k.upper() if len(k) <= 4 else k.title()  # "cto" → "CTO"; phrases get capitals
        title = {"Talent": "Talent Acquisition"}.get(title, title)
        if title not in out:
            out.append(title)
        if len(out) >= n:
            break
    return out


def _is(group: dict[str, Any], *words: str) -> bool:
    return any(w in fold(group.get("label")) for w in words)


def who_to_contact(s: Session, job: Job, company: Company) -> dict[str, Any]:
    """Which roles to look for at this company, and why, plus copyable LinkedIn and Apollo
    search hints. Small companies follow Settings → Contacts' small-company order (CTO, founder…);
    at large or unknown-size ones it's the head of the hiring team or the engineering manager,
    then talent acquisition. Nothing is searched or opened."""
    import urllib.parse

    ranking = ranking_settings(s)
    small = is_small(company, ranking.threshold)
    ordered = [ranking.groups[i] for i in ranking.order_for(company)
               if 0 <= i < len(ranking.groups)]
    team = [t.strip() for t in (job.matched_track or "").split("/") if t.strip()]
    roles = []
    if small:
        roles = [{"label": g.get("label") or "", "titles": _titles(g)} for g in ordered[:3]]
    else:
        if team:
            roles.append({"label": f"Head of the {'/'.join(team)} team",
                          "titles": [f"Head of {t}" for t in team]})
        managers = [g for g in ordered if _is(g, "manager")][:1]
        hr = [g for g in ordered if _is(g, "hr", "talent")][:1]
        roles += [{"label": g.get("label") or "", "titles": _titles(g)} for g in managers + hr]
    labels = [r["label"] for r in roles]
    size = size_label(company)
    if small:
        reason = (f"{company.name} is small ({size}): the {' or the '.join(labels[:2])} usually "
                  "reads cold emails and decides on hires, so write to them first.")
    else:
        lead = (f"{company.name} is large ({size})" if size != "size unknown"
                else f"{company.name}'s size is unknown, so it's treated as large")
        first = [x for x in labels if "hr" not in fold(x) and "talent" not in fold(x)]
        reason = (f"{lead}: write to the {' or the '.join(first[:2]) or 'hiring manager'} of the "
                  "team hiring; talent acquisition is the fallback.")
    titles = [t for r in roles for t in r["titles"]][:6]
    query = "(" + " OR ".join(f'"{t}"' for t in titles) + f') "{company.name}"'
    seniority = sorted({v for r in roles for w in fold(r["label"]) if (v := _SENIORITY.get(w))})
    return {
        "company_size": size,
        "small": small,
        "reason": reason,
        "roles": roles,
        "linkedin_query": query,
        "linkedin_url": "https://www.linkedin.com/search/results/people/?keywords="
                        + urllib.parse.quote(query),
        "apollo": {"company": company.name, "domain": company.domain or "",
                   "titles": titles, "seniority": seniority},
    }
