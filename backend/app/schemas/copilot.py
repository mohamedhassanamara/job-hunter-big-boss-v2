from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CopilotMessageOut(BaseModel):
    id: int
    role: str  # user | assistant
    content: str
    model: str | None
    warnings: list[dict[str, Any]]
    duration_ms: int | None
    error: str | None
    created_at: datetime


class CopilotThreadOut(BaseModel):
    id: int
    application_id: int | None
    job_id: int | None
    title: str
    message_count: int
    updated_at: datetime


class CopilotThreadDetail(CopilotThreadOut):
    messages: list[CopilotMessageOut]
    starters: list[str]
    model: str


class CopilotAsk(BaseModel):
    question: str


class CopilotStatus(BaseModel):
    ok: bool
    model: str
    message: str
