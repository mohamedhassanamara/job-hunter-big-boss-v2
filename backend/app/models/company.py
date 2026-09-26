from datetime import datetime

from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field
from app.models.enums import ContactSource


class Company(TableBase, table=True):
    __tablename__ = "company"

    name: str
    normalized_name: str = Field(unique=True, index=True)
    domain: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    contacted_at: datetime | None = dt_field()


class Contact(TableBase, table=True):
    __tablename__ = "contact"

    company_id: int = Field(foreign_key="company.id", index=True)
    full_name: str
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    source: ContactSource = enum_field(ContactSource.apollo_dump)
    imported_batch: str | None = None
