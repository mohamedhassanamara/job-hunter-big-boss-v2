"""Builds API DTOs from ORM rows with a handful of batched queries (no N+1)."""

from collections.abc import Iterable, Sequence
from typing import Any

from sqlmodel import Session, col, func, select

from app.models import (
    Application,
    ApplicationEvent,
    Company,
    CompanyLookup,
    Contact,
    CoverLetter,
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
    TracksOut,
)
from app.schemas.tracking import InterviewOut, ResponseOut, TrackedItem
from app.services import tracking
from app.services import tracks as track_service
from app.services.pipeline import ALLOWED, stage_label


def fit_band(score: int | None) -> str:
    if score is None:
        return "pending"
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
        select(FitScore)
        .where(col(FitScore.job_id).in_(ids))
        .order_by(col(FitScore.created_at), col(FitScore.id))
    ).all()
    return {r.job_id: r for r in rows}  # later rows overwrite earlier → latest wins


def _fit_status(fit: FitScore) -> str:
    if fit.prompt_version is None:  # legacy mock score from before real scoring
        return "pending"
    return fit.status


def fit_brief(fit: FitScore | None, experience_version: str | None = None) -> FitBrief | None:
    if fit is None:
        return None
    status = _fit_status(fit)
    score = fit.score if status == "ok" else None
    return FitBrief(
        score=score,
        band="failed" if status == "failed" else fit_band(score),
        status=status,
        confidence=fit.confidence,
        hard_flag=any(f.get("severity") == "hard" for f in fit.red_flags or []),
        flag_count=len(fit.red_flags or []),
        stale=bool(
            status == "ok"
            and experience_version
            and fit.experience_version
            and fit.experience_version != experience_version
        ),
        model=fit.model,
        prompt_version=fit.prompt_version,
    )


def current_experience_version(session: Session) -> str:
    from app.services.scoring import load_context

    return load_context(session).experience_version


_STAGE_ORDER = list(Stage)


def allowed_stages(app: Application) -> list[str]:
    return [s.value for s in sorted(ALLOWED[Stage(app.stage)], key=_STAGE_ORDER.index)]


def tracks_out(t: track_service.Tracks | None) -> TracksOut:
    return TracksOut(**vars(t)) if t else TracksOut()


def application_brief(app: Application,
                      tracks: track_service.Tracks | None = None) -> ApplicationBrief:
    return ApplicationBrief(
        id=app.id,
        stage=app.stage,
        stage_label=stage_label(app.stage, tracks),
        route=app.route,
        tracks=tracks_out(tracks),
        contact_tier=app.contact_tier,
        close_reason=app.close_reason,
        stage_changed_at=app.stage_changed_at,
    )


def _job_item(
    job: Job, company: Company, app: Application, fit: FitScore | None, exp_version: str | None,
    tracks: track_service.Tracks | None = None,
) -> JobListItem:
    return JobListItem(
        id=job.id,
        description_level=job.description_level,
        user_label=job.user_label,
        matched_track=job.matched_track,
        matched_role=job.matched_role,
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
        fit=fit_brief(fit, exp_version),
        application=application_brief(app, tracks),
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
    exp_version = current_experience_version(session) if jobs else None
    rows = job_rows(session, jobs)
    tracks = track_service.for_apps(session, [r[2] for r in rows])
    return [_job_item(*row, exp_version, tracks.get(row[2].id)) for row in rows]


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
    tracks = track_service.for_apps(session, list(apps))
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
                stage_label=stage_label(a.stage, tracks.get(a.id)),
                route=a.route,
                tracks=tracks_out(tracks.get(a.id)),
                contact_tier=a.contact_tier,
                close_reason=a.close_reason,
                stage_changed_at=a.stage_changed_at,
                updated_at=a.updated_at,
                allowed_stages=allowed_stages(a),
            )
        )
    return cards


def contact_out(c: Contact, ranking: list[dict[str, Any]] | None = None) -> ContactOut:
    label = None
    if ranking is not None and 0 <= c.role_rank < len(ranking):
        label = ranking[c.role_rank].get("label")
    return ContactOut(
        id=c.id,
        company_id=c.company_id,
        full_name=c.full_name,
        title=c.title,
        email=c.email,
        linkedin_url=c.linkedin_url,
        source=c.source,
        role_rank=c.role_rank,
        role_label=label,
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
            stage_label=stage_label(apps[j.id].stage),
        )
        for j in jobs
        if j.id in apps
    ]


def contact_alert_fields(session: Session, app: Application,
                         contact: Contact | None) -> dict[str, Any]:
    """The contact's active alerts and, when there are any, the next contact by the ranking."""
    from app.schemas.jobs import ContactAlertOut
    from app.services import contact_check

    alerts = contact_check.active(session, contact.id) if contact else []
    nxt = contact_check.next_contact(session, app) if alerts else None
    return {"contact_alerts": [ContactAlertOut.model_validate(a, from_attributes=True)
                               for a in alerts],
            "next_contact": contact_out(nxt, _ranking(session)) if nxt else None}


def job_detail(session: Session, job: Job) -> JobDetail:
    (j, company, app, fit) = job_rows(session, [job])[0]
    exp_version = current_experience_version(session)
    base = _job_item(j, company, app, fit, exp_version, track_service.for_app(session, app))
    brief = base.fit
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
            **brief.model_dump(),
            sub_scores=fit.sub_scores or {},
            red_flags=fit.red_flags or [],
            strengths=fit.strengths,
            gaps=fit.gaps,
            summary=fit.summary,
            error=fit.error,
            duration_ms=fit.duration_ms,
            created_at=fit.created_at,
        )
        if fit and brief
        else None,
        notes=app.notes,
        company_reason=app.company_reason or "",
        tracking=tracked_item(session, row) if (row := tracking.row_for(session, app)) else None,
        contact=contact_out(contact, _ranking(session)) if contact else None,
        lookup_status=_lookup_status(session, company.id),
        **contact_alert_fields(session, app, contact),
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
                locked=c.locked_at is not None,
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


def tracked_item(session: Session, r: tracking.TrackedRow) -> TrackedItem:
    a = r.application
    cv = session.get(CVVersion, a.applied_cv_version_id) if a.applied_cv_version_id else None
    letter = session.get(CoverLetter, a.applied_cover_letter_id) \
        if a.applied_cover_letter_id else None
    days = r.days_to_first_answer
    return TrackedItem(
        application_id=a.id, job_id=r.job.id, title=r.job.title,
        company=r.company.name if r.company else "", track=r.job.matched_track,
        country=r.job.country, source=r.job.source, url=r.job.url, stage=a.stage,
        stage_label=stage_label(a.stage, track_service.for_app(session, a)),
        close_reason=a.close_reason,
        applied_at=a.applied_at, applied_method=a.applied_method,
        applied_cv_version_id=a.applied_cv_version_id,
        applied_cv_version=cv.version if cv else None,
        applied_cover_letter_id=a.applied_cover_letter_id,
        applied_cover_letter_version=letter.version if letter else None,
        applied_notes=a.applied_notes,
        responses=[ResponseOut.model_validate(x, from_attributes=True) for x in r.responses],
        interviews=[InterviewOut.model_validate(x, from_attributes=True) for x in r.interviews],
        days_to_first_response=round(days, 1) if days is not None else None,
    )


def _ranking(session: Session) -> list[dict[str, Any]]:
    from app.services.contacts import role_ranking

    return role_ranking(session)


def _lookup_status(session: Session, company_id: int) -> str | None:
    row = session.exec(select(CompanyLookup).where(CompanyLookup.company_id == company_id)).first()
    return row.status if row else None
