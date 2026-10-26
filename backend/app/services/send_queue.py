"""The send queue: one approved email at a time, a random gap apart (uniform between the
Settings → Email minimum and maximum, default 4-7 minutes, drawn fresh after every send), at most
`max_items` per queue, pause/resume, persisted in the database so it survives restarts: the
planned next send is `send_queue.next_send_at`, so a restart keeps the schedule and never sends
early or twice.

Safety rules:
- Only approved drafts in the queue are sent, and only while the queue is running.
- The queue can't be started before one successful test send to your own address.
- An item marked `sending` when the app stopped becomes `unknown`: it is never resent blindly
  (check Gmail's Sent folder, then mark it sent or retry it).
- Every attempt is written to `send_log`. A failure is visible and retryable; an auth/config
  failure also pauses the queue.
- A sent email locks the CV version it attached and moves the job to Sent (done) with
  method = email, so follow-ups, replies and stats work as for web applications.
"""

import logging
import random
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import Engine
from sqlmodel import Session, col, func, select

from app.models import (
    Application,
    Company,
    Contact,
    CVVersion,
    Job,
    OutreachDraft,
    QueueEvent,
    SendLog,
    SendQueue,
    SendQueueItem,
)
from app.models.base import utcnow
from app.models.enums import (
    ApplyMethod,
    DraftStatus,
    EventKind,
    QueueItemStatus,
    QueueStatus,
    Stage,
)
from app.providers.base import Mailer, SendFailed
from app.services import dnc, outreach, pipeline, tracking, verifier
from app.services.cv_check import violation

log = logging.getLogger("send_queue")
TICK_SECONDS = 30


class QueueError(ValueError):
    pass


DEFAULT_GAP_MINUTES = (4.0, 7.0)


def gap_bounds(s: Session) -> tuple[float, float]:
    """(minimum, maximum) minutes between two sends, from Settings → Email."""
    cfg = outreach._setting(s, "smtp")
    try:
        lo = float(cfg.get("gap_min_minutes") or DEFAULT_GAP_MINUTES[0])
        hi = float(cfg.get("gap_max_minutes") or DEFAULT_GAP_MINUTES[1])
    except (TypeError, ValueError):
        return DEFAULT_GAP_MINUTES
    return (lo, hi) if 1 <= lo <= hi else DEFAULT_GAP_MINUTES


def draw_gap(lo: float, hi: float, rng: random.Random | None = None) -> timedelta:
    """One random gap, uniform between the bounds (whole seconds)."""
    return timedelta(seconds=round((rng or random).uniform(lo * 60, hi * 60)))


def average_gap(s: Session) -> timedelta:
    lo, hi = gap_bounds(s)
    return timedelta(minutes=(lo + hi) / 2)


def queue(s: Session) -> SendQueue:
    row = s.exec(select(SendQueue)).first()
    if row is None:
        row = SendQueue()
        s.add(row)
        s.flush()
    return row


def set_status(s: Session, q: SendQueue, new: QueueStatus, reason: str | None = None,
               actor: str = "user", now: datetime | None = None) -> None:
    """The only writer of `queue.status`: every real change is logged as a `queue_event`."""
    old = QueueStatus(q.status)
    q.paused_reason = reason if new == QueueStatus.paused else None
    if new != QueueStatus.running:
        q.next_send_at = None
    if old != new:
        s.add(QueueEvent(at=now or utcnow(), from_status=old.value, to_status=new.value,
                         reason=reason, actor=actor))
    q.status = new
    s.add(q)


def pending_count(s: Session, q: SendQueue) -> int:
    return s.exec(select(func.count()).select_from(SendQueueItem).where(
        SendQueueItem.queue_id == q.id, SendQueueItem.status == QueueItemStatus.pending)).one()


