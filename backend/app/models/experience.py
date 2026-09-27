from datetime import date

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import TableBase, enum_field, json_field
from app.models.enums import ExperienceKind


class ExperienceItem(TableBase, table=True):
    __tablename__ = "experience_item"

    kind: ExperienceKind = enum_field(index=True)
    title: str
    org: str | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    summary: str | None = Field(default=None, sa_type=Text)
    bullets: list[str] = json_field()
    tags: list[str] = json_field()
    position: int = 0
    is_active: bool = True
    # Test-CV data the user asked for; shown with a warning and removable in one click.
    is_placeholder: bool = False
    url: str | None = None  # certifications (verification link), projects (repo/demo)
    credential_id: str | None = None  # certifications
