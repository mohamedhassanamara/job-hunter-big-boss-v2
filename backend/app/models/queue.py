from datetime import datetime

from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, utcnow
from app.models.enums import QueueItemStatus, QueueStatus


class SendQueue(TableBase, table=True):
    __tablename__ = "send_queue"

    status: QueueStatus = enum_field(QueueStatus.idle)
    interval_minutes: int = 15
    max_items: int = 20
    next_send_at: datetime | None = dt_field()
    # Why it is paused: "manual" (you pressed Pause) or "fatal" (a send failed for good). An
    # idle queue restarts itself when an email is added; a paused one never does.
    paused_reason: str | None = None


class QueueEvent(TableBase, table=True):
    """Every queue state change (idle, running, paused), so restarts and stalls can be counted."""

    __tablename__ = "queue_event"

    at: datetime = dt_field(default_factory=utcnow, index=True)
    from_status: str
    to_status: str
    reason: str | None = None  # manual | fatal | empty | resume | added
    actor: str  # user | worker | auto_on_add


class SendQueueItem(TableBase, table=True):
    __tablename__ = "send_queue_item"

    queue_id: int = Field(foreign_key="send_queue.id", index=True)
    draft_id: int = Field(foreign_key="outreach_draft.id", unique=True)
    position: int = 0
    scheduled_at: datetime | None = dt_field()
    sent_at: datetime | None = dt_field()
    status: QueueItemStatus = enum_field(QueueItemStatus.pending)
    error: str | None = None
    attempts: int = 0
    last_attempt_at: datetime | None = dt_field()
    message_id: str | None = None


class SendLog(TableBase, table=True):
    """Every send attempt, test or real, success or failure. Never deleted."""

    __tablename__ = "send_log"

    draft_id: int | None = Field(default=None, foreign_key="outreach_draft.id", index=True)
    kind: str  # test | real
    to: str
    subject: str
    status: str  # sent | failed
    error: str | None = None
    message_id: str | None = None
    attachment: str | None = None
    at: datetime = dt_field(default_factory=utcnow)
