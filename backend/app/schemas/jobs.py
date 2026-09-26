from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CompanyRef(BaseModel):
    id: int
    name: str
    contacted_at: datetime | None = None


class FitBrief(BaseModel):
    score: int
    band: str  # strong | good | fair | weak


class FitDetail(FitBrief):
    strengths: list[str]
    gaps: list[str]
    summary: str
    model: str
    created_at: datetime


class ApplicationBrief(BaseModel):
    id: int
    stage: str
    stage_label: str
    route: str
    contact_tier: str
    close_reason: str | None
    stage_changed_at: datetime


class JobListItem(BaseModel):
    id: int
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
    contact: ContactOut | None
    company_contacts: int
    other_jobs_at_company: list[RelatedJob]
    duplicates: list[RelatedJob]
    cv_versions: list[CVBrief]
    drafts: list[DraftBrief]
    events: list[EventOut]
    allowed_stages: list[str]


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
