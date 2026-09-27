import threading

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.models import ExperienceItem, Job
from app.models.enums import FitStatus
from app.providers.base import FitAssessment, JobSnapshot, ScoringFailed, SubScore
from app.services import scoring


class CountingScorer:
    model = "test-model"

    def __init__(self, fail: bool = False, gate: threading.Event | None = None):
        self.calls = 0
        self.fail = fail
        self.gate = gate
        self.lock = threading.Lock()

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        with self.lock:
            self.calls += 1
        if self.gate:
            self.gate.wait(5)
        if self.fail:
            raise ScoringFailed("Invalid model output after a retry: role_match: missing")
        quote = " ".join(job.description.split()[:6])
        sub = SubScore(score=8, reason="fits", evidence=quote)
        return FitAssessment(role_match=sub, skills_match=sub, seniority_fit=sub,
                             location_eligibility=sub, language_requirements=sub,
                             strengths=["x"], gaps=[], summary="ok")


def first_job_id() -> int:
    with Session(engine) as s:
        return s.exec(select(Job.id)).first()


def test_score_is_cached_until_something_changes(seeded: None) -> None:
    job_id, scorer = first_job_id(), CountingScorer()
    row = scoring.score_job(engine, job_id, scorer)
    assert row.status == FitStatus.ok and row.score == 80 and scorer.calls == 1
    assert row.sub_scores["role_match"]["evidence_verified"] is True
    again = scoring.score_job(engine, job_id, scorer)
    assert again.id == row.id and scorer.calls == 1  # cache hit: no LLM call

    with Session(engine) as s:  # the listing changed upstream → new content hash → rescore
        job = s.get(Job, job_id)
        job.description += "\nNew requirement: Kafka."
        s.add(job)
        s.commit()
    scoring.score_job(engine, job_id, scorer)
    assert scorer.calls == 2
    scoring.score_job(engine, job_id, scorer, force=True)
    assert scorer.calls == 3


def test_failures_are_stored_with_the_error_and_no_score(seeded: None) -> None:
    row = scoring.score_job(engine, first_job_id(), CountingScorer(fail=True))
    assert row.status == FitStatus.failed and row.score is None
    assert "Invalid model output" in (row.error or "")


def test_experience_change_marks_scores_stale_without_rescoring(seeded: None) -> None:
    scorer = CountingScorer()
    job_id = first_job_id()
    scoring.score_job(engine, job_id, scorer)
    with Session(engine) as s:
        before = scoring.counts(s)
        s.add(ExperienceItem(kind="skill", title="New skill group", tags=["rust"]))
        s.commit()
        after = scoring.counts(s)
    assert job_id not in before.stale_ids and job_id in after.stale_ids
    assert scorer.calls == 1  # nothing rescored automatically


def test_queue_runs_in_background_and_can_cancel(seeded: None) -> None:
    gate = threading.Event()
    scorer = CountingScorer(gate=gate)
    queue = scoring.ScoringQueue(engine, lambda model: scorer)
    with Session(engine) as s:
        ids = list(s.exec(select(Job.id)).all())[:6]
    assert queue.enqueue(ids, force=True) == 6
    assert queue.enqueue(ids[:2]) == 0  # already queued: deduplicated
    status = queue.status()
    assert status["running"] and status["total"] == 6
    assert queue.cancel() >= 4  # pending ones dropped; the in-flight one finishes
    gate.set()
    assert queue.wait()
    assert queue.status()["running"] is False and scorer.calls <= 2


def test_queue_isolates_failures(seeded: None) -> None:
    scorer = CountingScorer(fail=True)
    queue = scoring.ScoringQueue(engine, lambda model: scorer)
    with Session(engine) as s:
        ids = list(s.exec(select(Job.id)).all())[:3]
    queue.enqueue(ids, force=True)
    assert queue.wait()
    status = queue.status()
    assert status["failed"] == 3 and "Invalid model output" in status["last_error"]


def test_blocked_when_model_missing(seeded: None) -> None:
    class Unhealthy(CountingScorer):
        def health(self):  # noqa: ANN201
            class H:
                ok = False
                message = "Model qwen2.5:7b isn't pulled. Run: ollama pull qwen2.5:7b"
            return H()

    queue = scoring.ScoringQueue(engine, lambda model: Unhealthy())
    queue.enqueue([first_job_id()])
    assert "ollama pull" in (queue.blocked or "") and not queue.status()["running"]


def test_weights_change_recomputes_without_llm(client: TestClient) -> None:
    scorer = CountingScorer()
    job_id = first_job_id()
    scoring.score_job(engine, job_id, scorer)
    weights = {"role_match": 1, "skills_match": 0, "seniority_fit": 0,
               "location_eligibility": 0, "language_requirements": 0}
    settings = client.get("/api/settings").json()["values"]["scoring"]
    client.put("/api/settings/scoring", json={"value": {**settings, "weights": weights}})
    with Session(engine) as s:
        latest = scoring.latest_fit(s, job_id)
    assert latest.score == 80 and scorer.calls == 1


def test_api_status_rescore_and_labels(client: TestClient) -> None:
    status = client.get("/api/scoring/status").json()
    assert status["jobs_total"] > 0 and status["prompt_version"].startswith("fit_score/v")
    assert client.get("/api/scoring/health").json()["model_present"] is True  # mock in tests
    job_id = first_job_id()
    assert client.post(f"/api/jobs/{job_id}/rescore").json()["enqueued"] == 1
    scoring.workspace_queue("real").wait()
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["fit_detail"]["status"] == "ok" and detail["fit_detail"]["sub_scores"]
    labeled = client.put(f"/api/jobs/{job_id}/label", json={"label": "good"}).json()
    assert labeled["user_label"] == "good"
    assert client.put(f"/api/jobs/{job_id}/label", json={"label": None}).json()["user_label"] is None
    assert client.put(f"/api/jobs/{job_id}/label", json={"label": "meh"}).status_code == 422


@pytest.fixture(autouse=True)
def _drain_queues():
    yield
    for q in scoring._queues.values():
        q.cancel()
        q.wait(5)


def test_cloud_models_may_run_more_workers() -> None:
    from app.services.scoring import max_concurrency

    assert max_concurrency("qwen2.5:7b") == 2
    assert max_concurrency("gemma4:31b-cloud") == 8
