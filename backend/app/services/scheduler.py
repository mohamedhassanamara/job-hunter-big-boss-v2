"""Daily discovery via APScheduler. Only ever touches the real workspace."""

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
JOB_ID = "daily-discovery"
_scheduler: BackgroundScheduler | None = None


def _run_scheduled() -> None:
    from app.db import engine
    from app.services.discovery import RunInProgress, enabled_sources, run_discovery
    from app.services.scoring import workspace_queue

    with Session(engine) as s:
        sources = job_sources(enabled_sources(s))
    try:
        run_discovery(engine, sources, RunTrigger.scheduled,
                      on_jobs=workspace_queue("real").enqueue)
    except RunInProgress:
        log.info("Scheduled discovery skipped: a run is already in progress")


def configure(schedule: dict[str, Any] | None) -> None:
    if _scheduler is None:
        return
    if _scheduler.get_job(JOB_ID):
        _scheduler.remove_job(JOB_ID)
    schedule = schedule or {}
    if not schedule.get("enabled", True):
        return
    hour, minute = (schedule.get("time") or "07:00").split(":")[:2]
    _scheduler.add_job(
        _run_scheduled,
        CronTrigger(hour=int(hour), minute=int(minute)),
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )


def next_run_at() -> datetime | None:
    job = _scheduler.get_job(JOB_ID) if _scheduler else None
    return job.next_run_time if job else None


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
