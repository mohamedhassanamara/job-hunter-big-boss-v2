"""Contact providers (Phase 12): which company was queried at which provider and when (the cache),
what each key has used this month, which keys are disabled, and a log of every paid call."""

from datetime import datetime
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import TableBase, dt_field, json_field, utcnow


class CompanyProviderRun(TableBase, table=True):
    __tablename__ = "company_provider_run"

    company_id: int = Field(foreign_key="company.id", index=True)
    provider: str = Field(index=True)  # hunter | prospeo | apollo | apify
    key_label: str | None = None
    queried_at: datetime = dt_field(default_factory=utcnow)
    status: str = "ok"  # ok | empty | error
    credits: float = 0
    cost_usd: float = 0
    # The people the search listed (name, title, provider id, email if revealed): reused instead
    # of searching again.
    candidates: list[dict[str, Any]] = json_field(list)
    note: str | None = None


class ProviderKeyState(TableBase, table=True):
    """A key (by label) the app stopped using: refused by the provider, or out of credits."""

    __tablename__ = "provider_key_state"
    __table_args__ = (UniqueConstraint("provider", "key_label"),)

    provider: str
    key_label: str
    disabled_at: datetime | None = dt_field()
    disabled_reason: str | None = None
    monthly_limit: float | None = None  # credits (Apify: dollars) from the provider's account


class ProviderUsage(TableBase, table=True):
    __tablename__ = "provider_usage"
    __table_args__ = (UniqueConstraint("provider", "key_label", "period"),)

    provider: str
    key_label: str
    period: str  # YYYY-MM (UTC): a new month starts from zero
    credits: float = 0
    cost_usd: float = 0
    calls: int = 0


class ProviderCall(TableBase, table=True):
    __tablename__ = "provider_call"

    provider: str = Field(index=True)
    key_label: str | None = None
    endpoint: str
    company_id: int | None = Field(default=None, index=True)
    credits: float = 0
    cost_usd: float = 0
    ok: bool = True
    result: str = ""
