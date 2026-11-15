"""Streak freezes: bought with tokens, owned until used, at most CAP owned at a time.

A purchase is two rows written in one commit: a negative `TokenEntry` (kind "freeze", the same
ledger as the shop, so the balance stays the sum of the ledger) and a `StreakFreeze` row that
records the price paid. A refused purchase (cap, balance, bad price) writes neither. Owned =
rows with `used_on` empty; nothing expires. Using a freeze is a separate step (`use`, next commit).
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlmodel import Session, func, select

from app.models import StreakFreeze, TokenEntry
from app.models.base import utcnow
from app.services.motivation import rewards
from app.services.motivation.rewards import RewardError

CAP = 2  # freezes you can hold at once


@dataclass
class FreezeState:
    price: int
    owned: int
    cap: int
    can_buy: bool
    reason: str | None  # why Buy is off (None when it is on)


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


def state(s: Session, cfg: dict[str, Any]) -> FreezeState:
    cost, have = price(cfg), owned(s)
    balance = rewards.balance(s)
    reason = None
    if have >= CAP:
        reason = f"You already hold {CAP} freezes"
    elif balance < cost:
        reason = f"{cost - balance} more token{'s' if cost - balance != 1 else ''} needed"
    return FreezeState(price=cost, owned=have, cap=CAP, can_buy=reason is None, reason=reason)


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
