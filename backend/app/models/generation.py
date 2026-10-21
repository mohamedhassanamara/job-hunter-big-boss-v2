"""Background drafting of the CV (when a job is shortlisted) and the email (when a verified contact
and an approved CV both exist). Persistent, so a restart carries on (`services/generation.py`)."""

from datetime import datetime
from typing import Any

from sqlmodel import Field

from app.models.base import TableBase, dt_field, json_field, utcnow


class GenerationTask(TableBase, table=True):
    __tablename__ = "generation_task"

    application_id: int = Field(foreign_key="application.id", index=True)
    kind: str  # cv | email
    # queued | running | done | failed | skipped | cancelled
    status: str = Field(default="queued", index=True)
    trigger: str = "manual"  # shortlist | cv_approved | contact_ready | retry
    use: str | None = None  # "claude": this task only (the Generate with Claude button)
    model: str | None = None  # what actually wrote it
    attempts: int = 0
    error: str | None = None
    warning: str | None = None  # shown when skipped (e.g. the pool is incomplete)
    retryable: bool = True
    result_id: int | None = None  # the CV version or the draft
    details: dict[str, Any] = json_field(dict)  # calls, retries, seconds, tokens
    queued_at: datetime = dt_field(default_factory=utcnow)
    not_before: datetime | None = dt_field()  # backoff or quota reset
    started_at: datetime | None = dt_field()
    finished_at: datetime | None = dt_field()
