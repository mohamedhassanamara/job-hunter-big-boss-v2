"""The cold-email route inside the job flow: effective route, the `drafted` stage, approve vs.
add to queue, "I sent it myself", and the Job page step endpoint."""

from sqlmodel import Session

from app.db import engine
from app.models import Application, Contact, CVVersion
from app.models.enums import Route, Stage
from app.services import outreach, pipeline
from tests.test_outreach import Script, good_plan, job_ready  # noqa: F401 (fixture)


def test_effective_route_follows_the_contact_until_set() -> None:
    app = Application(job_id=1, stage=Stage.new, route=Route.undecided)
    assert pipeline.effective_route(app) == Route.web_apply
    app.contact_id = 5
    assert pipeline.effective_route(app) == Route.cold_email
    app.route = Route.web_apply
    assert pipeline.effective_route(app) == Route.web_apply  # an explicit route wins


def test_stage_labels_for_both_routes() -> None:
    assert pipeline.stage_label(Stage.drafted, Route.cold_email) == "Email drafted"
    assert pipeline.stage_label(Stage.ready, Route.cold_email) == "Ready to send"
    assert pipeline.stage_label(Stage.ready, Route.web_apply) == "Ready to apply"
    assert pipeline.stage_label(Stage.done, Route.cold_email) == "Sent"
    assert pipeline.stage_label(Stage.done, Route.web_apply) == "Applied"
    assert pipeline.can_transition(Stage.cv_ready, Stage.drafted)
    assert pipeline.can_transition(Stage.drafted, Stage.ready)
    assert not pipeline.can_transition(Stage.drafted, Stage.done)


def step(client, app_id: int) -> dict:  # noqa: ANN001
    return client.get(f"/api/applications/{app_id}/outreach").json()


def test_email_route_end_to_end_through_the_api(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    app_id = job_ready["app"]
    assert step(client, app_id)["step"] == "draft"
    draft = outreach.generate(engine, app_id, Script(good_plan(job_ready)))
    with Session(engine) as s:
        assert s.get(Application, app_id).stage == Stage.drafted
    assert step(client, app_id)["step"] == "review"

    approved = client.post(f"/api/outreach/drafts/{draft.id}/approve").json()
    assert approved["status"] == "approved"
    with Session(engine) as s:
        assert s.get(Application, app_id).stage == Stage.ready  # Ready to send, not queued
    assert step(client, app_id)["step"] == "queue"

    queued = client.post(f"/api/outreach/drafts/{draft.id}/queue").json()
    assert queued["status"] == "queued"
    now = step(client, app_id)
    assert now["step"] == "queued" and now["queue_position"] >= 1

    items = client.get("/api/queue").json()["items"]
    item = next(i for i in items if i["draft_id"] == draft.id)
    client.delete(f"/api/queue/items/{item['id']}")
    assert step(client, app_id)["step"] == "queue"  # removed: still approved

    sent = client.post(f"/api/applications/{app_id}/sent-manually",
                       json={"sent_on": "2026-09-30"}).json()
    assert sent["step"] == "sent" and sent["sent_at"].startswith("2026-09-30")
    with Session(engine) as s:
        app = s.get(Application, app_id)
        assert (app.stage, app.applied_method) == (Stage.done, "email")
        assert s.get(CVVersion, job_ready["cv"]).locked_at is not None


def test_rejecting_the_last_draft_goes_back_to_cv_ready_and_restore_returns(
        job_ready: dict, client) -> None:  # noqa: F811, ANN001
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    client.post(f"/api/outreach/drafts/{draft.id}/reject")
    with Session(engine) as s:
        assert s.get(Application, job_ready["app"]).stage == Stage.cv_ready
    client.post(f"/api/outreach/drafts/{draft.id}/restore")
    with Session(engine) as s:
        assert s.get(Application, job_ready["app"]).stage == Stage.drafted


def test_patch_cannot_skip_the_email_steps(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    app_id = job_ready["app"]
    assert client.patch(f"/api/applications/{app_id}", json={"stage": "drafted"}).status_code == 409
    with Session(engine) as s:
        app = s.get(Application, app_id)
        app.stage = Stage.ready
        s.add(app)
        s.commit()
    r = client.patch(f"/api/applications/{app_id}", json={"stage": "done"})
    assert r.status_code == 409 and "sent" in r.json()["detail"].lower()


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
    assert step(client, app_id)["step"] == "contact"
    with Session(engine) as s:
        app = s.get(Application, app_id)
        app.contact_id = contact_id
        s.get(CVVersion, job_ready["cv"]).status = "draft"
        s.add(app)
        s.commit()
    assert step(client, app_id)["step"] == "cv"


def test_dtos_carry_the_effective_route(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        job_id = app.job_id
        assert s.get(Contact, app.contact_id) is not None
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["application"]["effective_route"] == "cold_email"
    card = next(c for c in client.get("/api/applications").json()
                if c["application_id"] == job_ready["app"])
    assert card["effective_route"] == "cold_email"
