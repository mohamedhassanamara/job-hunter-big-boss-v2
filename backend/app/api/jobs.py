from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlmodel import col, func, select

from app.api.deps import SessionDep, get_or_404
from app.models import Application, Company, FitScore, Job
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
    limit: int | None = Query(None, ge=1, le=500, description="page size (default: all)"),
    offset: int = Query(0, ge=0),
) -> JobList:
    """Filter and sort on a lean read of every job (no descriptions, no score JSON), then build
    the full cards for the requested page only. `total` is the filtered count."""
    now = utcnow()
    newest = select(func.max(FitScore.id)).group_by(FitScore.job_id)
    fit_cols = [FitScore.job_id, FitScore.score, FitScore.status, FitScore.prompt_version]
    if flags:  # the red-flag JSON is read only when it is filtered on
        fit_cols.append(FitScore.red_flags)
    fits = {r[0]: r for r in session.exec(select(*fit_cols).where(col(FitScore.id).in_(newest)))}
    rows = session.exec(
        select(Job.id, Job.title, Job.source, Job.sources, Job.remote_type, Job.country,
               Job.matched_track, Job.posted_at, Job.discovered_at, Job.user_label,
               Job.duplicate_of_id, Company.name, Application.stage)
        .join(Company, col(Company.id) == col(Job.company_id))
        .join(Application, col(Application.job_id) == col(Job.id))
        .order_by(col(Job.id))).all()

    def score_of(job_id: int) -> int | None:
        f = fits.get(job_id)  # a pending/legacy or failed score has no number
        return f[1] if f is not None and f[3] is not None and f[2] == "ok" else None

    def keep(r) -> bool:  # noqa: ANN001
        (job_id, title, src, sources, remote_type, country_code, matched, posted, discovered,
         user_label, dup, company, st) = r
        if stage == "new" and st != Stage.new:
            return False
        if stage == "open" and st == Stage.closed:
            return False
        if q:
            needle = q.lower()
            if needle not in title.lower() and needle not in company.lower():
                return False
        if source and not any(x in source for x in (sources or [src])):
            return False
        if remote and remote_type not in remote:
            return False
        if country and (country_code or "REMOTE") not in country:
            return False
        if track and (matched or "NONE") not in track:
            return False
        score = score_of(job_id)
        if min_score is not None and (score is None or score < min_score):
            return False
        if posted_within is not None and (posted or discovered) < now - timedelta(
                days=posted_within):
            return False
        if label == "unlabeled" and user_label is not None:
            return False
        if label in ("good", "maybe", "no") and user_label != label:
            return False
        if flags:
            red = (fits[job_id][4] if job_id in fits else None) or []
            if flags == "hide_hard" and any(f.get("severity") == "hard" for f in red):
                return False
            if flags == "only_flagged" and not red:
                return False
        return not (hide_duplicates and dup is not None)

    kept = [r for r in rows if keep(r)]
    if sort == "fit":
        # Scored jobs first by score; pending/failed after, newest first.
        kept.sort(key=lambda r: (-(score_of(r[0]) if score_of(r[0]) is not None else -1),
                                 -(r[7] or r[8]).timestamp()))
    else:
        kept.sort(key=lambda r: r[7] or r[8], reverse=True)
    page = kept[offset:offset + limit] if limit is not None else kept[offset:]
    by_id = {j.id: j for j in session.exec(select(Job).where(
        col(Job.id).in_([r[0] for r in page]))).all()}
    by_item = {i.id: i for i in job_items(session, [by_id[r[0]] for r in page])}
    return JobList(items=[by_item[r[0]] for r in page if r[0] in by_item], total=len(kept))


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
