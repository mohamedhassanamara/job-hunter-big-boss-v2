"""Streak freezes: bought with tokens, owned until used, at most CAP owned at a time.

A purchase is two rows written in one commit: a negative `TokenEntry` (kind "freeze", the same
ledger as the shop, so the balance stays the sum of the ledger) and a `StreakFreeze` row that
records the price paid. A refused purchase (cap, balance, bad price) writes neither. Owned =
rows with `used_on` empty; nothing expires. `use` freezes today without moving tokens.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlmodel import Session, func, select

from app.models import StreakFreeze, TokenEntry
from app.models.base import utcnow
from app.services import motivation as mv
from app.services.motivation import activity, rewards
from app.services.motivation.rewards import RewardError

CAP = 2  # freezes you can hold at once


@dataclass
class FreezeState:
    price: int
    owned: int
    cap: int
    can_buy: bool
    reason: str | None  # why Buy is off (None when it is on)
    use: str = "available"  # available | none_owned | used_today | goal_met | weekend
    use_reason: str | None = None  # why using one is off (None when it is on)


def price(cfg: dict[str, Any]) -> int:
    """The current price: a positive integer from Settings → Motivation."""
    value = cfg.get("freeze_price")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RewardError("The freeze price must be a positive whole number of tokens")
    return value


def owned(s: Session) -> int:
    return int(s.exec(select(func.count()).select_from(StreakFreeze)
                      .where(StreakFreeze.used_on.is_(None))).one())  # type: ignore[union-attr]


def used_days(s: Session) -> set[date]:
    """The days a freeze covers (what the streak and its history are computed with)."""
    return set(s.exec(select(StreakFreeze.used_on)
                      .where(StreakFreeze.used_on.is_not(None))).all())  # type: ignore[union-attr]


def use_state(s: Session, cfg: dict[str, Any], now: datetime | None = None
              ) -> tuple[str, str | None]:
    """Whether a freeze can be used right now: (state, reason). Today only, on a workday, never
    when the goal is already met, once per day, and only with one owned."""
    day = mv.today(cfg, now)
    if day.weekday() >= 5:
        return "weekend", "Weekends carry your streak by themselves"
    if day in used_days(s):
        return "used_today", "Today is already frozen"
    count = activity.per_day(s, cfg).get(day, 0)
    if count >= max(1, int(cfg["daily_goal"])):
        return "goal_met", "Today's goal is already met"
    if owned(s) < 1:
        return "none_owned", "You have no freeze"
    return "available", None


def use(s: Session, cfg: dict[str, Any], now: datetime | None = None) -> StreakFreeze:
    """Freeze today: consumes one owned freeze (no tokens move: they were paid at purchase) and
    marks today as a completed workday. The streak and its history take it from `used_on`."""
    with rewards._lock:
        kind, reason = use_state(s, cfg, now)
        if kind != "available":
            raise RewardError(reason or "You can't use a freeze now")
        row = s.exec(select(StreakFreeze).where(StreakFreeze.used_on.is_(None))  # type: ignore[union-attr]
                     .order_by(StreakFreeze.id)).first()
        row.used_on = mv.today(cfg, now)
        s.add(row)
        try:
            s.commit()
        except Exception:
            s.rollback()
            raise
        s.refresh(row)
        return row


def state(s: Session, cfg: dict[str, Any]) -> FreezeState:
    cost, have = price(cfg), owned(s)
    balance = rewards.balance(s)
    reason = None
    if have >= CAP:
        reason = f"You already hold {CAP} freezes"
    elif balance < cost:
        reason = f"{cost - balance} more token{'s' if cost - balance != 1 else ''} needed"
    kind, why = use_state(s, cfg)
    return FreezeState(price=cost, owned=have, cap=CAP, can_buy=reason is None, reason=reason,
                       use=kind, use_reason=why)


def buy(s: Session, cfg: dict[str, Any]) -> StreakFreeze:
    with rewards._lock:  # one purchase at a time: a double click can't pass the cap or the balance
        cost = price(cfg)
        if owned(s) >= CAP:
            raise RewardError(f"You already hold {CAP} freezes: use one first")
        have = rewards.balance(s)
        if have < cost:
            raise RewardError(f"Not enough tokens: {have} of {cost}")
        try:
            entry = TokenEntry(amount=-cost, kind="freeze", note="Streak freeze")
            s.add(entry)
            s.flush()
            row = StreakFreeze(price=cost, bought_at=utcnow(), purchase_entry_id=entry.id)
            s.add(row)
            s.commit()
        except Exception:
            s.rollback()
            raise
        s.refresh(row)
        return row
