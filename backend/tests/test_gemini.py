"""Gemini bulk scoring: key order, daily quota per Pacific day, minute limiter, refused keys,
retries, and the queue waiting (not switching model) when every key is out of quota.
Mock HTTP transport and fake time only: no network, no real key."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, delete, select

from app.db import engine
from app.models import Job, ProviderKeyState, ProviderUsage, ScoringTask
from app.models.enums import ScoringTaskStatus
from app.providers.base import (
    ConcurrencyLimited,
    FitAssessment,
    JobSnapshot,
    QuotaWait,
    ScoringFailed,
    SubScore,
    TransientError,
)
from app.providers.gemini import GeminiFitScorer, classify_error
from app.services import scoring
from app.services.gemini_keys import KeyPool, next_reset, pacific_day

MODEL = "gemini-3.5-flash-lite"
KEYS = [("key 1", "k1-secret"), ("key 2", "k2-secret")]
JOB = JobSnapshot(title="Data Engineer", company="Acme", location="Paris", remote_type="onsite",
                  description="Build pipelines with Spark and dbt.")


class Clock:
    """Fake wall clock shared by the pool's minute window and its Pacific-day logic."""

    def __init__(self, start: datetime):
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now.timestamp()

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)

    def utc(self) -> datetime:
        return self.now


@pytest.fixture
def clean(seeded: None) -> None:
    with Session(engine) as s:
        s.exec(delete(ProviderUsage).where(col(ProviderUsage.provider).like("gemini%")))
        s.exec(delete(ProviderKeyState).where(ProviderKeyState.provider == "gemini"))
        s.commit()


def make_pool(clock: Clock, *, rpd: int = 500, rpm: int = 15, keys=None) -> KeyPool:
    return KeyPool(engine, MODEL, rpm=rpm, rpd=rpd, keys=keys if keys is not None else KEYS,
                   clock=clock.time, sleep=clock.sleep, now=clock.utc)


def valid_json() -> str:
    sub = SubScore(score=8, reason="fits", evidence="")
    a = FitAssessment(role_match=sub, skills_match=sub, seniority_fit=sub, location_eligibility=sub,
                      language_requirements=sub, strengths=["x"], gaps=[], summary="ok")
    return a.model_dump_json()


def gemini_ok(text: str | None = None, tokens: int = 4800) -> httpx.Response:
    body = {"candidates": [{"content": {"parts": [{"text": text or valid_json()}]}}],
            "usageMetadata": {"promptTokenCount": tokens, "candidatesTokenCount": 600}}
    return httpx.Response(200, json=body)


def error(status: int, message: str, quota_id: str = "") -> httpx.Response:
    details = [{"violations": [{"quotaId": quota_id}]}] if quota_id else []
    return httpx.Response(status, json={"error": {"code": status, "message": message,
                                                  "details": details}})


DAILY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"


class Server:
    """Scripted Gemini: a list of responders per key; records which key each request used."""

    def __init__(self, script: dict[str, list]):
        self.script, self.seen = script, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = request.url.params["key"]
        self.seen.append(key)
        queue = self.script.get(key, [])
        item = queue.pop(0) if queue else gemini_ok()
        return item() if callable(item) else item


def scorer(server: Server, pool: KeyPool, clock: Clock) -> GeminiFitScorer:
    return GeminiFitScorer(MODEL, pool, transport=httpx.MockTransport(server), sleep=clock.sleep)


@pytest.mark.parametrize(("status", "body", "kind"), [
    (200, "", None),
    (429, DAILY, "daily"),
    (429, "Quota exceeded for GenerateRequestsPerDayPerProjectPerModel", "daily"),
    (429, MINUTE, "rate"),
    (429, "GenerateContentInputTokensPerModelPerMinute-FreeTier", "rate"),
    (400, "API key not valid. Please pass a valid API key.", "refused"),
    (403, "PERMISSION_DENIED: your project has been suspended", "refused"),
    (401, "API_KEY_INVALID", "refused"),
    (400, "Request contains an invalid argument.", "fatal"),
    (503, "high demand", "transient"),
    (500, "Internal error", "transient"),
])
def test_error_classification(status: int, body: str, kind: str | None) -> None:
    assert classify_error(status, body) == kind


