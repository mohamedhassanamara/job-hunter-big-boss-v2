"""Motivation (Phase 11): opened chests, the token ledger, the shop, WOOPs, wins and goal tiles.

A separate module: it only reads application data (services/motivation/activity.py) and only
writes these tables. The streak is never stored: it's computed from the history every time.
"""

from datetime import datetime

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import TableBase, dt_field, utcnow


class ChestOpen(TableBase, table=True):
    """A chest you opened. Never deleted, even if an application is undone."""

    __tablename__ = "chest_open"

    opened_at: datetime = dt_field(default_factory=utcnow)
    tokens: int  # 1-10, drawn on the server
    cost: int  # the chest goal when it was opened (applications it used up)
    ordinal: int  # 1st, 2nd… chest


class TokenEntry(TableBase, table=True):
    """The token ledger: the balance is the sum of `amount`. Generic, so tokens can get other
    uses later (kind + ref_id say where an entry comes from)."""

    __tablename__ = "token_entry"

    at: datetime = dt_field(default_factory=utcnow)
    amount: int  # + earned, - spent
    kind: str = Field(sa_type=Text)  # chest | purchase | refund | adjust
    ref_id: int | None = None
    note: str = Field(default="", sa_type=Text)


class ShopItem(TableBase, table=True):
    __tablename__ = "shop_item"

    name: str
    price: int
    emoji: str | None = None
    image_name: str | None = None  # a file under data/motivation/<workspace>/
    archived: bool = False
    position: int = 0


class Purchase(TableBase, table=True):
    __tablename__ = "purchase"

    item_id: int | None = Field(default=None, foreign_key="shop_item.id")
    name: str  # as it was when bought
    price: int
    emoji: str | None = None
    bought_at: datetime = dt_field(default_factory=utcnow)
    redeemed_at: datetime | None = dt_field()


class Woop(TableBase, table=True):
    __tablename__ = "woop"

    wish: str = Field(default="", sa_type=Text)
    outcome: str = Field(default="", sa_type=Text)
    obstacle: str = Field(default="", sa_type=Text)
    plan: str = Field(default="", sa_type=Text)


class WinEntry(TableBase, table=True):
    __tablename__ = "win_entry"

    text: str = Field(sa_type=Text)


class GoalTile(TableBase, table=True):
    """One of your images or videos (My goals), stored under data/motivation/<workspace>/."""

    __tablename__ = "goal_tile"

    kind: str  # image | video
    file_name: str  # uuid + extension
    original_name: str = ""
    mime: str
    size: int
    caption: str = Field(default="", sa_type=Text)
    position: int = 0
