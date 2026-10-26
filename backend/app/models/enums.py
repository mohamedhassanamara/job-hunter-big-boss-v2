"""String enums shared by models, schemas and services. Stored as VARCHAR (values, not names)."""

from enum import StrEnum


class Source(StrEnum):
    adzuna = "adzuna"
    remotive = "remotive"
    arbeitnow = "arbeitnow"
    wttj = "wttj"
    boards = "boards"  # company job boards (Greenhouse, Lever, Ashby, Workable, SmartRecruiters)
    bayt = "bayt"
    linkedin = "linkedin"  # imported by you with the LinkedIn bookmark (never discovered/scraped)


# The sources discovery runs: LinkedIn jobs only arrive through your one-click import.
DISCOVERY_SOURCES = [s for s in Source if s != Source.linkedin]


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
    apollo_dump = "apollo_dump"  # from an imported Apollo CSV
    found = "found"  # you found them (Apollo extension) in the Get contact step
    manual = "manual"  # added by hand from Change contact
    hunter = "hunter"  # Try Hunter found the email (you confirmed it)
    prospeo = "prospeo"  # the contact waterfall (Phase 12): see contact.found_by_*
    apollo = "apollo"
    apify = "apify"
    pattern = "pattern"  # email built from the company's pattern, then verified
    linkedin = "linkedin"  # someone to message on LinkedIn (hiring team, alumni…): no email needed


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


class ContactSearch(StrEnum):
    """The company's Get contact state (replaces the old per-company lookup queue)."""

    none = "none"  # nothing special: its jobs join Contacts to get once past New
    not_found = "not_found"  # you looked with the Apollo extension and found nobody
    never = "never"  # a job board / aggregator: never looked up, its jobs go to web apply


class ContactTier(StrEnum):
    imported = "imported"  # an imported (CSV) contact, best ranked
    found = "found"  # a contact you found or added (extension, Hunter, by hand)
    to_get = "to_get"  # nobody yet: in Contacts to get once the job is past New
    none = "none"  # nobody to write to (nobody found, or never looked up)


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
    linkedin = "linkedin"  # Easy Apply, or the company site reached from LinkedIn
    other = "other"


class ResponseChannel(StrEnum):
    """Which track a reply came through (stats per track)."""

    application = "application"
    email = "email"
    linkedin = "linkedin"


class LinkedInGroup(StrEnum):
    """Who to message on LinkedIn, in the order they're suggested."""

    hiring_team = "hiring_team"
    alumni = "alumni"
    lead = "lead"
    recruiter = "recruiter"
    other = "other"


class LinkedInStatus(StrEnum):
    to_contact = "to_contact"
    sent = "sent"  # you sent the connection request yourself
    accepted = "accepted"
    messaged = "messaged"  # you sent the follow-up
    replied = "replied"


class ResponseKind(StrEnum):
    positive = "positive"
    rejection = "rejection"
    other = "other"
    do_not_contact = "do_not_contact"  # asked not to be contacted


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
    interview_prep_generated = "interview_prep_generated"
    interview_prep_approved = "interview_prep_approved"
    letter_approved = "letter_approved"
    sent = "sent"
    applied = "applied"
    applied_undone = "applied_undone"  # you undid "Mark applied"
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
