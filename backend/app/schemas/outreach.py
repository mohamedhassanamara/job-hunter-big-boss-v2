from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.jobs import FitBrief


class DraftContact(BaseModel):
    id: int
    full_name: str
    title: str | None
    email: str | None
    role_label: str | None = None


class DraftOut(BaseModel):
    id: int
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    fit: FitBrief | None
    contact: DraftContact | None
    subject: str
    body: str
    status: str
    edited: bool
    model: str
    cv_version: int | None
    created_at: datetime
    updated_at: datetime
    cv_version_id: int | None = None
    sentences: list[dict[str, Any]] = []  # [{text, citations, about_job}] as generated
    citations: dict[str, str] = {}  # pool id -> "Role at Org" (for hover)
    violations: list[dict[str, Any]] = []  # [{type, severity, message, where}]
    attempts: int = 1
    prompt_version: str | None = None
    duration_ms: int | None = None
    full_body: str = ""  # as sent: your text + signature + opt-out
    test_sent_at: datetime | None = None
    sent_at: datetime | None = None
    generated_via: str = "mock"  # "claude -p" = Claude Code headless (your subscription)
    auth: str | None = None  # the CLI's apiKeySource at generation ("none" = subscription)
    # "I have also applied through your careers page on …": available once Mark applied is in.
    application_mention: str | None = None
    mention_included: bool = False
    format: str = "reply"  # intro (prompt v4+: a personal introduction) | reply (older drafts)
    # The company signals the hook cites: {id, kind, fact, quote}; the source URL comes with it.
    signals: list[dict[str, Any]] = []
    needs_signal: bool = False
    research_note: str | None = None
    # The hook's claims checked against its signals: {status, model, claims, error, …}.
    hook_check: dict[str, Any] | None = None
    # When the greeting spells the name as the company's pages do: {first_name, url, title, excerpt}
    name_source: dict[str, Any] | None = None


class DraftProgress(BaseModel):
    status: str  # idle | running | done | failed
    phase: str  # starting | fetching | extracting | drafting | done
    done: int = 0
    total: int = 0
    draft_id: int | None = None
    error: str | None = None


class MentionIn(BaseModel):
    include: bool


class DraftPatch(BaseModel):
    subject: str | None = None
    body: str | None = None


class QueueItemOut(BaseModel):
    id: int
    position: int
    status: str
    scheduled_at: datetime | None
    sent_at: datetime | None
    error: str | None
    attempts: int = 0
    draft_id: int
    job_id: int
    subject: str
    contact_name: str | None
    contact_email: str | None
    company_name: str


class QueueCounts(BaseModel):
    pending: int
    sent: int
    failed: int
    unknown: int = 0


class QueueOut(BaseModel):
    status: str
    interval_minutes: int
    max_items: int
    next_send_at: datetime | None
    counts: QueueCounts
    items: list[QueueItemOut]
    test_sent: bool = False  # a test email reached your inbox (required before starting)
    own_address: str = ""


class SendLogOut(BaseModel):
    id: int
    draft_id: int | None
    kind: str
    to: str
    subject: str
    status: str
    error: str | None
    message_id: str | None
    attachment: str | None
    at: datetime


class OutreachStep(BaseModel):
    """Where a job is on the email route and the next action (the Job page stepper)."""

    step: str  # contact | cv | draft | review | queue | queued | sent
    route: str  # effective route
    contact_tier: str
    lookup_status: str | None
    has_contact: bool
    has_email: bool
    cv_version: int | None  # the approved CV (None = approve one first)
    draft: DraftOut | None
    queue_position: int | None
    queue_eta: datetime | None
    queue_status: str
    sent_at: datetime | None
    who_to_contact: dict[str, Any] | None = None  # roles, reason and search hints (no contact)


class SentManually(BaseModel):
    sent_on: str | None = None  # YYYY-MM-DD, default today
