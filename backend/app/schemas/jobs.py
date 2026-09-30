from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.tracking import TrackedItem


class CompanyRef(BaseModel):
    id: int
    name: str
    contacted_at: datetime | None = None


class FitBrief(BaseModel):
    score: int | None
    band: str  # strong | good | fair | weak | failed | pending
    status: str  # ok | failed | pending (queued / never scored)
    confidence: str  # high | medium | low
    hard_flag: bool = False
    flag_count: int = 0
    stale: bool = False
    # Provenance: which model and prompt version produced this score.
    model: str | None = None
    prompt_version: str | None = None


class FitDetail(FitBrief):
    sub_scores: dict[str, Any]
    red_flags: list[dict[str, Any]]
    strengths: list[str]
    gaps: list[str]
    summary: str
    model: str  # always set on a detail (the brief's field is optional)
    error: str | None
    duration_ms: int | None
    created_at: datetime


class TracksOut(BaseModel):
    """Both routes of a job (services/tracks.py)."""

    application: str = "not_ready"  # not_ready | ready | applied
    outreach: str = "no_contact"  # no_contact | contact | drafted | approved | queued | sent
    applied_at: datetime | None = None
    web_method: str | None = None
    contact_name: str | None = None
    draft_id: int | None = None
    sent_at: datetime | None = None


class ApplicationBrief(BaseModel):
    id: int
    stage: str
    stage_label: str
    route: str
    tracks: TracksOut = TracksOut()
    contact_tier: str
    close_reason: str | None
    stage_changed_at: datetime


class JobListItem(BaseModel):
    id: int
    description_level: str = "full"
    user_label: str | None = None
    matched_track: str | None = None  # the user's track/role this title matched
    matched_role: str | None = None
    title: str
    company: CompanyRef
    source: str
    url: str
    location: str
    country: str | None
    remote_type: str
    salary_text: str | None
    posted_at: datetime | None
    discovered_at: datetime
    fit: FitBrief | None
    application: ApplicationBrief
    duplicate_of_id: int | None
    company_contacted: bool


class JobList(BaseModel):
    items: list[JobListItem]
    total: int


class ContactOut(BaseModel):
    id: int
    company_id: int
    full_name: str
    title: str | None
    email: str | None
    linkedin_url: str | None
    source: str
    role_rank: int = 999
    role_label: str | None = None  # the Settings → Contacts group the title matched


class EventOut(BaseModel):
    id: int
    kind: str
    from_stage: str | None
    to_stage: str | None
    message: str | None
    payload: dict[str, Any]
    at: datetime


class RelatedJob(BaseModel):
    id: int
    title: str
    source: str
    url: str
    stage: str
    stage_label: str


class CVBrief(BaseModel):
    id: int
    version: int
    status: str
    page_count: int | None
    generator_model: str
    locked: bool = False  # sent with the application: never changes
    created_at: datetime
    updated_at: datetime


class DraftBrief(BaseModel):
    id: int
    subject: str
    body: str
    status: str
    edited: bool
    contact_name: str | None
    created_at: datetime
    updated_at: datetime


class JobDetail(JobListItem):
    description: str
    fit_detail: FitDetail | None
    notes: str
    company_reason: str = ""
    contact: ContactOut | None
    company_contacts: int
    other_jobs_at_company: list[RelatedJob]
    duplicates: list[RelatedJob]
    cv_versions: list[CVBrief]
    drafts: list[DraftBrief]
    events: list[EventOut]
    allowed_stages: list[str]
    tracking: TrackedItem | None = None  # set once applied: how, CV sent, replies, interviews
    lookup_status: str | None = None  # company Apollo lookup: queued|found|not_found|skipped


class PipelineCard(BaseModel):
    application_id: int
    job_id: int
    title: str
    company_name: str
    source: str
    location: str
    remote_type: str
    fit: FitBrief | None
    stage: str
    stage_label: str
    route: str
    tracks: TracksOut = TracksOut()
    contact_tier: str
    close_reason: str | None
    stage_changed_at: datetime
    updated_at: datetime
    allowed_stages: list[str]


class ApplicationPatch(BaseModel):
    stage: str | None = None
    close_reason: str | None = None
    route: str | None = None
    notes: str | None = None
    company_reason: str | None = None  # your one-line reason for this company
