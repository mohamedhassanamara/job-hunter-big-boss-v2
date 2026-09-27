"""Fit scoring: cache, staleness and a background queue.

- cache_key = content hash + experience version + model + prompt version. An existing OK score
  with the same key is reused: nothing changed ⇒ no LLM call.
- Stale = the latest OK score was computed against an older experience version. Stale scores
  are only flagged; "Rescore stale" is a user action.
- The queue is persistent (scoring_run / scoring_task) and resumes after a restart. It uses
  the cloud model first with adaptive concurrency, retries concurrency 429s on the same job,
  switches to the local fallback on a usage limit, and checks model health before starting.
"""

import logging
import random
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import (
    AppSetting,
    Company,
    ExperienceItem,
    FitScore,
    Job,
    ScoringRun,
    ScoringTask,
    SearchProfile,
)
from app.models.base import utcnow
from app.models.enums import FitStatus, ScoringTaskStatus
from app.providers.base import (
    ConcurrencyLimited,
    FitScorer,
    JobSnapshot,
    QuotaExceeded,
    ScoringFailed,
)
from app.services import fit
from app.services.experience import format_range
from app.services.geo import country_catalog
from app.services.prompt import load_prompt

log = logging.getLogger("jobhunter.scoring")
DEFAULT_CLOUD = {"min": 1, "start": 4, "max": 4}
PROMPT_NAME = "fit_score"
_WORK_AUTH = {
    "needs_sponsorship": (
        "needs employer visa sponsorship to work in the target countries "
        "(not a citizen or resident of the EU or the Gulf states)"
    ),
    "eu_authorized": "authorized to work in the EU; needs a work visa outside it (e.g. the Gulf)",
}


# ------------------------------------------------------------------------------------ context


@dataclass
class ScoringContext:
    """Everything that is the same for every job in a scoring pass."""

    profile: dict[str, Any]
    scoring: dict[str, Any]
    model: str
    locations: list[str]
    experience_items: list[dict[str, Any]]
    experience_text: str
    experience_version: str
    config: fit.ScoringConfig
    tracks: list[dict[str, Any]] = field(default_factory=list)
    # Settings → Models: cloud primary, optional local fallback, adaptive concurrency range.
    fallback_model: str | None = None
    cloud_concurrency: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CLOUD))
    local_concurrency: int = 2

    @property
    def prompt_version(self) -> str:
        return load_prompt(PROMPT_NAME).version_id


def _setting(s: Session, key: str) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == key)).first()
    return dict(row.value) if row else {}


def _experience_line(item: ExperienceItem) -> str:
    dates = format_range(item.start_date, item.end_date)
    head = f"- [{item.kind}] {item.title}"
    if item.org:
        head += f", {item.org}"
    if dates:
        head += f" ({dates})"
    parts = [head]
    if item.summary:
        parts.append(f"  {fit.one_line(item.summary)}")
    parts += [f"  • {fit.one_line(b, 200)}" for b in item.bullets[:5]]
    if item.tags:
        parts.append(f"  Skills: {', '.join(item.tags)}")
    return "\n".join(parts)


def load_context(s: Session) -> ScoringContext:
    profile = _setting(s, "profile")
    scoring = _setting(s, "scoring")
    models = _setting(s, "models")
    search = s.exec(select(SearchProfile).where(SearchProfile.is_active)).first()
    items = s.exec(
        select(ExperienceItem)
        .where(col(ExperienceItem.is_active))
        .order_by(col(ExperienceItem.kind), col(ExperienceItem.position))
    ).all()
    snapshot = [
        {
            "kind": i.kind, "title": i.title, "org": i.org, "summary": i.summary,
            "bullets": i.bullets, "tags": i.tags, "start": i.start_date, "end": i.end_date,
        }
        for i in items
    ]
    model_cfg = models.get("scoring") or {}
    cloud = {**DEFAULT_CLOUD, **(model_cfg.get("cloud_concurrency") or {})}
    local = int(model_cfg.get("local_concurrency") or scoring.get("concurrency") or 2)
    return ScoringContext(
        profile=profile,
        scoring=scoring,
        model=model_cfg.get("model", "qwen2.5:7b"),
        fallback_model=model_cfg.get("fallback") or None,
        cloud_concurrency={k: max(1, min(8, int(v))) for k, v in cloud.items()},
        local_concurrency=max(1, min(2, local)),
        tracks=search.tracks if search else [],
        locations=search.locations if search else [],
        experience_items=snapshot,
        experience_text="\n".join(_experience_line(i) for i in items)
        or "(no experience entered yet)",
        experience_version=fit.experience_version(snapshot, profile),
        config=fit.ScoringConfig.from_settings(scoring, profile),
    )


