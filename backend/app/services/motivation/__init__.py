"""Motivation (Phase 11): streak, chests, tokens and shop, and the Motiv Center.

Ground rules: a separate module that never changes or blocks an existing flow. It only reads
application data (activity.py) and only writes its own tables (models/motivation.py). One
setting (`motivation.enabled`) hides all of it.
"""

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, select

from app.models import AppSetting
from app.models.base import utcnow

DEFAULT_MOTIVATION: dict[str, Any] = {
    "enabled": True,
    "daily_goal": 5,  # applications per workday
    "count_emails": False,  # also count sent cold emails
    "count_linkedin": False,  # also count sent LinkedIn requests
    "chest_goal": 30,
    "timezone": "Africa/Tunis",
    "max_upload_mb": 100,
    "chests_since": None,  # set once (the day the feature started): chests count from then
}


def settings(s: Session) -> dict[str, Any]:
    """The motivation settings, with defaults. The first read stamps `chests_since` (today, in
    your timezone), so chests count applications from the day the feature started."""
    row = s.exec(select(AppSetting).where(AppSetting.key == "motivation")).first()
    value = {**DEFAULT_MOTIVATION, **(dict(row.value) if row else {})}
    if not value.get("chests_since"):
        value["chests_since"] = today(value).isoformat()
        if row is None:
            row = AppSetting(key="motivation", value=value)
        else:
            row.value = value
        s.add(row)
        s.commit()
    return value


def zone(cfg: dict[str, Any]) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.get("timezone") or "Africa/Tunis")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Africa/Tunis")


def local_day(at: datetime, cfg: dict[str, Any]) -> date:
    """The day something happened, in your timezone (naive datetimes are UTC, as stored)."""
    aware = at if at.tzinfo else at.replace(tzinfo=UTC)
    return aware.astimezone(zone(cfg)).date()


def today(cfg: dict[str, Any], now: datetime | None = None) -> date:
    return local_day(now or utcnow(), cfg)
