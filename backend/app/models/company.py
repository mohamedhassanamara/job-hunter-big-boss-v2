from datetime import datetime
from typing import Any

from sqlalchemy import Index, Text, text
from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field, utcnow
from app.models.enums import ContactSearch, ContactSource, ImportStatus


class Company(TableBase, table=True):
    __tablename__ = "company"

    name: str
    normalized_name: str = Field(unique=True, index=True)
    domain: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    contacted_at: datetime | None = dt_field()
    research_refreshed_at: datetime | None = dt_field()  # last company research (cold emails)
    # Headcount: an exact number, or an upper bound (e.g. 200 for "under 200" from an Apollo list).
    employees: int | None = None
    employees_max: int | None = None
    size_source: str | None = None  # manual | apollo_list
    # You looked at the "looks like a job board" suggestion and said no.
    aggregator_reviewed: bool = False
    # Your answer to the agency rule (services/agency.py): employer | agency | None (the rule).
    agency_override: str | None = None
    # Get contact: nobody found with the Apollo extension, or never look up (a job board).
    contact_search: ContactSearch = enum_field(ContactSearch.none)
    contact_search_at: datetime | None = dt_field()
    contact_search_notes: str = Field(default="", sa_type=Text)
    # Phase 12 company cache: what the contact waterfall learned (the providers already queried and
    # when are in `company_provider_run`; people are the company's `contact` rows with provenance).
    domain_source: str | None = None  # manual | pdl | listing | provider
    industry: str | None = None
    email_pattern: str | None = None  # "{first}.{last}" (Hunter's notation)
    pattern_confidence: int | None = None  # 0-100
    pattern_evidence: dict[str, Any] = json_field(dict)  # {"source": ..., "samples": [...]}
    last_enriched_at: datetime | None = dt_field()
    # The domain mail and provider lookups use when it isn't the website's (sekoia.com vs
    # sekoia.io): set from verified emails or by you. `domain` stays the website's.
    email_domain: str | None = None
    # Every known domain: {domain: {source, mx, checked_at, note}} (services/domains.py)
    domains: dict[str, Any] = json_field(dict)


class CompanyAlias(TableBase, table=True):
    """Another spelling of a company (after you confirm a merge): ingest and imports map it."""

    __tablename__ = "company_alias"

    normalized_name: str = Field(unique=True, index=True)
    company_id: int = Field(foreign_key="company.id", index=True)


class CompanyMergeDecision(TableBase, table=True):
    """Your answer to a merge suggestion, so it isn't suggested again."""

    __tablename__ = "company_merge_decision"

    pair_key: str = Field(unique=True, index=True)  # "<norm a>|<norm b>", sorted
    decision: str  # merged | rejected
    kept_company_id: int | None = None
    merged_name: str | None = None


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
    # Get contact: you confirmed they're there (or entered them) on this date; stale after
    # Settings → Contacts verify_days. Left / wrong person: never picked again.
    verified_at: datetime | None = dt_field()
    verified_how: str | None = None  # entered | still_there | hunter
    left_at: datetime | None = dt_field()
    left_reason: str | None = None  # left | wrong_person
    # Provenance of a contact a provider found (Phase 12), and the deliverability of its email.
    found_by_provider: str | None = None  # hunter | prospeo | apollo | apify | pattern
    found_by_key: str | None = None  # key label ("prospeo#2"), never the key itself
    found_by_actor: str | None = None  # the Apify Actor
    found_at: datetime | None = dt_field()
    verification_status: str | None = None  # valid | accept_all | unknown | invalid


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
