"""Builds API DTOs from ORM rows with a handful of batched queries (no N+1)."""

from collections.abc import Iterable, Sequence

from sqlmodel import Session, col, func, select

from app.models import (
    Application,
    ApplicationEvent,
    Company,
    Contact,
    CVVersion,
    FitScore,
    Job,
    OutreachDraft,
)
from app.models.enums import Stage
from app.schemas.jobs import (
    ApplicationBrief,
    CompanyRef,
    ContactOut,
    CVBrief,
    DraftBrief,
    EventOut,
    FitBrief,
    FitDetail,
    JobDetail,
    JobListItem,
    PipelineCard,
    RelatedJob,
)
from app.services.pipeline import ALLOWED, stage_label


def fit_band(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 65:
        return "good"
    if score >= 50:
        return "fair"
    return "weak"


def latest_fits(session: Session, job_ids: Iterable[int]) -> dict[int, FitScore]:
    ids = list(job_ids)
    if not ids:
        return {}
    rows = session.exec(
        select(FitScore).where(col(FitScore.job_id).in_(ids)).order_by(col(FitScore.created_at))
    ).all()
    return {r.job_id: r for r in rows}  # later rows overwrite earlier → latest wins


def fit_brief(fit: FitScore | None) -> FitBrief | None:
    return FitBrief(score=fit.score, band=fit_band(fit.score)) if fit else None


def allowed_stages(app: Application) -> list[str]:
    return [s.value for s in ALLOWED[Stage(app.stage)]]


def application_brief(app: Application) -> ApplicationBrief:
    return ApplicationBrief(
        id=app.id,
        stage=app.stage,
        stage_label=stage_label(app.stage, app.route),
        route=app.route,
        contact_tier=app.contact_tier,
        close_reason=app.close_reason,
        stage_changed_at=app.stage_changed_at,
    )


def _job_item(job: Job, company: Company, app: Application, fit: FitScore | None) -> JobListItem:
    return JobListItem(
        id=job.id,
        title=job.title,
        company=CompanyRef(id=company.id, name=company.name, contacted_at=company.contacted_at),
        source=job.source,
        url=job.url,
        location=job.location,
        country=job.country,
        remote_type=job.remote_type,
        salary_text=job.salary_text,
        posted_at=job.posted_at,
        discovered_at=job.discovered_at,
        fit=fit_brief(fit),
        application=application_brief(app),
        duplicate_of_id=job.duplicate_of_id,
        # "Already contacted" means *another* application at this company went out.
        company_contacted=company.contacted_at is not None and app.applied_at is None,
    )


def job_rows(
    session: Session, jobs: Sequence[Job]
) -> list[tuple[Job, Company, Application, FitScore | None]]:
    if not jobs:
        return []
    ids = [j.id for j in jobs]
    companies = {
        c.id: c
        for c in session.exec(
            select(Company).where(col(Company.id).in_({j.company_id for j in jobs}))
        ).all()
    }
    apps = {
        a.job_id: a
        for a in session.exec(select(Application).where(col(Application.job_id).in_(ids))).all()
    }
    fits = latest_fits(session, ids)
    return [(j, companies[j.company_id], apps[j.id], fits.get(j.id)) for j in jobs if j.id in apps]


def job_items(session: Session, jobs: Sequence[Job]) -> list[JobListItem]:
    return [_job_item(*row) for row in job_rows(session, jobs)]


def job_item(session: Session, job: Job) -> JobListItem:
    return job_items(session, [job])[0]


def pipeline_cards(session: Session, apps: Sequence[Application]) -> list[PipelineCard]:
    if not apps:
        return []
    jobs = {
        j.id: j
        for j in session.exec(select(Job).where(col(Job.id).in_([a.job_id for a in apps]))).all()
    }
    companies = {
        c.id: c
        for c in session.exec(
            select(Company).where(col(Company.id).in_({j.company_id for j in jobs.values()}))
        ).all()
    }
    fits = latest_fits(session, jobs.keys())
    cards = []
    for a in apps:
        job = jobs[a.job_id]
        cards.append(
            PipelineCard(
                application_id=a.id,
                job_id=job.id,
                title=job.title,
                company_name=companies[job.company_id].name,
                source=job.source,
                location=job.location,
                remote_type=job.remote_type,
                fit=fit_brief(fits.get(job.id)),
                stage=a.stage,
                stage_label=stage_label(a.stage, a.route),
                route=a.route,
                contact_tier=a.contact_tier,
                close_reason=a.close_reason,
                stage_changed_at=a.stage_changed_at,
                updated_at=a.updated_at,
                allowed_stages=allowed_stages(a),
            )
        )
    return cards


def contact_out(c: Contact) -> ContactOut:
    return ContactOut(
        id=c.id,
        company_id=c.company_id,
        full_name=c.full_name,
        title=c.title,
        email=c.email,
        linkedin_url=c.linkedin_url,
        source=c.source,
    )


def related_jobs(session: Session, jobs: Sequence[Job]) -> list[RelatedJob]:
    if not jobs:
        return []
    apps = {
        a.job_id: a
        for a in session.exec(
            select(Application).where(col(Application.job_id).in_([j.id for j in jobs]))
        ).all()
    }
    return [
        RelatedJob(
            id=j.id,
            title=j.title,
            source=j.source,
            url=j.url,
            stage=apps[j.id].stage,
            stage_label=stage_label(apps[j.id].stage, apps[j.id].route),
        )
        for j in jobs
        if j.id in apps
    ]


def job_detail(session: Session, job: Job) -> JobDetail:
    (j, company, app, fit) = job_rows(session, [job])[0]
    base = _job_item(j, company, app, fit)
    contact = session.get(Contact, app.contact_id) if app.contact_id else None
    contact_count = session.exec(
        select(func.count()).select_from(Contact).where(Contact.company_id == company.id)
    ).one()
    others = session.exec(
        select(Job).where(
            Job.company_id == company.id,
            Job.id != j.id,
            col(Job.duplicate_of_id).is_(None),
        )
    ).all()
    others = [o for o in others if o.id != j.duplicate_of_id]
    dup_root = j.duplicate_of_id or j.id
    dups = session.exec(
        select(Job).where(
            (col(Job.duplicate_of_id) == dup_root) | (col(Job.id) == dup_root), Job.id != j.id
        )
    ).all()
    cvs = session.exec(
        select(CVVersion)
        .where(CVVersion.application_id == app.id)
        .order_by(col(CVVersion.version).desc())
    ).all()
    drafts = session.exec(
        select(OutreachDraft)
        .where(OutreachDraft.application_id == app.id)
        .order_by(col(OutreachDraft.created_at).desc())
    ).all()
    draft_contacts = {
        c.id: c
        for c in session.exec(
            select(Contact).where(col(Contact.id).in_({d.contact_id for d in drafts}))
        ).all()
    }
    events = session.exec(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app.id)
        .order_by(col(ApplicationEvent.at).desc(), col(ApplicationEvent.id).desc())
    ).all()
    return JobDetail(
        **base.model_dump(),
        description=j.description,
        fit_detail=FitDetail(
            score=fit.score,
            band=fit_band(fit.score),
            strengths=fit.strengths,
            gaps=fit.gaps,
            summary=fit.summary,
            model=fit.model,
            created_at=fit.created_at,
        )
        if fit
        else None,
        notes=app.notes,
        contact=contact_out(contact) if contact else None,
        company_contacts=contact_count,
        other_jobs_at_company=related_jobs(session, others),
        duplicates=related_jobs(session, dups),
        cv_versions=[
            CVBrief(
                id=c.id,
                version=c.version,
                status=c.status,
                page_count=c.page_count,
                generator_model=c.generator_model,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in cvs
        ],
        drafts=[
            DraftBrief(
                id=d.id,
                subject=d.subject,
                body=d.body,
                status=d.status,
                edited=d.edited,
                contact_name=draft_contacts[d.contact_id].full_name
                if d.contact_id in draft_contacts
                else None,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in drafts
        ],
        events=[
            EventOut(
                id=e.id,
                kind=e.kind,
                from_stage=e.from_stage,
                to_stage=e.to_stage,
                message=e.message,
                payload=e.payload,
                at=e.at,
            )
            for e in events
        ],
        allowed_stages=allowed_stages(app),
    )
