"""Discovery: pull from enabled sources, dedupe, score, create applications.
Phase 0 runs against MockJobSource only (no network)."""

from sqlmodel import Session, select

from app.models import (
    Application,
    ApplicationEvent,
    AppSetting,
    Company,
    Contact,
    FitScore,
    Job,
    SearchProfile,
    SourceRun,
)
from app.models.base import utcnow
from app.models.enums import ContactSource, ContactTier, EventKind, RunStatus, Source
from app.providers.base import JobSnapshot, ProfileSpec
from app.providers.registry import fit_scorer, job_sources
from app.services.dedupe import dedupe_key, normalize_company
from app.services.experience import experience_snapshots


def enabled_sources(session: Session) -> list[Source]:
    setting = session.exec(select(AppSetting).where(AppSetting.key == "sources")).first()
    flags = setting.value if setting else {}
    return [s for s in Source if flags.get(s.value, True)]


def run_discovery(session: Session) -> tuple[list[SourceRun], int]:
    profile = session.exec(select(SearchProfile).where(SearchProfile.is_active)).first()
    spec = ProfileSpec.model_validate(profile, from_attributes=True) if profile else ProfileSpec()
    experience = experience_snapshots(session)
    scorer = fit_scorer()
    runs: list[SourceRun] = []
    total_new = 0

    for source in job_sources(enabled_sources(session)):
        run = SourceRun(source=source.source, profile_id=profile.id if profile else None)
        session.add(run)
        session.flush()
        raw_jobs = source.fetch(spec)
        run.fetched_count = len(raw_jobs)
        for raw in raw_jobs:
            exists = session.exec(
                select(Job).where(Job.source == raw.source, Job.external_id == raw.external_id)
            ).first()
            if exists:
                continue
            norm = normalize_company(raw.company)
            company = session.exec(select(Company).where(Company.normalized_name == norm)).first()
            if company is None:
                company = Company(name=raw.company, normalized_name=norm)
                session.add(company)
                session.flush()
            key = dedupe_key(raw.company, raw.title, raw.country)
            original = session.exec(
                select(Job).where(Job.dedupe_key == key, Job.duplicate_of_id == None)  # noqa: E711
            ).first()
            job = Job(
                **raw.model_dump(exclude={"company"}),
                company_id=company.id,
                source_run_id=run.id,
                dedupe_key=key,
                duplicate_of_id=original.id if original else None,
            )
            session.add(job)
            session.flush()
            if original:
                run.duplicate_count += 1
            else:
                run.new_count += 1
            fit = scorer.score(
                JobSnapshot(
                    title=job.title,
                    company=company.name,
                    location=job.location,
                    remote_type=job.remote_type,
                    description=job.description,
                ),
                experience,
            )
            session.add(FitScore(job_id=job.id, profile_id=run.profile_id, **fit.model_dump()))
            contact = session.exec(
                select(Contact).where(
                    Contact.company_id == company.id, Contact.source == ContactSource.apollo_dump
                )
            ).first()
            app = Application(
                job_id=job.id,
                contact_id=contact.id if contact else None,
                contact_tier=ContactTier.apollo_dump if contact else ContactTier.none,
            )
            session.add(app)
            session.flush()
            session.add(
                ApplicationEvent(
                    application_id=app.id,
                    kind=EventKind.discovered,
                    message=f"Discovered on {source.source.value} · fit {fit.score}",
                )
            )
        run.status = RunStatus.success
        run.finished_at = utcnow()
        total_new += run.new_count
        runs.append(run)
    session.commit()
    return runs, total_new
