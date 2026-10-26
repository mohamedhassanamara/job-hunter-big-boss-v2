"""An emptied (idle) send queue restarts when an approved email is added; a paused one never
does; every state change is logged."""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.db import engine
from app.models import OutreachDraft, QueueEvent, SendLog, SendQueueItem
from app.models.enums import QueueStatus
from app.providers.mock import MockMailer
from app.services import outreach, send_queue
from tests.test_outreach import (  # noqa: F401, F811 (fixtures)
    NOW,
    Script,
    fresh_queue,
    good_plan,
    job_ready,
    mark_verified,
)


def set_test_send(s: Session, present: bool) -> None:
    for row in s.exec(select(SendLog).where(SendLog.kind == "test")).all():
        s.delete(row)
    if present:
        s.add(SendLog(kind="test", to="me@example.com", subject="test", status="sent"))
    s.commit()


def events(s: Session) -> list[tuple[str, str, str | None, str]]:
    rows = s.exec(select(QueueEvent).order_by(QueueEvent.id)).all()
    return [(e.from_status, e.to_status, e.reason, e.actor) for e in rows]


def drafted(job_ready: dict) -> int:  # noqa: F811
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    with Session(engine) as s:
        mark_verified(s, s.get(OutreachDraft, draft.id))
        s.commit()
    return draft.id


def enqueue(draft_id: int) -> None:
    with Session(engine) as s:
        assert send_queue.enqueue(s, s.get(OutreachDraft, draft_id))
        s.commit()


def test_adding_to_an_idle_queue_starts_it_and_the_next_tick_sends(
        job_ready: dict, fresh_queue: None) -> None:  # noqa: F811  # noqa: F811
    with Session(engine) as s:
        for e in s.exec(select(QueueEvent)).all():
            s.delete(e)
        set_test_send(s, True)
    draft_id = drafted(job_ready)
    enqueue(draft_id)
    with Session(engine) as s:
        q = send_queue.queue(s)
        assert q.status == QueueStatus.running and q.next_send_at is not None
        assert events(s) == [("idle", "running", "added", "auto_on_add")]
    mailer = MockMailer()
    assert send_queue.tick(engine, lambda s: mailer, datetime.now(UTC)) == "sent"
    assert len(mailer.sent) == 1
    # nothing left: the next tick idles the queue, and that is logged too
    later = datetime.now(UTC) + timedelta(hours=1)  # past the random gap
    assert send_queue.tick(engine, lambda s: mailer, later) == "empty"
    with Session(engine) as s:
        assert events(s)[-1] == ("running", "idle", "empty", "worker")


def test_without_a_test_send_the_queue_stays_idle(job_ready: dict, fresh_queue: None) -> None:  # noqa: F811
    with Session(engine) as s:
        set_test_send(s, False)
    enqueue(drafted(job_ready))
    with Session(engine) as s:
        assert send_queue.queue(s).status == QueueStatus.idle


def test_a_queue_you_paused_stays_paused(job_ready: dict, fresh_queue: None) -> None:  # noqa: F811
    with Session(engine) as s:
        set_test_send(s, True)
        send_queue.resume(s, NOW)
        send_queue.pause(s)
        s.commit()
    enqueue(drafted(job_ready))
    with Session(engine) as s:
        q = send_queue.queue(s)
        assert q.status == QueueStatus.paused and q.paused_reason == "manual"
        assert events(s)[-2:] == [("idle", "running", "resume", "user"),
                                  ("running", "paused", "manual", "user")]
        send_queue.resume(s, NOW)
        s.commit()
        assert send_queue.queue(s).paused_reason is None
        assert events(s)[-1] == ("paused", "running", "resume", "user")


def test_a_fatal_pause_is_not_restarted_by_adding(job_ready: dict, fresh_queue: None) -> None:  # noqa: F811
    from app.providers.base import SendFailed

    class Refuses(MockMailer):
        def send(self, email):  # noqa: ANN001
            raise SendFailed("The password was refused", fatal=True)

    with Session(engine) as s:
        set_test_send(s, True)
    enqueue(drafted(job_ready))
    now = datetime.now(UTC)
    assert send_queue.tick(engine, lambda s: Refuses(), now) == "failed (queue paused)"
    with Session(engine) as s:
        q = send_queue.queue(s)
        assert q.status == QueueStatus.paused and q.paused_reason == "fatal"
        assert events(s)[-1] == ("running", "paused", "fatal", "worker")
        item = s.exec(select(SendQueueItem)).first()
        assert item is not None
