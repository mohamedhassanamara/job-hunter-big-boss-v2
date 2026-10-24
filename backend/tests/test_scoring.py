import threading

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.models import ExperienceItem, Job
from app.models.enums import FitStatus
from app.providers.base import CoreRequirement, FitAssessment, JobSnapshot, ScoringFailed, SubScore
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
    assert queue.enqueue(ids, force=True, only_open=False) == 6
    assert queue.enqueue(ids[:2]) == 0  # already queued: deduplicated
    status = queue.status()
    assert status["running"] and status["total"] == 6
    # Default model is cloud (4 workers): up to 4 in flight; the rest are dropped.
    assert queue.cancel() >= 2
    gate.set()
    assert queue.wait()
    assert queue.status()["running"] is False and scorer.calls <= 4


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


def test_bulk_rescore_of_existing_scores_needs_confirmation(client: TestClient) -> None:
    preview = client.get("/api/scoring/rescore-preview?scope=all").json()
    assert preview["count"] > 0 and preview["model"] and preview["eta_seconds"] is not None
    assert client.post("/api/scoring/rescore", json={"scope": "all"}).status_code == 409
    assert client.post("/api/scoring/rescore", json={"scope": "stale"}).status_code == 409
    assert client.post("/api/scoring/rescore", json={"scope": "failed"}).status_code == 200
    ok = client.post("/api/scoring/rescore", json={"scope": "all", "confirm": True})
    assert ok.status_code == 200 and ok.json()["enqueued"] > 0
    scoring.workspace_queue("real").cancel()


def test_cache_hit_from_a_duplicate_gives_the_job_its_own_score(seeded: None) -> None:
    """Two jobs with identical content (cross-source duplicates): the second reuses the first's
    result without a model call, but still gets its own fit_score row."""
    scorer = CountingScorer()
    with Session(engine) as s:
        first = s.exec(select(Job)).first()
        twin = Job(**first.model_dump(exclude={"id", "created_at", "updated_at", "external_id",
                                               "source"}),
                   source="wttj", external_id="twin-1")
        s.add(twin)
        s.commit()
        first_id, twin_id = first.id, twin.id
    a = scoring.score_job(engine, first_id, scorer, force=True)
    b = scoring.score_job(engine, twin_id, scorer)
    assert scorer.calls == 1  # cache hit, no second model call
    assert b.job_id == twin_id and b.id != a.id and b.score == a.score
    with Session(engine) as s:
        assert scoring.latest_fit(s, twin_id).id == b.id


class MissingCoreScorer(CountingScorer):
    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        base = super().assess(system, user, job)
        quote = " ".join(job.description.split()[:6])
        base.core_requirements = [CoreRequirement(requirement="Cobol", evidence=quote, missing=True)]
        return base


def test_a_missing_core_requirement_is_stored_capped_and_shown_in_the_api(client: TestClient) -> None:
    job_id = first_job_id()
    row = scoring.score_job(engine, job_id, MissingCoreScorer())
    assert row.score == 60 and row.core_requirements[0]["counts"] is True
    detail = client.get(f"/api/jobs/{job_id}").json()["fit_detail"]
    assert detail["capped_by"] == "missing_core" and detail["missing_core"] == "Cobol"
    assert detail["core_requirements"][0]["requirement"] == "Cobol"
    # the cap is a setting: raising it to 100 recomputes the stored score without a model call
    scoring_cfg = client.get("/api/settings").json()["values"]["scoring"]
    client.put("/api/settings/scoring", json={"value": {**scoring_cfg, "missing_core_cap": 100}})
    assert client.get(f"/api/jobs/{job_id}").json()["fit_detail"]["score"] == 80


class GenericCoreScorer(CountingScorer):
    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        base = super().assess(system, user, job)
        quote = " ".join(job.description.split()[:6])
        base.core_requirements = [
            CoreRequirement(requirement="Mainframe tooling", evidence=quote, missing=True)]
        return base


