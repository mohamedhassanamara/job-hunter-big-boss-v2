from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class SourceRunOut(BaseModel):
    id: int
    discovery_run_id: int | None
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    kept_count: int
    filtered_count: int
    new_count: int
    updated_count: int
    duplicate_count: int
    error: str | None
    details: dict[str, Any]


class RoleIO(BaseModel):
    title: str
    # {lang: [titles]}; omit (null) to get suggestions filled in on save.
    variants: dict[str, list[str]] | None = None


class TrackIO(BaseModel):
    name: str
    years_experience: float | None = None
    # Honesty (services/honesty.py): professional experience, or projects only (then the years
    # wording is never attached to this track) and how it was gained.
    experience: Literal["professional", "projects"] = "professional"
    experience_note: str = ""
    roles: list[RoleIO] = []


class SearchProfileIO(BaseModel):
    name: str
    roles: list[str] = []  # derived from tracks on save (read-only for clients)
    tracks: list[TrackIO] = []
    keywords: list[str]
    excluded_keywords: list[str]
    locations: list[str]
    remote_policy: str
    remote_scope: str = "anywhere"
    min_fit_score: int
    max_age_days: int = 30


class CountryOut(BaseModel):
    code: str
    name: str
    region: str


class SettingsOut(BaseModel):
    values: dict[str, dict[str, Any]]
    smtp_password_configured: bool
    database_path: str
    last_runs: list[SourceRunOut]
    next_run_at: datetime | None = None


class SettingValue(BaseModel):
    value: dict[str, Any]


class DiscoveryRunOut(BaseModel):
    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    totals: dict[str, int]
    sources: list[SourceRunOut]


class DiscoveryStatus(BaseModel):
    running: bool
    run: DiscoveryRunOut | None


class DiscoveryStarted(BaseModel):
    run_id: int


class SourceInfo(BaseModel):
    source: str
    name: str
    enabled: bool
    configured: bool
    config_hint: str | None
    cooldown_hours: float
    cooldown_remaining_minutes: int | None
    last_run: SourceRunOut | None
    # Target countries (from the search profile) this source cannot search.
    unsupported_countries: list[str] = []


class SampleJob(BaseModel):
    title: str
    company: str
    location: str
    remote_type: str
    url: str
    reason: str | None = None


class SourceTestResult(BaseModel):
    source: str
    fetched: int
    kept: int
    filtered: int
    requests: int
    reasons: dict[str, int]
    warnings: list[str]
    kept_samples: list[SampleJob]
    filtered_samples: list[SampleJob]
