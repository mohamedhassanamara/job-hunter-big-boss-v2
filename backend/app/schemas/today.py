from datetime import datetime

from pydantic import BaseModel

from app.schemas.jobs import JobListItem, PipelineCard
from app.schemas.settings import SourceRunOut


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


class TodayOut(BaseModel):
    new_high_fit: list[JobListItem]
    new_high_fit_total: int
    cvs_to_review: list[CVReviewItem]
    drafts_to_approve: list[DraftReviewItem]
    ready_to_apply: list[PipelineCard]
    interviews: list[PipelineCard]
    queue: QueueSummary
    last_runs: list[SourceRunOut]
    min_fit_score: int


class NavCounts(BaseModel):
    discover_new: int
    pipeline_active: int
    outreach_review: int
    queue_pending: int


class SearchHit(BaseModel):
    kind: str  # job | company | contact
    id: int
    title: str
    subtitle: str
    href: str


class SearchOut(BaseModel):
    hits: list[SearchHit]
