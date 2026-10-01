"""Fit before/after when a CV is approved: the job scored against the tailored CV (the same
gemma scorer and prompt, one call), next to its own fit (your master experience), plus the
lexical evidence check (services/fit_lexical.py, no model).

Stored in `cv_fit`, never as a `fit_score` row: the job's fit, its rank and the scores
fingerprint don't change. Runs once per approved CV version, in the background; a model problem
is stored as failed (never a default score). 429 → backoff and retry; quota → the local fallback.
"""

import threading
import time
from dataclasses import replace
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models import Application, Company, CVFit, CVVersion, Job
from app.models.base import utcnow
from app.providers.base import ConcurrencyLimited, JobSnapshot, QuotaExceeded, ScoringFailed
from app.services import fit, fit_lexical
from app.services.cv_pool import load_pool, years_facts

_running: set[int] = set()
_lock = threading.Lock()


def tailored_text(content: dict[str, Any]) -> str:
    """The tailored CV as the scorer's EXPERIENCE block (same shape as the master's lines)."""
    lines = []
    if content.get("summary"):
        lines.append(f"- [summary] {fit.one_line(content['summary'], 600)}")
    for r in content.get("roles") or []:
        head = f"- [job] {r.get('title', '')}, {r.get('org', '')}"
        if r.get("start") or r.get("end"):
            head += f" ({r.get('start', '')} – {r.get('end', '')})"
        lines.append(head)
        lines += [f"  • {fit.one_line(b, 200)}" for b in r.get("bullets") or []]
    for p in content.get("projects") or []:
        if isinstance(p, dict):
            lines.append(f"- [project] {p.get('title', '')}")
            lines += [f"  • {fit.one_line(b, 200)}" for b in p.get("bullets") or []]
    for e in content.get("education") or []:
        if isinstance(e, dict):
            lines.append(f"- [education] {e.get('title') or e.get('degree', '')}, "
                         f"{e.get('org') or e.get('school', '')}")
    for g in content.get("skills") or []:
        lines.append(f"- [skill] {g.get('category', '')}: {', '.join(g.get('items') or [])}")
    return "\n".join(lines)


def _held_years(s: Session) -> int | None:
    from app.services.cv_service import _tracks

    facts = years_facts(load_pool(s), _tracks(s))
    return max((int(f["years"]) for f in facts), default=None)


def lexical(s: Session, cv: CVVersion) -> dict[str, Any]:
    app = s.get(Application, cv.application_id)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    return fit_lexical.compare(load_pool(s), job.description or "", cv.content,
                               _held_years(s), company=company.name, title=job.title,
                               location=job.location)


def _assess(scorer_for: Any, ctx: Any, system: str, user: str, snapshot: JobSnapshot,
            sleep: Any = time.sleep) -> tuple[Any, str]:
    """One assessment with the queue's rules: 429 → back off and retry (3 tries), quota → the
    fallback model."""
    model = ctx.model
    for attempt in range(4):
        try:
            return scorer_for(model).assess(system, user, snapshot), model
        except ConcurrencyLimited:
            if attempt == 3:
                raise
            sleep(2.0 * 2 ** attempt)
        except QuotaExceeded:
            if not ctx.fallback_model or model == ctx.fallback_model:
                raise
            model = ctx.fallback_model
    raise ScoringFailed("No answer")


def run(engine: Engine, cv_id: int, *, mock: bool = False, sleep: Any = time.sleep) -> CVFit:
    """Score the job against this approved CV once (re-running replaces the result)."""
    from app.providers.registry import fit_scorer
    from app.services.scoring import latest_fit, load_context, render

    with Session(engine) as s:
        cv = s.get(CVVersion, cv_id)
        if cv is None:
            raise ValueError("CV not found")
        row = s.exec(select(CVFit).where(CVFit.cv_version_id == cv_id)).first() or \
            CVFit(cv_version_id=cv_id)
        app = s.get(Application, cv.application_id)
        job, base = s.get(Job, app.job_id), latest_fit(s, app.job_id)
        company = s.get(Company, job.company_id)
        row.base_fit_id = base.id if base else None
        row.base_score = base.score if base else None
        row.lexical = lexical(s, cv)
        row.status, row.error = "pending", None
        s.add(row)
        s.commit()
        ctx = load_context(s)
        ctx = replace(ctx, experience_text=tailored_text(cv.content or {}))
        system, user = render(job, company, ctx)
        snapshot = JobSnapshot(title=job.title, company=company.name, location=job.location,
                               remote_type=job.remote_type, description=job.description)
        level, remote, text = job.description_level, job.remote_type, \
            f"{job.title}\n{job.location}\n{job.description}"
    scorers: dict[str, Any] = {}

    def scorer_for(model: str) -> Any:
        if model not in scorers:
            scorers[model] = fit_scorer(mock=mock or None, model=model)
        return scorers[model]

    try:
        assessment, model = _assess(scorer_for, ctx, system, user, snapshot, sleep)
        record = fit.build_record(assessment, job_text=text, description_level=level,
                                  remote_type=remote, config=ctx.config)
        result = {"status": "ok", "score": record.get("score"),
                  "sub_scores": record.get("sub_scores") or {}, "model": model, "error": None}
    except ScoringFailed as exc:
        result = {"status": "failed", "score": None, "sub_scores": {}, "model": ctx.model,
                  "error": str(exc)[:500]}
    with Session(engine) as s:
        row = s.exec(select(CVFit).where(CVFit.cv_version_id == cv_id)).one()
        for k, v in result.items():
            setattr(row, k, v)
        row.prompt_version, row.scored_at = ctx.prompt_version, utcnow()
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def start(engine: Engine, cv_id: int, *, mock: bool = False) -> bool:
    """In the background (approving a CV doesn't wait for the model). One run per CV."""
    with _lock:
        if cv_id in _running:
            return False
        _running.add(cv_id)

    def work() -> None:
        try:
            run(engine, cv_id, mock=mock)
        except Exception:  # noqa: BLE001 (stored as failed by run; nothing else to do)
            pass
        finally:
            with _lock:
                _running.discard(cv_id)

    threading.Thread(target=work, name=f"cv-fit-{cv_id}", daemon=True).start()
    return True
