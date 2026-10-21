from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.jobs import ContactAlertOut, ContactOut, FitBrief


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
    full_body: str = ""  # as sent: your text + signature (+ an optional last line)
    test_sent_at: datetime | None = None
    sent_at: datetime | None = None
    generated_via: str = "mock"  # "claude -p" = Claude Code headless (your subscription)
    auth: str | None = None  # the CLI's apiKeySource at generation ("none" = subscription)
    # "I have also applied through your careers page on …": available once Mark applied is in.
    application_mention: str | None = None
    mention_included: bool = False
    format: str = "reply"  # applied (v11 follow-up) | intro (speculative) | reply (older drafts)
    # The company signals the hook cites: {id, kind, fact, quote}; the source URL comes with it.
    signals: list[dict[str, Any]] = []
    needs_signal: bool = False
    research_note: str | None = None
    # The hook's claims checked against its signals: {status, model, claims, error, …}.
    hook_check: dict[str, Any] | None = None
    # When the greeting spells the name as the company's pages do: {first_name, url, title, excerpt}
    name_source: dict[str, Any] | None = None
    # Signs the contact left: while any is active, the email can't be approved
    contact_alerts: list[ContactAlertOut] = []
    next_contact: ContactOut | None = None
    # The claim verifier (services/verifier.py): its last run and whether it still applies.
    verification: dict[str, Any] = {}
    verification_state: str = "none"  # passed | failed | error | stale | none
    # The email type and the language it is written in, with why (services/language.py).
    mode: str | None = None  # applied | speculative
    language: str | None = None
    language_detected: str | None = None  # the listing's language
    language_reason: str | None = None
    language_source: str | None = None  # auto | override | job | setting
    # Draft history: what you asked to change to get this version, and where it came from.
    feedback: str = ""
    parent_id: int | None = None
    source: str = "generated"  # generated | external (pasted from another AI)
    # Approved without the claim verifier: {at, ignored: [{type, severity, message}], …} or null.
    unverified_approval: dict[str, Any] | None = None


class DraftHistoryItem(BaseModel):
    id: int
    version: int
    status: str
    created_at: datetime
    subject: str
    words: int
    feedback: str = ""
    parent_id: int | None = None
    mode: str | None = None
    language: str | None = None
    source: str = "generated"
    prompt_version: str | None = None
    unverified: bool = False
    current: bool = False  # still alive (under review, approved, queued or sent)


class GenerateIn(BaseModel):
    """Optional body of the draft step: what to change, a language, the email type."""

    feedback: str = ""  # "What should change?" (optional): the model edits the draft toward it
    language: str | None = None  # en | fr: your override (kept for regenerations); auto clears it
    mode: str | None = None  # applied | speculative
    base_draft_id: int | None = None  # the draft to edit (default: the one under review)
    use: str | None = None  # "claude": this call only (after a Gemini failure)


class ApproveUnverifiedIn(BaseModel):
    confirm: bool = False


class ExternalPromptIn(BaseModel):
    mode: str | None = None
    language: str | None = None


class ExternalPromptOut(BaseModel):
    prompt: str
    mode: str
    language: dict[str, str]
    chars: int
    items: list[int]
    note: str
    listing_short: bool


class ExternalDraftIn(BaseModel):
    text: str
    mode: str | None = None
    language: str | None = None


class ExternalCheckOut(BaseModel):
    subject: str
    body: str
    mode: str
    language: dict[str, str]
    violations: list[dict[str, Any]]
    verification: dict[str, Any]
    errors: int


class DraftProgress(BaseModel):
    status: str  # idle | running | done | failed
    phase: str  # starting | fetching | extracting | drafting | done
    done: int = 0
    total: int = 0
    draft_id: int | None = None
    error: str | None = None
    generation_failed: bool = False  # the model didn't answer: offer Retry / Generate with Claude


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
    unverified: bool = False  # approved without the claim verifier


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

    step: str  # get_contact | verify_contact | cv | draft | review | queue | queued | sent
    route: str  # effective route
    contact_tier: str
    contact_search: str = "none"  # the company's: none | not_found | never
    has_contact: bool
    has_email: bool
    cv_version: int | None  # the approved CV (None = approve one first)
    # The draft step: which email to write by default (applied when the job has a posting) and
    # whether the stored listing is a short snippet (requirements like residency can't be seen).
    email_mode: str = "applied"  # applied | speculative
    listing_chars: int = 0
    listing_short: bool = False
    can_fetch_listing: bool = True  # never for LinkedIn jobs
    draft: DraftOut | None
    queue_position: int | None
    queue_eta: datetime | None
    queue_status: str
    sent_at: datetime | None
    who_to_contact: dict[str, Any] | None = None  # roles, reason and search hints (no contact)


class SentManually(BaseModel):
    sent_on: str | None = None  # YYYY-MM-DD, default today
