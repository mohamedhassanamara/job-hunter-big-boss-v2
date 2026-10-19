"""Interview preparation per job (Phase 12b): STAR stories and a pitch from the experience pool,
checked in code and by the claim verifier before you can approve them."""

from typing import Any

from sqlmodel import Field

from app.models.base import TableBase, enum_field, json_field
from app.models.enums import CVStatus


class InterviewPrep(TableBase, table=True):
    __tablename__ = "interview_prep"

    application_id: int = Field(foreign_key="application.id", index=True)
    version: int = 1
    status: CVStatus = enum_field(CVStatus.draft)  # draft | approved | superseded
    language: str = "en"
    content: dict[str, Any] = json_field(dict)  # pitch, stories, questions, ask_them
    violations: list[dict[str, Any]] = json_field(list)  # code checks (errors block approval)
    verification: dict[str, Any] = json_field(dict)  # the claim verifier's record
    generator_model: str | None = None
    prompt_version: str | None = None
    plan: dict[str, Any] = json_field(dict)  # what the model returned + attempts
    duration_ms: int | None = None
