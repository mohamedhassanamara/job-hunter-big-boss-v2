"""Background drafting: the CV when you shortlist a job, the email when a verified contact AND an
approved CV both exist. Drafts only: nothing is ever approved here, and nothing is announced with
a toast (the job card shows "CV ready to review" / "Email ready to review").

- Triggers are in-session hooks that INSERT a `generation_task` row (they commit with the request
  that caused them, so a worker can never start before the stage change is saved):
  `on_shortlisted` / `on_unshortlisted` from `pipeline.transition`, `maybe_enqueue_email` after a
  CV approval, a contact becoming ready, and a shortlist.
- One worker thread per real workspace polls the table (`tick`). It runs the same code as the
  manual buttons (`cv_service.generate`, `outreach.generate_applied`) with the generator chosen in
  Settings → Models. Gemini calls take the shared key pool at "user" priority, which keeps them
  under the per-key rate limits and ahead of background scoring.
- Failures never switch model: after the generator's own retries a task is `failed` (the page
  offers Retry and "Generate with Claude"); a used-up daily quota waits for the reset.
- The tour sandbox never enqueues (no worker, no real models); tests run `tick` with mocks.
"""

import logging
import threading
import time
from datetime import UTC, timedelta
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import Application, CVVersion, GenerationTask, Job, OutreachDraft
from app.models.base import utcnow
from app.models.enums import DraftStatus, Stage

log = logging.getLogger(__name__)

ACTIVE = ("queued", "running")
KINDS = ("cv", "email")
TICK_SECONDS = 3.0
RETRY_DELAY = timedelta(minutes=3)
MAX_ATTEMPTS = 2  # task-level, after the generator's own backoff
DEFAULTS = {"auto_cv": True, "auto_email": False}


def settings(s: Session) -> dict[str, bool]:
    from app.models import AppSetting

    row = s.exec(select(AppSetting).where(AppSetting.key == "generation")).first()
    return {**DEFAULTS, **{k: bool(v) for k, v in ((row.value if row else {}) or {}).items()
                           if k in DEFAULTS}}


def _is_sandbox(s: Session) -> bool:
    from app.db import demo_engine

    return s.get_bind() is demo_engine


# ------------------------------------------------------------------------------------ queueing


def active_task(s: Session, app_id: int, kind: str) -> GenerationTask | None:
    return s.exec(select(GenerationTask).where(
        GenerationTask.application_id == app_id, GenerationTask.kind == kind,
        col(GenerationTask.status).in_(ACTIVE)).order_by(col(GenerationTask.id).desc())).first()


def enqueue(s: Session, app_id: int, kind: str, trigger: str,
            use: str | None = None) -> GenerationTask | None:
    """Queue one task (never two active ones of a kind for a job). Not committed."""
    if _is_sandbox(s):
        return None
    existing = active_task(s, app_id, kind)
    if existing is not None:
        return existing
    task = GenerationTask(application_id=app_id, kind=kind, trigger=trigger, use=use)
    s.add(task)
    s.flush()
    return task


def has_cv(s: Session, app_id: int) -> bool:
    return s.exec(select(CVVersion.id).where(
        CVVersion.application_id == app_id)).first() is not None


def on_shortlisted(s: Session, app: Application, src: Stage | str) -> None:
    """From `pipeline.transition`: queue the CV draft. A step back from CV ready, a job that
    already has a CV (including the approve-CV double move) and the setting off queue nothing."""
    if Stage(src) == Stage.cv_ready or not settings(s)["auto_cv"] or has_cv(s, app.id):
        return
    enqueue(s, app.id, "cv", "shortlist")


def on_unshortlisted(s: Session, app: Application) -> None:
    """Un-shortlisting cancels what is still queued. A running generation finishes and its draft
    stays (finished drafts are never deleted)."""
    for task in s.exec(select(GenerationTask).where(
            GenerationTask.application_id == app.id, GenerationTask.status == "queued")).all():
        task.status, task.finished_at = "cancelled", utcnow()
        s.add(task)


