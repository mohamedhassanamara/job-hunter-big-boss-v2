"""Gemini for CV and email generation: the runner (backoff, key rotation, thinking, privacy guard),
the shared key pool (priority, reserve, pooled total), Settings → Models choice, and the background
drafting queue (shortlist → CV draft, un-shortlist cancels, skips, email when both inputs exist).
Mock HTTP and fake time: no network, no real key, no real model."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlmodel import Session, col, delete, select

from app.db import engine
from app.models import Application, CVVersion, GenerationTask, OutreachDraft
from app.models.enums import CVStatus, DraftStatus, Stage
from app.providers.base import CVGenerationFailed, SummaryDraft
from app.providers.gemini_generate import (
    GeminiRunner,
    GenerationFailed,
    PrivacyError,
    check_private,
    generation_failure,
    private_terms,
    thinking_config,
)
from app.services import generation, model_choice, pipeline
from app.services.gemini_keys import KeyPool
from tests.test_gemini import KEYS, MODEL, Clock, error, make_pool
from tests.test_tracking import make_app

NOON = datetime(2026, 10, 21, 12, tzinfo=UTC)
SUMMARY = SummaryDraft(summary_sentences=[], summary_short_sentences=[]).model_dump_json()


@pytest.fixture
def clean(seeded: None) -> None:
    from app.models import ProviderKeyState, ProviderUsage

    with Session(engine) as s:
        s.exec(delete(ProviderUsage).where(col(ProviderUsage.provider).like("gemini%")))
        s.exec(delete(ProviderKeyState).where(ProviderKeyState.provider == "gemini"))
        s.commit()


def ok(text: str = SUMMARY, tokens: int = 1200, thoughts: int | None = None) -> httpx.Response:
    usage = {"promptTokenCount": tokens, "candidatesTokenCount": 40}
    if thoughts is not None:
        usage["thoughtsTokenCount"] = thoughts
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}],
                                     "usageMetadata": usage})


def runner(clock: Clock, handler, *, level: str | None = "minimal", terms=None,
           keys=None, rpd: int = 500) -> tuple[GeminiRunner, list[dict]]:
    sent: list[dict] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        sent.append({"key": request.url.params["key"], "body": json.loads(request.content)})
        return handler(request, len(sent))

    r = GeminiRunner(make_pool(clock, keys=keys, rpd=rpd), MODEL, level, terms=terms,
                     transport=httpx.MockTransport(wrapped), sleep=clock.sleep)
    return r, sent


# ------------------------------------------------------------------------------- the runner


def test_thinking_levels() -> None:
    assert thinking_config("minimal") == {"thinkingLevel": "minimal"}
    assert thinking_config(None) == {"thinkingLevel": "minimal"}
    assert thinking_config("dynamic") == {"thinkingBudget": -1}
    assert thinking_config("nonsense") == {"thinkingLevel": "minimal"}


def test_a_call_sends_the_schema_and_thinking_and_counts_tokens(clean: None) -> None:
    clock = Clock(NOON)
    r, sent = runner(clock, lambda _r, _n: ok(thoughts=17))
    out = r.call("system", "user", SummaryDraft)
    assert isinstance(out, SummaryDraft)
    cfg = sent[0]["body"]["generationConfig"]
    assert cfg["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert cfg["responseMimeType"] == "application/json"
    assert "properties" in cfg["responseJsonSchema"]
    s = r.summary()
    assert (s["calls"], s["tokens_in"], s["tokens_thinking"], s["retries_503"]) == (1, 1200, 17, 0)


def test_503_retries_the_same_key_after_a_backoff_and_is_counted(clean: None) -> None:
    clock = Clock(NOON)
    r, sent = runner(clock, lambda _r, n: error(503, "high demand") if n == 1 else ok())
    r.call("s", "u", SummaryDraft)
    assert [x["key"] for x in sent] == ["k1-secret", "k1-secret"]  # no rotation
    assert r.summary()["retries_503"] == 1 and clock.slept[0] == 5.0


def test_after_three_tries_it_fails_and_never_falls_back(clean: None) -> None:
    clock = Clock(NOON)
    r, sent = runner(clock, lambda _r, _n: error(503, "high demand"))
    with pytest.raises(GenerationFailed) as exc:
        r.call("s", "u", SummaryDraft)
    assert exc.value.retryable and len(sent) == 3 and clock.slept == [5.0, 10.0]
    assert generation_failure(CVGenerationFailed("x")) is None
    assert generation_failure(RuntimeError("wrapped").with_traceback(None)) is None


def test_invalid_json_gets_one_retry_with_the_error_fed_back(clean: None) -> None:
    clock = Clock(NOON)
    r, sent = runner(clock, lambda _r, n: ok("not json") if n == 1 else ok())
    r.call("s", "u", SummaryDraft)
    assert r.summary()["invalid_retries"] == 1
    assert "Your answer was invalid" in json.dumps(sent[1]["body"]["contents"])


def test_a_daily_429_parks_the_key_and_stops(clean: None) -> None:
    clock = Clock(NOON)
    r, sent = runner(clock, lambda _r, n: error(
        429, "quota", "GenerateRequestsPerDayPerProjectPerModel") if n == 1 else ok(),
        keys=KEYS[:1])
    with pytest.raises(GenerationFailed) as exc:
        r.call("s", "u", SummaryDraft)
    assert [x["key"] for x in sent] == ["k1-secret"] and exc.value.quota_resume is not None


def test_quota_used_up_is_a_failure_that_knows_when_it_resumes(clean: None) -> None:
    clock = Clock(NOON)
    r, _sent = runner(clock, lambda _r, _n: ok(), rpd=0)
    with pytest.raises(GenerationFailed) as exc:
        r.call("s", "u", SummaryDraft)
    assert exc.value.quota_resume is not None


def test_private_contact_data_is_never_sent(clean: None) -> None:
    clock = Clock(NOON)
    profile = {"email": "me@example.com", "phone": "+216 12 345 678",
               "links": [{"url": "https://www.linkedin.com/in/me-handle/"}]}
    terms = private_terms(profile)
    r, sent = runner(clock, lambda _r, _n: ok(), terms=lambda: terms)
    for leaked in ("write to Me@Example.com", "call 21612345678", "see linkedin.com/in/me-handle"):
        with pytest.raises(PrivacyError):
            r.call("s", leaked, SummaryDraft)
    r.call("s", "nothing private here", SummaryDraft)
    assert len(sent) == 1  # only the clean call went out
    check_private("a project at lovester.net", terms)  # a link that isn't yours passes


# ------------------------------------------------------------------------------ the key pool


def test_background_yields_to_user_work_and_keeps_a_reserve(clean: None) -> None:
    clock = Clock(NOON)
    pool = KeyPool(engine, MODEL, rpm=100, rpd=12, user_reserve=2, keys=KEYS[:1],
                   clock=clock.time, sleep=lambda _s: setattr(pool, "_user_waiting", 0),
                   now=clock.utc)
    pool._user_waiting = 1  # a user call is waiting: background sleeps, then goes
    pool.acquire(100, priority="background")
    for _ in range(9):
        pool.acquire(100, priority="background")  # 10 of the day's 12
    with pytest.raises(Exception, match="quota is used up"):
        pool.acquire(100, priority="background")  # the last 2 are for you
    pool.acquire(100, priority="user")
    pool.acquire(100, priority="user")
    snap = pool.snapshot()
    assert snap["pooled"] == {"used": 12, "limit": 12, "remaining": 0, "keys": 1,
                              "user_reserve": 2}


# ----------------------------------------------------------------------------- model choice


def test_model_choice_defaults_and_claude_is_a_one_shot_override(seeded: None) -> None:
    with Session(engine) as s:  # the CV is APInex, the email Gemini
        assert model_choice.choice(s, "cv") == {
            "provider": "apinex", "model": "free/minimax-m3.1-flash", "thinking_level": None}
        assert model_choice.choice(s, "email") == {
            "provider": "gemini", "model": "gemini-3.5-flash-lite", "thinking_level": "minimal"}
        assert model_choice.choice(s, "email", "claude")["provider"] == "anthropic"
        assert model_choice.choice(s, "cv", "claude")["provider"] == "anthropic"
        assert model_choice.choice(s, "cv")["provider"] == "apinex"  # setting unchanged
    with pytest.raises(ValueError):
        model_choice.check({"cv": {"model": "gpt-9"}})
    model_choice.check({"cv": {"model": "free/minimax-m3.1-flash"}})  # APInex: the CV only
    for bad in ({"email": {"model": "free/minimax-m3.1-flash"}},
                {"letter": {"model": "free/minimax-m3.1-flash"}},
                {"interview": {"model": "free/minimax-m3.1-flash"}},
                {"rewrite": {"model": "free/minimax-m3.1-flash"}}):
        with pytest.raises(ValueError, match="APInex"):
            model_choice.check(bad)
    with pytest.raises(ValueError):
        model_choice.check({"email": {"model": "gemini-3.5-flash-lite", "thinking_level": "x"}})


# --------------------------------------------------------------------------------- the queue


def set_generation(s: Session, **values: bool) -> None:
    from app.models import AppSetting

    row = s.exec(select(AppSetting).where(AppSetting.key == "generation")).one()
    row.value = {**row.value, **values}
    s.add(row)
    s.flush()


def tasks(s: Session, app_id: int, kind: str | None = None) -> list[GenerationTask]:
    q = select(GenerationTask).where(GenerationTask.application_id == app_id)
    if kind:
        q = q.where(GenerationTask.kind == kind)
    return list(s.exec(q.order_by(col(GenerationTask.id))).all())


@pytest.fixture
def clean_tasks(seeded: None) -> None:
    with Session(engine) as s:
        s.exec(delete(GenerationTask))
        s.commit()


def test_shortlisting_queues_one_cv_task_and_unshortlisting_cancels_it(clean_tasks: None) -> None:
    with Session(engine) as s:
        app = make_app(s, stage=Stage.new, cv=None)
        pipeline.transition(s, app, Stage.shortlisted)
        s.flush()
        assert [(t.kind, t.status, t.trigger) for t in tasks(s, app.id)] == [
            ("cv", "queued", "shortlist")]
        pipeline.transition(s, app, Stage.new)
        pipeline.transition(s, app, Stage.shortlisted)
        s.flush()
        assert [t.status for t in tasks(s, app.id)] == ["cancelled", "queued"]
        s.rollback()


def test_a_job_that_already_has_a_cv_or_the_setting_off_queues_nothing(clean_tasks: None) -> None:
    with Session(engine) as s:
        app = make_app(s, stage=Stage.new, cv=CVStatus.draft)
        pipeline.transition(s, app, Stage.shortlisted)
        s.flush()
        assert tasks(s, app.id) == []
        other = make_app(s, stage=Stage.new, cv=None)
        set_generation(s, auto_cv=False)
        pipeline.transition(s, other, Stage.shortlisted)
        s.flush()
        assert tasks(s, other.id) == []
        s.rollback()


def test_the_worker_writes_a_draft_cv_and_never_approves(clean_tasks: None) -> None:
    with Session(engine) as s:
        app = make_app(s, stage=Stage.new, cv=None)
        pipeline.transition(s, app, Stage.shortlisted)
        s.commit()
        app_id = app.id
    assert generation.tick(engine, mock=True)
    with Session(engine) as s:
        (task,) = tasks(s, app_id)
        versions = list(s.exec(select(CVVersion).where(CVVersion.application_id == app_id)).all())
        assert task.status == "done" and task.result_id == versions[0].id
        assert [v.status for v in versions] == [CVStatus.draft]  # a draft to review
        assert Stage(s.get(Application, app_id).stage) == Stage.shortlisted
        states = generation.states(s, [app_id])
        assert states[app_id]["cv"] is None  # done says nothing: the draft is the state
    assert not generation.tick(engine, mock=True)  # nothing left


def test_an_incomplete_pool_skips_with_a_warning(clean_tasks: None, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("app.services.cv_pool.readiness", lambda _pool: [
        {"key": "roles", "severity": "blocker", "message": "Add at least one role in Experience."}])
    with Session(engine) as s:
        app = make_app(s, stage=Stage.new, cv=None)
        pipeline.transition(s, app, Stage.shortlisted)
        s.commit()
        app_id = app.id
    generation.tick(engine, mock=True)
    with Session(engine) as s:
        (task,) = tasks(s, app_id)
        assert task.status == "skipped" and "Add at least one role" in task.warning
        assert generation.states(s, [app_id])[app_id]["cv"]["status"] == "skipped"


def test_a_failed_generation_is_failed_not_switched_and_retries_once(
        clean_tasks: None, monkeypatch) -> None:  # noqa: ANN001
    from app.services.cv_service import CVError

    def boom(*_a, **_k):  # noqa: ANN002, ANN003
        try:
            raise GenerationFailed("Gemini did not answer after 6 tries (503)")
        except GenerationFailed as exc:
            raise CVError(str(exc)) from exc

    monkeypatch.setattr("app.services.cv_service.generate", boom)
    with Session(engine) as s:
        app = make_app(s, stage=Stage.new, cv=None)
        pipeline.transition(s, app, Stage.shortlisted)
        s.commit()
        app_id = app.id
    generation.tick(engine, mock=True)  # attempt 1: backoff, queued again
    with Session(engine) as s:
        (task,) = tasks(s, app_id)
        assert task.status == "queued" and task.not_before is not None and task.attempts == 1
        task.not_before = None
        s.add(task)
        s.commit()
    generation.tick(engine, mock=True)  # attempt 2: failed, with Retry / Claude on the page
    with Session(engine) as s:
        (task,) = tasks(s, app_id)
        assert task.status == "failed" and "did not answer" in task.error
        assert generation.states(s, [app_id])[app_id]["cv"]["status"] == "failed"


def test_email_is_queued_when_the_second_input_arrives_and_only_for_shortlisted_jobs(
        clean_tasks: None, monkeypatch) -> None:  # noqa: ANN001
    ready = {"contact": False}
    monkeypatch.setattr("app.services.get_contact.state",
                        lambda _s, _a: "ready" if ready["contact"] else "verify")
    with Session(engine) as s:
        set_generation(s, auto_cv=False, auto_email=True)
        app = make_app(s, stage=Stage.cv_ready, cv=CVStatus.approved)  # CV first
        s.flush()
        assert generation.maybe_enqueue_email(s, app, "cv_approved") is None  # no contact yet
        ready["contact"] = True  # the contact comes last
        task = generation.maybe_enqueue_email(s, app, "contact_ready")
        assert task is not None and task.kind == "email"
        assert generation.maybe_enqueue_email(s, app, "contact_ready") is task  # never two
        new = make_app(s, stage=Stage.new, cv=CVStatus.approved)  # not shortlisted
        assert generation.maybe_enqueue_email(s, new, "contact_ready") is None
        s.add(OutreachDraft(application_id=new.id, subject="s", body="b",
                            status=DraftStatus.draft, model="m"))
        done = make_app(s, stage=Stage.cv_ready, cv=CVStatus.approved)
        s.add(OutreachDraft(application_id=done.id, subject="s", body="b",
                            status=DraftStatus.draft, model="m"))
        s.flush()
        assert generation.maybe_enqueue_email(s, done, "cv_approved") is None  # a draft exists
        s.rollback()


def test_the_email_setting_starts_off(seeded: None) -> None:
    with Session(engine) as s:
        assert generation.settings(s) == {"auto_cv": True, "auto_email": False}


def test_a_garbled_sentence_is_a_warning_and_never_blocks_approval() -> None:
    from app.providers.base import VerifyClaim, VerifyPlan
    from app.services import verifier

    class Fake:
        model, prompt_version, via = "fake", "verify/test", "test"

        def verify(self, request: dict) -> VerifyPlan:
            return VerifyPlan(claims=[
                VerifyClaim(sentence="I built it.", claim="I built it.", about="candidate",
                            verdict="supported", source_id="facts", source_quote="I built it"),
                VerifyClaim(sentence="Fine fine and then.", claim="Fine fine and then.",
                            about="other", verdict="garbled", reason="Broken phrasing")])

    record = verifier.run(Fake(), "email", "I built it. Fine fine and then.",
                          {"facts": "I built it"})
    assert record["status"] == "passed" and record["blocking"] == 0
    assert [c["verdict"] for c in record["claims"]] == ["supported", "garbled"]


def test_task_details_work_for_claude_generators_too() -> None:
    """A Claude generator's `runner` attribute is the subprocess function, not a Gemini runner."""
    import subprocess

    class Claude:
        runner = staticmethod(subprocess.run)

    class Gemini:
        runner = type("R", (), {"summary": lambda self: {"calls": 2}})()

    assert generation._details(Claude()) == {}
    assert generation._details(Gemini()) == {"calls": 2}
