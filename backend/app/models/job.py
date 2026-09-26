from datetime import datetime

from sqlalchemy import Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field, utcnow
from app.models.enums import RemoteType, Source


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
    dedupe_key: str = Field(index=True)
    duplicate_of_id: int | None = Field(default=None, foreign_key="job.id")


class FitScore(TableBase, table=True):
    __tablename__ = "fit_score"

    job_id: int = Field(foreign_key="job.id", index=True)
    profile_id: int | None = Field(default=None, foreign_key="search_profile.id")
    score: int = Field(ge=0, le=100)
    strengths: list[str] = json_field()
    gaps: list[str] = json_field()
    summary: str = ""
    model: str = "mock"
