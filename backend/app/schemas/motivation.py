from datetime import date, datetime

from pydantic import BaseModel


class StreakDayOut(BaseModel):
    day: date
    count: int
    state: str  # met | missed | in_progress | weekend | weekend_idle | idle | future
    streak: int


class StreakOut(BaseModel):
    current: int
    longest: int
    today_count: int
    goal: int
    today_state: str  # met | in_progress | weekend | weekend_idle
    calendar: list[StreakDayOut] = []


class ChestsOut(BaseModel):
    goal: int
    progress: int
    available: int
    counted: int
    opened: int
    since: date


class SummaryOut(BaseModel):
    enabled: bool
    streak: StreakOut
    tokens: int
    chests: ChestsOut


class ChestOpenOut(BaseModel):
    id: int
    opened_at: datetime
    tokens: int
    cost: int
    ordinal: int


class OpenedOut(BaseModel):
    chest: ChestOpenOut
    balance: int
    chests: ChestsOut


class TokenEntryOut(BaseModel):
    id: int
    at: datetime
    amount: int
    kind: str
    note: str


class TokensOut(BaseModel):
    balance: int
    ledger: list[TokenEntryOut]


class ShopItemIn(BaseModel):
    name: str
    price: int
    emoji: str | None = None
    image_name: str | None = None


class ShopItemPatch(BaseModel):
    name: str | None = None
    price: int | None = None
    emoji: str | None = None
    image_name: str | None = None
    archived: bool | None = None


class ShopItemOut(BaseModel):
    id: int
    name: str
    price: int
    emoji: str | None
    image_name: str | None
    archived: bool


class PurchaseOut(BaseModel):
    id: int
    item_id: int | None
    name: str
    price: int
    emoji: str | None
    bought_at: datetime
    redeemed_at: datetime | None


class ShopOut(BaseModel):
    balance: int
    items: list[ShopItemOut]
    purchases: list[PurchaseOut]


class RedeemIn(BaseModel):
    redeemed: bool


class WoopIn(BaseModel):
    wish: str
    outcome: str = ""
    obstacle: str = ""
    plan: str = ""


class WoopOut(WoopIn):
    id: int
    created_at: datetime


class WinIn(BaseModel):
    text: str


class WinOut(BaseModel):
    id: int
    text: str
    created_at: datetime


class WinsOut(BaseModel):
    applications_week: int
    applications_total: int
    replies: int
    positive_replies: int
    interviews: int
    longest_streak: int
    chests_opened: int
    recent_rejection: bool
    journal: list[WinOut]


class SuggestionOut(BaseModel):
    label: str
    detail: str
    href: str


class GoalTileOut(BaseModel):
    id: int
    kind: str  # image | video
    file_name: str
    original_name: str
    mime: str
    size: int
    caption: str
    position: int


class GoalTilePatch(BaseModel):
    caption: str


class OrderIn(BaseModel):
    ids: list[int]


class ImageOut(BaseModel):
    name: str
