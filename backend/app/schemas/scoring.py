from typing import Literal

from pydantic import BaseModel


class InProgress(BaseModel):
    job_id: int
    title: str


class ScoringStatus(BaseModel):
    running: bool
    blocked: str | None
    queued: int
    in_progress: list[InProgress]
    done: int
    failed: int
    total: int
    avg_seconds: float | None
    eta_seconds: int | None
    last_error: str | None
    # This run's model-output counters: calls, invalid, valid_first_try, valid_after_retry,
    # failed_invalid (empty for the mock scorer).
    output_stats: dict[str, int] = {}
    # Workspace-wide state of the latest scores.
    jobs_total: int
    scored: int
    stale: int
    unscored: int
    failed_jobs: int
    model: str
    prompt_version: str


class ScoringHealth(BaseModel):
    reachable: bool
    model: str
    model_present: bool
    message: str
    models: list[str]
    pull_command: str


class RescoreIn(BaseModel):
    scope: Literal["stale", "failed", "unscored", "all", "jobs"] = "stale"
    job_ids: list[int] = []


class Enqueued(BaseModel):
    enqueued: int


class LabelIn(BaseModel):
    label: Literal["good", "maybe", "no"] | None


class PasteIn(BaseModel):
    description: str


class FullListingOut(BaseModel):
    ok: bool
    message: str
    can_paste: bool = False
    characters: int = 0
