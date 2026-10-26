from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CVVersionOut(BaseModel):
    id: int
    application_id: int
    version: int
    status: str
    content: dict[str, Any]  # the rendered CVDocument
    page_count: int | None
    fill: float | None
    fit_passes: int
    template: str
    generator_model: str
    violations: list[dict[str, Any]]
    duration_ms: int | None
    error: str | None
    has_pdf: bool
    # Summary warnings that were showing when this version was approved (empty = approved clean).
    approved_summary_warnings: list[dict[str, Any]] = []
    created_at: datetime
    updated_at: datetime


class SummaryIn(BaseModel):
    feedback: str | None = None  # "What should change?" (optional)
    use: str | None = None  # "claude" | "gemini": this call only (after a failure)


class SummaryCheckIn(BaseModel):
    text: str


class SummaryRestoreIn(BaseModel):
    index: int


class ReadinessItem(BaseModel):
    key: str
    severity: str  # blocker | warning
    message: str


class TemplateOut(BaseModel):
    name: str
    description: str
    paper: str
    builtin: bool
    valid: bool
    pages: int | None
    error: str | None
    is_default: bool = False


class CVStudio(BaseModel):
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    matched_track: str | None
    stage: str
    route: str
    has_contact: bool
    versions: list[CVVersionOut]
    readiness: list[ReadinessItem]
    templates: list[TemplateOut]
    usage: dict[str, Any] | None  # pool items used vs left out, for the current version
    download_name: str | None


class CVGenerateIn(BaseModel):
    template: str | None = None
    use: str | None = None  # "claude" | "gemini": this call only (after a failure)


class CVPatch(BaseModel):
    """force_in / force_out: keys like "role:12:0", "project:7", "cert:3"; text: key → edited
    text ("summary" or a bullet key). Omit a field to keep the current value."""

    force_in: list[str] | None = None
    force_out: list[str] | None = None
    text: dict[str, str] | None = None
    # bullet keys ("role:12:0") shown with the pool original instead of the adapted wording
    revert: list[str] | None = None
    # this CV uses the pool's bullets exactly as written, no adaptation anywhere
    original_only: bool | None = None
    template: str | None = None


class CVApproveResult(BaseModel):
    version: CVVersionOut
    stage: str
    route: str
    next_step: str  # draft_email | apply


class TemplateIn(BaseModel):
    name: str
    tex: str
    config: str
