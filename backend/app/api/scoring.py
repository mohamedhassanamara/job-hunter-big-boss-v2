import math
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import func
from sqlmodel import col, select

from app.api.deps import SessionDep, WorkspaceDep, get_or_404
from app.config import get_settings
from app.db import engine_for
from app.models import Company, FitScore, Job
from app.models.base import utcnow
from app.models.enums import DescriptionLevel
from app.providers.ollama import OllamaFitScorer
from app.schemas.jobs import JobListItem
from app.schemas.scoring import (
    ContinueWithIn,
    Enqueued,
    FullListingOut,
    LabelIn,
    PasteIn,
    RescoreIn,
    RescorePreview,
    ScoringHealth,
    ScoringStatus,
)
from app.services import scoring
from app.services.gemini_keys import configured_keys, pool_for
from app.services.listing import ListingUnavailable, fetch_full_listing, with_location_requirements
from app.services.text import html_to_text
from app.services.views import job_item

router = APIRouter(tags=["scoring"])


@router.get("/scoring/status", response_model=ScoringStatus)
def scoring_status(session: SessionDep, workspace: WorkspaceDep) -> ScoringStatus:
    queue = scoring.workspace_queue(workspace)
    counts = scoring.counts(session)
    ctx = scoring.load_context(session)
    current, total = _current_progress(session, ctx)
    return ScoringStatus(
        **queue.status(),
        jobs_total=counts.total,
        scored=counts.scored,
        stale=counts.stale,
        unscored=counts.unscored,
        failed_jobs=counts.failed,
        model=ctx.model,
        prompt_version=ctx.prompt_version,
        current_scored=current,
        current_total=total,
    )


def _latest_ok(session) -> dict[int, FitScore]:  # noqa: ANN001
    latest = select(func.max(FitScore.id)).where(FitScore.status == "ok").group_by(FitScore.job_id)
    return {r.job_id: r for r in session.exec(select(FitScore).where(col(FitScore.id).in_(latest)))}


def _on_current(row: FitScore | None, ctx: scoring.ScoringContext) -> bool:
    return bool(row and row.prompt_version == ctx.prompt_version and row.model == ctx.model)


def _current_progress(session, ctx: scoring.ScoringContext) -> tuple[int, int]:  # noqa: ANN001
    """(non-duplicate jobs on the current prompt + model, all non-duplicate jobs)."""
    ids = list(session.exec(select(Job.id).where(col(Job.duplicate_of_id).is_(None))).all())
    latest = _latest_ok(session)
    return sum(1 for i in ids if _on_current(latest.get(i), ctx)), len(ids)


@router.get("/scoring/health", response_model=ScoringHealth)
def scoring_health(
    session: SessionDep, workspace: WorkspaceDep, model: str | None = None
) -> ScoringHealth:
    """Health of the scoring model (or of `model`, e.g. the local fallback)."""
    model = model or scoring.load_context(session).model
    if workspace == "demo" or get_settings().job_sources == "mock":
        return ScoringHealth(reachable=True, model="mock-scorer", model_present=True,
                             message="Sample data uses a mock scorer", models=[], pull_command="")
    if model.startswith("gemini-"):
        keys = configured_keys()
        return ScoringHealth(
            reachable=bool(keys), model=model, model_present=bool(keys),
            message=f"{len(keys)} Gemini API key(s) configured" if keys
            else "No Gemini API key configured (GEMINI_API_KEYS in .env).",
            models=[], pull_command="")
    health = OllamaFitScorer(model).health()
    return ScoringHealth(
        reachable=health.reachable,
        model=health.model,
        model_present=health.model_present,
        message=health.message,
        models=health.models,
        pull_command=f"ollama pull {model}",
    )


_NEEDS_CONFIRM = ("all", "stale", "outdated")  # these re-score jobs that already have a score


def _outdated_ids(session) -> list[int]:  # noqa: ANN001
    """Non-duplicate jobs whose latest score isn't from the current prompt + model: never-scored
    first, then the best stored score first (so the top of Discover is consistent soonest)."""
    ctx = scoring.load_context(session)
    latest = _latest_ok(session)
    ids = session.exec(select(Job.id).where(col(Job.duplicate_of_id).is_(None))).all()
    todo = [i for i in ids if not _on_current(latest.get(i), ctx)]
    return sorted(todo, key=lambda i: (latest[i].score is not None, -(latest[i].score or 0), i)
                  if i in latest else (False, 0, i))


def _scope_ids(session, scope: str, job_ids: list[int]) -> list[int]:  # noqa: ANN001
    if scope == "outdated":
        return _outdated_ids(session)
    counts = scoring.counts(session)
    return {
        "stale": counts.stale_ids,
        "failed": counts.failed_ids,
        "unscored": counts.unscored_ids,
        "all": list(session.exec(select(Job.id)).all()),
        "jobs": job_ids,
    }[scope]


@router.get("/scoring/rescore-preview", response_model=RescorePreview)
def rescore_preview(scope: str, session: SessionDep, workspace: WorkspaceDep) -> RescorePreview:
    """What a bulk rescore would do: how many jobs, which model, roughly how long."""
    if scope not in ("stale", "failed", "unscored", "all", "outdated"):
        raise HTTPException(422, f"Unknown scope {scope}")
    ids = _scope_ids(session, scope, [])
    ctx = scoring.load_context(session)
    eta = scoring.estimate_seconds(session, ctx, len(ids))
    days = capacity = None
    if ctx.model.startswith("gemini-") and workspace_is_real(workspace):
        snap = pool_for(engine_for(workspace), ctx.model).snapshot()
        usable = [k for k in snap["keys"] if k["state"] != "disabled"]
        capacity = len(usable) * snap["limits"]["rpd"]
        left = max(0, len(ids) - snap["remaining_today"])
        days = 1 if left == 0 else (1 + math.ceil(left / capacity) if capacity else None)
    return RescorePreview(scope=scope, count=len(ids), model=ctx.model, eta_seconds=eta,
                          days=days, daily_capacity=capacity)


