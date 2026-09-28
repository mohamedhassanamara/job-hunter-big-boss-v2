from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.jobs import FitBrief


class DraftContact(BaseModel):
    id: int
    full_name: str
    title: str | None
    email: str | None
    role_label: str | None = None


class DraftOut(BaseModel):
    id: int
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    fit: FitBrief | None
    contact: DraftContact | None
    subject: str
    body: str
    status: str
    edited: bool
    model: str
    cv_version: int | None
    created_at: datetime
    updated_at: datetime
    cv_version_id: int | None = None
    sentences: list[dict[str, Any]] = []  # [{text, citations, about_job}] as generated
    citations: dict[str, str] = {}  # pool id -> "Role at Org" (for hover)
    violations: list[dict[str, Any]] = []  # [{type, severity, message, where}]
    attempts: int = 1
    prompt_version: str | None = None
    duration_ms: int | None = None
    full_body: str = ""  # as sent: your text + signature + opt-out
    test_sent_at: datetime | None = None
    sent_at: datetime | None = None


class DraftPatch(BaseModel):
    subject: str | None = None
    body: str | None = None


class QueueItemOut(BaseModel):
    id: int
    position: int
    status: str
    scheduled_at: datetime | None
    sent_at: datetime | None
    error: str | None
    attempts: int = 0
    draft_id: int
    job_id: int
    subject: str
    contact_name: str | None
    contact_email: str | None
    company_name: str


class QueueCounts(BaseModel):
    pending: int
    sent: int
    failed: int
    unknown: int = 0


class QueueOut(BaseModel):
    status: str
    interval_minutes: int
    max_items: int
    next_send_at: datetime | None
    counts: QueueCounts
    items: list[QueueItemOut]
    test_sent: bool = False  # a test email reached your inbox (required before starting)
    own_address: str = ""


class SendLogOut(BaseModel):
    id: int
    draft_id: int | None
    kind: str
    to: str
    subject: str
    status: str
    error: str | None
    message_id: str | None
    attachment: str | None
    at: datetime