def job_content_hash(job: Job, company: Company) -> str:
    return fit.content_hash(job.title, company.name, job.location, job.remote_type,
                            job.description)


_country_names = {c["code"]: c["name"] for c in country_catalog()}


def render(job: Job, company: Company, ctx: ScoringContext) -> tuple[str, str]:
    prompt = load_prompt(PROMPT_NAME)
    languages = ", ".join(
        f"{lang.get('language')} ({lang.get('level')})" for lang in ctx.profile.get("languages", [])
    )
    user = prompt.render(
        headline=ctx.profile.get("headline") or "(not provided)",
        based_in=ctx.profile.get("based_in") or "(not provided)",
        work_authorization=_WORK_AUTH.get(
            ctx.profile.get("work_authorization", "needs_sponsorship"), "unknown"
        ),
        nationality=ctx.profile.get("nationality") or "(not provided)",
        target_countries=", ".join(_country_names.get(c, c) for c in ctx.locations) or "any",
        languages=languages or "(not provided)",
        years_experience=ctx.profile.get("years_experience") or "(not provided)",
        experience=ctx.experience_text,
        title=job.title,
        company=company.name,
        location=f"{job.location or 'unknown'} ({job.country or 'country unknown'})",
        remote_type=job.remote_type,
        description_level={
            "full": "full listing",
            "summary": "summary and key missions only",
            "snippet": "short snippet only",
        }.get(job.description_level, job.description_level),
        description=fit.truncate_description(job.description or "(no description)"),
    )
    return prompt.system, user


# -------------------------------------------------------------------------------------- score


def latest_fit(s: Session, job_id: int) -> FitScore | None:
    return s.exec(
        select(FitScore)
        .where(FitScore.job_id == job_id)
        .order_by(col(FitScore.created_at).desc(), col(FitScore.id).desc())
    ).first()


def score_job(
    engine: Engine,
    job_id: int,
    scorer: FitScorer,
    *,
    force: bool = False,
    ctx: ScoringContext | None = None,
    store_failures: bool = True,
) -> FitScore:
    """Score one job (or reuse the cached score).

    store_failures=True (eval, one-off calls): never raises for model problems; failures are
    stored as status=failed with the error. store_failures=False (the queue): ScoringFailed and
    its retryable subclasses propagate so the queue can retry; it records the final failure."""
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        company = s.get(Company, job.company_id)
        assert company is not None
        ctx = ctx or load_context(s)
        content = job_content_hash(job, company)
        key = fit.cache_key(content, ctx.experience_version, scorer.model, ctx.prompt_version)
        if not force:
            cached = s.exec(
                select(FitScore)
                .where(FitScore.cache_key == key, FitScore.status == FitStatus.ok)
                .order_by(col(FitScore.created_at).desc())
            ).first()
            if cached is not None:
                # Re-surface it as the latest row if an older/other score is newer.
                latest = latest_fit(s, job_id)
                if latest is not None and latest.id != cached.id:
                    cached.created_at = utcnow()
                    s.add(cached)
                    s.commit()
                    s.refresh(cached)
                return cached

        system, user = render(job, company, ctx)
        snapshot = JobSnapshot(title=job.title, company=company.name, location=job.location,
                               remote_type=job.remote_type, description=job.description)
        row = FitScore(
            job_id=job.id,
            model=scorer.model,
            prompt_version=ctx.prompt_version,
            content_hash=content,
            experience_version=ctx.experience_version,
            cache_key=key,
            confidence=fit.confidence(job.description_level, job.description),
        )
        started = time.monotonic()
        try:
            assessment = scorer.assess(system, user, snapshot)
            record = fit.build_record(
                assessment,
                job_text=f"{job.title}\n{job.location}\n{job.description}",
                description_level=job.description_level,
                remote_type=job.remote_type,
                config=ctx.config,
            )
            for name, value in record.items():
                setattr(row, name, value)
            row.status = FitStatus.ok
        except ScoringFailed as exc:
            if not store_failures:
                raise
            row.status, row.error, row.score = FitStatus.failed, str(exc), None
        except Exception as exc:  # unexpected: still visible, never a silent default
            log.exception("scoring job %s crashed", job_id)
            row.status, row.error, row.score = FitStatus.failed, f"Unexpected error: {exc}", None
        row.duration_ms = int((time.monotonic() - started) * 1000)
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def record_failure(engine: Engine, job_id: int, model: str, error: str) -> None:
    """The queue gave up on a job (after its retries): store a visible failed score."""
    with Session(engine) as s:
        ctx = load_context(s)
        s.add(FitScore(job_id=job_id, model=model, prompt_version=ctx.prompt_version,
                       status=FitStatus.failed, error=error[:1000], score=None,
                       experience_version=ctx.experience_version))
        s.commit()


