from datetime import datetime
from typing import Any

from sqlalchemy import Text
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
    applied_cv_version_id: int | None = Field(default=None, foreign_key="cv_version.id")
    applied_notes: str = Field(default="", sa_type=Text)
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
