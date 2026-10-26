"""Review CVs → Regenerate selected: the selection the queue accepts, the estimate, the background
queue (a new DRAFT each time, approvals untouched, list order kept) and failed rows with Retry.
Mock generators only: no model, no network."""

import pytest
from sqlmodel import Session, delete, select

from app.db import engine
from app.models import Application, CVVersion, GenerationTask
from app.models.enums import CVStatus, Stage
from app.providers.gemini_generate import GenerationFailed
from app.providers.mock import MockCVGenerator
from app.services import cv_review, cv_service, generation
from tests.test_cv_review import clean
from tests.test_tracking import make_app


@pytest.fixture
def tasks_clean(seeded: None) -> None:
    with Session(engine) as s:
        s.exec(delete(GenerationTask))
        clean(s)
        s.commit()


def reviewable(s: Session) -> int:
    """A shortlisted job with a draft CV written by the mock generator."""
    app = make_app(s, stage=Stage.shortlisted, cv=None)
    s.commit()
    cv_service.generate(engine, app.id, MockCVGenerator())
    return app.id


def versions(app_id: int) -> list[tuple[int, str]]:
    with Session(engine) as s:
        return [(v.version, v.status) for v in s.exec(
            select(CVVersion).where(CVVersion.application_id == app_id)
            .order_by(CVVersion.version)).all()]


def test_the_selection_drops_duplicates_and_jobs_outside_the_list(client, tasks_clean) -> None:  # noqa: ANN001
    with Session(engine) as s:
        a, b = reviewable(s), reviewable(s)
        approved_only = make_app(s, stage=Stage.shortlisted, cv=CVStatus.approved)
        s.commit()
        outside = approved_only.id
    out = client.post("/api/cv/regenerate-batch", json={
        "application_ids": [b, a, b, outside], "mode": "whole"}).json()
    assert out["queued"] == 2 and out["skipped"] == [
        {"application_id": outside, "reason": "Not in the Review CVs list"}]
    with Session(engine) as s:  # queued in the order selected
        assert [t.application_id for t in s.exec(select(GenerationTask).order_by(
            GenerationTask.id)).all()] == [b, a]
    again = client.post("/api/cv/regenerate-batch", json={
        "application_ids": [a], "mode": "whole"}).json()
    assert again["queued"] == 0 and again["already_queued"] == 1  # never two active for a job


def test_the_estimate_and_the_confirmation_above_twenty(client, tasks_clean) -> None:  # noqa: ANN001
    whole = client.get("/api/cv/regenerate-batch/estimate?count=10&mode=whole").json()
    assert (whole["per_cv"], whole["requests"], whole["needs_confirmation"]) == (2, 20, False)
    assert client.get("/api/cv/regenerate-batch/estimate?count=4&mode=whole&feedback=shorter"
                      ).json()["per_cv"] == 3  # the summary is then written toward the feedback
    big = client.get("/api/cv/regenerate-batch/estimate?count=21").json()
    assert big["needs_confirmation"] is True and big["requests"] == 42
    assert big["remaining_gemini"] is not None  # against the daily cap left
    ids = list(range(900_000, 900_021))
    refused = client.post("/api/cv/regenerate-batch", json={"application_ids": ids})
    assert refused.status_code == 409 and "confirm" in refused.json()["detail"]
    assert client.post("/api/cv/regenerate-batch", json={
        "application_ids": ids, "confirm": True}).status_code == 200
    assert client.post("/api/cv/regenerate-batch", json={"application_ids": []}).status_code == 422
    assert client.post("/api/cv/regenerate-batch", json={
        "application_ids": [1], "use": "openai"}).status_code == 422


def test_a_regeneration_is_a_new_draft_and_leaves_the_approved_cv_and_the_order(  # noqa: ANN001
        client, tasks_clean) -> None:
    with Session(engine) as s:
        first, second = reviewable(s), reviewable(s)
        v1 = s.exec(select(CVVersion).where(CVVersion.application_id == first)).one()
        v1.status = CVStatus.approved  # approved v1, then a newer draft v2 for the same job
        s.add(v1)
        s.commit()
    cv_service.generate(engine, first, MockCVGenerator())
    with Session(engine) as s:
        order = [r.application_id for r in cv_review.rows(s)]
    assert order == [first, second] and versions(first) == [(1, "approved"), (2, "draft")]
    rows = {r["application_id"]: r for r in client.get("/api/cv/review").json()}
    assert rows[first]["has_approved"] is True and rows[second]["has_approved"] is False

    client.post("/api/cv/regenerate-batch", json={"application_ids": [first, second]})
    while generation.tick(engine, mock=True):
        pass
    assert versions(first) == [(1, "approved"), (2, "superseded"), (3, "draft")]
    assert versions(second) == [(1, "superseded"), (2, "draft")]
    after = client.get("/api/cv/review").json()
    assert [r["application_id"] for r in after] == order  # the list keeps its order
    assert {r["application_id"]: r["regen"]["status"] for r in after} == {
        first: "done", second: "done"}
    with Session(engine) as s:
        assert Stage(s.get(Application, first).stage) == Stage.shortlisted  # nothing approved


def test_summary_only_rewrites_the_summary_of_the_latest_draft_in_place(  # noqa: ANN001
        client, tasks_clean) -> None:
    with Session(engine) as s:
        app_id = reviewable(s)
    client.post("/api/cv/regenerate-batch", json={
        "application_ids": [app_id], "mode": "summary", "feedback": "shorter"})
    while generation.tick(engine, mock=True):
        pass
    assert versions(app_id) == [(1, "draft")]  # the same draft, not a new version
    with Session(engine) as s:
        (task,) = s.exec(select(GenerationTask)).all()
        assert task.status == "done" and task.details["request"]["feedback"] == "shorter"


def test_a_failed_row_shows_retry_and_a_gemini_retry_runs_once(  # noqa: ANN001
        client, tasks_clean, monkeypatch) -> None:
    with Session(engine) as s:
        app_id = reviewable(s)
    real = cv_service.generate

    def quota(*_a, **_k):  # noqa: ANN002, ANN003
        try:
            raise GenerationFailed("APInex needs the daily check-in (HTTP 402)", retryable=False)
        except GenerationFailed as exc:
            raise cv_service.CVError(str(exc)) from exc

    monkeypatch.setattr(cv_service, "generate", quota)
    client.post("/api/cv/regenerate-batch", json={"application_ids": [app_id]})
    generation.tick(engine, mock=True)
    (row,) = client.get("/api/cv/review").json()
    assert row["regen"]["status"] == "failed" and row["regen"]["retryable"] is False
    assert "402" in row["regen"]["error"]
    assert versions(app_id) == [(1, "draft")]  # nothing changed, nothing switched on its own

    monkeypatch.setattr(cv_service, "generate", real)
    assert client.post("/api/cv/regenerate-batch/retry", json={
        "application_id": app_id, "use": "gemini"}).json()["queued"] == 1
    generation.tick(engine, mock=True)
    with Session(engine) as s:
        last = s.exec(select(GenerationTask).order_by(GenerationTask.id.desc())).first()
        assert last.status == "done" and last.use == "gemini" and last.trigger == "retry"
    assert versions(app_id) == [(1, "superseded"), (2, "draft")]
    assert client.post("/api/cv/regenerate-batch/retry", json={
        "application_id": app_id}).status_code == 409  # nothing failed any more
