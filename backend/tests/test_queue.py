"""Persistent, cloud-first scoring queue: 429 retries, adaptive concurrency, quota fallback,
end-of-run retry, resume after restart. Mock scorers only (no model calls)."""

import threading

import pytest
from sqlmodel import Session, col, select

from app.db import engine
from app.models import FitScore, Job, ScoringRun, ScoringTask
from app.models.enums import ScoringTaskStatus
from app.providers.base import (
    ConcurrencyLimited,
    FitAssessment,
    JobSnapshot,
    QuotaExceeded,
    ScoringFailed,
    SubScore,
    TransientError,
)
from app.services import scoring
from app.services.scoring import ConcurrencyController, ScoringQueue

CLOUD, LOCAL = "free/minimax-m3.1-flash", "qwen2.5:7b"  # the scoring defaults (APInex, then Ollama)


def ok() -> FitAssessment:
    sub = SubScore(score=8, reason="fits", evidence="")
    return FitAssessment(role_match=sub, skills_match=sub, seniority_fit=sub,
                         location_eligibility=sub, language_requirements=sub,
                         strengths=[], gaps=[], summary="ok")


class Scripted:
    """Raises the queued errors in order (per job title), then answers."""

    def __init__(self, model: str, script: dict[str, list[Exception]] | None = None,
                 always: Exception | None = None):
        self.model, self.script, self.always = model, script or {}, always
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        with self.lock:
            self.calls.append(job.title)
            pending = self.script.get(job.title) or []
            error = pending.pop(0) if pending else self.always
        if error:
            raise error
        return ok()


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scoring, "BACKOFF_BASE", 0.01)
    monkeypatch.setattr(scoring, "BACKOFF_CAP", 0.05)


@pytest.fixture
def jobs(seeded: None) -> list[Job]:
    with Session(engine) as s:
        return list(s.exec(select(Job).order_by(col(Job.id)).limit(4)).all())


def run_of(queue: ScoringQueue) -> ScoringRun:
    with Session(engine) as s:
        return s.get(ScoringRun, queue.run_id)


def tasks_of(queue: ScoringQueue) -> list[ScoringTask]:
    with Session(engine) as s:
        return list(s.exec(select(ScoringTask).where(ScoringTask.run_id == queue.run_id)).all())


def test_concurrency_429_retries_the_same_job_and_never_fails(jobs: list[Job]) -> None:
    job = jobs[0]
    limited = ConcurrencyLimited("Ollama 429: too many concurrent requests")
    scorer = Scripted(CLOUD, {job.title: [limited, limited, limited]})
    queue = ScoringQueue(engine, lambda model: scorer)
    assert queue.enqueue([job.id], force=True) == 1
    assert queue.wait(10)
    assert scorer.calls == [job.title] * 4  # same job, retried until it went through
    run = run_of(queue)
    assert (run.done, run.failed, run.retried_429) == (1, 0, 3)
    (task,) = tasks_of(queue)
    assert task.status == ScoringTaskStatus.done and task.attempts == 0  # 429s never count


def test_adaptive_concurrency_goes_down_then_back_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scoring, "RAISE_AFTER", 3)
    now = [0.0]
    c = ConcurrencyController(4, 1, 4, clock=lambda: now[0], rand=lambda: 0.5)
    delays = [c.on_concurrency_limit() for _ in range(5)]
    assert c.limit == 1 and c.seen_min == 1  # -1 per 429, floored at min
    assert delays[:3] == [0.01, 0.02, 0.04] and max(delays) <= 0.05  # exponential, capped
    assert c.paused_until > 0
    for _ in range(9):
        c.on_success()
    assert c.limit == 4 and c.seen_max == 4  # +1 per streak of 3 successes, capped at max
    c.on_success()
    c.on_success()
    c.on_success()
    assert c.limit == 4


def test_jitter_stays_within_30_percent() -> None:
    lo = ConcurrencyController(4, 1, 4, rand=lambda: 0.0).on_concurrency_limit()
    hi = ConcurrencyController(4, 1, 4, rand=lambda: 1.0).on_concurrency_limit()
    assert lo == pytest.approx(0.01 * 0.7) and hi == pytest.approx(0.01 * 1.3)


def test_quota_limit_switches_the_run_to_local(jobs: list[Job]) -> None:
    cloud = Scripted(CLOUD, always=QuotaExceeded("Cloud usage limit: weekly usage limit"))
    local = Scripted(LOCAL)
    queue = ScoringQueue(engine, lambda model: {CLOUD: cloud, LOCAL: local}[model])
    queue.enqueue([j.id for j in jobs], force=True)
    assert queue.wait(10)
    run = run_of(queue)
    assert run.fallback_reason and "usage limit" in run.fallback_reason
    assert run.fallback_model == LOCAL and run.quota_hits >= 1
    assert run.done == len(jobs) and run.failed == 0
    assert {t.model_used for t in tasks_of(queue)} == {LOCAL}
    assert queue.status()["run"]["fallback_reason"]
    # Next run tries the cloud model again.
    cloud.always = None
    queue.enqueue([jobs[0].id], force=True)
    assert queue.wait(10)
    assert queue.model == CLOUD and run_of(queue).fallback_reason is None