def email_ready(s: Session, app: Application) -> bool:
    """Both inputs exist for a job you shortlisted, and there is a posting to follow up."""
    from app.services import get_contact, outreach

    if Stage(app.stage) not in (Stage.shortlisted, Stage.cv_ready):
        return False
    job = s.get(Job, app.job_id)
    if job is None or outreach.email_mode(job) != "applied":
        return False
    if outreach.approved_cv(s, app) is None or get_contact.state(s, app) != "ready":
        return False
    return s.exec(select(OutreachDraft.id).where(
        OutreachDraft.application_id == app.id,
        OutreachDraft.status != DraftStatus.rejected)).first() is None


def maybe_enqueue_email(s: Session, app: Application, trigger: str) -> GenerationTask | None:
    """Whichever of the verified contact and the approved CV comes last starts the draft."""
    if not settings(s)["auto_email"] or not email_ready(s, app):
        return None
    return enqueue(s, app.id, "email", trigger)


# ------------------------------------------------------------------------------------ the worker


def recover(engine: Engine) -> None:
    """After a restart: a task left running goes back to the queue."""
    with Session(engine) as s:
        for task in s.exec(select(GenerationTask).where(GenerationTask.status == "running")).all():
            task.status = "queued"
            s.add(task)
        s.commit()


def _claim(engine: Engine) -> int | None:
    now = utcnow()
    with Session(engine) as s:
        for task in s.exec(select(GenerationTask).where(GenerationTask.status == "queued")
                           .order_by(col(GenerationTask.id))).all():
            if task.not_before is not None and task.not_before > now:
                continue
            task.status, task.started_at = "running", now
            task.attempts += 1
            s.add(task)
            s.commit()
            return task.id
    return None


def _finish(engine: Engine, task_id: int, **fields: Any) -> None:
    with Session(engine) as s:
        task = s.get(GenerationTask, task_id)
        for k, v in fields.items():
            setattr(task, k, v)
        if task.status in ("done", "failed", "skipped", "cancelled"):
            task.finished_at = utcnow()
        s.add(task)
        s.commit()


def tick(engine: Engine, *, mock: bool, workspace: str = "real") -> bool:
    """Run one queued task (if any). True when it did something."""
    task_id = _claim(engine)
    if task_id is None:
        return False
    with Session(engine) as s:
        task = s.get(GenerationTask, task_id)
        kind, app_id, use = task.kind, task.application_id, task.use
        app = s.get(Application, app_id)
        skip = _skip_reason(s, app, kind)
    if skip is not None:
        _finish(engine, task_id, status="skipped", warning=skip)
        return True
    started = time.monotonic()
    try:
        if kind == "cv":
            result_id, model, details = _run_cv(engine, app_id, use, mock, workspace)
        else:
            result_id, model, details = _run_email(engine, app_id, use, mock)
    except Exception as exc:  # noqa: BLE001 (stored on the task, shown on the job)
        _failed(engine, task_id, exc)
        return True
    details["wall_seconds"] = round(time.monotonic() - started, 1)
    _finish(engine, task_id, status="done", result_id=result_id, model=model, details=details,
            error=None, warning=None)
    return True


def _skip_reason(s: Session, app: Application | None, kind: str) -> str | None:
    from app.services.cv_pool import load_pool, readiness

    if app is None:
        return "The job no longer exists"
    if kind == "cv":
        if Stage(app.stage) != Stage.shortlisted:
            return "No longer shortlisted"
        if has_cv(s, app.id):
            return "This job already has a CV"
        blockers = [r["message"] for r in readiness(load_pool(s)) if r["severity"] == "blocker"]
        if blockers:
            return "CV not generated: " + " ".join(blockers)
        return None
    return None if email_ready(s, app) else "The email is no longer ready to draft"


