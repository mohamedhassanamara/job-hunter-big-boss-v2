"""Local usage log: which screen, which key action, how long you waited. No page content."""

from datetime import datetime

from sqlmodel import Field

from app.models.base import TableBase, dt_field, utcnow


class UsageEvent(TableBase, table=True):
    """One row per screen visit, key action, slow wait or idle gap. Only route patterns, action
    names, a job id and durations are stored: never text from a page, a draft or a CV."""

    __tablename__ = "usage_event"

    at: datetime = dt_field(default_factory=utcnow, index=True)
    kind: str = Field(max_length=16)  # screen | action | wait | idle
    name: str = Field(max_length=100)
    screen: str | None = Field(default=None, max_length=100)
    job_id: int | None = None
    duration_ms: int | None = None  # screen: time you were active; wait/idle: its length
    wall_ms: int | None = None  # screen: enter to leave, idle included