def test_editing_the_exclusion_list_recomputes_stored_scores_without_a_rescore(
        client: TestClient) -> None:
    cfg = client.get("/api/settings").json()["values"]["scoring"]
    client.put("/api/settings/scoring", json={"value": {**cfg, "never_cap_on": ["Mainframe"]}})
    scorer, job_id = GenericCoreScorer(), first_job_id()
    row = scoring.score_job(engine, job_id, scorer)
    assert row.score == 80 and row.core_requirements[0]["excluded"] is True  # on the list
    client.put("/api/settings/scoring", json={"value": {**cfg, "never_cap_on": ["AWS"]}})
    detail = client.get(f"/api/jobs/{job_id}").json()["fit_detail"]
    assert detail["score"] == 60 and detail["missing_core"] == "Mainframe tooling"
    assert scorer.calls == 1  # recomputed, never rescored
    client.put("/api/settings/scoring", json={"value": {**cfg, "never_cap_on": ["Mainframe"]}})
    assert client.get(f"/api/jobs/{job_id}").json()["fit_detail"]["score"] == 80


def _close(job_id: int) -> None:
    from app.models import Application
    from app.models.enums import Stage
    with Session(engine) as s:
        app_row = s.exec(select(Application).where(Application.job_id == job_id)).one()
        app_row.stage = Stage.closed
        s.add(app_row)
        s.commit()


def test_open_jobs_helper_excludes_closed_and_duplicates(seeded: None) -> None:
    from app.services import open_jobs
    with Session(engine) as s:
        ids = list(s.exec(select(Job.id)).all())
        before = open_jobs.open_ids(s, ids)
        closed, dup = next(iter(before)), None
        dup = next(i for i in before if i != closed)
    _close(closed)
    with Session(engine) as s:
        job = s.get(Job, dup)
        job.duplicate_of_id = closed
        s.add(job)
        s.commit()
        after = open_jobs.open_ids(s, ids)
        assert closed not in after and dup not in after
        assert after == before - {closed, dup}
        split = open_jobs.split_open(s, [closed, dup])
        assert split.open == [] and split.skipped == 2


def test_queue_skips_a_job_closed_while_it_waited(seeded: None) -> None:
    from app.models import ScoringTask
    from app.models.enums import ScoringTaskStatus
    from app.services import open_jobs
    scorer = CountingScorer()
    queue = scoring.ScoringQueue(engine, lambda model: scorer)
    with Session(engine) as s:
        ids = [i for i in s.exec(select(Job.id)).all() if open_jobs.is_open(s, i)][:2]
        run = queue._new_run(s, "manual")
        for n, job_id in enumerate(ids):
            s.add(ScoringTask(run_id=run.id, job_id=job_id, position=n))
        s.commit()
    _close(ids[0])
    task = queue._claim()
    assert task is not None and task.job_id == ids[1]
    with Session(engine) as s:
        first = s.exec(select(ScoringTask).where(ScoringTask.job_id == ids[0])).one()
        assert first.status == ScoringTaskStatus.cancelled
    # The per-job Rescore still works on a closed job.
    assert queue.enqueue([ids[0]], force=True, only_open=False) == 1
    assert queue.enqueue([ids[0]], force=True) == 0
    assert queue.wait()


# ------------------------------------------------------------------------- APInex Client Tests


