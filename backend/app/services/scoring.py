"""Fit scoring: cache, staleness and a background queue.

- cache_key = content hash + experience version + model + prompt version. An existing OK score
  with the same key is reused: nothing changed ⇒ no LLM call.
- Stale = the latest OK score was computed against an older experience version. Stale scores
  are only flagged; "Rescore stale" is a user action.
- The queue runs in 1-2 worker threads per workspace. Before starting it checks the model is
  available; if not, it reports one clear "blocked" reason instead of failing every job.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import AppSetting, Company, ExperienceItem, FitScore, Job, SearchProfile
from app.models.base import utcnow
from app.models.enums import FitStatus
from app.providers.base import FitScorer, JobSnapshot, ScoringFailed
from app.services import fit
from app.services.experience import format_range
from app.services.geo import country_catalog
from app.services.prompt import load_prompt

log = logging.getLogger("jobhunter.scoring")
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
    return ScoringContext(
        profile=profile,
        scoring=scoring,
        model=(models.get("scoring") or {}).get("model", "qwen2.5:7b"),
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
) -> FitScore:
    """Score one job (or reuse the cached score). Never raises for model problems: failures
    are stored as status=failed with the error."""
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
            row.status, row.error, row.score = FitStatus.failed, str(exc), None
        except Exception as exc:  # unexpected: still visible, never a silent default
            log.exception("scoring job %s crashed", job_id)
            row.status, row.error, row.score = FitStatus.failed, f"Unexpected error: {exc}", None
        row.duration_ms = int((time.monotonic() - started) * 1000)
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


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


# -------------------------------------------------------------------------------------- queue


def max_concurrency(model: str) -> int:
    """Local models share the laptop (≤ 2 workers); cloud models (`…-cloud`) run remotely."""
    return 8 if model.endswith(("-cloud", ":cloud")) else 2


class ScoringQueue:
    """Background scorer for one workspace. Thread-safe; the app stays usable while it runs."""

    def __init__(self, engine: Engine, scorer_factory: Callable[[str], FitScorer]):
        self.engine = engine
        self.scorer_factory = scorer_factory
        self._lock = threading.Lock()
        self._pending: deque[tuple[int, bool]] = deque()
        self._queued: set[int] = set()
        self._current: dict[int, str] = {}
        self._workers: list[threading.Thread] = []
        self._cancel = False
        self.done = 0
        self.failed = 0
        self.total = 0
        self.durations: deque[float] = deque(maxlen=20)
        self.started_at: float | None = None
        self.blocked: str | None = None
        self.last_error: str | None = None

    # public -----------------------------------------------------------------------------------

    def enqueue(self, job_ids: Iterable[int], *, force: bool = False, front: bool = False) -> int:
        added = 0
        with self._lock:
            for job_id in job_ids:
                if job_id in self._queued or job_id in self._current:
                    continue
                self._queued.add(job_id)
                if front:
                    self._pending.appendleft((job_id, force))
                else:
                    self._pending.append((job_id, force))
                added += 1
            if added and not self._alive():
                self.done = self.failed = 0
                self.total = 0
                self.started_at = time.monotonic()
            self.total += added
        if added:
            self.start()
        return added

    def start(self) -> None:
        with self._lock:
            if self._alive() or not self._pending:
                return
            scorer, concurrency = self._make_scorer()
            health = getattr(scorer, "health", None)
            if health is not None:
                status = health()
                if not status.ok:
                    self.blocked = status.message
                    return
            self.blocked = None
            self._cancel = False
            self._workers = [
                threading.Thread(target=self._work, args=(scorer,), daemon=True,
                                 name=f"scoring-{i}")
                for i in range(concurrency)
            ]
            for t in self._workers:
                t.start()

    def cancel(self) -> int:
        with self._lock:
            n = len(self._pending)
            self._pending.clear()
            self._queued.clear()
            self._cancel = True
            self.total -= n
            return n

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._alive()
            remaining = len(self._pending) + len(self._current)
            avg = sum(self.durations) / len(self.durations) if self.durations else None
            workers = max(1, len(self._workers))
            return {
                "running": running,
                "blocked": self.blocked,
                "queued": len(self._pending),
                "in_progress": [{"job_id": k, "title": v} for k, v in self._current.items()],
                "done": self.done,
                "failed": self.failed,
                "total": self.total,
                "avg_seconds": round(avg, 1) if avg else None,
                "eta_seconds": round(avg * remaining / workers) if avg and remaining else None,
                "last_error": self.last_error,
            }

    def wait(self, timeout: float = 30) -> bool:
        """Test helper: block until the queue is idle."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if not self._alive() and not self._pending:
                    return True
            time.sleep(0.02)
        return False

    # internals --------------------------------------------------------------------------------

    def _alive(self) -> bool:
        return any(t.is_alive() for t in self._workers)

    def _make_scorer(self) -> tuple[FitScorer, int]:
        with Session(self.engine) as s:
            ctx = load_context(s)
        wanted = int(ctx.scoring.get("concurrency", 1))
        concurrency = max(1, min(max_concurrency(ctx.model), wanted))
        return self.scorer_factory(ctx.model), concurrency

    def _work(self, scorer: FitScorer) -> None:
        while True:
            with self._lock:
                if self._cancel or not self._pending:
                    return
                job_id, force = self._pending.popleft()
                self._queued.discard(job_id)
                self._current[job_id] = self._title(job_id)
            started = time.monotonic()
            try:
                row = score_job(self.engine, job_id, scorer, force=force)
                ok = row.status == FitStatus.ok
                error = row.error
            except Exception as exc:  # job deleted mid-run, DB error…
                ok, error = False, str(exc)
            with self._lock:
                self._current.pop(job_id, None)
                self.durations.append(time.monotonic() - started)
                if ok:
                    self.done += 1
                else:
                    self.failed += 1
                    self.last_error = error

    def _title(self, job_id: int) -> str:
        with Session(self.engine) as s:
            job = s.get(Job, job_id)
            return job.title if job else f"Job {job_id}"


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
