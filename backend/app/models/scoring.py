"""Persistent scoring queue: survives restarts (in_progress tasks are re-queued at startup)."""

from datetime import datetime

from sqlmodel import Field

from app.models.base import TableBase, dt_field, enum_field, utcnow
from app.models.enums import ScoringTaskStatus


class ScoringRun(TableBase, table=True):
    """One pass of the queue (after discovery, an explicit rescore, or a manual start)."""

    __tablename__ = "scoring_run"

    trigger: str = "manual"  # discovery | rescore | manual | resume
    started_at: datetime = dt_field(default_factory=utcnow)
    finished_at: datetime | None = dt_field()
    primary_model: str = ""
    fallback_model: str | None = None
    # Set when a cloud usage/quota limit switched the rest of the run to the local model.
    fallback_reason: str | None = None
    fallback_at: datetime | None = dt_field()
    done: int = 0
    failed: int = 0
    retried_429: int = 0  # concurrency 429s: re-queued at the front, never failures
    quota_hits: int = 0
    concurrency_min: int | None = None  # adaptive limit range seen during the run
    concurrency_max: int | None = None


class ScoringTask(TableBase, table=True):
    __tablename__ = "scoring_task"

    run_id: int = Field(foreign_key="scoring_run.id", index=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    force: bool = False  # explicit rescore: ignore the cache
    open_only: bool = True  # re-checked at pick time (False: per-job Rescore)
    position: float = Field(default=0, index=True)  # smaller = sooner; front = min - 1
    status: ScoringTaskStatus = enum_field(ScoringTaskStatus.queued, index=True)
    attempts: int = 0  # counted for real failures only (never for concurrency 429s)
    final_retry: bool = False  # failed tasks get one more try at the end of the run
    last_error: str | None = None
    model_used: str | None = None
    finished_at: datetime | None = dt_field()