@router.post("/scoring/rescore", response_model=Enqueued)
def rescore(body: RescoreIn, session: SessionDep, workspace: WorkspaceDep) -> Enqueued:
    if body.scope in _NEEDS_CONFIRM and not body.confirm:
        raise HTTPException(
            409, "Rescoring existing scores needs confirmation (see /scoring/rescore-preview)"
        )
    ids = _scope_ids(session, body.scope, body.job_ids)
    queue = scoring.workspace_queue(workspace)
    added = queue.enqueue(ids, force=body.scope in ("all", "jobs", "stale"), trigger="rescore")
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


def workspace_is_real(workspace: str) -> bool:
    return workspace != "demo" and get_settings().job_sources != "mock"


@router.get("/scoring/quota")
def scoring_quota(session: SessionDep, workspace: WorkspaceDep) -> dict[str, Any]:
    """Remaining Gemini quota per key (Settings → Models, Today). Other models have no quota."""
    ctx = scoring.load_context(session)
    if not ctx.model.startswith("gemini-"):
        return {"provider": "other", "model": ctx.model}
    if not workspace_is_real(workspace):  # the tour sandbox: a believable sample, nothing is called
        keys = [{"label": "key 1", "fingerprint": "a1b2c3", "used": 500, "limit": 500,
                 "remaining": 0, "state": "exhausted", "reason": None, "last_minute": 0},
                {"label": "key 2", "fingerprint": "d4e5f6", "used": 212, "limit": 500,
                 "remaining": 288, "state": "ok", "reason": None, "last_minute": 3}]
        return {"provider": "gemini", "model": ctx.model, "keys": keys, "sample": True,
                "limits": {"rpm": 15, "tpm": 250_000, "rpd": 500}, "remaining_today": 288,
                "day": "sample", "resets_at": None}
    return {"provider": "gemini", **pool_for(engine_for(workspace), ctx.model).snapshot()}


@router.post("/scoring/keys/{label}/enable")
def enable_key(label: str, session: SessionDep, workspace: WorkspaceDep) -> dict[str, bool]:
    """Use a Gemini key again after it was disabled because Google refused it."""
    ctx = scoring.load_context(session)
    if not workspace_is_real(workspace):
        raise HTTPException(409, "Sample data has no real keys")
    ok = pool_for(engine_for(workspace), ctx.model).enable(label)
    if not ok:
        raise HTTPException(404, f"No disabled key called {label}")
    return {"ok": True}


@router.post("/scoring/continue-with", response_model=Enqueued)
def continue_with(body: ContinueWithIn, workspace: WorkspaceDep) -> Enqueued:
    """Your explicit choice while the Gemini quota is used up: score the rest with another model
    (e.g. the Ollama cloud model) until the app restarts, or null to go back to Settings."""
    queue = scoring.workspace_queue(workspace)
    queue.continue_with(body.model)
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


def _store_full_description(session, job: Job, text: str, workspace: str) -> None:  # noqa: ANN001
    job.description = text
    job.description_level = DescriptionLevel.full
    job.full_fetched_at = utcnow()
    session.add(job)
    session.commit()
    scoring.workspace_queue(workspace).enqueue([job.id], front=True)


@router.post("/jobs/{job_id}/fetch-full", response_model=FullListingOut)
def fetch_full(job_id: int, session: SessionDep, workspace: WorkspaceDep) -> FullListingOut:
    """Fetch this one job's full listing (never in bulk) and rescore it."""
    job = get_or_404(session, Job, job_id, "Job")
    if workspace == "demo":
        return FullListingOut(ok=False, can_paste=True,
                              message="Sample data: paste a description to try it.")
    try:
        listing = fetch_full_listing(job.url)
    except ListingUnavailable as exc:
        return FullListingOut(ok=False, message=str(exc), can_paste=exc.can_paste)
    text = with_location_requirements(listing)
    _store_full_description(session, job, text, workspace)
    company = session.get(Company, job.company_id)
    if listing.company_url and company is not None and not company.website:
        company.website = listing.company_url  # captured: used to find the company's domain
        session.add(company)
    if listing.linkedin_url and company is not None and not company.linkedin_url:
        company.linkedin_url = listing.linkedin_url  # evidence for picking the right PDL company
        session.add(company)
    if listing.apply_url and not job.apply_url and listing.apply_url != job.url:
        job.apply_url = listing.apply_url
        session.add(job)
    session.commit()
    return FullListingOut(ok=True, message="Full listing fetched; rescoring.",
                          characters=len(text))


@router.put("/jobs/{job_id}/description", response_model=FullListingOut)
def paste_description(
    job_id: int, body: PasteIn, session: SessionDep, workspace: WorkspaceDep
) -> FullListingOut:
    """The user pasted the full listing text (for sites that block automated fetching)."""
    job = get_or_404(session, Job, job_id, "Job")
    text = html_to_text(body.description)
    if len(text) < 200:
        raise HTTPException(422, "That looks too short to be a full job description")
    _store_full_description(session, job, text, workspace)
    return FullListingOut(ok=True, message="Description saved; rescoring.", characters=len(text))


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
