from datetime import datetime

from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field, utcnow
from app.models.enums import RemotePolicy, RunStatus, Source


class SearchProfile(TableBase, table=True):
    __tablename__ = "search_profile"

    name: str
    roles: list[str] = json_field()
    keywords: list[str] = json_field()
    excluded_keywords: list[str] = json_field()
    locations: list[str] = json_field()
    remote_policy: RemotePolicy = enum_field(RemotePolicy.remote_ok)
    min_fit_score: int = 65
    is_active: bool = True


class SourceRun(TableBase, table=True):
    __tablename__ = "source_run"

    source: Source = enum_field()
    profile_id: int | None = Field(default=None, foreign_key="search_profile.id")
    started_at: datetime = dt_field(default_factory=utcnow)
    finished_at: datetime | None = dt_field()
    status: RunStatus = enum_field(RunStatus.running)
    fetched_count: int = 0
    new_count: int = 0
    duplicate_count: int = 0
    error: str | None = None
