from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlmodel import select

from app.api.deps import SessionDep, get_or_404
from app.models import Application, Job
from app.models.base import utcnow
from app.models.enums import CloseReason, Stage
from app.schemas.jobs import JobDetail, JobList, JobListItem
from app.services import pipeline
from app.services.views import job_detail, job_item, job_items

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobList)
def list_jobs(
    session: SessionDep,
    stage: Literal["new", "open", "all"] = "new",
    q: str | None = None,
    source: Annotated[list[str] | None, Query()] = None,
    remote: Annotated[list[str] | None, Query()] = None,
    country: Annotated[list[str] | None, Query()] = None,
    min_score: int | None = None,
    posted_within: int | None = Query(None, description="days"),
    hide_duplicates: bool = True,
    label: Literal["unlabeled", "good", "maybe", "no"] | None = None,
    flags: Literal["hide_hard", "only_flagged"] | None = None,
    track: Annotated[list[str] | None, Query()] = None,
    sort: Literal["fit", "newest"] = "fit",
) -> JobList:
    items = job_items(session, session.exec(select(Job)).all())
    now = utcnow()

    def keep(i: JobListItem) -> bool:
        st = i.application.stage
        if stage == "new" and st != Stage.new:
            return False
        if stage == "open" and st == Stage.closed:
            return False
        if q:
            needle = q.lower()
            if needle not in i.title.lower() and needle not in i.company.name.lower():
                return False
        if source and not any(s in source for s in (i.sources or [i.source])):
            return False
        if remote and i.remote_type not in remote:
            return False
        if country and (i.country or "REMOTE") not in country:
            return False
        if track and (i.matched_track or "NONE") not in track:
            return False
        score = i.fit.score if i.fit else None
        if min_score is not None and (score is None or score < min_score):
            return False
        if posted_within is not None:
            posted = i.posted_at or i.discovered_at
            if posted < now - timedelta(days=posted_within):
                return False
        if label == "unlabeled" and i.user_label is not None:
            return False
        if label in ("good", "maybe", "no") and i.user_label != label:
            return False
        if flags == "hide_hard" and i.fit and i.fit.hard_flag:
            return False
        if flags == "only_flagged" and not (i.fit and i.fit.flag_count):
            return False
        return not (hide_duplicates and i.duplicate_of_id is not None)

    items = [i for i in items if keep(i)]
    if sort == "fit":
        # Scored jobs first by score; pending/failed after, newest first.
        items.sort(
            key=lambda i: (
                -(i.fit.score if i.fit and i.fit.score is not None else -1),
                -(i.posted_at or i.discovered_at).timestamp(),
            )
        )
    else:
        items.sort(key=lambda i: i.posted_at or i.discovered_at, reverse=True)
    return JobList(items=items, total=len(items))


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, session: SessionDep) -> JobDetail:
    return job_detail(session, get_or_404(session, Job, job_id, "Job"))


def _app_for(session: SessionDep, job_id: int) -> tuple[Job, Application]:
    job = get_or_404(session, Job, job_id, "Job")
    app = session.exec(select(Application).where(Application.job_id == job.id)).one()
    return job, app


@router.post("/{job_id}/shortlist", response_model=JobListItem)
def shortlist(job_id: int, session: SessionDep) -> JobListItem:
    job, app = _app_for(session, job_id)
    pipeline.transition(session, app, Stage.shortlisted)
    session.commit()
    return job_item(session, job)


@router.post("/{job_id}/dismiss", response_model=JobListItem)
def dismiss(job_id: int, session: SessionDep) -> JobListItem:
    job, app = _app_for(session, job_id)
    pipeline.transition(session, app, Stage.closed, close_reason=CloseReason.dismissed)
    session.commit()
    return job_item(session, job)
