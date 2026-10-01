from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.get_contact import ToGetQueue
from app.schemas.jobs import JobListItem, PipelineCard
from app.schemas.settings import SourceRunOut
from app.schemas.tracking import ReminderOut


class CVReviewItem(BaseModel):
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    version: int
    created_at: datetime


class DraftReviewItem(BaseModel):
    draft_id: int
    job_id: int
    job_title: str
    company_name: str
    contact_name: str | None
    created_at: datetime


class QueueSummary(BaseModel):
    status: str
    next_send_at: datetime | None
    pending: int
    sent: int
    interval_minutes: int


class UpcomingInterview(BaseModel):
    interview_id: int
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    round: int
    type: str
    scheduled_at: datetime


class StatsSummary(BaseModel):
    applied_this_week: int
    applied_total: int
    responded: int
    response_rate: float | None


class TodayOut(BaseModel):
    new_high_fit: list[JobListItem]
    new_high_fit_total: int
    cvs_to_review: list[CVReviewItem]
    drafts_to_approve: list[DraftReviewItem]
    emails_to_queue: list[DraftReviewItem] = []  # approved, not yet in the send queue
    ready_to_apply: list[PipelineCard]
    # Applied on the website, nobody emailed yet: find someone there too (both routes).
    also_email: list[PipelineCard] = []
    # The Get contact step: jobs past New that need a contact or a verification (top 5).
    contacts_to_get: ToGetQueue | None = None
    # LinkedIn: searches not opened today, imports to decide on, requests to send, follow-ups.
    linkedin: dict[str, Any] | None = None
    reminders: list[ReminderOut]
    upcoming_interviews: list[UpcomingInterview]  # next 14 days, pending
    stats_summary: StatsSummary
    queue: QueueSummary
    last_runs: list[SourceRunOut]
    min_fit_score: int


class NavCounts(BaseModel):
    discover_new: int
    pipeline_active: int
    outreach_review: int
    queue_pending: int
    ready_to_apply: int
    contacts_to_get: int = 0


class SearchHit(BaseModel):
    kind: str  # job | company | contact
    id: int
    title: str
    subtitle: str
    href: str


class SearchOut(BaseModel):
    hits: list[SearchHit]
