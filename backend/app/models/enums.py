"""String enums shared by models, schemas and services. Stored as VARCHAR (values, not names)."""

from enum import StrEnum


class Source(StrEnum):
    adzuna = "adzuna"
    remotive = "remotive"
    arbeitnow = "arbeitnow"
    wttj = "wttj"


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


class Stage(StrEnum):
    new = "new"
    shortlisted = "shortlisted"
    cv_ready = "cv_ready"
    ready = "ready"
    done = "done"
    interview = "interview"
    closed = "closed"


class Route(StrEnum):
    undecided = "undecided"
    cold_email = "cold_email"
    web_apply = "web_apply"


class ContactTier(StrEnum):
    apollo_dump = "apollo_dump"
    lookup_queued = "lookup_queued"
    lookup_found = "lookup_found"
    none = "none"


class CloseReason(StrEnum):
    dismissed = "dismissed"
    rejected = "rejected"
    withdrawn = "withdrawn"
    no_response = "no_response"
    offer = "offer"


class EventKind(StrEnum):
    discovered = "discovered"
    stage_change = "stage_change"
    note = "note"
    cv_generated = "cv_generated"
    cv_approved = "cv_approved"
    draft_created = "draft_created"
    draft_approved = "draft_approved"
    sent = "sent"
    applied = "applied"
    contact_resolved = "contact_resolved"


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
