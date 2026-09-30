from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.jobs import ContactOut, FitBrief


class CompanyListItem(BaseModel):
    id: int
    name: str
    domain: str | None
    contact_count: int
    open_jobs: int
    contacted_at: datetime | None
    contact_search: str = "none"  # none | not_found (nobody found) | never (a job board)
    best_contact: str | None  # name · role of who its jobs are written to
    employees: int | None = None
    employees_max: int | None = None  # "under N" (e.g. from an Apollo list)
    size_source: str | None = None  # manual | apollo_list
    size_label: str = "size unknown"
    small: bool = False  # uses the small-company contact order (Settings → Contacts)


class CompanyList(BaseModel):
    items: list[CompanyListItem]
    total: int


class CompanyJob(BaseModel):
    application_id: int
    job_id: int
    title: str
    stage: str
    stage_label: str
    route: str
    contact_tier: str
    contact_id: int | None
    fit: FitBrief | None


class CompanyDetail(CompanyListItem):
    website: str | None
    contacts: list[ContactOut]  # most relevant role first
    jobs: list[CompanyJob]


class FilePreview(BaseModel):
    filename: str
    sha256: str
    total_rows: int
    columns: list[str]
    mapping: dict[str, str | None]  # our field -> CSV column
    sample: list[dict[str, str]]
    already_imported_at: datetime | None  # same file (hash) imported before


class ImportRunOut(BaseModel):
    id: int
    filename: str
    status: str  # running | done | failed
    total: int
    processed: int
    created: int
    updated: int
    skipped: int
    skipped_reasons: dict[str, Any]
    companies_created: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    backup_path: str | None = None


class NewContact(BaseModel):
    full_name: str
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    notes: str = ""


class MatchGroup(BaseModel):
    group: str
    jobs: int
    with_contact: int
    to_get: int
    no_contact: int


class MatchReport(BaseModel):
    totals: dict[str, int]
    by_track: list[MatchGroup]
    by_country: list[MatchGroup]
    contacts_to_get: int
    contacts: int
    companies_with_contacts: int
    changed: int | None = None
    at: str


class CompanySize(BaseModel):
    employees: int | None = None
    employees_max: int | None = None


class MergeSide(BaseModel):
    id: int
    name: str
    jobs: int
    contacts: int


class MergeSuggestion(BaseModel):
    a: MergeSide
    b: MergeSide
    reason: str


class MergeIn(BaseModel):
    keep_id: int
    merge_id: int


class MergeReject(BaseModel):
    a_id: int
    b_id: int
