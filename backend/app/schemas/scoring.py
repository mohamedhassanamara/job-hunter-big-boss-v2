from typing import Any, Literal

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
    # Set while every API key is out of quota: when the queue carries on by itself (UTC ISO).
    waiting_until: str | None = None
    # One-off model chosen with "continue with" (this process only), else null.
    override_model: str | None = None
    # This run's model-output counters: calls, invalid, valid_first_try, valid_after_retry,
    # failed_invalid (empty for the mock scorer).
    output_stats: dict[str, int] = {}
    # The current/last queue run: model in use, cloud→local fallback notice, 429 retries,
    # adaptive concurrency limit and range.
    run: dict[str, Any] | None = None
    # Workspace-wide state of the latest scores.
    jobs_total: int
    scored: int
    stale: int
    unscored: int
    failed_jobs: int
    model: str
    prompt_version: str
    # Rescore progress on Today: non-duplicate jobs whose latest score is from the current prompt
    # version and model, out of all non-duplicate jobs.
    current_scored: int = 0
    current_total: int = 0


class ScoringHealth(BaseModel):
    reachable: bool
    model: str
    model_present: bool
    message: str
    models: list[str]
    pull_command: str


class RescoreIn(BaseModel):
    scope: Literal["stale", "failed", "unscored", "all", "outdated", "jobs"] = "stale"
    job_ids: list[int] = []
    # Re-scoring jobs that already have a valid score (all, stale) needs an explicit OK.
    confirm: bool = False


class RescorePreview(BaseModel):
    scope: str
    count: int
    model: str
    eta_seconds: int | None
    # Gemini only: days of quota this takes (today's remaining quota counts) and per-day capacity.
    days: int | None = None
    daily_capacity: int | None = None


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


class ContinueWithIn(BaseModel):
    model: str | None = None  # null: back to Settings → Models
