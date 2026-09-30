"""String enums shared by models, schemas and services. Stored as VARCHAR (values, not names)."""

from enum import StrEnum


class Source(StrEnum):
    adzuna = "adzuna"
    remotive = "remotive"
    arbeitnow = "arbeitnow"
    wttj = "wttj"
    boards = "boards"  # company job boards (Greenhouse, Lever, Ashby, Workable, SmartRecruiters)
    bayt = "bayt"


class ScoringTaskStatus(StrEnum):
    queued = "queued"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class RemoteScope(StrEnum):
    """Which remote jobs count as eligible (see services/geo.remote_allows)."""

    anywhere = "anywhere"  # worldwide or EMEA regions, plus target countries
    europe = "europe"
    targets = "targets"


class RemotePolicy(StrEnum):
    any = "any"
    remote_ok = "remote_ok"
    remote_only = "remote_only"


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    skipped = "skipped"
    success = "success"
    partial = "partial"
    failed = "failed"


class RunTrigger(StrEnum):
    manual = "manual"
    scheduled = "scheduled"
    test = "test"


class RemoteType(StrEnum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"


class ContactSource(StrEnum):
    apollo_dump = "apollo_dump"
    apollo_lookup = "apollo_lookup"
    manual = "manual"


class ExperienceKind(StrEnum):
    job = "job"
    project = "project"
    skill = "skill"
    education = "education"
    certification = "certification"
    volunteering = "volunteering"
    summary = "summary"  # short summary snippets the CV generator picks from and rewords


class Stage(StrEnum):
    new = "new"
    shortlisted = "shortlisted"
    cv_ready = "cv_ready"
    drafted = "drafted"  # email route only: a cold-email draft is waiting for review
    ready = "ready"
    done = "done"
    interview = "interview"
    closed = "closed"


class Route(StrEnum):
    undecided = "undecided"
    cold_email = "cold_email"
    web_apply = "web_apply"


class ImportStatus(StrEnum):
    running = "running"
    done = "done"
    failed = "failed"


class LookupStatus(StrEnum):
    queued = "queued"
    found = "found"
    not_found = "not_found"
    skipped = "skipped"
    never = "never"  # a job board / aggregator: never looked up, its jobs go to web apply


class ContactTier(StrEnum):
    apollo_dump = "apollo_dump"
    lookup_queued = "lookup_queued"
    lookup_found = "lookup_found"
    none = "none"


class CloseReason(StrEnum):
    dismissed = "dismissed"
    rejected = "rejected"
    withdrawn = "withdrawn"
    no_response = "no_response"  # ghosted
    offer = "offer"  # legacy (before offers were split into accepted/declined)
    offer_accepted = "offer_accepted"
    offer_declined = "offer_declined"


class ApplyMethod(StrEnum):
    company_site = "company_site"
    job_board = "job_board"
    email = "email"
    other = "other"


class ResponseKind(StrEnum):
    positive = "positive"
    rejection = "rejection"
    other = "other"


class InterviewType(StrEnum):
    hr = "hr"
    technical = "technical"
    take_home = "take_home"
    final = "final"
    other = "other"


class InterviewOutcome(StrEnum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    cancelled = "cancelled"


class EventKind(StrEnum):
    discovered = "discovered"
    stage_change = "stage_change"
    note = "note"
    cv_generated = "cv_generated"
    cv_approved = "cv_approved"
    draft_created = "draft_created"
    draft_approved = "draft_approved"
    letter_generated = "letter_generated"
    letter_approved = "letter_approved"
    sent = "sent"
    applied = "applied"
    contact_resolved = "contact_resolved"
    response = "response"
    interview = "interview"
    reminder = "reminder"


class CVStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    superseded = "superseded"


class DraftStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"
    queued = "queued"
    sent = "sent"
    failed = "failed"


class QueueStatus(StrEnum):
    idle = "idle"
    running = "running"
    paused = "paused"


class QueueItemStatus(StrEnum):
    pending = "pending"
    sending = "sending"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"
    # Was being sent when the app stopped: never resent blindly; check Gmail's Sent folder.
    unknown = "unknown"


class FitStatus(StrEnum):
    ok = "ok"
    failed = "failed"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class DescriptionLevel(StrEnum):
    full = "full"  # the complete listing text
    summary = "summary"  # e.g. WTTJ search index: summary + key missions
    snippet = "snippet"  # e.g. Adzuna: ~500 chars


class UserLabel(StrEnum):
    good = "good"
    maybe = "maybe"
    no = "no"
