from datetime import date

from sqlalchemy import JSON, Text
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
    # The dates exactly as written ("Sep 2020 – June 2025", "07/2023 – 05/2024", "2020"). When set,
    # CVs print it as is; start_date/end_date stay for the years arithmetic.
    date_label: str | None = None


class ExperienceHistory(TableBase, table=True):
    """One row per change of a pool item's text (`services/experience_write.py` is the only
    writer): the item as it was, so any change can be undone. `source` says who made it: `user`
    (the Experience screen), `master_import`, `undo`."""

    __tablename__ = "experience_history"

    item_id: int = Field(index=True)
    action: str  # created | edited | archived | restored | deleted | undo
    source: str = "user"
    before: dict = Field(default_factory=dict, sa_type=JSON)  # TEXT_FIELDS before the change
    after: dict = Field(default_factory=dict, sa_type=JSON)
    note: str | None = None
