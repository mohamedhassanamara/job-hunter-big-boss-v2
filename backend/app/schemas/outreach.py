from datetime import datetime

from pydantic import BaseModel

from app.schemas.jobs import FitBrief


class DraftContact(BaseModel):
    id: int
    full_name: str
    title: str | None
    email: str | None


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


class QueueOut(BaseModel):
    status: str
    interval_minutes: int
    max_items: int
    next_send_at: datetime | None
    counts: QueueCounts
    items: list[QueueItemOut]
