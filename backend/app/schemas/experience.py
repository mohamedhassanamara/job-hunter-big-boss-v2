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
    is_active: bool = True


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
    is_active: bool | None = None


class ExperienceOut(ExperienceIn):
    id: int
    position: int
    updated_at: datetime


class ReorderIn(BaseModel):
    kind: str
    ids: list[int]