def recompute_all(engine: Engine) -> int:
    """Weights / cap / work authorization changed: recompute stored scores without the LLM."""
    with Session(engine) as s:
        ctx = load_context(s)
        rows = s.exec(select(FitScore).where(FitScore.status == FitStatus.ok)).all()
        n = 0
        for row in rows:
            if not row.sub_scores:
                continue
            score, flags = fit.recompute(row.sub_scores, row.red_flags, ctx.config)
            if score != row.score or flags != row.red_flags:
                row.score, row.red_flags = score, flags
                s.add(row)
                n += 1
        s.commit()
        return n


@dataclass
class ScoreCounts:
    total: int = 0
    scored: int = 0
    stale: int = 0
    unscored: int = 0
    failed: int = 0
    stale_ids: list[int] = field(default_factory=list)
    unscored_ids: list[int] = field(default_factory=list)
    failed_ids: list[int] = field(default_factory=list)


def counts(s: Session) -> ScoreCounts:
    """Per-job state of the latest score: scored (current), stale, failed or unscored."""
    ctx = load_context(s)
    latest: dict[int, FitScore] = {}
    for row in s.exec(select(FitScore).order_by(col(FitScore.created_at), col(FitScore.id))):
        latest[row.job_id] = row
    out = ScoreCounts()
    for job_id in s.exec(select(Job.id)).all():
        out.total += 1
        row = latest.get(job_id)
        if row is None or row.prompt_version is None:  # legacy mock scores count as unscored
            out.unscored += 1
            out.unscored_ids.append(job_id)
        elif row.status == FitStatus.failed:
            out.failed += 1
            out.failed_ids.append(job_id)
        elif row.experience_version != ctx.experience_version:
            out.stale += 1
            out.stale_ids.append(job_id)
        else:
            out.scored += 1
    return out


def estimate_seconds(s: Session, ctx: ScoringContext, n: int) -> int | None:
    """Rough wall time for n jobs with the configured model and parallelism (for the confirm
    dialog). Uses recent real durations for that model; ~20s per call when there is no history."""
    if n <= 0:
        return 0
    recent = s.exec(
        select(FitScore.duration_ms)
        .where(FitScore.model == ctx.model, FitScore.status == FitStatus.ok,
               col(FitScore.duration_ms).is_not(None))
        .order_by(col(FitScore.created_at).desc()).limit(50)
    ).all()
    per_job = (sum(recent) / len(recent) / 1000) if recent else 20.0
    workers = ctx.cloud_concurrency["start"] if is_cloud(ctx.model) else ctx.local_concurrency
    return round(per_job * n / max(1, workers))


# -------------------------------------------------------------------------------------- queue

MAX_ATTEMPTS = 3  # real failures (transient or not) per task; concurrency 429s never count
BACKOFF_BASE, BACKOFF_CAP, JITTER = 2.0, 30.0, 0.3  # seconds; ±30% jitter
RAISE_AFTER = 10  # successes in a row before the adaptive limit goes up by one


