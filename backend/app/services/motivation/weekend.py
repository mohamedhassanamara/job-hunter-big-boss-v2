"""Weekend coin: +1 token for a job marked Applied on a Saturday or Sunday.

Deliberately no other rule: contact, verification, email and the sent-only setting are all
ignored. One coin per job, ever (`weekend_coin.application_id` is unique), so Undo and a second
Mark applied never pay again. The day is the click day in your timezone (the same `local_day` the
streak uses). It changes nothing in the streak or the daily goal.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import Application, TokenEntry, WeekendCoin
from app.models.base import utcnow
from app.services import motivation as mv

log = logging.getLogger(__name__)

COIN = 1


def is_weekend(at: datetime, cfg: dict[str, Any]) -> bool:
    return mv.local_day(at, cfg).weekday() >= 5


def award(s: Session, app: Application, at: datetime | None = None) -> bool:
    """Award the coin when `at` (default: now) is a weekend day and this job never earned one.
    Returns whether a coin was added. Never raises: it must not fail a Mark applied."""
    try:
        when = at or utcnow()
        cfg = mv.settings(s)
        if not cfg.get("enabled", True) or not is_weekend(when, cfg):
            return False
        if s.exec(select(WeekendCoin.id).where(WeekendCoin.application_id == app.id)).first():
            return False
        day = mv.local_day(when, cfg)
        with s.begin_nested():
            entry = TokenEntry(amount=COIN, kind="weekend", ref_id=app.id,
                               note=f"Weekend application ({day.isoformat()})")
            s.add(entry)
            s.flush()
            s.add(WeekendCoin(application_id=app.id, day=day, awarded_at=when,
                              token_entry_id=entry.id))
            s.flush()
        return True
    except IntegrityError:
        return False
    except Exception:  # noqa: BLE001
        log.exception("weekend coin failed for application %s", app.id)
        return False
