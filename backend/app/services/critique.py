"""Critique: one Claude call on a CV, cover letter, email or LinkedIn message, listing what is
still weak from the reader's side. Never a rewrite; the latest result is kept on the document.

Rubric adapted from jobhunt-critique in github.com/mohamedaminehamdi/job-hunter (MIT License,
Copyright (c) 2026 Mohamed Amine Hamdi; see docs/CREDITS.md): unbacked claims first, then the
opening, buried evidence, duties instead of outcomes, specificity, real gaps.
"""

from typing import Any

from sqlmodel import Session

from app.models import (
    Application,
    Company,
    CoverLetter,
    CVVersion,
    Job,
    LinkedInOutreach,
    OutreachDraft,
)
from app.models.base import utcnow
from app.providers.base import DraftFailed
from app.services import fit_lexical
from app.services.cv_pool import load_pool, prompt_pool

KINDS = ("cv", "letter", "email", "linkedin_note", "linkedin_followup")


class CritiqueError(ValueError):
    pass


def _flatten(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [x for v in value.values() for x in _flatten(v)]
    if isinstance(value, list):
        return [x for v in value for x in _flatten(v)]
    return []


def _document(s: Session, kind: str, doc_id: int) -> tuple[Any, Application, str, str]:
    """(row, application, document text, label)."""
    if kind == "cv":
        row = s.get(CVVersion, doc_id)
        if row is None:
            raise CritiqueError("CV not found")
        _skim, text = fit_lexical.cv_text(row.content or {})
        return row, s.get(Application, row.application_id), text, f"CV v{row.version}"
    if kind == "letter":
        row = s.get(CoverLetter, doc_id)
        if row is None:
            raise CritiqueError("Letter not found")
        text = "\n".join(_flatten(row.content))
        return row, s.get(Application, row.application_id), text, "cover letter"
    if kind == "email":
        row = s.get(OutreachDraft, doc_id)
        if row is None:
            raise CritiqueError("Email not found")
        return row, s.get(Application, row.application_id), f"{row.subject}\n\n{row.body}", \
            "cold email"
    row = s.get(LinkedInOutreach, doc_id)
    if row is None:
        raise CritiqueError("LinkedIn message not found")
    msg = row.note if kind == "linkedin_note" else row.followup
    if not msg or not msg.get("text"):
        raise CritiqueError("Draft the message first")
    return row, s.get(Application, row.application_id), msg["text"], \
        "LinkedIn connection note" if kind == "linkedin_note" else "LinkedIn follow-up"


def critique(s: Session, kind: str, doc_id: int, critic: Any) -> dict[str, Any]:
    if kind not in KINDS:
        raise CritiqueError(f"Unknown document kind {kind!r}")
    row, app, text, label = _document(s, kind, doc_id)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    pool = load_pool(s)
    checks = fit_lexical.compare(pool, job.description or "",
                                 row.content if kind == "cv" else {"summary": text},
                                 company=company.name, title=job.title, location=job.location)
    request = {"document_kind": label, "document": text,
               "checks": {k: checks[k] for k in ("unbacked", "dropped", "gaps")},
               "job": {"title": job.title, "company": company.name,
                       "description": (job.description or "")[:5000]},
               "experience_pool": prompt_pool(pool)}
    try:
        plan = critic.critique(request)
    except DraftFailed as exc:
        raise CritiqueError(str(exc)) from exc
    result = {"issues": [i.model_dump() for i in plan.issues[:6]], "model": critic.model,
              "prompt_version": critic.prompt_version, "via": getattr(critic, "via", "mock"),
              "auth": getattr(critic, "auth_source", None), "created_at": utcnow().isoformat()}
    if kind.startswith("linkedin"):
        row.critique = {**(row.critique or {}), kind: result}
    else:
        row.plan = {**(row.plan or {}), "critique": result}
    s.add(row)
    return result