def is_cloud(model: str) -> bool:
    return model.endswith(("-cloud", ":cloud"))


def max_concurrency(model: str) -> int:
    """Local models share the laptop (≤ 2 workers); cloud models (`…-cloud`) run remotely."""
    return 8 if is_cloud(model) else 2


class ConcurrencyController:
    """Adaptive parallelism for one queue run.

    - A concurrency 429 lowers the limit by one (not below `minimum`) and pauses NEW calls for
      an exponential backoff with jitter (2s, 4s, 8s… capped at 30s).
    - After RAISE_AFTER successes in a row the limit goes back up by one (not above `maximum`).
    Workers call acquire()/release() around every model call.
    """

    def __init__(
        self, start: int, minimum: int, maximum: int, *,
        clock: Callable[[], float] = time.monotonic, rand: Callable[[], float] = random.random,
    ):
        self._cond = threading.Condition()
        self._clock, self._rand = clock, rand
        self.reconfigure(start, minimum, maximum)

    def reconfigure(self, start: int, minimum: int, maximum: int) -> None:
        with self._cond:
            self.min, self.max = max(1, minimum), max(1, maximum)
            self.limit = max(self.min, min(self.max, start))
            self.active = getattr(self, "active", 0)
            self.streak = self.consecutive_429 = 0
            self.paused_until = 0.0
            self.seen_min = self.seen_max = self.limit
            self._cond.notify_all()

    def acquire(self, stop: Callable[[], bool]) -> bool:
        with self._cond:
            while True:
                if stop():
                    return False
                wait = self.paused_until - self._clock()
                if wait <= 0 and self.active < self.limit:
                    self.active += 1
                    return True
                self._cond.wait(timeout=min(max(wait, 0.02), 0.25))

    def release(self) -> None:
        with self._cond:
            self.active = max(0, self.active - 1)
            self._cond.notify_all()

    def on_success(self) -> None:
        with self._cond:
            self.consecutive_429 = 0
            self.streak += 1
            if self.streak >= RAISE_AFTER and self.limit < self.max:
                self.limit += 1
                self.streak = 0
                self.seen_max = max(self.seen_max, self.limit)
                self._cond.notify_all()

    def on_concurrency_limit(self) -> float:
        """Returns the backoff (seconds) applied before the next call may start."""
        with self._cond:
            self.streak = 0
            self.consecutive_429 += 1
            self.limit = max(self.min, self.limit - 1)
            self.seen_min = min(self.seen_min, self.limit)
            delay = min(BACKOFF_CAP, BACKOFF_BASE * 2 ** (self.consecutive_429 - 1))
            delay *= 1 + JITTER * (2 * self._rand() - 1)
            self.paused_until = max(self.paused_until, self._clock() + delay)
            return delay


_ACTIVE = (ScoringTaskStatus.queued, ScoringTaskStatus.in_progress)


