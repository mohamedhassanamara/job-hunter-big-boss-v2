from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ConfirmationOut(BaseModel):
    id: int
    job_id: int
    source: str  # claude | gemma | manual | mock
    model: str
    via: str
    score: int | None
    band: str
    sub_scores: dict[str, Any]
    red_flags: list[dict[str, Any]]
    core_requirements: list[dict[str, Any]]
    capped_by: str | None  # hard_flag | missing_core | null
    missing_core: str | None
    strengths: list[str]
    gaps: list[str]
    summary: str
    confidence: str
    # advice apply|maybe|skip, why, seniority, skills, location_visa, language
    verdict: dict[str, Any]
    notes: str
    prompt_version: str | None
    created_at: datetime
    stale: bool  # the experience changed since this answer


class PasteIn(BaseModel):
    text: str


class ConfirmationPrompt(BaseModel):
    prompt: str
