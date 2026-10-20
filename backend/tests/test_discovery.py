import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import DiscoveryRun, Job, SourceRun
from app.models.enums import RemoteType, RunStatus, Source
from app.providers.base import ProfileSpec, RawJob
from app.seed.seed import seed
from app.services import discovery
from app.services.discovery import RunInProgress, run_discovery


def raw(source: Source, eid: str, title: str = "Data Engineer", company: str = "Acme S.L.",
        country: str | None = "ES", **kw) -> RawJob:
    return RawJob(
        source=source, external_id=eid, url=f"https://x.test/{source}/{eid}", title=title,
        company=company, location=kw.pop("location", "Madrid, Spain"), country=country,
        remote_type=kw.pop("remote_type", RemoteType.hybrid),
        posted_at=datetime.now(UTC) - timedelta(days=1), description="Build pipelines.", **kw,
    )


class FakeSource:
    def __init__(self, source: Source, jobs=None, error: Exception | None = None,
                 cooldown_hours: float = 0, configured: str | None = None):
        self.source, self.jobs, self.error = source, jobs or [], error
        self.cooldown_hours, self._configured, self.requests, self.calls = (
            cooldown_hours, configured, 0, 0,
        )

    def configured(self) -> str | None:
        return self._configured

    def fetch(self, profile: ProfileSpec) -> list[RawJob]:
        self.calls += 1
        self.requests = 1
        if self.error:
            raise self.error
        return list(self.jobs)


@pytest.fixture()
def empty_db() -> None:
    seed(engine, empty=True)


def source_runs(run_id: int) -> dict[str, SourceRun]:
    with Session(engine) as s:
        rows = s.exec(select(SourceRun).where(SourceRun.discovery_run_id == run_id)).all()
        return {r.source: r for r in rows}


def jobs() -> list[Job]:
    with Session(engine) as s:
        return list(s.exec(select(Job)).all())


def test_counts_filter_report_and_idempotency(empty_db: None) -> None:
    src = FakeSource(Source.adzuna, [
        raw(Source.adzuna, "1"),
        raw(Source.adzuna, "2", title="Sales Manager"),
        raw(Source.adzuna, "3", title="Data Engineer Intern"),
    ])
    run_id = run_discovery(engine, {Source.adzuna: src})
    sr = source_runs(run_id)["adzuna"]
    assert (sr.status, sr.fetched_count, sr.kept_count, sr.filtered_count, sr.new_count) == (
        RunStatus.success, 3, 1, 2, 1,
    )
    assert sr.details["reasons"] == {"title_no_role_match": 1, "title_excluded:intern": 1}
    assert {x["title"] for x in sr.details["samples"]} == {"Sales Manager", "Data Engineer Intern"}

    # Second run with the same listing (title changed upstream): additive discovery keeps the
    # stored job exactly as it was, only last_seen_at moves; no new rows.
    src.jobs = [raw(Source.adzuna, "1", title="Senior Data Engineer")]
    run2 = run_discovery(engine, {Source.adzuna: src})
    sr2 = source_runs(run2)["adzuna"]
    assert (sr2.new_count, sr2.updated_count) == (0, 1)
    all_jobs = jobs()
    assert len(all_jobs) == 1 and all_jobs[0].title == "Data Engineer"
    assert all_jobs[0].last_seen_at is not None


def test_cross_source_duplicate(empty_db: None) -> None:
    a = FakeSource(Source.adzuna, [raw(Source.adzuna, "a1", title="Data Engineer (m/f/d)")])
    w = FakeSource(Source.wttj, [raw(Source.wttj, "w1", title="Data Engineer - Remote",
                                     company="ACME SL")])
    run_id = run_discovery(engine, {Source.adzuna: a, Source.wttj: w})
    runs = source_runs(run_id)
    assert runs["adzuna"].new_count == 1 and runs["wttj"].duplicate_count == 1
    by_source = {j.source: j for j in jobs()}
    assert by_source["wttj"].duplicate_of_id == by_source["adzuna"].id