def enqueue(s: Session, draft: OutreachDraft) -> bool:
    """Add an approved draft; False when the queue already holds `max_items` pending."""
    contact = s.get(Contact, draft.contact_id) if draft.contact_id else None
    if reason := dnc.blocked_reason(s, contact):
        raise QueueError(f"Do not contact: {reason}")
    q = queue(s)
    if pending_count(s, q) >= q.max_items:
        return False
    last = s.exec(select(func.max(SendQueueItem.position)).where(
        SendQueueItem.queue_id == q.id)).one()
    existing = s.exec(select(SendQueueItem).where(SendQueueItem.draft_id == draft.id)).first()
    if existing is not None:  # a retried item goes back to the end
        existing.status, existing.position, existing.error = QueueItemStatus.pending, \
            (last or 0) + 1, None
        s.add(existing)
    else:
        s.add(SendQueueItem(queue_id=q.id, draft_id=draft.id, position=(last or 0) + 1))
    draft.status = DraftStatus.queued
    s.add(draft)
    # An idle queue (it emptied) starts again for the new email once a test send exists. A
    # paused one (by you, or after a failed send) stays paused until you resume it.
    if QueueStatus(q.status) == QueueStatus.idle and outreach.has_successful_test(s):
        set_status(s, q, QueueStatus.running, "added", "auto_on_add")
        q.next_send_at = utcnow()
    return True


def position_and_eta(s: Session, draft_id: int) -> tuple[int | None, datetime | None]:
    """Where a draft is in the queue (1 = next) and when it should go out (only while the queue
    runs: next_send_at, then the average gap per email ahead of it: an estimate)."""
    q = queue(s)
    pending = s.exec(select(SendQueueItem).where(
        SendQueueItem.queue_id == q.id, SendQueueItem.status == QueueItemStatus.pending)
        .order_by(col(SendQueueItem.position))).all()
    ids = [i.draft_id for i in pending]
    if draft_id not in ids:
        return None, None
    n = ids.index(draft_id)
    eta = None
    if q.status == QueueStatus.running:
        eta = (q.next_send_at or utcnow()) + average_gap(s) * n
    return n + 1, eta


def sent_manually(s: Session, app: Application, sent_at: datetime) -> OutreachDraft:
    """You sent the approved email yourself (from Gmail): recorded like a queue send — CV
    locked, job Sent, method email — and taken out of the queue if it was waiting there."""
    draft = s.exec(select(OutreachDraft).where(
        OutreachDraft.application_id == app.id,
        col(OutreachDraft.status).in_([DraftStatus.approved, DraftStatus.queued]))
        .order_by(col(OutreachDraft.id).desc())).first()
    if draft is None:
        raise QueueError("Approve the email first: that's the version recorded as sent")
    item = s.exec(select(SendQueueItem).where(SendQueueItem.draft_id == draft.id)).first()
    if item is None:
        item = SendQueueItem(queue_id=queue(s).id, draft_id=draft.id, position=0)
        s.add(item)
        s.flush()
    s.add(SendLog(draft_id=draft.id, kind="real", to="", subject=draft.subject, status="sent",
                  error="sent by you outside the app"))
    _mark_sent(s, item, draft, sent_at, None)
    return draft


def resume(s: Session, now: datetime | None = None) -> SendQueue:
    if not outreach.has_successful_test(s):
        raise QueueError("Send one test email to yourself first (Outreach → a draft → "
                         "Send test to me), then start the queue")
    q = queue(s)
    set_status(s, q, QueueStatus.running, "resume", "user", now)
    q.next_send_at = now or utcnow()  # the first email goes out on the next tick
    s.add(q)
    return q


def pause(s: Session) -> SendQueue:
    q = queue(s)
    set_status(s, q, QueueStatus.paused, "manual", "user")
    return q


def recover(engine: Engine) -> int:
    """At startup: an item left `sending` may or may not have gone out. Never resend it."""
    with Session(engine) as s:
        stuck = s.exec(select(SendQueueItem).where(
            SendQueueItem.status == QueueItemStatus.sending)).all()
        for item in stuck:
            item.status = QueueItemStatus.unknown
            item.error = ("The app stopped while sending: check Gmail's Sent folder, then mark "
                          "it sent or retry")
            s.add(item)
        s.commit()
        return len(stuck)


