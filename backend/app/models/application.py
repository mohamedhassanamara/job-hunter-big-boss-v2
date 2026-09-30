from datetime import datetime
from typing import Any

from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, json_field, utcnow
from app.models.enums import (
    ApplyMethod,
    CloseReason,
    ContactTier,
    CVStatus,
    DraftStatus,
    EventKind,
    Route,
    Stage,
)


class Application(TableBase, table=True):
    __tablename__ = "application"

    job_id: int = Field(foreign_key="job.id", unique=True, index=True)
    stage: Stage = enum_field(Stage.new, index=True)
    route: Route = enum_field(Route.undecided)
    contact_id: int | None = Field(default=None, foreign_key="contact.id")
    contact_tier: ContactTier = enum_field(ContactTier.none)
    close_reason: CloseReason | None = enum_field(None)
    notes: str = Field(default="", sa_type=Text)
    applied_at: datetime | None = dt_field()
    # Recorded by "Mark applied": how, with which (locked) CV version, and notes.
    applied_method: ApplyMethod | None = enum_field(None)
    # use_alter: cv_version also points at application, so this FK must not drive table order.
    applied_cv_version_id: int | None = Field(default=None, sa_column=Column(
        Integer, ForeignKey("cv_version.id", use_alter=True,
                            name="fk_application_applied_cv_version"), nullable=True))
    applied_notes: str = Field(default="", sa_type=Text)
    # The (locked) cover letter sent with a web application; None = sent without one.
    applied_cover_letter_id: int | None = Field(default=None, sa_column=Column(
        Integer, ForeignKey("cover_letter.id", use_alter=True,
                            name="fk_application_applied_cover_letter"), nullable=True))
    letter_language: str = "auto"  # auto (the listing's language) | fr | en
    stage_changed_at: datetime = dt_field(default_factory=utcnow)


class ApplicationEvent(TableBase, table=True):
    __tablename__ = "application_event"

    application_id: int = Field(foreign_key="application.id", index=True)
    kind: EventKind = enum_field()
    from_stage: str | None = None
    to_stage: str | None = None
    message: str | None = None
    payload: dict[str, Any] = json_field(dict)
    at: datetime = dt_field(default_factory=utcnow)


class CVVersion(TableBase, table=True):
    __tablename__ = "cv_version"

    application_id: int = Field(foreign_key="application.id", index=True)
    version: int = 1
    content: dict[str, Any] = json_field(dict)
    tex: str | None = Field(default=None, sa_type=Text)
    pdf_path: str | None = None
    page_count: int | None = None
    status: CVStatus = enum_field(CVStatus.draft)
    generator_model: str = "mock"
    template: str = "default"
    # The generator's ranked selection (pool item ids, reworded bullets with priorities) and the
    # user's overrides (forced in/out, edited text); `content` is the rendered CVDocument.
    plan: dict[str, Any] = json_field(dict)
    overrides: dict[str, Any] = json_field(dict)
    fill: float | None = None  # how full the page is (0-1)
    fit_passes: int = 0
    violations: list[dict[str, Any]] = json_field()  # fabrication/number checks, shown in the UI
    duration_ms: int | None = None
    error: str | None = Field(default=None, sa_type=Text)
    # Set when this version was sent with an application: never re-rendered or changed again.
    locked_at: datetime | None = dt_field()
    pdf_sha256: str | None = None


class OutreachDraft(TableBase, table=True):
    __tablename__ = "outreach_draft"

    application_id: int = Field(foreign_key="application.id", index=True)
    contact_id: int | None = Field(default=None, foreign_key="contact.id")
    subject: str = ""
    body: str = Field(default="", sa_type=Text)
    status: DraftStatus = enum_field(DraftStatus.draft, index=True)
    model: str = "mock"
    edited: bool = False
    # The approved CV the email is written from (and attached when sent).
    cv_version_id: int | None = Field(default=None, foreign_key="cv_version.id")
    # The model's sentences with their citations, and the automatic checks' findings.
    plan: dict[str, Any] = json_field(dict)
    violations: list[dict[str, Any]] = json_field()
    prompt_version: str | None = None
    duration_ms: int | None = None
    error: str | None = Field(default=None, sa_type=Text)
    test_sent_at: datetime | None = dt_field()
    sent_at: datetime | None = dt_field()
    message_id: str | None = None


class CoverLetter(TableBase, table=True):
    """A cover letter version for a web application, written from the approved CV."""

    __tablename__ = "cover_letter"

    application_id: int = Field(foreign_key="application.id", index=True)
    version: int = 1
    status: CVStatus = enum_field(CVStatus.draft)
    language: str = "en"  # fr | en
    # {salutation, paragraphs: [{sentences: [{text, citations, about_job}]}], closing}; after
    # you edit a paragraph, that paragraph is {text} (re-checked at text level).
    content: dict[str, Any] = json_field(dict)
    text: str = Field(default="", sa_type=Text)  # plain text (Copy as text)
    tex: str | None = Field(default=None, sa_type=Text)
    pdf_path: str | None = None
    page_count: int | None = None
    template: str = "default"
    cv_version_id: int | None = Field(default=None, foreign_key="cv_version.id")
    generator_model: str = "mock"
    prompt_version: str | None = None
    plan: dict[str, Any] = json_field(dict)  # the model's output and attempts
    violations: list[dict[str, Any]] = json_field()
    duration_ms: int | None = None
    error: str | None = Field(default=None, sa_type=Text)
    locked_at: datetime | None = dt_field()
    pdf_sha256: str | None = None


class ApplicationAnswer(TableBase, table=True):
    """An answer to a question from an application form, grounded like the cover letter."""

    __tablename__ = "application_answer"

    application_id: int = Field(foreign_key="application.id", index=True)
    question: str = Field(sa_type=Text)
    char_limit: int | None = None
    answer: str = Field(default="", sa_type=Text)
    language: str = "en"
    position: int = 0
    edited: bool = False
    plan: dict[str, Any] = json_field(dict)  # the model's sentences with citations
    violations: list[dict[str, Any]] = json_field()
    generator_model: str = "mock"
    prompt_version: str | None = None
