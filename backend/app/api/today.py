from fastapi import APIRouter
from sqlmodel import col, func, select

from app.api.deps import SessionDep
from app.api.get_contact import queue_out
from app.api.settings import last_runs
from app.models import (
    Application,
    Company,
    Contact,
    CVVersion,
    Job,
    OutreachDraft,
    SearchProfile,
    SendQueue,
    SendQueueItem,
)
from app.models.enums import CVStatus, DraftStatus, QueueItemStatus, Stage
from app.schemas.today import (
    CVReviewItem,
    DraftReviewItem,
    NavCounts,
    QueueSummary,
    SearchHit,
    SearchOut,
    StatsSummary,
    TodayOut,
    UpcomingInterview,
)
from app.schemas.tracking import ReminderOut
from app.services import get_contact, tracking
from app.services.views import job_items, pipeline_cards

router = APIRouter(tags=["today"])


@router.get("/today", response_model=TodayOut)
def today(session: SessionDep) -> TodayOut:
    profile = session.exec(select(SearchProfile).where(SearchProfile.is_active)).first()
    min_fit = profile.min_fit_score if profile else 65

    new_jobs = session.exec(
        select(Job)
        .join(Application, col(Application.job_id) == col(Job.id))
        .where(Application.stage == Stage.new, col(Job.duplicate_of_id).is_(None))
    ).all()
    high = [
        i for i in job_items(session, new_jobs)
        if i.fit and i.fit.score is not None and i.fit.score >= min_fit
    ]
    high.sort(key=lambda i: -(i.fit.score or 0) if i.fit else 0)

    # CVs to review: latest version per application is a draft.
    latest: dict[int, CVVersion] = {}
    for v in session.exec(select(CVVersion).order_by(col(CVVersion.version))).all():
        latest[v.application_id] = v
    review_versions = [v for v in latest.values() if v.status == CVStatus.draft]
    apps = {
        a.id: a
        for a in session.exec(
            select(Application).where(
                col(Application.id).in_([v.application_id for v in review_versions])
            )
        ).all()
    }
    jobs = {
        j.id: j
        for j in session.exec(
            select(Job).where(col(Job.id).in_([a.job_id for a in apps.values()]))
        ).all()
    }
    drafts = session.exec(
        select(OutreachDraft)
        .where(OutreachDraft.status == DraftStatus.draft)
        .order_by(col(OutreachDraft.created_at).desc())
    ).all()
    to_queue = session.exec(
        select(OutreachDraft)
        .where(OutreachDraft.status == DraftStatus.approved)
        .order_by(col(OutreachDraft.updated_at).desc())
    ).all()
    draft_apps = {
        a.id: a
        for a in session.exec(
            select(Application).where(col(Application.id).in_(
                [d.application_id for d in [*drafts, *to_queue]]))
        ).all()
    }
    jobs.update(
        {
            j.id: j
            for j in session.exec(
                select(Job).where(col(Job.id).in_([a.job_id for a in draft_apps.values()]))
            ).all()
        }
    )
    companies = {
        c.id: c
        for c in session.exec(
            select(Company).where(col(Company.id).in_({j.company_id for j in jobs.values()}))
        ).all()
    }
    contacts = {
        c.id: c
        for c in session.exec(
            select(Contact).where(col(Contact.id).in_({d.contact_id for d in [*drafts, *to_queue]}))
        ).all()
    }

    upcoming = [
        UpcomingInterview(
            interview_id=i.id, application_id=a.id, job_id=j.id, job_title=j.title,
            company_name=c.name, round=i.round, type=i.type, scheduled_at=i.scheduled_at,
        )
        for i, a, j, c in tracking.upcoming_interviews(session)
    ]

    queue = session.exec(select(SendQueue)).first()
    q_items = (
        session.exec(select(SendQueueItem).where(SendQueueItem.queue_id == queue.id)).all()
        if queue
        else []
    )

    def job_of(app_id: int, source: dict[int, Application]) -> Job:
        return jobs[source[app_id].job_id]

    return TodayOut(
        new_high_fit=high[:5],
        new_high_fit_total=len(high),
        cvs_to_review=[
            CVReviewItem(
                application_id=v.application_id,
                job_id=job_of(v.application_id, apps).id,
                job_title=job_of(v.application_id, apps).title,
                company_name=companies[job_of(v.application_id, apps).company_id].name,
                version=v.version,
                created_at=v.created_at,
            )
            for v in review_versions
        ],
        drafts_to_approve=[
            DraftReviewItem(
                draft_id=d.id,
                job_id=job_of(d.application_id, draft_apps).id,
                job_title=job_of(d.application_id, draft_apps).title,
                company_name=companies[job_of(d.application_id, draft_apps).company_id].name,
                contact_name=contacts[d.contact_id].full_name if d.contact_id in contacts else None,
                created_at=d.created_at,
            )
            for d in drafts
        ],
        emails_to_queue=[
            DraftReviewItem(
                draft_id=d.id,
                job_id=job_of(d.application_id, draft_apps).id,
                job_title=job_of(d.application_id, draft_apps).title,
                company_name=companies[job_of(d.application_id, draft_apps).company_id].name,
                contact_name=contacts[d.contact_id].full_name if d.contact_id in contacts else None,
                created_at=d.updated_at,
            )
            for d in to_queue
        ],
        ready_to_apply=pipeline_cards(session, tracking.ready_to_apply(session)),
        also_email=[c for c in pipeline_cards(session, tracking.also_email(session))
                    if c.tracks.outreach in ("no_contact", "verify", "contact")][:5],
        contacts_to_get=queue_out(session, limit=5),
        reminders=[ReminderOut(**r.__dict__) for r in tracking.reminders(session)],
        upcoming_interviews=upcoming,
        stats_summary=StatsSummary(**tracking.stats_summary(session)),
        queue=QueueSummary(
            status=queue.status if queue else "idle",
            next_send_at=queue.next_send_at if queue else None,
            pending=sum(1 for i in q_items if i.status == QueueItemStatus.pending),
            sent=sum(1 for i in q_items if i.status == QueueItemStatus.sent),
            interval_minutes=queue.interval_minutes if queue else 15,
        ),
        last_runs=last_runs(session),
        min_fit_score=min_fit,
    )


