from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class AppliedIn(BaseModel):
    applied_on: date | None = None  # default today
    method: str  # company_site | job_board | email | other
    cv_version_id: int | None = None  # default: the latest approved version
    cover_letter_id: int | None = None  # the approved letter sent with it (None = no letter)
    form_letter_id: int | None = None  # the approved form text pasted into the form, if any
    notes: str = ""


class ResponseIn(BaseModel):
    kind: str  # positive | rejection | other
    received_on: date | None = None
    notes: str = ""


class InterviewIn(BaseModel):
    scheduled_at: datetime
    type: str = "hr"  # hr | technical | take_home | final | other
    notes: str = ""
    outcome: str = "pending"  # pending | passed | failed | cancelled


class InterviewPatch(BaseModel):
    scheduled_at: datetime | None = None
    type: str | None = None
    notes: str | None = None
    outcome: str | None = None


class CloseIn(BaseModel):
    reason: str
    notes: str = ""


class SnoozeIn(BaseModel):
    until: datetime | None = None
    days: int = 3


class ReadyItem(BaseModel):
    application_id: int
    job_id: int
    title: str
    company: str
    track: str | None
    country: str | None
    url: str
    cv_version_id: int
    cv_version: int
    stage: str
    # The job's cover letter: the approved one (sent along), else the draft under review.
    letter_id: int | None = None
    letter_version: int | None = None
    letter_status: str = "none"  # none | draft | approved


class ResponseOut(BaseModel):
    id: int
    kind: str
    received_at: datetime
    notes: str


class InterviewOut(BaseModel):
    id: int
    round: int
    scheduled_at: datetime
    type: str
    notes: str
    outcome: str


class TrackedItem(BaseModel):
    application_id: int
    job_id: int
    title: str
    company: str
    track: str | None
    country: str | None
    source: str
    url: str
    stage: str
    stage_label: str
    close_reason: str | None
    applied_at: datetime
    applied_method: str | None
    applied_cv_version_id: int | None
    applied_cv_version: int | None
    applied_cover_letter_id: int | None = None
    applied_cover_letter_version: int | None = None
    applied_notes: str
    responses: list[ResponseOut]
    interviews: list[InterviewOut]
    days_to_first_response: float | None


class ReminderOut(BaseModel):
    application_id: int
    job_id: int
    job_title: str
    company: str
    key: str
    kind: str  # followup | ghost
    days: int
    due_at: datetime
    applied_at: datetime


class StatsOut(BaseModel):
    applied: int
    per_week: list[dict[str, Any]]
    response: dict[str, Any]
    interview: dict[str, Any]
    median_days_to_first_response: float | None
    by_track: list[dict[str, Any]]
    by_country: list[dict[str, Any]]
    by_source: list[dict[str, Any]]
    both_routes: int = 0  # jobs where you applied on the website AND emailed someone
    by_route: list[dict[str, Any]] = []  # web / email / both