def _run_cv(engine: Engine, app_id: int, use: str | None, mock: bool,
            workspace: str) -> tuple[int, str, dict[str, Any]]:
    from app.providers.registry import cv_generator
    from app.services import cv_service, model_choice
    from app.services import verifier as verifier_service

    with Session(engine) as s:
        pick = model_choice.choice(s, "cv", use)
        verifier = verifier_service.for_workspace(s, workspace)
    generator = cv_generator(mock=mock, model=pick["model"], engine=engine,
                             thinking_level=pick["thinking_level"])
    version = cv_service.generate(engine, app_id, generator, None, verifier=verifier)
    return version.id, generator.model, _details(generator)


def _run_email(engine: Engine, app_id: int, use: str | None,
               mock: bool) -> tuple[int, str, dict[str, Any]]:
    from app.providers.registry import email_drafter
    from app.services import model_choice, outreach

    with Session(engine) as s:
        pick = model_choice.choice(s, "email", use)
    drafter = email_drafter(mock=mock, model=pick["model"], engine=engine,
                            thinking_level=pick["thinking_level"])
    draft = outreach.generate_applied(engine, app_id, drafter)
    return draft.id, drafter.model, _details(drafter)


def _details(generator: Any) -> dict[str, Any]:
    runner = getattr(generator, "runner", None)  # Claude's `runner` is the subprocess function
    return runner.summary() if hasattr(runner, "summary") else {}


def _failed(engine: Engine, task_id: int, exc: Exception) -> None:
    from app.providers.gemini_generate import generation_failure

    message = str(exc)[:400]
    failure = generation_failure(exc)
    busy = "being drafted" in message  # one email at a time: try again shortly
    with Session(engine) as s:
        attempts = s.get(GenerationTask, task_id).attempts
    if failure is not None and failure.quota_resume is not None:
        resume = failure.quota_resume.astimezone(UTC) + timedelta(seconds=5)
        _finish(engine, task_id, status="queued", not_before=resume, attempts=attempts - 1,
                warning=f"Gemini's daily quota is used up: resumes at {resume:%H:%M} UTC",
                error=message)
    elif busy or (failure is not None and failure.retryable and attempts < MAX_ATTEMPTS):
        _finish(engine, task_id, status="queued", not_before=utcnow() + (
            timedelta(seconds=60) if busy else RETRY_DELAY), attempts=attempts - (1 if busy else 0),
                warning="Retrying shortly", error=message)
    else:
        _finish(engine, task_id, status="failed", error=message, warning=None,
                retryable=failure.retryable if failure is not None else True)
        log.warning("generation task %s failed: %s", task_id, message)


# ----------------------------------------------------------------------------- worker thread

_stop = threading.Event()
_thread: threading.Thread | None = None


def start_worker(engine: Engine) -> None:
    """Real workspace only (the sandbox never enqueues)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    from app.config import get_settings

    mock = get_settings().job_sources == "mock"
    recover(engine)
    _stop.clear()

    def loop() -> None:
        while not _stop.wait(TICK_SECONDS):
            try:
                while tick(engine, mock=mock) and not _stop.is_set():
                    pass
            except Exception:  # noqa: BLE001
                log.exception("generation worker tick failed")

    _thread = threading.Thread(target=loop, name="generation-worker", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()


# ---------------------------------------------------------------------------- for the DTOs


def states(s: Session, app_ids: list[int]) -> dict[int, dict[str, dict[str, Any] | None]]:
    """The latest task per job and kind that still says something: queued or running, failed,
    or skipped with a reason. Done and cancelled tasks say nothing (the draft is the state)."""
    out: dict[int, dict[str, dict[str, Any] | None]] = {}
    if not app_ids:
        return out
    for task in s.exec(select(GenerationTask).where(
            col(GenerationTask.application_id).in_(app_ids))
            .order_by(col(GenerationTask.id))).all():
        slot = out.setdefault(task.application_id, {"cv": None, "email": None})
        slot[task.kind] = None if task.status in ("done", "cancelled") else {
            "status": "generating" if task.status == "running" else task.status,
            "error": task.error, "warning": task.warning, "retryable": task.retryable}
    return out