def test_quota_without_fallback_pauses_and_keeps_jobs_queued(
    jobs: list[Job], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = scoring.load_context

    def no_fallback(s):  # noqa: ANN001, ANN202
        ctx = real(s)
        ctx.fallback_model = None
        return ctx

    monkeypatch.setattr(scoring, "load_context", no_fallback)
    cloud = Scripted(CLOUD, always=QuotaExceeded("Cloud usage limit: session usage limit"))
    queue = ScoringQueue(engine, lambda model: cloud)
    queue.enqueue([j.id for j in jobs], force=True)
    assert queue.wait(10)
    assert "No local fallback" in (queue.blocked or "")
    statuses = {t.status for t in tasks_of(queue)}
    assert statuses == {ScoringTaskStatus.queued} and run_of(queue).failed == 0  # none dropped
    queue.cancel()


def test_failures_retry_then_get_one_final_retry_at_the_end(jobs: list[Job]) -> None:
    flaky, broken = jobs[0], jobs[1]
    bad = ScoringFailed("Invalid model output after a retry: role_match: missing")
    scorer = Scripted(CLOUD, {
        flaky.title: [TransientError("Timed out"), TransientError("Timed out"), bad],  # 3 → failed
        broken.title: [bad] * 6,  # fails its 3 attempts and the 3 of the final retry
    })
    queue = ScoringQueue(engine, lambda model: scorer)
    queue.enqueue([flaky.id, broken.id], force=True)
    assert queue.wait(10)
    run = run_of(queue)
    assert (run.done, run.failed) == (1, 1)  # flaky recovered in the final retry
    by_job = {t.job_id: t for t in tasks_of(queue)}
    assert by_job[flaky.id].status == ScoringTaskStatus.done and by_job[flaky.id].final_retry
    assert by_job[broken.id].status == ScoringTaskStatus.failed
    with Session(engine) as s:
        latest = scoring.latest_fit(s, broken.id)
    assert latest.status == "failed" and "Invalid model output" in latest.error


def test_queue_resumes_after_a_restart(jobs: list[Job]) -> None:
    first = ScoringQueue(engine, lambda model: Scripted(CLOUD))
    with Session(engine) as s:  # simulate a crash: one task mid-flight, others waiting
        run = ScoringRun(trigger="discovery", primary_model=CLOUD)
        s.add(run)
        s.commit()
        s.refresh(run)
        for n, job in enumerate(jobs):
            status = ScoringTaskStatus.in_progress if n == 0 else ScoringTaskStatus.queued
            s.add(ScoringTask(run_id=run.id, job_id=job.id, force=True, position=n,
                              status=status))
        s.commit()
    del first
    scorer = Scripted(CLOUD)
    restarted = ScoringQueue(engine, lambda model: scorer)
    assert restarted.resume() == len(jobs)
    assert restarted.wait(10)
    assert sorted(scorer.calls) == sorted(j.title for j in jobs)
    assert all(t.status == ScoringTaskStatus.done for t in tasks_of(restarted))
    assert run_of(restarted).finished_at is not None


def test_enqueue_never_scored_skips_every_scored_job(jobs: list[Job]) -> None:
    scorer = Scripted(CLOUD)
    queue = ScoringQueue(engine, lambda model: scorer)
    with Session(engine) as s:
        scored = set(s.exec(select(FitScore.job_id)).all())
        never = [j for j in s.exec(select(Job)).all() if j.id not in scored]
    assert queue.enqueue_never_scored() == len(never)
    assert queue.wait(10)
    assert sorted(scorer.calls) == sorted(j.title for j in never)
    assert queue.enqueue_never_scored() == 0  # now everything has a score


def test_startup_resume_requeues_but_sends_nothing(jobs: list[Job]) -> None:
    with Session(engine) as s:
        run = ScoringRun(trigger="discovery", primary_model=CLOUD)
        s.add(run)
        s.commit()
        s.refresh(run)
        for n, job in enumerate(jobs):
            status = ScoringTaskStatus.in_progress if n == 0 else ScoringTaskStatus.queued
            s.add(ScoringTask(run_id=run.id, job_id=job.id, force=True, position=n,
                              status=status))
        s.commit()
    scorer = Scripted(CLOUD)
    restarted = ScoringQueue(engine, lambda model: scorer)
    assert restarted.resume(start=False) == len(jobs)  # what app startup does
    assert scorer.calls == [] and not restarted._alive()
    assert all(t.status == ScoringTaskStatus.queued for t in tasks_of(restarted))
    restarted.start()  # your explicit start
    assert restarted.wait(10) and len(scorer.calls) == len(jobs)
