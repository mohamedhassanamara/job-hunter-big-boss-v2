"""Chests, the token ledger and the shop.

Chests: every `chest_goal` applications (counted since `chests_since`, the same definition as
the streak) unlock a chest. Opening one draws 1-10 tokens (uniform, on the server) and uses up
`chest_goal` applications; extras carry over and several chests can wait. Opened chests and
tokens are never taken back, and each chest keeps its own cost, so changing the goal never
re-awards anything.

Tokens: a ledger (`token_entry`); the balance is the sum. The shop spends them: a purchase never
takes the balance below 0.
"""

import secrets
import threading
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlmodel import Session, col, func, select

from app.models import ChestOpen, Purchase, ShopItem, TokenEntry
from app.models.base import utcnow
from app.services.motivation import activity

_lock = threading.Lock()  # one chest / one purchase at a time (double clicks)


class RewardError(Exception):
    """Shown to the user (no chest waiting, not enough tokens…)."""


@dataclass
class Chests:
    goal: int
    progress: int  # toward the next chest (0..goal-1, or more while chests wait)
    available: int  # chests waiting to be opened
    counted: int  # applications counted since `since`
    opened: int
    since: date


def chests(s: Session, cfg: dict[str, Any]) -> Chests:
    goal = max(1, int(cfg.get("chest_goal") or 30))
    since = date.fromisoformat(cfg["chests_since"])
    counted = activity.total_since(s, cfg, since)
    used = s.exec(select(func.coalesce(func.sum(ChestOpen.cost), 0))).one()
    opened = s.exec(select(func.count()).select_from(ChestOpen)).one()
    left = max(0, counted - int(used))  # an undo never takes an opened chest back
    available = left // goal
    return Chests(goal=goal, progress=left - available * goal, available=available,
                  counted=counted, opened=int(opened), since=since)


def balance(s: Session) -> int:
    return int(s.exec(select(func.coalesce(func.sum(TokenEntry.amount), 0))).one())


def open_chest(s: Session, cfg: dict[str, Any]) -> ChestOpen:
    with _lock:
        state = chests(s, cfg)
        if state.available < 1:
            raise RewardError(f"No chest to open yet: {state.progress}/{state.goal}")
        row = ChestOpen(tokens=secrets.randbelow(10) + 1, cost=state.goal,
                        ordinal=state.opened + 1, opened_at=utcnow())
        s.add(row)
        s.flush()
        s.add(TokenEntry(amount=row.tokens, kind="chest", ref_id=row.id,
                         note=f"Chest #{row.ordinal}"))
        s.commit()
        s.refresh(row)
        return row


def history(s: Session) -> list[ChestOpen]:
    return list(s.exec(select(ChestOpen).order_by(col(ChestOpen.opened_at).desc())).all())


def ledger(s: Session, limit: int = 100) -> list[TokenEntry]:
    return list(s.exec(select(TokenEntry).order_by(col(TokenEntry.at).desc(),
                                                   col(TokenEntry.id).desc()).limit(limit)).all())


# --------------------------------------------------------------------------------- shop


def _check(name: str, price: int) -> None:
    if not name.strip():
        raise RewardError("Give the item a name")
    if not isinstance(price, int) or not 1 <= price <= 10_000:
        raise RewardError("The price must be between 1 and 10 000 tokens")


def items(s: Session, archived: bool = False) -> list[ShopItem]:
    stmt = select(ShopItem).order_by(col(ShopItem.position), col(ShopItem.id))
    if not archived:
        stmt = stmt.where(col(ShopItem.archived).is_(False))
    return list(s.exec(stmt).all())


def save_item(s: Session, item: ShopItem | None, *, name: str, price: int,
              emoji: str | None, image_name: str | None) -> ShopItem:
    _check(name, price)
    if item is None:
        last = s.exec(select(func.coalesce(func.max(ShopItem.position), 0))).one()
        item = ShopItem(name=name, price=price, position=int(last) + 1)
    item.name, item.price = name.strip(), price
    item.emoji = (emoji or "").strip()[:8] or None
    item.image_name = image_name
    s.add(item)
    s.commit()
    s.refresh(item)
    return item


def buy(s: Session, item: ShopItem) -> Purchase:
    with _lock:
        if item.archived:
            raise RewardError("This item is archived")
        have = balance(s)
        if have < item.price:
            raise RewardError(f"Not enough tokens: {have} of {item.price}")
        row = Purchase(item_id=item.id, name=item.name, price=item.price, emoji=item.emoji,
                       bought_at=utcnow())
        s.add(row)
        s.flush()
        s.add(TokenEntry(amount=-item.price, kind="purchase", ref_id=row.id, note=item.name))
        s.commit()
        s.refresh(row)
        return row


def purchases(s: Session) -> list[Purchase]:
    return list(s.exec(select(Purchase).order_by(col(Purchase.bought_at).desc())).all())


def set_redeemed(s: Session, row: Purchase, redeemed: bool) -> Purchase:
    row.redeemed_at = utcnow() if redeemed else None
    s.add(row)
    s.commit()
    s.refresh(row)
    return row
