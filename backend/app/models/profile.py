from datetime import datetime
from typing import Any

from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field, utcnow
from app.models.enums import RemotePolicy, RemoteScope, RunStatus, RunTrigger, Source


class SearchProfile(TableBase, table=True):
    __tablename__ = "search_profile"

    name: str
    roles: list[str] = json_field()  # all role titles, derived from `tracks` on save
    # [{name, years_experience, roles: [{title, variants: {lang: [..]}}]}]
    tracks: list[dict[str, Any]] = json_field()
    keywords: list[str] = json_field()
    excluded_keywords: list[str] = json_field()
    locations: list[str] = json_field()
    remote_policy: RemotePolicy = enum_field(RemotePolicy.remote_ok)
    remote_scope: RemoteScope = enum_field(RemoteScope.anywhere)
    min_fit_score: int = 65
    max_age_days: int = 30
    is_active: bool = True


class DiscoveryRun(TableBase, table=True):
    """One press of "Run discovery" (or one scheduled run), grouping a SourceRun per source."""

    __tablename__ = "discovery_run"

    trigger: RunTrigger = enum_field(RunTrigger.manual)
    status: RunStatus = enum_field(RunStatus.running)
    started_at: datetime = dt_field(default_factory=utcnow)
    finished_at: datetime | None = dt_field()
    totals: dict[str, Any] = json_field(dict)


class SourceRun(TableBase, table=True):
    __tablename__ = "source_run"

    discovery_run_id: int | None = Field(default=None, foreign_key="discovery_run.id", index=True)
    source: Source = enum_field()
    profile_id: int | None = Field(default=None, foreign_key="search_profile.id")
    started_at: datetime = dt_field(default_factory=utcnow)
    finished_at: datetime | None = dt_field()
    status: RunStatus = enum_field(RunStatus.running)
    fetched_count: int = 0
    kept_count: int = 0
    filtered_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    error: str | None = None
    # Filter reasons {code: n}, filtered samples, request count, warnings — for tuning.
    details: dict[str, Any] = json_field(dict)
