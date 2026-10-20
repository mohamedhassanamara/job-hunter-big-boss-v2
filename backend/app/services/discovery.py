"""Discovery runs: fetch every enabled source, pre-filter, ingest. One run at a time.

A run is a DiscoveryRun with one SourceRun per enabled source. Each source is isolated: a
failure is recorded on its SourceRun and never stops the others.
"""

import logging
import threading
from collections.abc import Callable
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.config import get_settings
from app.models import AppSetting, DiscoveryRun, SearchProfile, SourceRun
from app.models.base import utcnow
from app.models.enums import DISCOVERY_SOURCES, RunStatus, RunTrigger, Source
from app.providers.base import JobSource, ProfileSpec
from app.services.ingest import ingest
from app.services.prefilter import prefilter

_lock = threading.Lock()
MAX_SAMPLES = 50


class RunInProgress(RuntimeError):
    pass


def _logger() -> logging.Logger:
    log = logging.getLogger("jobhunter.discovery")
    if not log.handlers:
        log_dir = get_settings().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_dir / "discovery.log", maxBytes=2_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log


def _source_flags(session: Session) -> dict[str, Any]:
    setting = session.exec(select(AppSetting).where(AppSetting.key == "sources")).first()
    return setting.value if setting else {}


def paused_sources(session: Session) -> dict[str, str]:
    """Sources paused with a reason (e.g. blocked by the site): never run by any run, and no
    failure alert while paused. Resuming (Settings → Sources) removes the entry."""
    paused = _source_flags(session).get("paused")
    return {k: str(v) for k, v in paused.items()} if isinstance(paused, dict) else {}


def enabled_sources(session: Session) -> list[Source]:
    flags, paused = _source_flags(session), paused_sources(session)
    return [s for s in DISCOVERY_SOURCES if flags.get(s.value, True) and s.value not in paused]


def prepare_source(session: Session, source: JobSource) -> JobSource:
    """Hand a source its Settings value (e.g. the company board list) before it is used."""
    if key := getattr(source, "settings_key", None):
        row = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
        source.apply_settings(row.value if row else {})  # type: ignore[attr-defined]
    return source


def active_profile(session: Session) -> tuple[int | None, ProfileSpec]:
    profile = session.exec(select(SearchProfile).where(SearchProfile.is_active)).first()
    if profile is None:
        return None, ProfileSpec()
    return profile.id, ProfileSpec.model_validate(profile, from_attributes=True)


def is_running() -> bool:
    return _lock.locked()


def mark_stale_runs(engine: Engine) -> None:
    """Called at startup: nothing can be running yet, so leftover 'running' rows were
    interrupted by a crash or restart and will never finish."""
    unfinished = [RunStatus.running, RunStatus.pending]
    with Session(engine) as s:
        for run in s.exec(select(DiscoveryRun).where(col(DiscoveryRun.status).in_(unfinished))):
            run.status, run.finished_at = RunStatus.failed, utcnow()
            s.add(run)
        for sr in s.exec(select(SourceRun).where(col(SourceRun.status).in_(unfinished))):
            sr.status, sr.finished_at = RunStatus.failed, utcnow()
            sr.error = "Interrupted (the app restarted mid-run)"
            s.add(sr)
        s.commit()


def begin_run(engine: Engine, trigger: RunTrigger, sources: list[Source]) -> int:
    """Reserve the run lock and create the run rows. Caller must then call execute_run."""
    if not _lock.acquire(blocking=False):
        raise RunInProgress("A discovery run is already in progress")
    try:
        with Session(engine) as s:
            profile_id, _ = active_profile(s)
            run = DiscoveryRun(trigger=trigger)
            s.add(run)
            s.flush()
            for src in sources:
                s.add(
                    SourceRun(
                        discovery_run_id=run.id,
                        source=src,
                        profile_id=profile_id,
                        status=RunStatus.pending,
                    )
                )
            s.commit()
            return run.id
    except Exception:
        _lock.release()
        raise


def _last_fetch(s: Session, source: Source, exclude_run: int) -> SourceRun | None:
    return s.exec(
        select(SourceRun)
        .where(
            SourceRun.source == source,
            col(SourceRun.status).in_([RunStatus.success, RunStatus.partial]),
            SourceRun.discovery_run_id != exclude_run,
        )
        .order_by(col(SourceRun.started_at).desc())
    ).first()