class ScoringQueue:
    """Persistent background scorer for one workspace (tasks live in `scoring_task`).

    Cloud model first (Settings → Models), adaptive concurrency, and:
    - concurrency 429 → the SAME job goes back to the front, retried after backoff, never failed
    - usage/quota limit → the rest of this run uses the local fallback model (visible notice)
    - other errors → up to MAX_ATTEMPTS, then failed; failed tasks get one more try at the end
    - restart → `resume()` puts in-progress tasks back in the queue and carries on
    """

    def __init__(self, engine: Engine, scorer_factory: Callable[[str], FitScorer]):
        self.engine = engine
        self.scorer_factory = scorer_factory
        self._lock = threading.RLock()
        self._workers: list[threading.Thread] = []
        self._scorers: dict[str, FitScorer] = {}
        self._current: dict[int, str] = {}
        self._stop = False  # workers exit (cancel, or paused by a quota limit with no fallback)
        self._cancelled = False  # user cancel: in-flight jobs are dropped, not re-queued
        self.controller: ConcurrencyController | None = None
        self.model: str | None = None
        self.run_id: int | None = None
        self.blocked: str | None = None
        self.last_error: str | None = None
        self.durations: deque[float] = deque(maxlen=30)

    # public -----------------------------------------------------------------------------------

    def enqueue(
        self, job_ids: Iterable[int], *, force: bool = False, front: bool = False,
        trigger: str = "manual",
    ) -> int:
        ids = list(dict.fromkeys(job_ids))
        with self._lock, Session(self.engine) as s:
            busy = set(s.exec(select(ScoringTask.job_id).where(
                col(ScoringTask.status).in_(_ACTIVE))).all())
            new = [i for i in ids if i not in busy]
            if new:
                run = self._active_run(s) or self._new_run(s, trigger)
                positions = s.exec(select(ScoringTask.position).where(
                    col(ScoringTask.status).in_(_ACTIVE))).all()
                if front:
                    base = (min(positions) if positions else 0) - len(new)
                else:
                    base = (max(positions) if positions else 0) + 1
                for n, job_id in enumerate(new):
                    s.add(ScoringTask(run_id=run.id, job_id=job_id, force=force,
                                      position=base + n))
                s.commit()
        if new:
            self.start()
        return len(new)

    def enqueue_never_scored(self, trigger: str = "discovery") -> int:
        """After discovery: jobs that have NO score row at all. Existing scores are never
        re-queued here; rescoring is always an explicit user action."""
        with Session(self.engine) as s:
            scored = select(FitScore.job_id).distinct()
            ids = s.exec(select(Job.id).where(col(Job.id).not_in(scored))
                         .order_by(col(Job.id))).all()
        return self.enqueue(ids, trigger=trigger)

    def resume(self) -> int:
        """At startup: tasks interrupted by a restart go back to the queue, then it runs on."""
        with self._lock, Session(self.engine) as s:
            for task in s.exec(select(ScoringTask).where(
                    ScoringTask.status == ScoringTaskStatus.in_progress)).all():
                task.status = ScoringTaskStatus.queued
                s.add(task)
            s.commit()
            queued = len(s.exec(select(ScoringTask.id).where(
                ScoringTask.status == ScoringTaskStatus.queued)).all())
        if queued:
            self.start()
        else:
            self._finish_if_idle()
        return queued

    def start(self) -> None:
        with self._lock:
            if self._alive():
                return
            with Session(self.engine) as s:
                if not s.exec(select(ScoringTask.id).where(
                        ScoringTask.status == ScoringTaskStatus.queued)).first():
                    return
                ctx = load_context(s)
                run = self._active_run(s) or self._new_run(s, "resume")
                self.run_id = run.id
                fallback_reason = run.fallback_reason
            model, problem = self._choose_model(ctx, fallback_reason)
            if model is None:
                self.blocked = problem
                return
            self.blocked = None
            self._use_model(model, ctx)
            self._stop = self._cancelled = False
            assert self.controller is not None
            self._workers = [
                threading.Thread(target=self._work, daemon=True, name=f"scoring-{i}")
                for i in range(self.controller.max)
            ]
            for t in self._workers:
                t.start()

    def cancel(self) -> int:
        with self._lock, Session(self.engine) as s:
            tasks = s.exec(select(ScoringTask).where(
                ScoringTask.status == ScoringTaskStatus.queued)).all()
            for task in tasks:
                task.status = ScoringTaskStatus.cancelled
                s.add(task)
            s.commit()
            self._stop = self._cancelled = True
        self._finish_if_idle()
        return len(tasks)

    def status(self) -> dict[str, Any]:
        with self._lock, Session(self.engine) as s:
            run = s.get(ScoringRun, self.run_id) if self.run_id else s.exec(
                select(ScoringRun).order_by(col(ScoringRun.id).desc())).first()
            tasks = s.exec(select(ScoringTask.status).where(
                ScoringTask.run_id == run.id)).all() if run else []
            queued = sum(1 for t in tasks if t == ScoringTaskStatus.queued)
            waiting_retry = sum(1 for t in tasks if t == ScoringTaskStatus.failed)
            running = self._alive()
            avg = sum(self.durations) / len(self.durations) if self.durations else None
            limit = self.controller.limit if self.controller else 1
            remaining = queued + len(self._current) + (waiting_retry if running else 0)
            stats: dict[str, int] = {}
            for scorer in self._scorers.values():
                for k, v in (getattr(scorer, "stats", {}) or {}).items():
                    stats[k] = stats.get(k, 0) + v
            return {
                "running": running,
                "blocked": self.blocked,
                "queued": queued,
                "in_progress": [{"job_id": k, "title": v} for k, v in self._current.items()],
                "done": run.done if run else 0,
                "failed": run.failed if run else 0,
                "total": len([t for t in tasks if t != ScoringTaskStatus.cancelled]),
                "avg_seconds": round(avg, 1) if avg else None,
                "eta_seconds": round(avg * remaining / max(1, limit)) if avg and remaining
                else None,
                "last_error": self.last_error,
                "output_stats": stats,
                "run": None if run is None else {
                    "id": run.id, "trigger": run.trigger,
                    "model": self.model or run.primary_model,
                    "primary_model": run.primary_model, "fallback_model": run.fallback_model,
                    "fallback_reason": run.fallback_reason,
                    "fallback_at": run.fallback_at.isoformat() if run.fallback_at else None,
                    "retried_429": run.retried_429, "quota_hits": run.quota_hits,
                    "concurrency_limit": self.controller.limit if self.controller else None,
                    "concurrency_min": run.concurrency_min, "concurrency_max": run.concurrency_max,
                    "finished": run.finished_at is not None,
                },
            }

    def wait(self, timeout: float = 30) -> bool:
        """Test helper: block until the queue is idle."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if not self._alive():
                    return True
            time.sleep(0.02)
        return False

    # model choice -----------------------------------------------------------------------------

    def _scorer_for(self, model: str) -> FitScorer:
        with self._lock:
            if model not in self._scorers:
                self._scorers[model] = self.scorer_factory(model)
            return self._scorers[model]

    def _healthy(self, model: str) -> tuple[bool, str]:
        health = getattr(self._scorer_for(model), "health", None)
        if health is None:  # mock scorers
            return True, "Ready"
        status = health()
        return bool(status.ok), str(status.message)

    def _choose_model(
        self, ctx: ScoringContext, fallback_reason: str | None
    ) -> tuple[str | None, str]:
        fallback = ctx.fallback_model if ctx.fallback_model != ctx.model else None
        if fallback_reason and fallback:  # this run already hit the cloud usage limit
            ok, message = self._healthy(fallback)
            return (fallback, "") if ok else (None, message)
        ok, message = self._healthy(ctx.model)
        if ok:
            return ctx.model, ""
        if fallback and self._healthy(fallback)[0]:
            self._record_fallback(f"{ctx.model} unavailable: {message}", fallback)
            return fallback, ""
        return None, message

    def _use_model(self, model: str, ctx: ScoringContext) -> None:
        self.model = model
        if is_cloud(model):
            c = ctx.cloud_concurrency
            start, low, high = c["start"], c["min"], c["max"]
        else:
            start = low = high = ctx.local_concurrency
        if self.controller is None:
            self.controller = ConcurrencyController(start, low, high)
        else:
            self.controller.reconfigure(start, low, high)
        self._update_run(concurrency_min=self.controller.limit,
                         concurrency_max=self.controller.limit, set_models=(ctx, model))

    def _switch_to_fallback(self, reason: str, failed_model: str) -> bool:
        """Cloud usage limit: the rest of this run goes to the local model. False if there is no
        usable fallback (the queue then pauses; tasks stay queued, nothing is failed).
        `failed_model` is the model that hit the limit: parallel calls hit it together, and only
        the first one switches; the others just retry on the new model."""
        with self._lock, Session(self.engine) as s:
            ctx = load_context(s)
            if self.model != failed_model:  # another worker already switched
                return True
        fallback = ctx.fallback_model
        if not fallback or fallback == failed_model:
            self.blocked = f"{reason}. No local fallback model configured (Settings → Models)."
            self._stop = True
            return False
        with self._lock:
            if self.model != fallback:
                self._record_fallback(reason, fallback)
                self._use_model(fallback, ctx)
                log.warning("scoring switched to %s: %s", fallback, reason)
        return True

    # workers ----------------------------------------------------------------------------------

    def _work(self) -> None:
        assert self.controller is not None
        while True:
            if not self.controller.acquire(lambda: self._stop):
                return
            task = self._claim()
            if task is None:
                self.controller.release()
                if self._final_retry_round():
                    continue
                self._finish_if_idle()
                return
            try:
                self._run_task(task)
            finally:
                self.controller.release()

    def _claim(self) -> ScoringTask | None:
        with self._lock, Session(self.engine) as s:
            if self._stop:
                return None
            task = s.exec(select(ScoringTask).where(
                ScoringTask.status == ScoringTaskStatus.queued
            ).order_by(col(ScoringTask.position), col(ScoringTask.id))).first()
            if task is None:
                return None
            task.status = ScoringTaskStatus.in_progress
            s.add(task)
            s.commit()
            s.refresh(task)
            job = s.get(Job, task.job_id)
            self._current[task.job_id] = job.title if job else f"Job {task.job_id}"
            s.expunge(task)
            return task

    def _run_task(self, task: ScoringTask) -> None:
        assert self.controller is not None
        model = self.model or ""
        started = time.monotonic()
        try:
            row = score_job(self.engine, task.job_id, self._scorer_for(model), force=task.force,
                            store_failures=False)
        except ConcurrencyLimited as exc:
            self.controller.on_concurrency_limit()
            self._update_run(retried_429=1, concurrency_min=self.controller.limit)
            self._requeue(task, front=True, error=str(exc))
            return
        except QuotaExceeded as exc:
            self._update_run(quota_hits=1)
            self._switch_to_fallback(str(exc), model)
            self._requeue(task, front=True, error=str(exc))
            return
        except Exception as exc:  # TransientError, ScoringFailed, DB errors… (not a default)
            if not isinstance(exc, ScoringFailed):
                log.exception("scoring job %s crashed", task.job_id)
            self._failed_attempt(task, model, str(exc) or exc.__class__.__name__)
            return
        self.controller.on_success()
        self.durations.append(time.monotonic() - started)
        self._update_run(done=1, concurrency_max=self.controller.limit)
        self._finish_task(task, ScoringTaskStatus.done, model_used=row.model)

    def _requeue(self, task: ScoringTask, *, front: bool, error: str | None = None,
                 count_attempt: bool = False) -> None:
        with self._lock, Session(self.engine) as s:
            row = s.get(ScoringTask, task.id)
            if row is None:
                return
            positions = s.exec(select(ScoringTask.position).where(
                col(ScoringTask.status).in_(_ACTIVE), ScoringTask.id != task.id)).all()
            if front:
                row.position = (min(positions) if positions else row.position) - 1
            else:
                row.position = (max(positions) if positions else row.position) + 1
            row.status = (ScoringTaskStatus.cancelled if self._cancelled
                          else ScoringTaskStatus.queued)
            row.attempts += 1 if count_attempt else 0
            row.last_error = error
            s.add(row)
            s.commit()
            self._current.pop(task.job_id, None)

    def _failed_attempt(self, task: ScoringTask, model: str, error: str) -> None:
        self.last_error = error
        attempts = task.attempts + 1
        if attempts < MAX_ATTEMPTS:
            self._requeue(task, front=False, error=error, count_attempt=True)
            return
        if task.final_retry:  # already had its end-of-run retry: this is final
            record_failure(self.engine, task.job_id, model, error)
            self._update_run(failed=1)
        self._finish_task(task, ScoringTaskStatus.failed, attempts=attempts, error=error)

    def _finish_task(self, task: ScoringTask, status: ScoringTaskStatus, *,
                     model_used: str | None = None, attempts: int | None = None,
                     error: str | None = None) -> None:
        with self._lock, Session(self.engine) as s:
            row = s.get(ScoringTask, task.id)
            if row is not None:
                row.status = status
                row.model_used = model_used or row.model_used
                row.attempts = attempts if attempts is not None else row.attempts
                row.last_error = error
                row.finished_at = utcnow()
                s.add(row)
                s.commit()
            self._current.pop(task.job_id, None)

    def _final_retry_round(self) -> bool:
        """Queue drained: failed tasks of this run get one more try (attempts reset)."""
        with self._lock, Session(self.engine) as s:
            if self._stop or self._current or not self.run_id:
                return False
            tasks = s.exec(select(ScoringTask).where(
                ScoringTask.run_id == self.run_id,
                ScoringTask.status == ScoringTaskStatus.failed,
                col(ScoringTask.final_retry).is_(False))).all()
            for task in tasks:
                task.status, task.final_retry, task.attempts = (
                    ScoringTaskStatus.queued, True, 0)
                s.add(task)
            s.commit()
            return bool(tasks)

    def _finish_if_idle(self) -> None:
        with self._lock, Session(self.engine) as s:
            busy = s.exec(select(ScoringTask.id).where(
                col(ScoringTask.status).in_(_ACTIVE))).first()
            if busy and not self._cancelled:
                return
            run = self._active_run(s)
            if run is not None and not self._current:
                run.finished_at = utcnow()
                s.add(run)
                s.commit()

    # runs -------------------------------------------------------------------------------------

    @staticmethod
    def _active_run(s: Session) -> ScoringRun | None:
        return s.exec(select(ScoringRun).where(col(ScoringRun.finished_at).is_(None))
                      .order_by(col(ScoringRun.id).desc())).first()

    def _new_run(self, s: Session, trigger: str) -> ScoringRun:
        ctx = load_context(s)
        run = ScoringRun(trigger=trigger, primary_model=ctx.model,
                         fallback_model=ctx.fallback_model)
        s.add(run)
        s.commit()
        s.refresh(run)
        self.run_id = run.id
        self.last_error = None
        self.durations.clear()
        return run

    def _record_fallback(self, reason: str, fallback: str) -> None:
        with self._lock, Session(self.engine) as s:
            run = s.get(ScoringRun, self.run_id) if self.run_id else None
            if run is not None and run.fallback_reason is None:
                run.fallback_reason, run.fallback_at = reason[:300], utcnow()
                run.fallback_model = fallback
                s.add(run)
                s.commit()

    def _update_run(self, *, done: int = 0, failed: int = 0, retried_429: int = 0,
                    quota_hits: int = 0, concurrency_min: int | None = None,
                    concurrency_max: int | None = None,
                    set_models: tuple[ScoringContext, str] | None = None) -> None:
        with self._lock, Session(self.engine) as s:
            run = s.get(ScoringRun, self.run_id) if self.run_id else None
            if run is None:
                return
            run.done += done
            run.failed += failed
            run.retried_429 += retried_429
            run.quota_hits += quota_hits
            if concurrency_min is not None:
                run.concurrency_min = min(run.concurrency_min or concurrency_min,
                                          concurrency_min)
            if concurrency_max is not None:
                run.concurrency_max = max(run.concurrency_max or concurrency_max,
                                          concurrency_max)
            if set_models and not run.primary_model:
                run.primary_model = set_models[0].model
            s.add(run)
            s.commit()

    def _alive(self) -> bool:
        return any(t.is_alive() for t in self._workers)


_queues: dict[int, ScoringQueue] = {}
_queues_lock = threading.Lock()


def queue_for(engine: Engine, *, mock: bool) -> ScoringQueue:
    """One queue per workspace engine (real = Ollama, sandbox/tests = mock)."""
    from app.providers.registry import fit_scorer

    with _queues_lock:
        queue = _queues.get(id(engine))
        if queue is None:
            queue = ScoringQueue(engine, lambda model: fit_scorer(mock=mock, model=model))
            _queues[id(engine)] = queue
        return queue


def workspace_queue(workspace: str) -> ScoringQueue:
    """The queue for a workspace: the tour sandbox (and tests) always use the mock scorer."""
    from app.config import get_settings
    from app.db import engine_for

    mock = workspace == "demo" or get_settings().job_sources == "mock"
    return queue_for(engine_for(workspace), mock=mock)  # type: ignore[arg-type]
