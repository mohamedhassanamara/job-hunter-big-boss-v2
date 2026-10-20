from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field, utcnow
from app.models.enums import DescriptionLevel, FitStatus, RemoteType, Source, UserLabel


class Job(TableBase, table=True):
    __tablename__ = "job"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_job_source_external"),)

    source: Source = enum_field()
    external_id: str
    source_run_id: int | None = Field(default=None, foreign_key="source_run.id")
    url: str
    # Where the listing says to apply, when it isn't the listing page itself (ATS boards, JSON-LD).
    apply_url: str | None = None
    title: str
    company_id: int = Field(foreign_key="company.id", index=True)
    location: str = ""
    country: str | None = None
    remote_type: RemoteType = enum_field(RemoteType.unknown)
    description: str = Field(default="", sa_type=Text)
    salary_text: str | None = None
    posted_at: datetime | None = dt_field()
    discovered_at: datetime = dt_field(default_factory=utcnow)
    last_seen_at: datetime | None = dt_field()
    dedupe_key: str = Field(index=True)
    duplicate_of_id: int | None = Field(default=None, foreign_key="job.id")
    # How much of the listing we have: drives scoring confidence.
    description_level: DescriptionLevel = enum_field(DescriptionLevel.full)
    full_fetched_at: datetime | None = dt_field()
    # The user's manual judgment (for evaluating the scorer), separate from the pipeline stage.
    user_label: UserLabel | None = enum_field(None)
    labeled_at: datetime | None = dt_field()
    # Which of the user's tracks/roles (Settings → Search profile) the title matched.
    matched_track: str | None = Field(default=None, index=True)
    matched_role: str | None = None
    # Imported with the LinkedIn bookmark: the job id and how each field was captured
    # ({field: "json-ld" | "page" | "meta" | "url" | "you" | "missing"}).
    linkedin_job_id: str | None = Field(default=None, index=True)
    capture: dict[str, Any] | None = Field(default=None, sa_type=JSON)


class FitScore(TableBase, table=True):
    """One scoring attempt. The latest row per job is authoritative; history is kept."""

    __tablename__ = "fit_score"

    job_id: int = Field(foreign_key="job.id", index=True)
    profile_id: int | None = Field(default=None, foreign_key="search_profile.id")
    status: FitStatus = enum_field(FitStatus.ok)
    error: str | None = None
    # Computed in code from sub_scores + weights (never produced by the LLM). Null when failed.
    score: int | None = Field(default=None, ge=0, le=100)
    sub_scores: dict[str, Any] = json_field(dict)
    red_flags: list[dict[str, Any]] = json_field()
    # Prompt v5: [{requirement, evidence, evidence_verified, missing, counts, note?}]; `counts` caps
    core_requirements: list[dict[str, Any]] = json_field()
    strengths: list[str] = json_field()
    gaps: list[str] = json_field()
    summary: str = ""
    confidence: str = "medium"
    model: str = "mock"
    prompt_version: str | None = None
    content_hash: str | None = None
    experience_version: str | None = None
    cache_key: str | None = Field(default=None, index=True)
    duration_ms: int | None = None


class FitConfirmation(TableBase, table=True):
    """A second opinion on one job (Ask Claude, the Gemma fallback, or a pasted Gemini Pro
    answer). Stored next to the main score, never in place of it; the newest row is shown."""

    __tablename__ = "fit_confirmation"

    job_id: int = Field(foreign_key="job.id", index=True)
    source: str  # claude | gemma | manual | mock
    model: str
    via: str = ""  # claude -p | gemini api | paste
    prompt_version: str | None = None  # the scoring prompt it used
    confirm_prompt_version: str | None = None  # the verdict addendum
    experience_version: str | None = None
    # Same arithmetic as the main score (fit.build_record), same caps.
    score: int | None = Field(default=None, ge=0, le=100)
    sub_scores: dict[str, Any] = json_field(dict)
    red_flags: list[dict[str, Any]] = json_field()
    core_requirements: list[dict[str, Any]] = json_field()
    strengths: list[str] = json_field()
    gaps: list[str] = json_field()
    summary: str = ""
    confidence: str = "medium"
    # {advice: apply|maybe|skip, why, seniority, skills, location_visa, language}
    verdict: dict[str, Any] = json_field(dict)
    notes: str = ""  # e.g. "Claude was unavailable (…): this answer comes from gemma-4-31b-it."
    duration_ms: int | None = None
