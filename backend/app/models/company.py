from datetime import datetime
from typing import Any

from sqlalchemy import Index, Text, text
from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field, utcnow
from app.models.enums import ContactSource, ImportStatus, LookupStatus


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
    __table_args__ = (
        # Dedupe keys: the email (when present) and company + folded name.
        Index("uq_contact_email", "email_normalized", unique=True,
              sqlite_where=text("email_normalized IS NOT NULL")),
        Index("ix_contact_company_name", "company_id", "normalized_name"),
    )

    company_id: int = Field(foreign_key="company.id", index=True)
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    normalized_name: str = ""
    title: str | None = None
    email: str | None = None
    email_normalized: str | None = None
    linkedin_url: str | None = None
    source: ContactSource = enum_field(ContactSource.apollo_dump)
    imported_batch: str | None = None
    # Position in Settings → Contacts role ranking (0 = most relevant); cached, re-derived when
    # the ranking changes.
    role_rank: int = Field(default=999, index=True)
    notes: str = Field(default="", sa_type=Text)


class ContactImport(TableBase, table=True):
    """One CSV import run (processed in batches in the background)."""

    __tablename__ = "contact_import"

    filename: str
    file_sha256: str = Field(index=True)
    status: ImportStatus = enum_field(ImportStatus.running)
    total: int = 0
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    skipped_reasons: dict[str, Any] = json_field(dict)
    companies_created: int = 0
    mapping: dict[str, Any] = json_field(dict)
    error: str | None = Field(default=None, sa_type=Text)
    started_at: datetime = dt_field(default_factory=utcnow)
    finished_at: datetime | None = dt_field()


class CompanyLookup(TableBase, table=True):
    """Tier 2 of contact resolution: a manual Apollo-extension lookup, one per company."""

    __tablename__ = "company_lookup"

    company_id: int = Field(foreign_key="company.id", unique=True, index=True)
    status: LookupStatus = enum_field(LookupStatus.queued, index=True)
    priority: int = 0  # best fit among the company's open jobs
    queued_at: datetime = dt_field(default_factory=utcnow)
    resolved_at: datetime | None = dt_field()
    snoozed_until: datetime | None = dt_field()
    notes: str = Field(default="", sa_type=Text)
