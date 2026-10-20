"""Ask Claude: a second opinion on one job, stored NEXT TO the main score, never replacing it.

- The prompt is the scoring prompt (same system prompt, same user prompt, same schema) plus the
  short verdict addendum (`prompts/confirm_verdict.md`), so the confirmation score is comparable
  with the main one: same arithmetic, same caps (`fit.build_record`).
- Order: Claude Code headless (your subscription, same subscription check as the CV), then Gemma
  through the Gemini API; if both fail, the copy-paste flow: copy the prompt into the Gemini Pro
  app and paste its JSON answer back. Whatever answered is recorded, with a note when an earlier
  step was skipped and why.
- Only this module and `recompute_all` write `fit_confirmation`; scoring never reads it.
"""

import json
import logging
import threading
import time
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import Company, FitConfirmation, Job
from app.providers.base import ConfirmationAnswer, ScoringFailed
from app.providers.gemini import parse_confirmation
from app.providers.ollama import inline_schema, schema_instruction
from app.services import fit, scoring
from app.services.prompt import load_prompt

log = logging.getLogger(__name__)

PROMPT = "confirm_verdict"
_running: set[int] = set()
_running_lock = threading.Lock()


class ConfirmationUnavailable(RuntimeError):
    """Every automatic step failed. `notes` says why; the copy-paste flow is still possible."""

    def __init__(self, notes: list[str]):
        super().__init__(" | ".join(notes) or "No confirmation model is available.")
        self.notes = notes


class ConfirmationBusy(RuntimeError):
    """A confirmation for this job is already running."""


class ConfirmationInvalid(ValueError):
    """The pasted answer isn't valid JSON for the schema."""


def prompts_for(session: Session, job_id: int) -> tuple[str, str, Job, Company, Any]:
    job = session.get(Job, job_id)
    if job is None:
        raise LookupError(f"Job {job_id} not found")
    company = session.get(Company, job.company_id)
    assert company is not None
    ctx = scoring.load_context(session)
    system, user = scoring.render(job, company, ctx)
    return f"{system}\n\n{load_prompt(PROMPT).system}", user, job, company, ctx


def manual_prompt(engine: Engine, job_id: int) -> str:
    """Everything to paste into the Gemini Pro app: instructions, candidate and job, schema."""
    with Session(engine) as s:
        system, user, *_ = prompts_for(s, job_id)
    schema = schema_instruction(inline_schema(ConfirmationAnswer))
    return (f"{system}{schema}\n\n---\n\n{user}\n\n---\nAnswer with the JSON object only, no "
            "other text.")


def _store(engine: Engine, job_id: int, answer: ConfirmationAnswer, *, source: str, model: str,
           via: str, notes: str, seconds: float) -> FitConfirmation:
    with Session(engine) as s:
        _, _, job, _, ctx = prompts_for(s, job_id)
        record = fit.build_record(
            answer, job_text=f"{job.title}\n{job.location}\n{job.description}",
            description_level=job.description_level, remote_type=job.remote_type,
            config=ctx.config, experience_text=ctx.experience_text, job_title=job.title)
        row = FitConfirmation(
            job_id=job_id, source=source, model=model, via=via, prompt_version=ctx.prompt_version,
            confirm_prompt_version=load_prompt(PROMPT).version_id,
            experience_version=ctx.experience_version, score=record["score"],
            sub_scores=record["sub_scores"], red_flags=record["red_flags"],
            core_requirements=record["core_requirements"], strengths=record["strengths"],
            gaps=record["gaps"], summary=record["summary"], confidence=record["confidence"],
            verdict=answer.verdict.model_dump(), notes=notes,
            duration_ms=int(seconds * 1000))
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def latest(session: Session, job_id: int) -> FitConfirmation | None:
    return session.exec(select(FitConfirmation).where(FitConfirmation.job_id == job_id)
                        .order_by(col(FitConfirmation.created_at).desc(),
                                  col(FitConfirmation.id).desc())).first()


def ask(engine: Engine, job_id: int, confirmers: list[tuple[str, Any]]) -> FitConfirmation:
    """Run the confirmers in order until one answers. A failing step is not fatal: it is noted
    and the next one runs. Raises ConfirmationUnavailable (with the notes) if none does."""
    with _running_lock:
        if job_id in _running:
            raise ConfirmationBusy(f"Job {job_id} is already being confirmed")
        _running.add(job_id)
    try:
        with Session(engine) as s:
            system, user, *_ = prompts_for(s, job_id)
        skipped: list[str] = []
        for source, confirmer in confirmers:
            started = time.monotonic()
            try:
                answer = confirmer.confirm(system, user)
            except Exception as exc:  # any provider failure moves on to the next step
                reason = f"{confirmer.model} ({getattr(confirmer, 'via', source)}): {exc}"[:300]
                log.warning("confirmation step %s failed for job %s: %s", source, job_id, reason)
                skipped.append(reason)
                continue
            notes = ""
            if skipped:
                notes = ("Skipped: " + " | ".join(skipped)
                         + f". This answer comes from {confirmer.model}.")
            return _store(engine, job_id, answer, source=source, model=confirmer.model,
                          via=getattr(confirmer, "via", source), notes=notes,
                          seconds=time.monotonic() - started)
        raise ConfirmationUnavailable(skipped)
    finally:
        with _running_lock:
            _running.discard(job_id)


def store_manual(engine: Engine, job_id: int, text: str) -> FitConfirmation:
    """A reply pasted from the Gemini Pro app (a fence or a {"properties": …} wrapper is fine)."""
    try:
        answer = parse_confirmation(text)
    except (ValidationError, json.JSONDecodeError, ScoringFailed) as exc:
        raise ConfirmationInvalid(
            "That isn't the JSON answer the prompt asks for: " + str(exc)[:200]) from exc
    return _store(engine, job_id, answer, source="manual", model="Gemini Pro app (pasted)",
                  via="paste", notes="Pasted by you from the Gemini Pro app.", seconds=0.0)
