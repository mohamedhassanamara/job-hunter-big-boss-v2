from datetime import datetime

from pydantic import BaseModel

from app.schemas.jobs import ContactOut, RelatedJob


class CompanyListItem(BaseModel):
    id: int
    name: str
    domain: str | None
    contact_count: int
    open_jobs: int
    contacted_at: datetime | None


class CompanyDetail(CompanyListItem):
    website: str | None
    contacts: list[ContactOut]
    jobs: list[RelatedJob]


class ImportPreview(BaseModel):
    filename: str
    total_rows: int
    columns: list[str]
    mapping: dict[str, str | None]  # our field -> CSV column
    sample: list[dict[str, str]]


class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    mock: bool = True


class LookupItem(BaseModel):
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    fit: int | None
    queued_at: datetime


class LookupQueue(BaseModel):
    daily_cap: int
    used_today: int
    items: list[LookupItem]