def test_failing_source_does_not_break_others(empty_db: None) -> None:
    ok = FakeSource(Source.remotive, [raw(Source.remotive, "r1", country=None,
                                          remote_type=RemoteType.remote, location="Europe")])
    bad = FakeSource(Source.arbeitnow, error=RuntimeError("HTTP 503 upstream down"))
    unconfigured = FakeSource(Source.adzuna, configured="ADZUNA_APP_ID/ADZUNA_APP_KEY missing")
    run_id = run_discovery(engine, {Source.arbeitnow: bad, Source.remotive: ok,
                                    Source.adzuna: unconfigured})
    runs = source_runs(run_id)
    assert runs["arbeitnow"].status == RunStatus.failed
    assert "503" in (runs["arbeitnow"].error or "")
    assert runs["adzuna"].status == RunStatus.failed
    assert "Not configured" in (runs["adzuna"].error or "")
    assert runs["remotive"].status == RunStatus.success and runs["remotive"].new_count == 1
    with Session(engine) as s:
        run = s.get(DiscoveryRun, run_id)
        assert run is not None and run.status == RunStatus.partial
        assert run.totals["failed"] == 2 and run.totals["new"] == 1


def test_cooldown_skips_second_fetch(empty_db: None) -> None:
    src = FakeSource(Source.remotive, [], cooldown_hours=6)
    run_discovery(engine, {Source.remotive: src})
    second = run_discovery(engine, {Source.remotive: src})
    assert src.calls == 1
    assert source_runs(second)["remotive"].status == RunStatus.skipped


def test_overlapping_run_is_rejected(empty_db: None) -> None:
    gate = threading.Event()
    release = threading.Event()

    class SlowSource(FakeSource):
        def fetch(self, profile: ProfileSpec) -> list[RawJob]:
            gate.set()
            release.wait(5)
            return []

    slow = SlowSource(Source.adzuna)
    run_id = discovery.start_run_in_background(engine, {Source.adzuna: slow})
    assert gate.wait(5)
    with pytest.raises(RunInProgress):
        run_discovery(engine, {Source.adzuna: FakeSource(Source.adzuna)})
    release.set()
    for _ in range(100):
        if not discovery.is_running():
            break
        threading.Event().wait(0.05)
    assert source_runs(run_id)["adzuna"].status == RunStatus.success


def test_discovery_never_rescores_existing_jobs(empty_db: None) -> None:
    """Additive discovery: a job seen again keeps its content and score; only never-scored jobs
    reach the scoring queue."""
    from app.models import FitScore
    from app.services.scoring import ScoringQueue
    from tests.test_queue import Scripted

    scorer = Scripted("gemma4:31b-cloud")
    queue = ScoringQueue(engine, lambda model: scorer)
    src = FakeSource(Source.adzuna, [raw(Source.adzuna, "1")])
    run_discovery(engine, {Source.adzuna: src}, on_jobs=lambda _ids: queue.enqueue_never_scored())
    assert queue.wait(10) and len(scorer.calls) == 1
    with Session(engine) as s:
        job = s.exec(select(Job)).one()
        before = (job.title, job.description, len(s.exec(select(FitScore)).all()))

    # Same listing again with new upstream text, plus one brand-new listing.
    src.jobs = [raw(Source.adzuna, "1", title="Senior Data Engineer", description_level="full"),
                raw(Source.adzuna, "2", title="AI Engineer")]
    src.jobs[0].description = "Totally rewritten description"
    run_discovery(engine, {Source.adzuna: src}, on_jobs=lambda _ids: queue.enqueue_never_scored())
    assert queue.wait(10)
    assert scorer.calls == ["Data Engineer", "AI Engineer"]  # only the new job was scored
    with Session(engine) as s:
        job = s.get(Job, job.id)
        assert (job.title, job.description) == before[:2]
        scores = s.exec(select(FitScore).where(FitScore.job_id == job.id)).all()
        assert len(scores) == 1  # never rescored by discovery


def test_paused_sources_are_never_run() -> None:
    from app.models import AppSetting

    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "sources")).first()
        if row is None:
            row = AppSetting(key="sources", value={})
        original = dict(row.value)
        row.value = {**original, "paused": {"bayt": "blocked"}}
        s.add(row)
        s.commit()
        assert Source.bayt not in discovery.enabled_sources(s)
        assert discovery.paused_sources(s) == {"bayt": "blocked"}
        row.value = original
        s.add(row)
        s.commit()
        assert Source.bayt in discovery.enabled_sources(s)
