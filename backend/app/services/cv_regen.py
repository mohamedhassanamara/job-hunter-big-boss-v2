"""Review CVs → "Regenerate selected": queue one background task per CV (`generation_task`, kind
`cv_regen`, run by the generation worker with the CV model from Settings → Models and its retry
rules). Each result is a new DRAFT version; an approved CV is never changed or un-approved.

No automatic model switch: an APInex quota failure (HTTP 402) leaves that row failed with Retry
and "Retry with Gemini" (`use="gemini"`, one call, never automatic).
"""

from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import Application, CVVersion, GenerationTask
from app.models.base import utcnow
from app.models.enums import CVStatus, Stage
from app.services import generation

KIND = "cv_regen"
MODES = ("whole", "summary")
CONFIRM_ABOVE = 20  # more CVs than this need an explicit confirmation
DONE_VISIBLE_HOURS = 24


class RegenError(ValueError):
    pass


def requests_per_cv(mode: str, feedback: str | None) -> int:
    """About how many model requests one CV takes: the 2-pass plan (+1 to write the summary toward
    your feedback), or a summary and its possible retry."""
    return 2 if mode == "summary" else 2 + (1 if (feedback or "").strip() else 0)


def estimate(s: Session, engine: Engine, count: int, mode: str, feedback: str | None,
             use: str | None = None) -> dict[str, Any]:
    from app.services import model_choice
    from app.services.gemini_keys import pool_for

    per_cv = requests_per_cv(mode, feedback)
    requests = per_cv * count
    try:
        pick = model_choice.choice(s, "cv", use)
    except ValueError:  # Gemini paused and asked for
        pick = {"provider": "gemini", "model": model_choice.DEFAULT_GEMINI}
    remaining = cap = None
    if not generation._is_sandbox(s):  # noqa: SLF001 (the tour never calls a model)
        gem = pick["model"] if pick["provider"] == "gemini" else model_choice.DEFAULT_GEMINI
        pooled = pool_for(engine, gem).snapshot()["pooled"]
        remaining, cap = int(pooled["remaining"]), int(pooled["limit"])
    return {"count": count, "per_cv": per_cv, "requests": requests,
            "provider": pick["provider"], "model": pick["model"],
            "remaining_gemini": remaining, "gemini_cap": cap,
            "exceeds_remaining": remaining is not None and pick["provider"] == "gemini"
            and requests > remaining,
            "needs_confirmation": count > CONFIRM_ABOVE, "confirm_above": CONFIRM_ABOVE}


def latest_version(s: Session, app_id: int) -> CVVersion:
    v = s.exec(select(CVVersion).where(CVVersion.application_id == app_id,
                                       CVVersion.status != CVStatus.superseded)
               .order_by(col(CVVersion.version).desc())).first()
    if v is None:
        raise RegenError("This job has no CV to regenerate")
    return v


def skip_reason(s: Session, app: Application) -> str | None:
    """Why a queued regeneration no longer runs (checked when the worker claims it)."""
    from app.services.cv_pool import load_pool, readiness

    if Stage(app.stage) != Stage.shortlisted:
        return "No longer shortlisted"
    try:
        v = latest_version(s, app.id)
    except RegenError as exc:
        return str(exc)
    if v.locked_at is not None:
        return "This CV was already sent: it stays as it was"
    blockers = [r["message"] for r in readiness(load_pool(s)) if r["severity"] == "blocker"]
    return "CV not generated: " + " ".join(blockers) if blockers else None


def select_rows(s: Session, app_ids: list[int]) -> tuple[list[int], list[dict[str, Any]]]:
    """The selection as the queue will take it: duplicates dropped, order kept, and only jobs
    that are in the Review CVs list; the rest come back with the reason."""
    from app.services import cv_review  # (cv_review reads this module's row states)

    review = {r.application_id for r in cv_review.rows(s)}
    seen: set[int] = set()
    ok: list[int] = []
    skipped: list[dict[str, Any]] = []
    for app_id in app_ids:
        if app_id in seen:
            continue
        seen.add(app_id)
        if app_id in review:
            ok.append(app_id)
        else:
            skipped.append({"application_id": app_id, "reason": "Not in the Review CVs list"})
    return ok, skipped


def enqueue_batch(s: Session, app_ids: list[int], mode: str, feedback: str | None,
                  use: str | None, batch_id: str) -> dict[str, Any]:
    """One queued task per CV (never two active ones for a job). Not committed."""
    if mode not in MODES:
        raise RegenError("mode must be whole or summary")
    if generation._is_sandbox(s):  # noqa: SLF001
        raise RegenError("The tour sandbox never calls a model: nothing was queued")
    ok, skipped = select_rows(s, app_ids)
    queued, already = 0, 0
    request = {"mode": mode, "feedback": (feedback or "").strip() or None, "batch_id": batch_id}
    for app_id in ok:
        if generation.active_task(s, app_id, KIND) is not None:
            already += 1
            continue
        task = generation.enqueue(s, app_id, KIND, "regenerate", use)
        if task is not None:
            task.details = {"request": request}
            s.add(task)
            queued += 1
    return {"queued": queued, "already_queued": already, "skipped": skipped,
            "batch_id": batch_id}


def retry(s: Session, app_id: int, use: str | None) -> GenerationTask:
    """Queue the failed regeneration of a row again (same request), optionally on Gemini for this
    one call. Not committed."""
    last = s.exec(select(GenerationTask).where(
        GenerationTask.application_id == app_id, GenerationTask.kind == KIND)
        .order_by(col(GenerationTask.id).desc())).first()
    if last is None or last.status != "failed":
        raise RegenError("There is no failed regeneration to retry for this CV")
    task = generation.enqueue(s, app_id, KIND, "retry", use)
    if task is None:
        raise RegenError("The tour sandbox never calls a model")
    task.details = {"request": dict((last.details or {}).get("request") or {})}
    s.add(task)
    return task


def states(s: Session, app_ids: list[int]) -> dict[int, dict[str, Any]]:
    """The latest regeneration per job for the list rows: queued, running, done (for a day),
    failed (with whether Retry helps)."""
    out: dict[int, dict[str, Any]] = {}
    if not app_ids:
        return out
    now = utcnow()
    for t in s.exec(select(GenerationTask).where(
            col(GenerationTask.application_id).in_(app_ids), GenerationTask.kind == KIND)
            .order_by(col(GenerationTask.id))).all():
        if t.status == "cancelled":
            out.pop(t.application_id, None)
            continue
        if t.status == "done" and t.finished_at is not None and (
                now - t.finished_at).total_seconds() > DONE_VISIBLE_HOURS * 3600:
            out.pop(t.application_id, None)
            continue
        out[t.application_id] = {
            "status": "running" if t.status == "running" else t.status,
            "error": t.error if t.status == "failed" else None,
            "warning": t.warning, "retryable": t.retryable, "model": t.model}
    return out