def cooldown_remaining(s: Session, source: JobSource, exclude_run: int = -1) -> timedelta | None:
    if not source.cooldown_hours:
        return None
    last = _last_fetch(s, source.source, exclude_run)
    if last is None:
        return None
    remaining = last.started_at + timedelta(hours=source.cooldown_hours) - utcnow()
    return remaining if remaining.total_seconds() > 0 else None


def _run_source(engine: Engine, run_id: int, source: JobSource) -> list[int]:
    log = _logger()
    with Session(engine) as s:
        sr = s.exec(
            select(SourceRun).where(
                SourceRun.discovery_run_id == run_id, SourceRun.source == source.source
            )
        ).one()
        sr.status, sr.started_at = RunStatus.running, utcnow()
        s.add(sr)
        s.commit()
        try:
            prepare_source(s, source)
            if reason := source.configured():
                raise RuntimeError(f"Not configured: {reason}")
            if wait := cooldown_remaining(s, source, exclude_run=run_id):
                hours = wait.total_seconds() / 3600
                sr.status = RunStatus.skipped
                sr.error = (
                    f"Skipped: fetched recently (cooldown {source.cooldown_hours:g}h, "
                    f"{hours:.1f}h left)"
                )
                sr.finished_at = utcnow()
                s.add(sr)
                s.commit()
                log.info("%s skipped: cooldown", source.source)
                return []

            profile_id, profile = active_profile(s)
            raw = source.fetch(profile)
            result = prefilter(raw, profile)
            stats = ingest(s, result.kept, source_run_id=sr.id, profile_id=profile_id)
            sr.fetched_count = len(raw)
            sr.kept_count = len(result.kept)
            sr.filtered_count = len(result.dropped)
            sr.new_count, sr.updated_count, sr.duplicate_count = (
                stats.new, stats.updated, stats.duplicates,
            )
            sr.details = {
                "requests": source.requests,
                "warnings": list(getattr(source, "warnings", [])),
                "boards": dict(getattr(source, "board_results", {})),
                "reasons": result.reason_counts(),
                "samples": [
                    {
                        "title": d.job.title,
                        "company": d.job.company,
                        "location": d.job.location,
                        "reason": d.reason,
                        "url": d.job.url,
                    }
                    for d in result.dropped[:MAX_SAMPLES]
                ],
            }
            sr.status, sr.finished_at = RunStatus.success, utcnow()
            s.add(sr)
            s.commit()
            log.info(
                "%s: fetched=%d kept=%d filtered=%d new=%d updated=%d duplicates=%d requests=%d",
                source.source, len(raw), len(result.kept), len(result.dropped), stats.new,
                stats.updated, stats.duplicates, source.requests,
            )
            for d in result.dropped:
                log.info("%s filtered [%s] %s | %s | %s", source.source, d.reason, d.job.title,
                         d.job.company, d.job.location)
            return stats.job_ids
        except Exception as exc:  # one source must never break the others
            s.rollback()
            sr = s.get(SourceRun, sr.id)
            assert sr is not None
            sr.status, sr.finished_at = RunStatus.failed, utcnow()
            sr.error = str(exc)[:1000] or type(exc).__name__
            s.add(sr)
            s.commit()
            log.exception("%s failed", source.source)
            return []


def execute_run(
    engine: Engine,
    run_id: int,
    sources: dict[Source, JobSource],
    on_jobs: Callable[[list[int]], None] | None = None,
) -> None:
    """Run every source of a begun run, then finalize it. Always releases the lock.
    `on_jobs` receives the new/changed job ids (the scoring queue)."""
    job_ids: list[int] = []
    try:
        for source in sources.values():
            job_ids += _run_source(engine, run_id, source)
        with Session(engine) as s:
            run = s.get(DiscoveryRun, run_id)
            assert run is not None
            srs = s.exec(select(SourceRun).where(SourceRun.discovery_run_id == run_id)).all()
            statuses = {sr.status for sr in srs}
            if statuses <= {RunStatus.success, RunStatus.skipped}:
                run.status = RunStatus.success
            elif statuses == {RunStatus.failed}:
                run.status = RunStatus.failed
            else:
                run.status = RunStatus.partial
            run.totals = {
                key: sum(getattr(sr, f"{key}_count") for sr in srs)
                for key in ("fetched", "kept", "filtered", "new", "updated", "duplicate")
            } | {"failed": sum(1 for sr in srs if sr.status == RunStatus.failed)}
            run.finished_at = utcnow()
            s.add(run)
            s.commit()
    finally:
        _lock.release()
    if on_jobs:  # even with no new jobs: leftovers that were never scored get queued too
        try:
            on_jobs(job_ids)
        except Exception:
            _logger().exception("could not queue scoring")


