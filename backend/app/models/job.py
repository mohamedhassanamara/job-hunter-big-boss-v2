from datetime import datetime
from typing import Any

from sqlalchemy import Text, UniqueConstraint
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
