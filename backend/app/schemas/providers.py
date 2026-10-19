from datetime import datetime

from pydantic import BaseModel


class KeyStatusOut(BaseModel):
    provider: str
    label: str
    unit: str  # credits | usd
    used: float
    limit: float
    remaining: float
    calls: int
    disabled: bool
    disabled_reason: str | None


class ProviderCallOut(BaseModel):
    provider: str
    key_label: str | None
    endpoint: str
    credits: float
    cost_usd: float
    ok: bool
    result: str
    created_at: datetime


class ProvidersOut(BaseModel):
    keys: list[KeyStatusOut]
    recent_calls: list[ProviderCallOut]
    max_age_days: int
    spend_usd: float  # Apify, this month
    warnings: list[str]  # disabled keys, keys out of credits
