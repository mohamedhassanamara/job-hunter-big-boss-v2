from datetime import date, datetime

from pydantic import BaseModel


class ExperienceIn(BaseModel):
    kind: str
    title: str
    org: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    summary: str | None = None
    bullets: list[str] = []
    tags: list[str] = []
    tracks: list[str] = []
    is_active: bool = True
    url: str | None = None
    credential_id: str | None = None
    date_label: str | None = None


class ExperiencePatch(BaseModel):
    kind: str | None = None
    title: str | None = None
    org: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    summary: str | None = None
    bullets: list[str] | None = None
    tags: list[str] | None = None
    tracks: list[str] | None = None
    is_active: bool | None = None
    url: str | None = None
    credential_id: str | None = None
    date_label: str | None = None


class ExperienceOut(ExperienceIn):
    id: int
    position: int
    is_placeholder: bool = False
    updated_at: datetime


class ReorderIn(BaseModel):
    kind: str
    ids: list[int]


class HistoryOut(BaseModel):
    id: int
    item_id: int
    action: str
    source: str
    before: dict
    after: dict
    note: str | None = None
    created_at: datetime
