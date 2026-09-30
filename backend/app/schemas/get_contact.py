from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.jobs import ContactAlertOut, ContactOut, FitBrief


class Provenance(BaseModel):
    kind: str  # import | found | manual | hunter
    label: str  # "wissem-list.csv", "you, with the Apollo extension"…
    at: datetime | None


class GetContactCompany(BaseModel):
    id: int
    name: str
    domain: str | None
    contact_search: str  # none | not_found | never
    contact_search_notes: str
    aggregator: list[str]  # "looks like a job board" signals (a suggestion)


class GetContactView(BaseModel):
    """The Get contact step for one job."""

    application_id: int
    job_id: int
    job_title: str
    state: str  # get | verify | ready | never
    company: GetContactCompany
    contact: ContactOut | None
    provenance: Provenance | None
    verified_at: datetime | None
    verified_how: str | None
    verify_days: int
    stale: bool  # verified, but longer ago than verify_days
    who: dict[str, Any]  # who_to_contact() + steps
    links: dict[str, str | None]  # company_linkedin, people_search, website, profile
    alerts: list[ContactAlertOut]
    next_contact: ContactOut | None
    others: list[ContactOut]  # other contacts at the company, best ranked first
    found_today: int
    daily_limit: int


class ToGetItem(BaseModel):
    application_id: int
    job_id: int
    job_title: str
    company_id: int
    company_name: str
    stage: str
    stage_label: str
    fit: FitBrief | None
    state: str  # get | verify
    nobody_found: bool
    contact_name: str | None
    stale: bool


class ToGetQueue(BaseModel):
    items: list[ToGetItem]
    total: int
    found_today: int
    daily_limit: int


class VerifyIn(BaseModel):
    action: str  # still_there | left | wrong_person


class FoundIn(BaseModel):
    full_name: str
    title: str | None = None
    email: str
    linkedin_url: str | None = None
    via: str = "found"  # found (Apollo extension) | hunter


class ContactEdit(BaseModel):
    full_name: str | None = None
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None


class ContactSearchIn(BaseModel):
    status: str  # none | not_found | never
    notes: str = ""
    application_id: int | None = None  # returns that job's view


class PasteIn(BaseModel):
    text: str


class PasteOut(BaseModel):
    full_name: str | None
    title: str | None
    email: str | None
    linkedin_url: str | None
    company: str | None
    notes: list[str]


class HunterCredits(BaseModel):
    configured: bool
    error: str | None = None
    plan: str | None = None
    searches_left: int | None = None
    searches_available: int | None = None
    verifications_left: int | None = None
    verifications_available: int | None = None
    reset_date: str | None = None


class HunterFindIn(BaseModel):
    application_id: int
    full_name: str  # first and last name (Hunter's email-finder needs both)


class HunterVerifyIn(BaseModel):
    email: str


class HunterFindOut(BaseModel):
    email: str | None
    score: int | None
    full_name: str | None
    position: str | None
    linkedin_url: str | None
    status: str | None
    credits: HunterCredits


class HunterVerifyOut(BaseModel):
    email: str
    result: str
    status: str
    score: int | None
    credits: HunterCredits
