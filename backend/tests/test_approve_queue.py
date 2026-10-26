"""Approve adds to the send queue (setting, default on) and Remove from queue undoes it."""

from sqlmodel import Session, select

from app.db import engine
from app.models import OutreachDraft, SendQueueItem
from app.models.enums import DraftStatus
from tests.test_outreach import fresh_queue, job_ready  # noqa: F401, F811 (fixtures)
from tests.test_queue_restart import drafted


def approved_draft(job_ready: dict) -> int:  # noqa: F811
    draft_id = drafted(job_ready)
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        d.status = DraftStatus.approved
        s.add(d)
        s.commit()
    return draft_id


def test_the_setting_defaults_to_on_and_is_validated(client) -> None:
    from app.services import outreach

    with Session(engine) as s:
        assert outreach.outreach_settings(s)["approve_adds_to_queue"] is True
    current = client.get("/api/settings").json()["values"]["outreach"]
    ok = client.put("/api/settings/outreach", json={"value": {**current,
                                                              "approve_adds_to_queue": False}})
    assert ok.status_code == 200
    assert ok.json()["values"]["outreach"]["approve_adds_to_queue"] is False
    bad = client.put("/api/settings/outreach", json={"value": {**current,
                                                               "approve_adds_to_queue": "yes"}})
    assert bad.status_code == 422
    client.put("/api/settings/outreach", json={"value": current})  # leave it as it was


def test_queueing_an_approved_email_and_removing_it_leaves_it_approved(
        client, job_ready: dict, fresh_queue: None) -> None:  # noqa: F811
    draft_id = approved_draft(job_ready)
    assert client.post(f"/api/outreach/drafts/{draft_id}/queue").json()["status"] == "queued"
    queue = client.get("/api/queue").json()
    item = next(i for i in queue["items"] if i["draft_id"] == draft_id)
    assert client.delete(f"/api/queue/items/{item['id']}").status_code == 200
    with Session(engine) as s:
        assert s.get(OutreachDraft, draft_id).status == DraftStatus.approved
        assert s.exec(select(SendQueueItem).where(SendQueueItem.draft_id == draft_id)).first() \
            is None
    assert client.post(f"/api/outreach/drafts/{draft_id}/queue").status_code == 200  # again


def test_a_full_queue_refuses_so_add_all_can_stop(
        client, job_ready: dict, fresh_queue: None) -> None:  # noqa: F811
    from app.services import send_queue

    first = approved_draft(job_ready)
    with Session(engine) as s:
        q = send_queue.queue(s)
        q.max_items = 1
        s.add(q)
        s.commit()
    assert client.post(f"/api/outreach/drafts/{first}/queue").status_code == 200
    second = approved_draft(job_ready)
    full = client.post(f"/api/outreach/drafts/{second}/queue")
    assert full.status_code == 409 and "full" in full.json()["detail"]
