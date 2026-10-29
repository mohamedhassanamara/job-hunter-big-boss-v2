"""Scheduled discovery via APScheduler (several times a day, optionally weekdays only). Only
ever touches the real workspace."""

import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.models import AppSetting
from app.models.enums import RunTrigger
from app.providers.registry import job_sources

log = logging.getLogger("jobhunter.discovery")
JOB_ID = "daily-discovery"  # each time of day is JOB_ID-0, JOB_ID-1, …
DEFAULT_TIMES = ["07:00", "15:00"]
MAX_TIMES = 6
_scheduler: BackgroundScheduler | None = None


def _run_scheduled() -> None:
    from app.db import engine
    from app.services.discovery import (
        RunInProgress,
        after_discovery,
        enabled_sources,
        run_discovery,
    )
    from app.services.scoring import workspace_queue

    with Session(engine) as s:
        sources = job_sources(enabled_sources(s))
    try:
        queue = workspace_queue("real")
        run_discovery(engine, sources, RunTrigger.scheduled,
                      on_jobs=lambda ids: after_discovery(engine, ids, queue))
    except RunInProgress:
        log.info("Scheduled discovery skipped: a run is already in progress")


def normalize(schedule: dict[str, Any] | None) -> tuple[list[str], bool]:
    """(times of day, weekdays only). A stored `{time: "07:00"}` (one run a day, every day)
    keeps working: it is one time, weekends included."""
    schedule = schedule or {}
    times = schedule.get("times")
    if not times:
        times = [schedule["time"]] if schedule.get("time") else DEFAULT_TIMES[:1]
    return sorted(dict.fromkeys(times)), bool(schedule.get("weekdays_only", False))


def valid_time(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return False
    hh, mm = value[:2], value[3:]
    return hh.isdigit() and mm.isdigit() and int(hh) < 24 and int(mm) < 60


def _job_ids() -> list[str]:
    return [j.id for j in _scheduler.get_jobs() if j.id.startswith(JOB_ID)] if _scheduler else []


def configure(schedule: dict[str, Any] | None) -> None:
    if _scheduler is None:
        return
    for job_id in _job_ids():
        _scheduler.remove_job(job_id)
    if not (schedule or {}).get("enabled", True):
        return
    times, weekdays_only = normalize(schedule)
    for n, at in enumerate(times):
        hour, minute = at.split(":")[:2]
        _scheduler.add_job(
            _run_scheduled,
            CronTrigger(hour=int(hour), minute=int(minute),
                        day_of_week="mon-fri" if weekdays_only else "*"),
            id=f"{JOB_ID}-{n}",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )


def next_run_at() -> datetime | None:
    times = [j.next_run_time for j in _scheduler.get_jobs()
             if j.id.startswith(JOB_ID) and j.next_run_time] if _scheduler else []
    return min(times) if times else None


def start(engine: Any) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.start()
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "schedule")).first()
    configure(row.value if row else None)


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