def after_discovery(engine: Engine, job_ids: list[int], queue: Any = None) -> None:
    """What every run does with its jobs: resolve contacts (local, instant), then queue scoring
    for jobs never scored. Each step is isolated: one failing never blocks the other."""
    from app.services.contacts import resolve_after_discovery

    try:
        resolve_after_discovery(engine, job_ids)
    except Exception:
        _logger().exception("contact matching after discovery failed")
    if queue is not None:
        from app.services.scoring import auto_score_enabled

        if auto_score_enabled(engine):
            queue.enqueue_never_scored()


def run_discovery(
    engine: Engine,
    sources: dict[Source, JobSource],
    trigger: RunTrigger = RunTrigger.manual,
    on_jobs: Callable[[list[int]], None] | None = None,
) -> int:
    """Synchronous run (scheduler, tests)."""
    run_id = begin_run(engine, trigger, list(sources))
    execute_run(engine, run_id, sources, on_jobs)
    return run_id


def start_run_in_background(
    engine: Engine,
    sources: dict[Source, JobSource],
    trigger: RunTrigger = RunTrigger.manual,
    on_jobs: Callable[[list[int]], None] | None = None,
) -> int:
    run_id = begin_run(engine, trigger, list(sources))
    threading.Thread(
        target=execute_run,
        args=(engine, run_id, sources, on_jobs),
        name=f"discovery-{run_id}",
        daemon=True,
    ).start()
    return run_id


class SourceCoolingDown(RuntimeError):
    pass


def test_source(engine: Engine, source: JobSource):  # noqa: ANN201 (FilterResult)
    """Dry run: fetch + parse + pre-filter, write no jobs. Recorded as a `test` SourceRun so it
    still counts towards the source's cooldown (Remotive's daily request budget)."""
    if _lock.locked():
        raise RunInProgress("A discovery run is in progress; try again when it finishes")
    with Session(engine) as s:
        prepare_source(s, source)
        if reason := source.configured():
            raise RuntimeError(f"Not configured: {reason}")
        if wait := cooldown_remaining(s, source):
            minutes = int(wait.total_seconds() // 60) + 1
            raise SourceCoolingDown(
                f"Fetched recently; this source asks for at most one fetch every "
                f"{source.cooldown_hours:g}h. Try again in {minutes} min."
            )
        profile_id, profile = active_profile(s)
        run = DiscoveryRun(trigger=RunTrigger.test)
        s.add(run)
        s.flush()
        sr = SourceRun(discovery_run_id=run.id, source=source.source, profile_id=profile_id,
                       status=RunStatus.running)
        s.add(sr)
        s.commit()
        try:
            raw = source.fetch(profile)
            result = prefilter(raw, profile)
        except Exception as exc:
            sr.status = run.status = RunStatus.failed
            sr.error = str(exc)[:1000]
            sr.finished_at = run.finished_at = utcnow()
            s.add_all([sr, run])
            s.commit()
            raise
        sr.status = run.status = RunStatus.success
        sr.fetched_count, sr.kept_count, sr.filtered_count = (
            len(raw), len(result.kept), len(result.dropped),
        )
        sr.details = {
            "dry_run": True,
            "requests": source.requests,
            "warnings": list(getattr(source, "warnings", [])),
            "boards": dict(getattr(source, "board_results", {})),
            "reasons": result.reason_counts(),
        }
        sr.finished_at = run.finished_at = utcnow()
        run.totals = {"fetched": len(raw), "kept": len(result.kept),
                      "filtered": len(result.dropped)}
        s.add_all([sr, run])
        s.commit()
        return result, source.requests, list(getattr(source, "warnings", []))
