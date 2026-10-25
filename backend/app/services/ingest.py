"""Idempotent ingestion of pre-filtered jobs.

- Same (source, external_id) seen again → ONLY last_seen_at is updated ("updated" = seen again).
  Discovery is additive: an existing job's content, score, label, stage and notes are never
  touched, so nothing already scored is ever rescored by a discovery run.
- Same dedupe key as an existing job from anywhere → stored, flagged duplicate_of ("duplicate").
- Otherwise → new job + application (+ Apollo contact match) ("new"); the background scorer
  (services/scoring.py) scores never-scored jobs afterwards.
"""

from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.models import Application, ApplicationEvent, Company, Contact, Job
from app.models.base import utcnow
from app.models.enums import ContactSource, ContactTier, DescriptionLevel, EventKind
from app.providers.base import RawJob
from app.services.dedupe import dedupe_key, normalize_company

SOURCE_NAMES = {
    "adzuna": "Adzuna",
    "remotive": "Remotive",
    "arbeitnow": "Arbeitnow",
    "wttj": "Welcome to the Jungle",
    "boards": "Company job boards",
    "bayt": "Bayt",
    "linkedin": "LinkedIn (your import)",
}


@dataclass
class IngestStats:
    new: int = 0
    updated: int = 0
    duplicates: int = 0
    job_ids: list[int] = field(default_factory=list)  # new jobs only


def _company(session: Session, name: str) -> Company:
    norm = normalize_company(name)
    company = session.exec(select(Company).where(Company.normalized_name == norm)).first()
    if company is None:  # a spelling merged into another company (Contacts → Merges)
        from app.services.company_merge import resolve_alias

        company = resolve_alias(session, norm)
    if company is None:
        company = Company(name=name.strip(), normalized_name=norm)
        session.add(company)
        session.flush()
    return company


def ingest(
    session: Session,
    jobs: list[RawJob],
    *,
    source_run_id: int | None,
    profile_id: int | None,
) -> IngestStats:
    """Fit scoring is not done here: new jobs are queued for the background scorer."""
    stats = IngestStats()
    now = utcnow()
    for raw in jobs:
        existing = session.exec(
            select(Job).where(Job.source == raw.source, Job.external_id == raw.external_id)
        ).first()
        if existing:
            existing.last_seen_at = now  # still listed; nothing else changes
            session.add(existing)
            stats.updated += 1
            continue

        company = _company(session, raw.company)
        key = dedupe_key(company.name, raw.title, raw.country)
        original = session.exec(
            select(Job).where(Job.dedupe_key == key, col(Job.duplicate_of_id).is_(None))
        ).first()
        if not original and raw.apply_url:
            original = session.exec(
                select(Job).where(
                    Job.apply_url == raw.apply_url,
                    col(Job.duplicate_of_id).is_(None),
                )
            ).first()

        if original:
            # Merge into existing canonical job instead of creating a duplicate row
            src_str = str(raw.source.value if hasattr(raw.source, "value") else raw.source)
            sources_list = list(original.sources or [])
            if src_str not in sources_list:
                sources_list.append(src_str)
            original.sources = sources_list

            urls_dict = dict(original.source_urls or {})
            urls_dict[src_str] = raw.url
            original.source_urls = urls_dict

            if raw.apply_url and not original.apply_url:
                original.apply_url = raw.apply_url

            if len(raw.description or "") > len(original.description or ""):
                original.description = raw.description
                original.description_level = raw.description_level
                if raw.description_level == DescriptionLevel.full:
                    original.full_fetched_at = now

            original.last_seen_at = now
            session.add(original)
            stats.duplicates += 1
            continue

        src_str = str(raw.source.value if hasattr(raw.source, "value") else raw.source)
        job = Job(
            **raw.model_dump(exclude={"company"}),
            company_id=company.id,
            source_run_id=source_run_id,
            dedupe_key=key,
            duplicate_of_id=None,
            sources=[src_str],
            source_urls={src_str: raw.url},
            discovered_at=now,
            last_seen_at=now,
        )
        session.add(job)
        session.flush()
        stats.new += 1
        stats.job_ids.append(job.id)

        contact = session.exec(
            select(Contact).where(
                Contact.company_id == company.id, Contact.source == ContactSource.apollo_dump,
                col(Contact.left_at).is_(None),
            )
        ).first()
        application = Application(
            job_id=job.id,
            contact_id=contact.id if contact else None,
            contact_tier=ContactTier.imported if contact else ContactTier.to_get,
        )
        session.add(application)
        session.flush()
        message = f"Discovered on {SOURCE_NAMES.get(raw.source, raw.source)}"
        session.add(
            ApplicationEvent(
                application_id=application.id, kind=EventKind.discovered, message=message
            )
        )
    return stats