@router.get("/nav-counts", response_model=NavCounts)
def nav_counts(session: SessionDep) -> NavCounts:
    def count(stmt) -> int:  # noqa: ANN001
        return session.exec(stmt).one()

    return NavCounts(
        discover_new=count(
            select(func.count()).select_from(Application).where(Application.stage == Stage.new)
        ),
        pipeline_active=count(
            select(func.count())
            .select_from(Application)
            .where(col(Application.stage).not_in([Stage.new, Stage.closed]))
        ),
        outreach_review=count(
            select(func.count())
            .select_from(OutreachDraft)
            .where(OutreachDraft.status == DraftStatus.draft)
        ),
        queue_pending=count(
            select(func.count())
            .select_from(SendQueueItem)
            .where(SendQueueItem.status == QueueItemStatus.pending)
        ),
        ready_to_apply=len(tracking.ready_to_apply(session)),
        contacts_to_get=len(get_contact.queue(session)),
    )


@router.get("/search", response_model=SearchOut)
def search(q: str, session: SessionDep) -> SearchOut:
    q = q.strip()
    if not q:
        return SearchOut(hits=[])
    hits: list[SearchHit] = []
    jobs = session.exec(
        select(Job, Company)
        .join(Company, col(Company.id) == col(Job.company_id))
        .where(
            col(Job.duplicate_of_id).is_(None),
            col(Job.title).icontains(q) | col(Company.name).icontains(q),
        )
        .limit(8)
    ).all()
    hits += [
        SearchHit(
            kind="job", id=j.id, title=j.title, subtitle=f"{c.name} · {j.location}",
            href=f"/jobs/{j.id}",
        )
        for j, c in jobs
    ]
    for c in session.exec(select(Company).where(col(Company.name).icontains(q)).limit(5)).all():
        hits.append(
            SearchHit(
                kind="company", id=c.id, title=c.name, subtitle=c.domain or "Company",
                href=f"/contacts?company={c.id}",
            )
        )
    contacts = session.exec(
        select(Contact, Company)
        .join(Company, col(Company.id) == col(Contact.company_id))
        .where(col(Contact.full_name).icontains(q) | col(Contact.title).icontains(q))
        .limit(6)
    ).all()
    hits += [
        SearchHit(
            kind="contact", id=p.id, title=p.full_name, subtitle=f"{p.title} · {c.name}",
            href=f"/contacts?company={c.id}",
        )
        for p, c in contacts
    ]
    return SearchOut(hits=hits)
