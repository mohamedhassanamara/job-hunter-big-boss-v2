"""Credits per key and Apify spend, tracked locally with monthly resets (Phase 12).

A key is only ever used when `used + cost <= limit`, so a key can never be pushed past its credits.
Limits come from the provider's own account endpoint when it has one (Hunter, Prospeo, Apify:
`sync`), otherwise from Settings → Contacts (Apollo has no balance endpoint on free plans).
A key the provider refuses (auth error, suspended) is disabled and never tried again until you
re-enable it; a key the provider says is out of credits is parked until the next month.
Keys are only ever referred to by label ("prospeo#2"), never stored or logged.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.config import get_settings
from app.models import AppSetting, ProviderCall, ProviderKeyState, ProviderUsage
from app.models.base import utcnow
from app.providers.contact_finders import Cost

PROVIDERS = ("hunter", "prospeo", "apollo", "apify")
UNITS = {"hunter": "credits", "prospeo": "credits", "apollo": "credits", "apify": "usd"}
DEFAULTS: dict[str, Any] = {
    "max_age_days": 90,  # a company looked up less than this long ago isn't queried again
    "max_reveals": 2,  # emails revealed (paid) per provider per click
    "limits": {"hunter": 50, "prospeo": 100, "apollo": 50, "apify": 5.0},
}


def settings(s: Session) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == "providers")).first()
    value = row.value if row else {}
    return {**DEFAULTS, **value, "limits": {**DEFAULTS["limits"], **(value.get("limits") or {})}}


def period(now: datetime | None = None) -> str:
    return (now or utcnow()).strftime("%Y-%m")


def keys_for(provider: str) -> list[tuple[str, str]]:
    """[(label, key)] in the order of .env."""
    cfg = get_settings()
    raw = {"hunter": cfg.hunter_api_keys or cfg.hunter_api_key, "prospeo": cfg.prospeo_api_keys,
           "apollo": cfg.apollo_api_keys, "apify": cfg.apify_token}[provider]
    return [(f"{provider}#{i}", k.strip()) for i, k in enumerate(raw.split(","), 1) if k.strip()]


def _state(s: Session, provider: str, label: str) -> ProviderKeyState:
    st = s.exec(select(ProviderKeyState).where(ProviderKeyState.provider == provider,
                                               ProviderKeyState.key_label == label)).first()
    if st is None:
        st = ProviderKeyState(provider=provider, key_label=label)
        s.add(st)
        s.flush()
    return st


def _usage(s: Session, provider: str, label: str, now: datetime | None = None) -> ProviderUsage:
    p = period(now)
    u = s.exec(select(ProviderUsage).where(ProviderUsage.provider == provider,
                                           ProviderUsage.key_label == label,
                                           ProviderUsage.period == p)).first()
    if u is None:
        u = ProviderUsage(provider=provider, key_label=label, period=p)
        s.add(u)
        s.flush()
    return u


def limit_of(s: Session, provider: str, label: str) -> float:
    st = _state(s, provider, label)
    return st.monthly_limit if st.monthly_limit is not None else float(
        settings(s)["limits"][provider])


def used_of(u: ProviderUsage, provider: str) -> float:
    return u.cost_usd if UNITS[provider] == "usd" else u.credits


def remaining(s: Session, provider: str, label: str, now: datetime | None = None) -> float:
    return max(0.0, limit_of(s, provider, label) - used_of(_usage(s, provider, label, now),
                                                          provider))


def usable(s: Session, provider: str, label: str, need: float, now: datetime | None = None) -> bool:
    st = _state(s, provider, label)
    return st.disabled_at is None and remaining(s, provider, label, now) + 1e-9 >= need


def next_key(s: Session, provider: str, need: float, skip: set[str] | None = None,
             now: datetime | None = None,
             keys: list[tuple[str, str]] | None = None) -> tuple[str, str] | None:
    """The first key of the provider (in .env order) that is enabled and has `need` left."""
    for label, key in keys if keys is not None else keys_for(provider):
        if label not in (skip or set()) and usable(s, provider, label, need, now):
            return label, key
    return None


def record(s: Session, provider: str, label: str | None, endpoint: str, cost: Cost, *,
           ok: bool = True, result: str = "", company_id: int | None = None,
           now: datetime | None = None) -> None:
    """Count the spend on the key's month and log the call."""
    if label:
        u = _usage(s, provider, label, now)
        u.credits += cost.credits
        u.cost_usd += cost.usd
        u.calls += 1
        s.add(u)
    s.add(ProviderCall(provider=provider, key_label=label, endpoint=endpoint,
                       company_id=company_id, credits=cost.credits, cost_usd=cost.usd, ok=ok,
                       result=result[:200]))
    s.flush()


def disable(s: Session, provider: str, label: str, reason: str) -> None:
    st = _state(s, provider, label)
    st.disabled_at, st.disabled_reason = utcnow(), reason[:200]
    s.add(st)
    s.flush()


def enable(s: Session, provider: str, label: str) -> None:
    st = _state(s, provider, label)
    st.disabled_at = st.disabled_reason = None
    s.add(st)


def exhaust(s: Session, provider: str, label: str, now: datetime | None = None) -> None:
    """The provider says the key is out of credits: park it until the month resets."""
    u = _usage(s, provider, label, now)
    limit = limit_of(s, provider, label)
    if UNITS[provider] == "usd":
        u.cost_usd = max(u.cost_usd, limit)
    else:
        u.credits = max(u.credits, limit)
    s.add(u)


@dataclass
class KeyStatus:
    provider: str
    label: str
    unit: str
    used: float
    limit: float
    remaining: float
    calls: int
    disabled: bool
    disabled_reason: str | None


def status(s: Session, now: datetime | None = None) -> list[KeyStatus]:
    rows: list[KeyStatus] = []
    for provider in PROVIDERS:
        for label, _ in keys_for(provider):
            st, u = _state(s, provider, label), _usage(s, provider, label, now)
            used, limit = used_of(u, provider), limit_of(s, provider, label)
            rows.append(KeyStatus(provider, label, UNITS[provider], round(used, 4), limit,
                                  round(max(0.0, limit - used), 4), u.calls,
                                  st.disabled_at is not None, st.disabled_reason))
    return rows


def apply_remote(s: Session, provider: str, label: str, *, limit: float, used: float,
                 now: datetime | None = None) -> None:
    """Take the provider's own numbers (free account endpoints): they win over local counts."""
    st, u = _state(s, provider, label), _usage(s, provider, label, now)
    st.monthly_limit = limit
    if UNITS[provider] == "usd":
        u.cost_usd = used
    else:
        u.credits = used
    s.add(st)
    s.add(u)


def sync_remote(s: Session) -> list[str]:
    """Read the real limits and usage from Hunter, Prospeo and Apify (their free account
    endpoints, no credit). Best effort: a failure is returned as a warning and the local counts
    stay. Apollo has no such endpoint on free plans."""
    from app.providers.contact_finders import FinderError, KeyRefused, accounts

    warnings: list[str] = []
    for provider, fn in (("hunter", accounts.hunter), ("prospeo", accounts.prospeo),
                         ("apify", accounts.apify)):
        for label, key in keys_for(provider):
            try:
                limit, used = fn(key)
            except KeyRefused as exc:
                disable(s, provider, label, f"refused by {provider}: {exc}")
                warnings.append(f"{label} was refused by {provider} and is disabled")
                continue
            except FinderError as exc:
                warnings.append(f"{label}: could not read the balance ({exc})"[:200])
                continue
            apply_remote(s, provider, label, limit=limit, used=used)
    s.flush()
    return warnings
