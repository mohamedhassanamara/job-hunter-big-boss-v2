"""LinkedIn as its own channel (Phase 10): daily search links you opened, the LinkedIn messages
track per job and person, and the CV fit before/after. Nothing here talks to LinkedIn: the app
builds links and reads the one job page you hand it with the bookmark."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field
from app.models.enums import LinkedInGroup, LinkedInStatus


class LinkedInLinkOpen(TableBase, table=True):
    """You opened a daily search link (the "opened today" mark; a new day starts clean)."""

    __tablename__ = "linkedin_link_open"
    __table_args__ = (UniqueConstraint("key", "day", name="uq_linkedin_link_open"),)

    key: str = Field(index=True)  # role|country|filters
    day: date = Field(index=True)


class LinkedInOutreach(TableBase, table=True):
    """One person to message on LinkedIn about one job: the connection note, then a follow-up."""

    __tablename__ = "linkedin_outreach"
    __table_args__ = (UniqueConstraint("application_id", "contact_id", name="uq_linkedin_person"),)

    application_id: int = Field(foreign_key="application.id", index=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    # Who they are (the note's angle): detected from their title, yours to override.
    group: LinkedInGroup = enum_field(LinkedInGroup.other)
    alumni: bool = False
    hiring_team: bool = False  # they posted this job / are on its hiring team (captured)
    status: LinkedInStatus = enum_field(LinkedInStatus.to_contact, index=True)
    # The drafts: {text, plan, violations, model, prompt_version, auth, via, created_at, edited}
    note: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    followup: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    critique: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    sent_at: datetime | None = dt_field()
    accepted_at: datetime | None = dt_field()
    messaged_at: datetime | None = dt_field()
    replied_at: datetime | None = dt_field()
    notes: str = Field(default="", sa_type=Text)
    # LinkedIn Premium InMail (a message to someone you're not connected with): {subject, text,
    # citations, violations, verification, ...}. Sending one uses a monthly credit; a reply within
    # 90 days gives it back (inmail_refunded_at).
    inmail: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    inmail_sent_at: datetime | None = dt_field()
    inmail_refunded_at: datetime | None = dt_field()
    # Where this person came from: manual | captured | viewed_profile. `reason` is for you only
    # ("viewed my profile on 20 Oct"); it is never given to a drafting model.
    source: str = "manual"
    reason: str = ""
    viewed_on: date | None = None


class LinkedInLead(TableBase, table=True):
    """Someone who viewed your profile whose company has no job in the app yet. Kept until a job
    at that company exists, then linked into the LinkedIn track (services/linkedin_track)."""

    __tablename__ = "linkedin_lead"

    full_name: str
    title: str | None = None
    company_name: str = ""
    linkedin_url: str | None = None
    viewed_on: date | None = None
    reason: str = ""
    linked_outreach_id: int | None = Field(default=None, foreign_key="linkedin_outreach.id")


class CVFit(TableBase, table=True):
    """Fit before/after for an approved CV: the job scored against the tailored CV (one model
    call, stored apart from the job's own fit) and the lexical evidence check (no model)."""

    __tablename__ = "cv_fit"

    cv_version_id: int = Field(foreign_key="cv_version.id", index=True, unique=True)
    base_fit_id: int | None = Field(default=None, foreign_key="fit_score.id")
    base_score: int | None = None
    score: int | None = None  # the tailored CV's
    sub_scores: dict[str, Any] = json_field(dict)
    status: str = "pending"  # pending | ok | failed
    error: str | None = Field(default=None, sa_type=Text)
    model: str | None = None
    prompt_version: str | None = None
    lexical: dict[str, Any] = json_field(dict)  # before/after evidence report
    scored_at: datetime | None = dt_field()
