"""Background drafting status (services/generation.py): a light poll for the job cards."""

from typing import Any

from fastapi import APIRouter
from sqlmodel import func, select

from app.api.deps import SessionDep
from app.models import GenerationTask
from app.services import generation

router = APIRouter(tags=["generation"])


@router.get("/generation/status")
def status(session: SessionDep) -> dict[str, Any]:
    """Counts by status plus a `signature` that changes whenever a task finishes or fails, so the
    page refreshes its cards exactly then (no toasts)."""
    rows = dict(session.exec(select(GenerationTask.status, func.count()).group_by(
        GenerationTask.status)).all())
    last = session.exec(select(func.max(GenerationTask.updated_at))).one()
    active = sum(int(rows.get(k, 0)) for k in generation.ACTIVE)
    return {"active": active, "queued": int(rows.get("queued", 0)),
            "running": int(rows.get("running", 0)), "failed": int(rows.get("failed", 0)),
            "signature": f"{sum(rows.values())}:{rows.get('done', 0)}:{rows.get('failed', 0)}:"
                         f"{rows.get('skipped', 0)}:{last.isoformat() if last else ''}",
            "auto": generation.settings(session)}

