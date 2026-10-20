"""Ask Claude (a second opinion next to the main score): see services/confirmation.py."""

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep, WorkspaceDep, get_or_404
from app.config import get_settings
from app.db import engine_for
from app.models import AppSetting, FitConfirmation, Job
from app.providers import registry
from app.schemas.confirmation import ConfirmationOut, ConfirmationPrompt, PasteIn
from app.services import confirmation, fit
from app.services.views import current_experience_version, fit_band

router = APIRouter(tags=["confirmation"])


def _out(session, row: FitConfirmation) -> ConfirmationOut:  # noqa: ANN001
    current = current_experience_version(session)
    return ConfirmationOut(
        id=row.id, job_id=row.job_id, source=row.source, model=row.model, via=row.via,
        score=row.score, band=fit_band(row.score), sub_scores=row.sub_scores,
        red_flags=row.red_flags, core_requirements=row.core_requirements,
        capped_by=fit.cap_reason(row.red_flags, row.core_requirements),
        missing_core=next((c["requirement"] for c in row.core_requirements if c.get("counts")),
                          None),
        strengths=row.strengths, gaps=row.gaps, summary=row.summary, confidence=row.confidence,
        verdict=row.verdict, notes=row.notes, prompt_version=row.prompt_version,
        created_at=row.created_at,
        stale=bool(row.experience_version and row.experience_version != current))


def _is_mock(workspace: str) -> bool:
    return workspace == "demo" or get_settings().job_sources == "mock"


def _claude_model(session) -> str:  # noqa: ANN001
    from sqlmodel import select

    from app.providers.claude_confirm import DEFAULT_MODEL

    row = session.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    return ((row.value if row else {}).get("confirm") or {}).get("model") or DEFAULT_MODEL


@router.get("/jobs/{job_id}/confirmation", response_model=ConfirmationOut | None)
def get_confirmation(job_id: int, session: SessionDep) -> ConfirmationOut | None:
    get_or_404(session, Job, job_id, "Job")
    row = confirmation.latest(session, job_id)
    return _out(session, row) if row else None


@router.post("/jobs/{job_id}/confirm", response_model=ConfirmationOut)
def ask(job_id: int, session: SessionDep, workspace: WorkspaceDep) -> ConfirmationOut:
    """Ask Claude (your subscription), falling back to Gemma, then to the copy-paste flow."""
    get_or_404(session, Job, job_id, "Job")
    engine = engine_for(workspace)
    steps = registry.confirmers(mock=_is_mock(workspace), engine=engine,
                                claude_model=_claude_model(session))
    try:
        row = confirmation.ask(engine, job_id, steps)  # type: ignore[arg-type]
    except confirmation.ConfirmationBusy as exc:
        raise HTTPException(409, "Already asking about this job. Give it a moment.") from exc
    except confirmation.ConfirmationUnavailable as exc:
        raise HTTPException(
            503, f"Neither Claude nor the Gemma fallback answered ({exc}). You can copy the "
                 "prompt into the Gemini Pro app and paste the answer back.") from exc
    session.expire_all()
    return _out(session, row)


@router.get("/jobs/{job_id}/confirmation/prompt", response_model=ConfirmationPrompt)
def manual_prompt(job_id: int, session: SessionDep, workspace: WorkspaceDep) -> ConfirmationPrompt:
    get_or_404(session, Job, job_id, "Job")
    return ConfirmationPrompt(prompt=confirmation.manual_prompt(engine_for(workspace), job_id))


@router.post("/jobs/{job_id}/confirmation/paste", response_model=ConfirmationOut)
def paste(job_id: int, body: PasteIn, session: SessionDep,
          workspace: WorkspaceDep) -> ConfirmationOut:
    get_or_404(session, Job, job_id, "Job")
    try:
        row = confirmation.store_manual(engine_for(workspace), job_id, body.text)
    except confirmation.ConfirmationInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return _out(session, row)
