from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CVVersionOut(BaseModel):
    id: int
    application_id: int
    version: int
    status: str
    content: dict[str, Any]
    page_count: int | None
    generator_model: str
    created_at: datetime
    updated_at: datetime


class CVStudio(BaseModel):
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    stage: str
    route: str
    has_contact: bool
    versions: list[CVVersionOut]


class CVPatch(BaseModel):
    content: dict[str, Any]


class CVApproveResult(BaseModel):
    version: CVVersionOut
    stage: str
    route: str
    next_step: str  # draft_email | mark_ready_to_apply
