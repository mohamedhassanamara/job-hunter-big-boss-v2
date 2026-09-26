from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SourceRunOut(BaseModel):
    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    new_count: int
    duplicate_count: int
    error: str | None


class SearchProfileIO(BaseModel):
    name: str
    roles: list[str]
    keywords: list[str]
    excluded_keywords: list[str]
    locations: list[str]
    remote_policy: str
    min_fit_score: int


class SettingsOut(BaseModel):
    values: dict[str, dict[str, Any]]
    smtp_password_configured: bool
    database_path: str
    last_runs: list[SourceRunOut]


class SettingValue(BaseModel):
    value: dict[str, Any]


class DiscoveryResult(BaseModel):
    runs: list[SourceRunOut]
    new_jobs: int