def _mark_sent(s: Session, item: SendQueueItem, draft: OutreachDraft, at: datetime,
               message_id: str | None) -> None:
    item.status, item.sent_at, item.message_id, item.error = QueueItemStatus.sent, at, \
        message_id, None
    draft.status, draft.sent_at, draft.message_id = DraftStatus.sent, at, message_id
    s.add(item)
    s.add(draft)
    app = s.get(Application, draft.application_id)
    cv = s.get(CVVersion, draft.cv_version_id) if draft.cv_version_id else None
    if cv is not None:
        tracking.lock_cv(cv)
        s.add(cv)
    contact = s.get(Contact, draft.contact_id) if draft.contact_id else None
    if app is not None:
        first = app.applied_at  # a web application may already be in (both routes)
        if Stage(app.stage) == Stage.cv_ready:
            pipeline.transition(s, app, Stage.ready)
        if Stage(app.stage) == Stage.ready:
            pipeline.transition(s, app, Stage.done, message="Emailed")
        app.applied_at = min(first, at) if first else at  # the first time you reached out
        app.applied_method = app.applied_method if first else ApplyMethod.email
        app.applied_cv_version_id = cv.id if cv else app.applied_cv_version_id
        s.add(app)
        pipeline.log_event(s, app, EventKind.sent,
                           f"Email sent to {contact.email if contact else '?'}",
                           message_id=message_id, cv_version=cv.version if cv else None)
        job = s.get(Job, app.job_id)
        company = s.get(Company, job.company_id) if job else None
        if company is not None and company.contacted_at is None:
            company.contacted_at = at
            s.add(company)


def _back_to_review(s: Session, item: SendQueueItem, draft: OutreachDraft, entry: SendLog,
                    reason: str, now: datetime) -> None:
    """Not sent: the draft goes back to review with the reason (approving it again verifies
    the current text again); the queue moves on to the next email."""
    message = f"Not sent: {reason}. It's back in review: approve it again to re-verify"
    item.status, item.error = QueueItemStatus.cancelled, message
    draft.status = DraftStatus.draft
    draft.unverified_approval = {}  # approving it again (or unverified again) is a new decision
    draft.violations = [v for v in draft.violations or [] if v.get("type") != "send_gate"] \
        + [violation("send_gate", message, "body")]
    entry.error = message
    s.add_all([item, draft, entry])
    app = s.get(Application, draft.application_id)
    if app is not None:
        pipeline.log_event(s, app, EventKind.note, message)
    q = queue(s)
    q.next_send_at = now  # nothing went out: the next email can go on the next tick
    s.add(q)
    s.commit()
    log.warning("draft %s not sent: %s", draft.id, reason)


