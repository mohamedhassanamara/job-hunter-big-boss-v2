from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.services import usage

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageBatch(BaseModel):
    events: list[dict[str, Any]]


@router.post("/events")
def post_events(body: UsageBatch, session: SessionDep) -> dict[str, Any]:
    return usage.record(session, body.events)


@router.get("/report")
def get_report(session: SessionDep, last: int = 1) -> dict[str, Any]:
    """The latest session(s) with the log's own state (a Settings card reads this)."""
    found = usage.reports(session, last=max(1, min(last, 20)))
    return {"enabled": usage.settings(session)["enabled"], "sessions": found}


@router.delete("")
def clear_log(session: SessionDep) -> dict[str, int]:
    return {"deleted": usage.clear(session)}
