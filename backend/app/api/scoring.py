from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import SessionDep, WorkspaceDep, get_or_404
from app.config import get_settings
from app.models import Job
from app.models.base import utcnow
from app.providers.ollama import OllamaFitScorer
from app.schemas.jobs import JobListItem
from app.schemas.scoring import (
    Enqueued,
    LabelIn,
    RescoreIn,
    ScoringHealth,
    ScoringStatus,
)
from app.services import scoring
from app.services.views import job_item

router = APIRouter(tags=["scoring"])


@router.get("/scoring/status", response_model=ScoringStatus)
def scoring_status(session: SessionDep, workspace: WorkspaceDep) -> ScoringStatus:
    queue = scoring.workspace_queue(workspace)
    counts = scoring.counts(session)
    ctx = scoring.load_context(session)
    return ScoringStatus(
        **queue.status(),
        jobs_total=counts.total,
        scored=counts.scored,
        stale=counts.stale,
        unscored=counts.unscored,
        failed_jobs=counts.failed,
        model=ctx.model,
        prompt_version=ctx.prompt_version,
    )


@router.get("/scoring/health", response_model=ScoringHealth)
def scoring_health(session: SessionDep, workspace: WorkspaceDep) -> ScoringHealth:
    model = scoring.load_context(session).model
    if workspace == "demo" or get_settings().job_sources == "mock":
        return ScoringHealth(reachable=True, model="mock-scorer", model_present=True,
                             message="Sample data uses a mock scorer", models=[], pull_command="")
    health = OllamaFitScorer(model).health()
    return ScoringHealth(
        reachable=health.reachable,
        model=health.model,
        model_present=health.model_present,
        message=health.message,
        models=health.models,
        pull_command=f"ollama pull {model}",
    )


@router.post("/scoring/rescore", response_model=Enqueued)
def rescore(body: RescoreIn, session: SessionDep, workspace: WorkspaceDep) -> Enqueued:
    counts = scoring.counts(session)
    ids = {
        "stale": counts.stale_ids,
        "failed": counts.failed_ids,
        "unscored": counts.unscored_ids,
        "all": list(session.exec(select(Job.id)).all()),
        "jobs": body.job_ids,
    }[body.scope]
    queue = scoring.workspace_queue(workspace)
    added = queue.enqueue(ids, force=body.scope in ("all", "jobs"))
    if queue.blocked:
        raise HTTPException(503, queue.blocked)
    return Enqueued(enqueued=added)


@router.post("/scoring/start", response_model=Enqueued)
def start(workspace: WorkspaceDep) -> Enqueued:
    """Retry after being blocked (e.g. the model was just pulled)."""
    queue = scoring.workspace_queue(workspace)
    queue.start()
    if queue.blocked:
        raise HTTPException(503, queue.blocked)
    return Enqueued(enqueued=queue.status()["queued"])


@router.post("/scoring/cancel", response_model=Enqueued)
def cancel(workspace: WorkspaceDep) -> Enqueued:
    return Enqueued(enqueued=-scoring.workspace_queue(workspace).cancel())


@router.post("/jobs/{job_id}/rescore", response_model=Enqueued)
def rescore_job(job_id: int, session: SessionDep, workspace: WorkspaceDep) -> Enqueued:
    get_or_404(session, Job, job_id, "Job")
    queue = scoring.workspace_queue(workspace)
    added = queue.enqueue([job_id], force=True, front=True)
    if queue.blocked:
        raise HTTPException(503, queue.blocked)
    return Enqueued(enqueued=added)


@router.put("/jobs/{job_id}/label", response_model=JobListItem)
def label_job(job_id: int, body: LabelIn, session: SessionDep) -> JobListItem:
    """The user's Good / Maybe / No judgment, used to evaluate the scorer (not a stage)."""
    job = get_or_404(session, Job, job_id, "Job")
    job.user_label = body.label
    job.labeled_at = utcnow() if body.label else None
    session.add(job)
    session.commit()
    session.refresh(job)
    return job_item(session, job)
