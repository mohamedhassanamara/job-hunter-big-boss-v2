"""Two tracks per job, derived (no state of their own besides `application.web_applied_at`):

- Application (the web application): not_ready (no approved CV) → ready → applied.
- Outreach (the cold email): no_contact → contact → drafted → approved → queued → sent.

A job can do both. `application.stage` stays the overall position; `done` means at least one
track finished, labelled "Applied", "Emailed" or "Applied + emailed".
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from app.models import Application, Contact, CVVersion, OutreachDraft
from app.models.enums import CVStatus, DraftStatus, Stage

_DRAFT_ORDER = {DraftStatus.sent: 5, DraftStatus.queued: 4, DraftStatus.failed: 4,
                DraftStatus.approved: 3, DraftStatus.draft: 2}
_OUTREACH = {DraftStatus.sent: "sent", DraftStatus.queued: "queued",
             DraftStatus.failed: "queued", DraftStatus.approved: "approved",
             DraftStatus.draft: "drafted"}


@dataclass
class Tracks:
    application: str  # not_ready | ready | applied
    outreach: str  # no_contact | contact | drafted | approved | queued | sent
    applied_at: datetime | None = None
    web_method: str | None = None
    contact_name: str | None = None
    draft_id: int | None = None
    sent_at: datetime | None = None

    @property
    def applied(self) -> bool:
        return self.application == "applied"

    @property
    def emailed(self) -> bool:
        return self.outreach == "sent"


def application_status(app: Application, has_approved_cv: bool) -> str:
    if app.web_applied_at is not None:
        return "applied"
    return "ready" if has_approved_cv else "not_ready"


def outreach_status(app: Application, draft: OutreachDraft | None) -> str:
    if draft is not None:
        return _OUTREACH[DraftStatus(draft.status)]
    return "contact" if app.contact_id else "no_contact"


def latest_draft(drafts: Iterable[OutreachDraft]) -> OutreachDraft | None:
    """The draft that tells where the email is: the furthest along, newest first."""
    live = [d for d in drafts if DraftStatus(d.status) in _DRAFT_ORDER]
    return max(live, key=lambda d: (_DRAFT_ORDER[DraftStatus(d.status)], d.id or 0),
               default=None)


def for_apps(s: Session, apps: list[Application]) -> dict[int, Tracks]:
    """Both tracks for many applications with three queries."""
    ids = [a.id for a in apps if a.id is not None]
    if not ids:
        return {}
    approved = set(s.exec(select(CVVersion.application_id).where(
        col(CVVersion.application_id).in_(ids), CVVersion.status == CVStatus.approved)).all())
    drafts: dict[int, list[OutreachDraft]] = {}
    for d in s.exec(select(OutreachDraft).where(col(OutreachDraft.application_id).in_(ids))).all():
        drafts.setdefault(d.application_id, []).append(d)
    contact_ids = {a.contact_id for a in apps if a.contact_id}
    names = {c.id: c.full_name for c in s.exec(
        select(Contact).where(col(Contact.id).in_(contact_ids))).all()} if contact_ids else {}
    out = {}
    for a in apps:
        draft = latest_draft(drafts.get(a.id, []))
        out[a.id] = Tracks(
            application=application_status(a, a.id in approved),
            outreach=outreach_status(a, draft), applied_at=a.web_applied_at,
            web_method=a.web_method, contact_name=names.get(a.contact_id),
            draft_id=draft.id if draft else None,
            sent_at=draft.sent_at if draft and DraftStatus(draft.status) == DraftStatus.sent
            else None)
    return out


def for_app(s: Session, app: Application) -> Tracks:
    return for_apps(s, [app])[app.id]


def done_label(tracks: Tracks | None) -> str:
    if tracks is None:
        return "Done"
    if tracks.applied and tracks.emailed:
        return "Applied + emailed"
    return "Emailed" if tracks.emailed else "Applied"


def ready_label(tracks: Tracks | None) -> str:
    if tracks is not None and tracks.outreach in ("approved", "queued"):
        return "Ready to send"
    return "Ready to apply"


def stage_label(stage: Stage | str, tracks: Tracks | None = None) -> str:
    from app.services.pipeline import STAGE_LABELS

    stage = Stage(stage)
    if stage == Stage.done:
        return done_label(tracks)
    if stage == Stage.ready:
        return ready_label(tracks)
    return STAGE_LABELS[stage]
