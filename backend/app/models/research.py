"""Company research for cold emails (services/research.py): fetched pages, verified signals, the
log of each run (with every model call), and the email regression set."""

from datetime import datetime
from typing import Any

from sqlalchemy import Text
from sqlmodel import Field

from app.models.base import TableBase, dt_field, json_field, utcnow


class CompanyPage(TableBase, table=True):
    __tablename__ = "company_page"

    company_id: int = Field(foreign_key="company.id", index=True)
    research_run_id: int | None = Field(default=None, foreign_key="research_run.id")
    url: str
    kind: str = "page"  # page | news
    title: str = ""
    text: str = Field(default="", sa_type=Text)
    page_date: datetime | None = dt_field()
    fetched_at: datetime = dt_field(default_factory=utcnow)


class CompanySignal(TableBase, table=True):
    """A fact about the company with its exact supporting quote (verified in the fetched text)."""

    __tablename__ = "company_signal"

    company_id: int = Field(foreign_key="company.id", index=True)
    research_run_id: int | None = Field(default=None, foreign_key="research_run.id")
    # product | technical | customer_result | launch | funding | expansion | other
    kind: str = "other"
    fact: str = Field(sa_type=Text)
    quote: str = Field(default="", sa_type=Text)
    source_url: str = ""
    page_date: datetime | None = dt_field()
    fetched_at: datetime = dt_field(default_factory=utcnow)
    origin: str = "research"  # research | manual
    verified: bool = False
    selected: bool = False  # used by this company's emails
    dismissed: bool = False


class ResearchRun(TableBase, table=True):
    __tablename__ = "research_run"

    company_id: int = Field(foreign_key="company.id", index=True)
    trigger: str = "draft"  # draft | manual
    status: str = "running"  # running | done | failed | cached
    started_at: datetime = dt_field(default_factory=utcnow)
    finished_at: datetime | None = dt_field()
    pages: int = 0
    signals_kept: int = 0
    signals_dropped: int = 0
    # One entry per model call: {model, prompt_version, duration_ms, outcome, tokens?}
    calls: list[dict[str, Any]] = json_field()
    warnings: list[str] = json_field()
    error: str | None = Field(default=None, sa_type=Text)


class EmailExample(TableBase, table=True):
    """The email regression set: your reference examples and every email you approve or reject.
    `inputs` is the EmailRequest snapshot, so `make eval-emails` can write it again."""

    __tablename__ = "email_example"

    kind: str  # reference_good | reference_bad | approved | rejected
    language: str = "en"
    subject: str = ""
    body: str = Field(default="", sa_type=Text)
    draft_id: int | None = Field(default=None, foreign_key="outreach_draft.id")
    company: str = ""
    inputs: dict[str, Any] = json_field(dict)
    note: str = ""


class ContactAlert(TableBase, table=True):
    """A sign the contact may have left or changed role, found in the company's researched pages
    or news (services/contact_check.py). Active until you dismiss it (you verified them)."""

    __tablename__ = "contact_alert"

    contact_id: int = Field(foreign_key="contact.id", index=True)
    company_id: int = Field(foreign_key="company.id", index=True)
    key: str = Field(unique=True)  # contact + source + kind: found again, it stays one alert
    kind: str = "left"  # left (named with a departure word) | new_holder (someone else named)
    reason: str = ""  # e.g. "“révoque” next to their name"
    excerpt: str = Field(default="", sa_type=Text)
    source_url: str = ""
    source_title: str = ""
    page_date: datetime | None = dt_field()
    detected_at: datetime = dt_field(default_factory=utcnow)
    dismissed_at: datetime | None = dt_field()
