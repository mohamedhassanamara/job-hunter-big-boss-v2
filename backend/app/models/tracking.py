"""After applying: replies, interview rounds, and reminder snoozes/dismissals. Reminders
themselves are computed (services/tracking.py), so a changed setting applies immediately."""

from datetime import datetime

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, utcnow
from app.models.enums import InterviewOutcome, InterviewType, ResponseKind


class ApplicationResponse(TableBase, table=True):
    __tablename__ = "application_response"

    application_id: int = Field(foreign_key="application.id", index=True)
    kind: ResponseKind = enum_field()
    received_at: datetime = dt_field(default_factory=utcnow)
    notes: str = Field(default="", sa_type=Text)


class Interview(TableBase, table=True):
    __tablename__ = "interview"

    application_id: int = Field(foreign_key="application.id", index=True)
    round: int = 1
    scheduled_at: datetime = dt_field(default_factory=utcnow)
    type: InterviewType = enum_field(InterviewType.hr)
    notes: str = Field(default="", sa_type=Text)
    outcome: InterviewOutcome = enum_field(InterviewOutcome.pending)


class ReminderAction(TableBase, table=True):
    """A snooze or dismissal of one computed reminder (key: followup:7, followup:14, ghost)."""

    __tablename__ = "reminder_action"

    application_id: int = Field(foreign_key="application.id", index=True)
    key: str = Field(index=True)
    snoozed_until: datetime | None = dt_field()
    dismissed_at: datetime | None = dt_field()