def test_pacific_day_and_reset() -> None:
    # 2026-10-21 03:00 UTC is still 20 Oct in Pacific (PDT, UTC-7); the reset is 07:00 UTC.
    now = datetime(2026, 10, 21, 3, 0, tzinfo=UTC)
    assert pacific_day(now) == "2026-10-20"
    assert next_reset(now) == datetime(2026, 10, 21, 7, 0, tzinfo=UTC)
    assert pacific_day(datetime(2026, 10, 21, 7, 0, tzinfo=UTC)) == "2026-10-21"
    # after the clocks go back (PST, UTC-8)
    assert next_reset(datetime(2026, 11, 10, 12, 0, tzinfo=UTC)) == datetime(
        2026, 11, 11, 8, 0, tzinfo=UTC)


def test_key_one_until_its_daily_quota_is_used_then_key_two_then_wait(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    pool = make_pool(clock, rpd=3, rpm=100)
    assert [pool.acquire().label for _ in range(3)] == ["key 1"] * 3
    assert [pool.acquire().label for _ in range(3)] == ["key 2"] * 3
    with pytest.raises(QuotaWait) as wait:
        pool.acquire()
    assert wait.value.resume_at == next_reset(clock.now) == datetime(2026, 10, 21, 7, 0, tzinfo=UTC)
    snap = pool.snapshot()
    assert [k["state"] for k in snap["keys"]] == ["exhausted", "exhausted"]
    assert snap["remaining_today"] == 0 and snap["resets_at"].startswith("2026-10-21T07:00")
    # the next Pacific day starts from zero, on key 1 again
    clock.now = datetime(2026, 10, 21, 7, 1, tzinfo=UTC)
    assert pool.acquire().label == "key 1"
    assert pool.snapshot()["keys"][0]["used"] == 1


def test_usage_survives_a_restart(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    first = make_pool(clock, rpd=2, rpm=100)
    first.acquire()
    first.acquire()
    again = make_pool(clock, rpd=2, rpm=100)  # a new process: same database
    assert again.acquire().label == "key 2"


def test_the_minute_limit_waits_on_the_same_key(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    pool = make_pool(clock, rpm=2)
    labels = [pool.acquire().label for _ in range(3)]
    assert labels == ["key 1", "key 1", "key 1"]  # never spills to key 2 for a per-minute limit
    assert sum(clock.slept) >= 60  # the third call waited for the window


def test_no_key_and_all_keys_refused_are_waits_that_need_you(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    with pytest.raises(QuotaWait, match="No Gemini API key") as none:
        make_pool(clock, keys=[]).acquire()
    assert none.value.resume_at is None
    pool = make_pool(clock)
    for _ in range(2):
        pool.disable(pool.acquire(), "HTTP 400: API key not valid")
    with pytest.raises(QuotaWait, match="refused or disabled") as refused:
        pool.acquire()
    assert refused.value.resume_at is None
    assert pool.snapshot()["keys"][0]["state"] == "disabled"
    assert pool.enable("key 1") and pool.acquire().label == "key 1"


def test_scoring_returns_a_validated_assessment(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    server = Server({})
    result = scorer(server, make_pool(clock), clock).assess("system", "user", JOB)
    assert result.role_match.score == 8 and server.seen == ["k1-secret"]


def test_a_daily_429_parks_the_key_and_the_same_request_moves_to_key_two(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    pool = make_pool(clock)
    server = Server({"k1-secret": [error(429, "Quota exceeded", DAILY)]})
    assert scorer(server, pool, clock).assess("s", "u", JOB).role_match.score == 8
    assert server.seen == ["k1-secret", "k2-secret"]
    assert pool.snapshot()["keys"][0]["state"] == "exhausted"
    scorer(server, pool, clock).assess("s", "u", JOB)
    assert server.seen[-1] == "k2-secret"  # key 1 is not tried again today


def test_both_keys_out_of_daily_quota_waits_for_the_reset(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    server = Server({"k1-secret": [error(429, "q", DAILY)], "k2-secret": [error(429, "q", DAILY)]})
    with pytest.raises(QuotaWait) as wait:
        scorer(server, make_pool(clock), clock).assess("s", "u", JOB)
    assert wait.value.resume_at == datetime(2026, 10, 21, 7, 0, tzinfo=UTC)
    assert server.seen == ["k1-secret", "k2-secret"]  # one try each, no loop


def test_a_refused_key_is_disabled_and_never_retried(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    pool = make_pool(clock)
    server = Server({"k1-secret": [error(400, "API key not valid. Please pass a valid API key.")]})
    s = scorer(server, pool, clock)
    s.assess("s", "u", JOB)
    s.assess("s", "u", JOB)
    assert server.seen == ["k1-secret", "k2-secret", "k2-secret"]
    snap = pool.snapshot()["keys"]
    assert snap[0]["state"] == "disabled" and "not valid" in snap[0]["reason"]
    assert "k1-secret" not in json.dumps(snap)  # keys are never exposed, only label + fingerprint


def test_503_is_retried_with_backoff_then_gives_up_as_transient(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    busy = error(503, "This model is currently experiencing high demand.")
    ok_after = Server({"k1-secret": [busy, busy]})
    assert scorer(ok_after, make_pool(clock), clock).assess("s", "u", JOB).role_match.score == 8
    assert clock.slept[:2] == [5.0, 10.0] and ok_after.seen == ["k1-secret"] * 3
    clock2 = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    down = Server({"k1-secret": [busy] * 4})
    with pytest.raises(TransientError):
        scorer(down, make_pool(clock2), clock2).assess("s", "u", JOB)
    assert len(down.seen) == 4 and clock2.slept == [5.0, 10.0, 20.0]


def test_a_minute_limit_429_is_a_concurrency_limit_for_the_queue(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    server = Server({"k1-secret": [error(429, "Too many requests", MINUTE)]})
    with pytest.raises(ConcurrencyLimited):
        scorer(server, make_pool(clock), clock).assess("s", "u", JOB)


def test_invalid_json_gets_one_repair_retry(clean: None) -> None:
    clock = Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC))
    server = Server({"k1-secret": [gemini_ok("not json")]})
    s = scorer(server, make_pool(clock), clock)
    assert s.assess("s", "u", JOB).role_match.score == 8
    assert s.stats["invalid"] == 1 and s.stats["valid_after_retry"] == 1
    bad = Server({"k1-secret": [gemini_ok("not json"), gemini_ok("{}")]})
    with pytest.raises(ScoringFailed, match="Invalid model output"):
        scorer(bad, make_pool(clock), clock).assess("s", "u", JOB)


def test_a_fenced_or_wrapped_answer_is_accepted() -> None:
    from app.providers.gemini import _parse

    wrapped = json.dumps({"properties": json.loads(valid_json())})
    assert _parse(f"```json\n{wrapped}\n```").role_match.score == 8


# ------------------------------------------------------------------------------------- queue


class QuotaScorer:
    def __init__(self, model: str, resume_at: datetime | None):
        self.model, self.resume_at = model, resume_at

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        raise QuotaWait("Today's Gemini quota is used up on 2 key(s).", self.resume_at)


class AnswerScorer:
    model = "gemma4:31b-cloud"

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        return FitAssessment.model_validate_json(valid_json())


def test_the_queue_waits_when_every_key_is_out_of_quota_and_continues_when_you_choose(
        clean: None) -> None:
    resume = datetime.now(UTC) + timedelta(hours=5)
    queue = scoring.ScoringQueue(
        engine, lambda model: QuotaScorer(model, resume) if model.startswith("gemini")
        else AnswerScorer())
    queue.model_override = MODEL
    with Session(engine) as s:
        ids = [j for j in s.exec(select(Job.id).order_by(col(Job.id)).limit(3)).all()]
    queue.enqueue(ids)
    assert queue.wait(10)
    status = queue.status()
    assert status["running"] is False and "quota is used up" in (status["blocked"] or "")
    assert status["waiting_until"] == resume.isoformat() and status["failed"] == 0
    with Session(engine) as s:
        tasks = s.exec(select(ScoringTask).where(ScoringTask.job_id.in_(ids))).all()
        assert all(t.status == ScoringTaskStatus.queued for t in tasks)  # nothing failed or lost
    assert queue._wake_timer is not None and queue._wake_timer.is_alive()  # noqa: SLF001
    # your explicit choice: the Ollama cloud model for the rest of this process
    queue.continue_with("gemma4:31b-cloud")
    assert queue.wait(15)
    assert queue.status()["blocked"] is None and queue.status()["override_model"]
    with Session(engine) as s:
        done = s.exec(select(ScoringTask).where(ScoringTask.job_id.in_(ids))).all()
        assert all(t.status == ScoringTaskStatus.done for t in done)
    queue.continue_with(None)  # back to Settings → Models
    assert queue.model_override is None


# ------------------------------------------------------------------------------------- API


@pytest.fixture
def gemini_model(client: TestClient, monkeypatch: pytest.MonkeyPatch, clean: None) -> None:
    from app.api import scoring as scoring_api
    from app.services import gemini_keys

    monkeypatch.setattr(gemini_keys, "configured_keys", lambda: KEYS)
    monkeypatch.setattr(scoring_api, "workspace_is_real", lambda workspace: True)
    models = client.get("/api/settings").json()["values"]["models"]
    client.put("/api/settings/models", json={"value": {
        **models, "scoring": {**models["scoring"], "model": MODEL, "fallback": None}}})


def test_quota_endpoint_per_key_and_rescore_preview_in_days(
        client: TestClient, gemini_model: None) -> None:
    quota = client.get("/api/scoring/quota").json()
    assert quota["provider"] == "gemini"
    assert [k["label"] for k in quota["keys"]] == ["key 1", "key 2"]
    assert quota["remaining_today"] == 1000 and quota["limits"]["rpd"] == 500
    assert "k1-secret" not in json.dumps(quota)
    preview = client.get("/api/scoring/rescore-preview", params={"scope": "outdated"}).json()
    assert preview["model"] == MODEL and preview["daily_capacity"] == 1000
    assert preview["days"] == 1 and preview["count"] > 0  # the sample is far below 1,000 jobs
    with Session(engine) as s:  # key 1 used up for today (the endpoint above created the row)
        row = s.exec(select(ProviderUsage).where(
            ProviderUsage.provider == MODEL, ProviderUsage.key_label == "key 1",
            ProviderUsage.period == pacific_day())).one()
        row.calls = 500
        s.add(row)
        s.commit()
    assert client.get("/api/scoring/quota").json()["keys"][0]["state"] == "exhausted"
    assert client.get("/api/scoring/quota").json()["remaining_today"] == 500


def test_the_outdated_scope_is_best_first_and_skips_duplicates(
        client: TestClient, gemini_model: None) -> None:
    from app.api.scoring import _latest_ok, _outdated_ids

    with Session(engine) as s:
        ids = _outdated_ids(s)
        latest = _latest_ok(s)
        dup = set(s.exec(select(Job.id).where(col(Job.duplicate_of_id).is_not(None))).all())
        assert ids and not (set(ids) & dup)
        scores = [latest[i].score for i in ids if i in latest]
        assert scores == sorted(scores, reverse=True)  # best first
    assert client.post("/api/scoring/rescore", json={"scope": "outdated"}).status_code == 409


def test_the_quota_endpoint_has_nothing_to_say_for_other_models(client: TestClient) -> None:
    assert client.get("/api/scoring/quota").json()["provider"] == "other"


def test_auto_score_after_discovery_can_be_turned_off(client: TestClient) -> None:
    from app.services import discovery

    class Recorder:
        calls = 0

        def enqueue_never_scored(self) -> int:
            Recorder.calls += 1
            return 0

    cfg = client.get("/api/settings").json()["values"]["scoring"]
    discovery.after_discovery(engine, [], Recorder())
    assert Recorder.calls == 1  # on by default (also for a setting saved before the toggle existed)
    client.put("/api/settings/scoring", json={"value": {**cfg, "auto_score_new": False}})
    discovery.after_discovery(engine, [], Recorder())
    assert Recorder.calls == 1
    client.put("/api/settings/scoring", json={"value": {**cfg, "auto_score_new": True}})
    discovery.after_discovery(engine, [], Recorder())
    assert Recorder.calls == 2


def test_continue_with_and_key_enable_endpoints(client: TestClient, gemini_model: None) -> None:
    assert client.post("/api/scoring/continue-with", json={"model": None}).status_code == 200
    assert client.post("/api/scoring/keys/key%201/enable").status_code == 404  # nothing disabled
    pool = make_pool(Clock(datetime(2026, 10, 20, 18, 0, tzinfo=UTC)))
    pool.disable(pool.acquire(), "HTTP 400: API key not valid")
    from app.services.gemini_keys import pool_for

    pool_for(engine, MODEL).enable("key 1")  # what the endpoint does
    assert pool_for(engine, MODEL).snapshot()["keys"][0]["state"] in ("ok", "exhausted")
