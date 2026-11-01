"""Studio "Generate CV": a general CV for a track (or the all-purpose master), made from the
experience pool without a job. Never stored: the PDF lives in a temp dir and in memory, and is
deleted after it's downloaded, when it expires, or when the server stops."""

import atexit
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session

from app.providers.base import CVGenerationFailed, CVGenerator
from app.services import bullet_tailor, cv_rules
from app.services.cv_build import fit_to_page
from app.services.cv_check import canonicalize, check_plan, verbatim_skills
from app.services.cv_pool import cv_profile, load_pool, readiness
from app.services.cv_render import load_template
from app.services.cv_service import (
    CVError,
    _template,
    _tracks,
    build_track_request,
    cv_settings,
    fit_layout,
    ground_summary,
)

ALL_PURPOSE = "all_purpose"
TTL_SECONDS = 3600
_ROOT = Path(tempfile.mkdtemp(prefix="jh-track-cv-"))
_LOCK = threading.RLock()
_JOBS: dict[str, "TrackCV"] = {}


@dataclass
class TrackCV:
    id: str
    track: str
    status: str = "running"  # running | ready | failed
    error: str | None = None
    pdf_path: Path | None = None
    page_count: int | None = None
    model: str | None = None
    filename: str = "CV.pdf"
    issues: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)


def options(engine: Engine) -> list[dict[str, str]]:
    """All-purpose first, then every registered track of the active search profile."""
    with Session(engine) as s:
        tracks = _tracks(s)
    return [{"value": ALL_PURPOSE, "label": "All-Purpose (Master / General)"},
            *[{"value": t["name"], "label": t.get("label") or t["name"]}
              for t in tracks if t.get("name")]]


def resolve(engine: Engine, track: str) -> str | None:
    """The track name for a request (None = all-purpose); ValueError when it isn't registered."""
    if track == ALL_PURPOSE:
        return None
    if track not in {o["value"] for o in options(engine)}:
        raise ValueError(f"Unknown track '{track}'")
    return track


def _sweep() -> None:
    now = time.time()
    stale = [k for k, j in _JOBS.items()
             if j.status != "running" and now - j.created > TTL_SECONDS]
    for key in stale:
        discard(key)


def discard(job_id: str) -> None:
    with _LOCK:
        _JOBS.pop(job_id, None)
    shutil.rmtree(_ROOT / job_id, ignore_errors=True)


@atexit.register
def _cleanup() -> None:
    shutil.rmtree(_ROOT, ignore_errors=True)


def get(job_id: str) -> TrackCV | None:
    return _JOBS.get(job_id)


def start(engine: Engine, track: str, generator: CVGenerator, template: str | None = None,
          verifier: Any = None, *, wait: bool = False) -> TrackCV:
    name = resolve(engine, track)
    with _LOCK:
        _sweep()
        job = TrackCV(id=uuid.uuid4().hex, track=track)
        _JOBS[job.id] = job
    run = threading.Thread(target=_work, args=(engine, job, name, generator, template, verifier),
                           name=f"track-cv-{job.id[:8]}", daemon=True)
    run.start()
    if wait:
        run.join()
    return job


def _work(engine: Engine, job: TrackCV, track: str | None, generator: CVGenerator,
          template: str | None, verifier: Any) -> None:
    try:
        generate(engine, job, track, generator, template, verifier)
        job.status = "ready"
    except (CVError, CVGenerationFailed) as exc:
        job.status, job.error = "failed", str(exc)
    except Exception as exc:  # noqa: BLE001  (the page shows it; never crash the thread silently)
        job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"


def generate(engine: Engine, job: TrackCV, track: str | None, generator: CVGenerator,
             template: str | None, verifier: Any) -> None:
    """The same pipeline as a job CV (generate → tailoring → verify → plan → summary → fit)."""
    with Session(engine) as s:
        pool = load_pool(s)
        blockers = [r["message"] for r in readiness(pool) if r["severity"] == "blocker"]
        if blockers:
            raise CVError(" ".join(blockers))
        template_name = _template(template, s)
        request = build_track_request(s, track, pool)
        rules = {**cv_rules.structure(cv_settings(s)),
                 "_qualifiers": cv_rules.qualifiers(cv_settings(s))}
        banned = cv_rules.banned(cv_settings(s))
    try:
        plan = generator.generate(request)
        plan = verbatim_skills(canonicalize(plan, pool), pool)
        plan, issues, _ = bullet_tailor.enforce(plan, pool)
        plan, verifier_issues, _ = bullet_tailor.verify(plan, pool, verifier)
        plan, plan_issues = check_plan(plan, pool)
        plan, summary_issues, _ = ground_summary(plan, pool, request, generator, rules,
                                                 banned=banned)
    except CVGenerationFailed as exc:
        raise CVError(str(exc)) from exc
    plan = bullet_tailor.pin_originals(verbatim_skills(canonicalize(plan, pool), pool), pool)
    out_dir = _ROOT / job.id
    with Session(engine) as s:
        lay = fit_layout(s, plan, pool, track or "")
        profile = cv_profile(pool)
        result = fit_to_page(plan, pool, profile, load_template(template_name), out_dir,
                             overrides={}, lay=lay)
    if not result.compiled.ok or not result.compiled.pdf_path:
        raise CVError(f"The CV didn't compile: {result.compiled.error}")
    job.pdf_path = Path(result.compiled.pdf_path)
    job.page_count = result.compiled.pages or None
    job.model = generator.model
    job.issues = [*issues, *verifier_issues, *plan_issues, *summary_issues]
    job.summary = plan.summary
    job.skills = [i for g in result.document.skills for i in g.items]
    stem = "".join(c if c.isalnum() else "_" for c in (profile.full_name or "CV")).strip("_")
    job.filename = f"{stem}_CV_{track or 'All_Purpose'}.pdf".replace(" ", "_")