def test_apinex_client_parsing_and_fallback() -> None:
    import json
    import httpx
    from app.providers.apinex_client import APInexClient

    sample_output = {
        "overall_score": 88,
        "verdict": "apply",
        "disqualifying_flags": [],
        "dimensions": {
            "role_match": {"score": 9, "reason": "Exact match for senior backend"},
            "skills_match": {"score": 9, "reason": "Python and FastAPI proficiency"},
            "seniority_fit": {"score": 8, "reason": "Exceeds 5 years required"},
            "location_eligibility": {"score": 9, "reason": "EU Blue Card eligible in Germany"},
            "language_requirements": {"score": 9, "reason": "English is primary work language"},
        },
        "key_strengths": ["Python", "FastAPI", "PostgreSQL"],
        "critical_gaps": [],
        "summary": "Outstanding candidate for this backend role with full alignment.",
    }

    # Case 1: Primary succeeds with code fences
    fenced_content = f"```json\n{json.dumps(sample_output)}\n```"

    def mock_primary_ok(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        assert data["model"] == "free/minimax-m3.1-flash"
        assert "Authorization" in request.headers
        resp = {"choices": [{"message": {"content": fenced_content}}]}
        return httpx.Response(200, json=resp)

    client = APInexClient(api_key="test-key", transport=httpx.MockTransport(mock_primary_ok))
    parsed = client.complete_sync("system prompt", "user prompt")
    assert parsed["overall_score"] == 88
    assert parsed["dimensions"]["role_match"]["score"] == 9

    # Case 2: Primary encounters 429 with "Retry in 1s" -> sleeps and retries same model
    calls = []
    sleeps = []

    def mock_retry_on_429(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        calls.append(data["model"])
        if len(calls) == 1:
            return httpx.Response(
                429,
                text="HTTP 429 Rate limit exceeded. Max 15 requests per minute for this account. Retry in 1s.",
            )
        resp = {"choices": [{"message": {"content": json.dumps(sample_output)}}]}
        return httpx.Response(200, json=resp)

    client_retry = APInexClient(
        api_key="test-key",
        sleep_fn=lambda s: sleeps.append(s),
        transport=httpx.MockTransport(mock_retry_on_429),
    )
    res = client_retry.complete_sync("system", "user")
    assert res["verdict"] == "apply"
    assert calls == ["free/minimax-m3.1-flash", "free/minimax-m3.1-flash"]
    assert len(sleeps) == 1
    assert abs(sleeps[0] - 2.5) < 0.01


def test_fit_assessment_cleanly_parses_apinex_v7_schema() -> None:
    from app.providers.base import FitAssessment

    raw_response = {
        "overall_score": 85,
        "verdict": "apply",
        "disqualifying_flags": [],
        "dimensions": {
            "role_match": {"score": 9, "reason": "Title and track align well"},
            "skills_match": {"score": 8, "reason": "Strong Python/Docker; Kubernetes is plus"},
            "seniority_fit": {"score": 9, "reason": "Candidate has 6 years; asks 4+"},
            "location_eligibility": {"score": 9, "reason": "Germany self-filed EU Blue Card supported"},
            "language_requirements": {"score": 10, "reason": "Fluent English meets requirement"},
        },
        "key_strengths": ["Python", "Docker", "Architecture"],
        "critical_gaps": [],
        "summary": "Candidate matches backend engineer requirements well. Eligible for EU work permit.",
    }

    assessment = FitAssessment.model_validate(raw_response)
    assert assessment.overall_score == 85
    assert assessment.verdict == "apply"
    assert assessment.role_match.score == 9
    assert assessment.skills_match.score == 8
    assert assessment.location_eligibility.score == 9
    assert assessment.strengths == ["Python", "Docker", "Architecture"]
    assert assessment.gaps == []
    assert len(assessment.red_flags) == 0


def test_german_eu_listing_without_explicit_ban_not_disqualified(seeded: None) -> None:
    """Verifies that an EU/German job listing without explicit bans is not disqualified."""
    from app.providers.base import FitAssessment, JobSnapshot, SubScore
    from app.services import fit

    sub_high = SubScore(score=9, reason="Strong match")
    sub_loc = SubScore(score=9, reason="Berlin office, candidate self-files EU Blue Card")

    assessment = FitAssessment(
        role_match=sub_high,
        skills_match=sub_high,
        seniority_fit=sub_high,
        location_eligibility=sub_loc,
        language_requirements=sub_high,
        disqualifying_flags=[],
        strengths=["FastAPI", "Python"],
        gaps=[],
        summary="Strong candidate for Berlin tech position.",
    )

    job_text = (
        "Senior Python Engineer\n"
        "Company: Acme GmbH\n"
        "Location: Berlin, Germany\n"
        "We are looking for a Senior Python Engineer to build high-scale APIs. "
        "English is our working language. German is a plus. "
        "Visa support and relocation assistance provided for qualified candidates."
    )

    config = fit.ScoringConfig.from_settings(
        {"weights": {"location_eligibility": 0.20}},
        {"work_authorization": "needs_sponsorship", "nationality": "Moroccan",
         "languages": [{"language": "English", "level": "Native"}]}
    )

    record = fit.build_record(
        assessment,
        job_text=job_text,
        description_level="full",
        remote_type="hybrid",
        config=config,
        experience_text="6 years Python and backend engineering experience.",
        job_title="Senior Python Engineer",
    )

    assert record["score"] >= 80
    assert len([f for f in record["red_flags"] if f.get("severity") == "hard"]) == 0
    assert record["sub_scores"]["location_eligibility"]["score"] == 9


def test_live_apinex_invocation_if_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invokes live APInex API when APINEX_LIVE=1 and APINEX_API_KEY is configured in the environment."""
    import os
    import socket
    from tests.conftest import _real_connect
    from app.config import get_settings
    from app.providers.apinex_client import APInexClient
    from app.providers.base import FitAssessment

    if not os.environ.get("APINEX_LIVE"):
        pytest.skip("Set APINEX_LIVE=1 to run the live gateway integration test")

    api_key = os.environ.get("APINEX_API_KEY") or getattr(get_settings(), "apinex_api_key", "")
    if not api_key:
        pytest.skip("APINEX_API_KEY not configured; skipping live test")

    from app.services.prompt import load_prompt

    monkeypatch.setattr(socket.socket, "connect", _real_connect)
    client = APInexClient(api_key=api_key)
    prompt = load_prompt("fit_score")
    user = (
        "CANDIDATE\n"
        "Headline: Senior Python Engineer\n"
        "Based in: Berlin, Germany\n"
        "Nationality: German\n"
        "Work authorization: eu_authorized\n"
        "Target countries: Germany\n"
        "Languages: English (Native), German (Native)\n"
        "Years of experience (total): 5\n\n"
        "TRACK\n"
        "Track: Backend\n"
        "Track roles: Python Developer\n"
        "Years in this track: 5\n"
        "Matched role: Python Developer\n\n"
        "EXPERIENCE\n"
        "- [work] Python Developer, Tech GmbH (2020 - Present)\n"
        "  Built backend services in Python and FastAPI.\n\n"
        "JOB\n"
        "Title: Python Developer\n"
        "Company: Berlin Startup\n"
        "Location: Berlin, Germany\n"
        "Work mode: onsite\n"
        "Description (full):\n"
        "<<<\n"
        "Looking for a Python Developer with 3+ years experience. English and German working environment.\n"
        ">>>"
    )
    result = client.complete_sync(prompt.system, user)
    assert isinstance(result, dict)
    assessment = FitAssessment.model_validate(result)
    assert assessment.role_match.score >= 0
    assert assessment.verdict in ("apply", "maybe", "skip")


def test_apinex_rate_limiter_throttles_16th_call() -> None:
    from app.providers.apinex_client import RollingRateLimiter

    sleeps: list[float] = []

    def mock_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    limiter = RollingRateLimiter(limit=15, window=60.0, sleep_fn=mock_sleep)

    # First 15 calls go through immediately with 0 sleep
    for _ in range(15):
        waited = limiter.acquire_sync()
        assert waited == 0.0

    assert len(sleeps) == 0

    # 16th call must be throttled
    waited_16 = limiter.acquire_sync()
    assert waited_16 > 0.0
    assert len(sleeps) == 1
    assert sleeps[0] == waited_16


def test_apinex_exhaustion_triggers_ollama_fallback() -> None:
    """Verifies that when APInex returns 429 persistently or quota exhausted, QuotaExceeded is raised."""
    import httpx
    from app.providers.apinex_client import APInexClient, RollingRateLimiter
    from app.providers.base import QuotaExceeded

    def mock_all_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit exceeded across all free gateway keys")

    limiter = RollingRateLimiter(limit=100, window=60.0, sleep_fn=lambda s: None)
    client = APInexClient(
        api_key="test-key",
        sleep_fn=lambda s: None,
        limiter=limiter,
        transport=httpx.MockTransport(mock_all_429),
    )

    with pytest.raises(QuotaExceeded) as exc_info:
        client.complete_sync("system prompt", "user prompt")

    assert "APInex" in str(exc_info.value)
    assert "rate limit exhausted" in str(exc_info.value)

    # Also verify immediate QuotaExceeded on balance/quota exhaustion keywords
    def mock_quota_zero(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text='{"error": "insufficient_quota", "message": "Daily balance exceeded"}')

    client_exhausted = APInexClient(
        api_key="test-key",
        sleep_fn=lambda s: None,
        limiter=limiter,
        transport=httpx.MockTransport(mock_quota_zero),
    )
    with pytest.raises(QuotaExceeded) as exc_info_quota:
        client_exhausted.complete_sync("system", "user")
    assert "quota exhausted" in str(exc_info_quota.value).lower()


def test_gemini_is_hard_deprecated_for_scoring() -> None:
    from app.providers.registry import fit_scorer

    with pytest.raises(ValueError, match="Gemini is deprecated for scoring"):
        fit_scorer(model="gemini-3.5-flash-lite", mock=False)



