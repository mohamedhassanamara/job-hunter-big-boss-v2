from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import col, select

from app.api.deps import SessionDep
from app.models import Application, Company, CoverLetter, CVVersion, Job

router = APIRouter(tags=["studio"])
KINDS = ("cv", "pdf", "form")
STATUSES = ("draft", "approved", "sent", "superseded")


class StudioDocument(BaseModel):
    kind: str  # cv | pdf (cover letter) | form (form text)
    id: int
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    version: int
    status: str  # draft | approved | sent (locked) | superseded
    language: str | None
    detail: str  # "1 page · 91% full", "256 words", "791/1000 characters"
    problems: int  # blocking checks
    updated_at: datetime


class StudioList(BaseModel):
    items: list[StudioDocument]
    total: int
    counts: dict[str, int]  # per kind, before the kind filter


def _status(row: CVVersion | CoverLetter) -> str:
    return "sent" if row.locked_at is not None else str(row.status)


def _errors(row: CVVersion | CoverLetter) -> int:
    return sum(1 for v in row.violations or [] if v.get("severity") == "error")


@router.get("/studio/documents", response_model=StudioList)
def documents(session: SessionDep, kind: str | None = None, status: str | None = None,
              q: str | None = None, offset: int = 0, limit: int = 100) -> StudioList:
    """Every CV version and cover letter (PDF and form text) across jobs, newest first."""
    if kind and kind not in KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(KINDS)}")
    if status and status not in STATUSES:
        raise HTTPException(422, f"status must be one of {', '.join(STATUSES)}")
    jobs = {a.id: (a, j, c) for a, j, c in session.exec(
        select(Application, Job, Company)
        .join(Job, col(Job.id) == col(Application.job_id))
        .join(Company, col(Company.id) == col(Job.company_id))
        .where(col(Application.id).in_(
            select(CVVersion.application_id).union(select(CoverLetter.application_id))))).all()}
    docs: list[StudioDocument] = []
    for v in session.exec(select(CVVersion)).all():
        if v.application_id not in jobs:
            continue
        a, j, c = jobs[v.application_id]
        fill = f" · {round(v.fill * 100)}% full" if v.fill is not None else ""
        docs.append(StudioDocument(
            kind="cv", id=v.id, application_id=a.id, job_id=j.id, job_title=j.title,
            company_name=c.name, version=v.version, status=_status(v), language="en",
            detail=f"{v.page_count} page{fill}" if v.page_count else "not compiled",
            problems=_errors(v), updated_at=v.updated_at))
    for letter in session.exec(select(CoverLetter)).all():
        if letter.application_id not in jobs:
            continue
        a, j, c = jobs[letter.application_id]
        fmt = letter.format or "pdf"
        length = len(letter.text or "")
        detail = (f"{length}/{letter.char_limit} characters" if letter.char_limit
                  else f"{length} characters") if fmt == "form" else \
            f"{letter.page_count or '?'} page · {len((letter.text or '').split())} words"
        docs.append(StudioDocument(
            kind=fmt, id=letter.id, application_id=a.id, job_id=j.id, job_title=j.title,
            company_name=c.name, version=letter.version, status=_status(letter),
            language=letter.language, detail=detail, problems=_errors(letter),
            updated_at=letter.updated_at))
    if status:
        docs = [d for d in docs if d.status == status]
    if q:
        needle = q.lower()
        docs = [d for d in docs if needle in d.job_title.lower()
                or needle in d.company_name.lower()]
    counts = {k: sum(1 for d in docs if d.kind == k) for k in KINDS}
    if kind:
        docs = [d for d in docs if d.kind == kind]
    docs.sort(key=lambda d: d.updated_at, reverse=True)
    return StudioList(items=docs[offset:offset + limit], total=len(docs), counts=counts)
