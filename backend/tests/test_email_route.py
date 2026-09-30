"""Both routes on one job: the Application and Outreach tracks, derived from the data; the stage
reaches `done` with the first route and never goes back; approve vs. add to queue; "I sent it
myself"; the Job page step endpoint."""

from sqlmodel import Session

from app.db import engine
from app.models import Application, Contact, CVVersion, OutreachDraft
from app.models.base import utcnow
from app.models.enums import DraftStatus, Stage
from app.services import outreach, pipeline, tracks
from tests.test_outreach import Script, good_plan, job_ready  # noqa: F401 (fixture)


def test_tracks_are_derived_from_the_data() -> None:
    app = Application(id=1, job_id=1, stage=Stage.new)
    assert tracks.application_status(app, has_approved_cv=False) == "not_ready"
    assert tracks.application_status(app, has_approved_cv=True) == "ready"
    assert tracks.outreach_status(app, None) == "no_contact"
    app.contact_id = 5
    assert tracks.outreach_status(app, None) == "contact"
    drafts = [OutreachDraft(id=1, application_id=1, status=DraftStatus.sent),
              OutreachDraft(id=2, application_id=1, status=DraftStatus.draft),
              OutreachDraft(id=3, application_id=1, status=DraftStatus.rejected)]
    assert tracks.latest_draft(drafts).id == 1  # the furthest along wins
    assert tracks.outreach_status(app, tracks.latest_draft(drafts)) == "sent"


def test_stage_moves_no_longer_have_an_email_only_stage() -> None:
    assert not any(s.value == "drafted" for s in Stage)
    assert pipeline.can_transition(Stage.cv_ready, Stage.ready)
    assert pipeline.can_transition(Stage.ready, Stage.done)
    assert not pipeline.can_transition(Stage.cv_ready, Stage.done)


def app_json(client, app_id: int) -> dict:  # noqa: ANN001
    return next(c for c in client.get("/api/applications").json()
                if c["application_id"] == app_id)


def step(client, app_id: int) -> dict:  # noqa: ANN001
    return client.get(f"/api/applications/{app_id}/outreach").json()


def test_apply_then_email_on_the_same_job(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    app_id = job_ready["app"]
    card = app_json(client, app_id)
    assert card["tracks"]["application"] == "ready" and card["tracks"]["outreach"] == "contact"

    draft = outreach.generate(engine, app_id, Script(good_plan(job_ready)))
    card = app_json(client, app_id)
    assert card["stage"] == "cv_ready" and card["tracks"]["outreach"] == "drafted"
    assert step(client, app_id)["step"] == "review"

    client.post(f"/api/outreach/drafts/{draft.id}/approve")
    card = app_json(client, app_id)
    assert (card["stage"], card["stage_label"]) == ("ready", "Ready to send")
    client.post(f"/api/outreach/drafts/{draft.id}/queue")
    assert app_json(client, app_id)["tracks"]["outreach"] == "queued"
    item = next(i for i in client.get("/api/queue").json()["items"] if i["draft_id"] == draft.id)
    client.delete(f"/api/queue/items/{item['id']}")
    assert app_json(client, app_id)["tracks"]["outreach"] == "approved"

    r = client.post(f"/api/applications/{app_id}/applied",
                    json={"method": "company_site", "applied_on": "2026-09-29"})
    assert r.status_code == 200, r.text
    card = app_json(client, app_id)
    assert (card["stage"], card["stage_label"]) == ("done", "Applied")
    assert card["tracks"]["application"] == "applied"
    assert card["tracks"]["outreach"] == "approved"  # the email can still go out

    sent = client.post(f"/api/applications/{app_id}/sent-manually", json={"sent_on": "2026-09-30"})
    assert sent.json()["step"] == "sent"
    card = app_json(client, app_id)
    assert (card["stage"], card["stage_label"]) == ("done", "Applied + emailed")
    with Session(engine) as s:
        app = s.get(Application, app_id)
        assert app.web_applied_at.date().isoformat() == "2026-09-29"
        assert app.applied_at.date().isoformat() == "2026-09-29"  # the first time you reached out
        assert s.get(CVVersion, job_ready["cv"]).locked_at is not None


def test_email_then_apply_on_the_same_job(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    app_id = job_ready["app"]
    draft = outreach.generate(engine, app_id, Script(good_plan(job_ready)))
    client.post(f"/api/outreach/drafts/{draft.id}/approve")
    client.post(f"/api/applications/{app_id}/sent-manually", json={"sent_on": "2026-09-28"})
    card = app_json(client, app_id)
    assert (card["stage"], card["stage_label"]) == ("done", "Emailed")
    ready = [r["application_id"] for r in client.get("/api/applications/ready").json()]
    assert app_id in ready  # still to apply on the website
    client.post(f"/api/applications/{app_id}/applied", json={"method": "company_site"})
    card = app_json(client, app_id)
    assert (card["stage"], card["stage_label"]) == ("done", "Applied + emailed")
    with Session(engine) as s:
        app = s.get(Application, app_id)
        assert app.applied_at.date().isoformat() == "2026-09-28" and app.applied_method == "email"
    assert app_id not in [r["application_id"] for r in client.get("/api/applications/ready").json()]


def test_reject_and_restore_only_change_the_draft(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    client.post(f"/api/outreach/drafts/{draft.id}/reject")
    card = app_json(client, job_ready["app"])
    assert card["stage"] == "cv_ready" and card["tracks"]["outreach"] == "contact"
    client.post(f"/api/outreach/drafts/{draft.id}/restore")
    assert app_json(client, job_ready["app"])["tracks"]["outreach"] == "drafted"


def test_patch_cannot_mark_done(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    app_id = job_ready["app"]
    with Session(engine) as s:
        app = s.get(Application, app_id)
        app.stage = Stage.ready
        s.add(app)
        s.commit()
    r = client.patch(f"/api/applications/{app_id}", json={"stage": "done"})
    assert r.status_code == 409 and "Mark applied" in r.json()["detail"]
    assert client.patch(f"/api/applications/{app_id}", json={"stage": "drafted"}).status_code == 422


def test_sent_manually_needs_an_approved_email(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    r = client.post(f"/api/applications/{job_ready['app']}/sent-manually", json={})
    assert r.status_code == 409 and "Approve" in r.json()["detail"]


def test_steps_before_a_draft_contact_then_cv(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    app_id = job_ready["app"]
    with Session(engine) as s:
        app = s.get(Application, app_id)
        contact_id, app.contact_id = app.contact_id, None
        s.add(app)
        s.commit()
    assert step(client, app_id)["step"] == "get_contact"
    with Session(engine) as s:  # a contact that was never verified: verify first
        app = s.get(Application, app_id)
        app.contact_id = contact_id
        s.get(Contact, contact_id).verified_at = None
        s.add(app)
        s.commit()
    assert step(client, app_id)["step"] == "verify_contact"
    with Session(engine) as s:
        s.get(Contact, contact_id).verified_at = utcnow()
        s.get(CVVersion, job_ready["cv"]).status = "draft"
        s.commit()
    assert step(client, app_id)["step"] == "cv"


def test_job_detail_carries_both_tracks(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        job_id = s.get(Application, job_ready["app"]).job_id
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["application"]["tracks"]["application"] == "ready"
    assert detail["application"]["tracks"]["outreach"] == "contact"
    assert detail["application"]["tracks"]["contact_name"].startswith("Ana")
