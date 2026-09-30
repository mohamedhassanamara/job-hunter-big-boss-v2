from typing import Any

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import TableBase, json_field


class CopilotThread(TableBase, table=True):
    """A Copilot conversation: one per job (application_id set), or global (None)."""

    __tablename__ = "copilot_thread"

    application_id: int | None = Field(default=None, foreign_key="application.id", index=True)
    title: str = ""
    archived: bool = False  # "Clear" on a job starts a new thread; the old one is kept


class CopilotMessage(TableBase, table=True):
    __tablename__ = "copilot_message"

    thread_id: int = Field(foreign_key="copilot_thread.id", index=True)
    role: str  # user | assistant
    content: str = Field(default="", sa_type=Text)
    model: str | None = None
    # Numbers/tools in the answer that are neither in your experience nor the listing.
    warnings: list[dict[str, Any]] = json_field()
    duration_ms: int | None = None
    error: str | None = Field(default=None, sa_type=Text)