def tick(engine: Engine, mailer_for: Callable[[Session], Mailer],
         now: datetime | None = None) -> str:
    """Send at most one email if the queue is running and due. Returns what happened."""
    now = now or utcnow()
    with Session(engine) as s:
        q = queue(s)
        if q.status != QueueStatus.running:
            return "not running"
        if q.next_send_at and now < q.next_send_at:
            return "waiting"
        item = s.exec(select(SendQueueItem).where(
            SendQueueItem.queue_id == q.id, SendQueueItem.status == QueueItemStatus.pending)
            .order_by(col(SendQueueItem.position))).first()
        if item is None:
            set_status(s, q, QueueStatus.idle, "empty", "worker", now)
            s.commit()
            return "empty"
        draft = s.get(OutreachDraft, item.draft_id)
        if draft is None or draft.status not in (DraftStatus.queued, DraftStatus.approved):
            item.status, item.error = QueueItemStatus.cancelled, "The draft is no longer approved"
            s.add(item)
            s.commit()
            return "skipped"
        item.status, item.attempts, item.last_attempt_at = QueueItemStatus.sending, \
            item.attempts + 1, now
        s.add(item)
        s.commit()  # persisted before sending: a crash from here on leaves `sending` → unknown
        item_id, draft_id = item.id, draft.id
    with Session(engine) as s:
        item, draft = s.get(SendQueueItem, item_id), s.get(OutreachDraft, draft_id)
        entry = SendLog(draft_id=draft_id, kind="real", to="", subject=draft.subject,
                        status="failed")
        try:
            email = outreach.outgoing(s, engine, draft)
            entry.to, entry.subject, entry.attachment = email.to, email.subject, \
                email.attachment_name
            # Asked not to be contacted (flag, address or domain): pulled back with the reason.
            contact = s.get(Contact, draft.contact_id) if draft.contact_id else None
            if reason := dnc.blocked_reason(s, contact, email.to):
                _back_to_review(s, item, draft, entry, f"do not contact: {reason}", now)
                return "blocked"
            # The final gate: exactly the text and CV that were approved and verified.
            if reason := verifier.send_gate(draft, email.subject, email.body,
                                            email.attachment_path, email.to):
                _back_to_review(s, item, draft, entry, reason, now)
                return "blocked"
            message_id = mailer_for(s).send(email)
        except (SendFailed, outreach.OutreachError) as exc:
            fatal = isinstance(exc, SendFailed) and exc.fatal
            item.status, item.error = QueueItemStatus.failed, str(exc)
            entry.error = str(exc)
            s.add(item)
            s.add(entry)
            q = queue(s)
            if fatal:
                set_status(s, q, QueueStatus.paused, "fatal", "worker", now)
            else:
                q.next_send_at = now + draw_gap(*gap_bounds(s))
            s.add(q)
            s.commit()
            log.warning("send failed for draft %s: %s", draft_id, exc)
            return "failed (queue paused)" if fatal else "failed"
        entry.status, entry.message_id = "sent", message_id
        s.add(entry)
        _mark_sent(s, item, draft, now, message_id)
        q = queue(s)
        q.next_send_at = now + draw_gap(*gap_bounds(s))  # a fresh gap after every send
        s.add(q)
        s.commit()
        return "sent"


def retry(s: Session, item: SendQueueItem) -> SendQueueItem:
    """A failed or unknown item goes back to the end of the queue."""
    if item.status not in (QueueItemStatus.failed, QueueItemStatus.unknown):
        raise QueueError("Only failed or unknown items can be retried")
    draft = s.get(OutreachDraft, item.draft_id)
    if draft is None:
        raise QueueError("Draft not found")
    draft.status = DraftStatus.approved
    if not enqueue(s, draft):
        raise QueueError("The queue is full (20 pending); wait for some to go out")
    return item


def mark_sent(s: Session, item: SendQueueItem, now: datetime | None = None) -> SendQueueItem:
    """An `unknown` item you found in Gmail's Sent folder."""
    if item.status != QueueItemStatus.unknown:
        raise QueueError("Only items with an unknown outcome can be marked sent")
    draft = s.get(OutreachDraft, item.draft_id)
    s.add(SendLog(draft_id=item.draft_id, kind="real", to="", subject=draft.subject,
                  status="sent", error="marked sent by you (found in Gmail)"))
    _mark_sent(s, item, draft, item.last_attempt_at or now or utcnow(), None)
    return item


# ------------------------------------------------------------------------------------ worker

_stop = threading.Event()
_thread: threading.Thread | None = None


def default_mailer(s: Session) -> Mailer:
    from app.providers.registry import mailer

    smtp = outreach._setting(s, "smtp")
    return mailer(address=smtp.get("address", ""), from_name=smtp.get("from_name", ""))


def start_worker(engine: Engine) -> None:
    global _thread
    if _thread is not None:
        return
    recovered = recover(engine)
    if recovered:
        log.warning("%s email(s) were being sent when the app stopped: marked unknown",
                    recovered)

    def loop() -> None:
        while not _stop.wait(TICK_SECONDS):
            try:
                tick(engine, default_mailer)
            except Exception:
                log.exception("send queue tick failed")

    _thread = threading.Thread(target=loop, name="send-queue", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()
