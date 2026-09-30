"""The Copilot: questions about a job (or your search in general), answered by the local model
with the app's data as context. It only answers: no tools, no write path.

Context for a job thread: the listing, the fit score and its reasons, the approved CV, the
latest cover letter, both routes' status, your profile and your experience pool. A global
thread gets your profile and pool. After each answer, numbers and tools that are in neither your
experience nor the listing are listed as warnings (the same check as emails)."""

import json
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import (
    Application,
    Company,
    CopilotMessage,
    CopilotThread,
    CoverLetter,
    CVVersion,
    FitScore,
    Job,
)
from app.models.enums import CVStatus
from app.services import outreach_check as oc
from app.services.cv_claims import exact_statement
from app.services.cv_pool import Pool, load_pool, prompt_pool, years_facts

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "copilot.md"
HISTORY = 12  # earlier messages sent back with each question
LISTING_CHARS = 7000
STARTERS = {
    "job": ["What should I highlight in the interview?",
            "Is my CV missing something for this role?",
            "Write a LinkedIn message to the CTO", "Translate my cover letter into English"],
    "global": ["Which of my projects fits data engineering roles best?",
               "What should I add to my experience pool?",
               "Write a short LinkedIn headline from my experience"],
}


class Copilot(Protocol):
    model: str

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]: ...


class CopilotError(ValueError):
    """Shown to the user."""


def prompt_sections() -> tuple[str, dict[str, str]]:
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## \w+\n|\Z)", text, re.M | re.S))
    return (f"copilot/v{version.group(1) if version else '0'}",
            {k: v.strip() for k, v in sections.items()})


def prompt_version() -> tuple[str, str]:
    version, sections = prompt_sections()
    return version, sections["system"]


# ------------------------------------------------------------------------------------ threads


def job_thread(s: Session, app_id: int) -> CopilotThread:
    """The job's current thread (created on first use)."""
    thread = s.exec(select(CopilotThread).where(CopilotThread.application_id == app_id,
                                                col(CopilotThread.archived).is_(False))
                    .order_by(col(CopilotThread.id).desc())).first()
    if thread is None:
        job = s.exec(select(Job).join(Application, col(Application.job_id) == col(Job.id))
                     .where(Application.id == app_id)).first()
        thread = CopilotThread(application_id=app_id, title=job.title if job else "Job")
        s.add(thread)
        s.commit()
        s.refresh(thread)
    return thread


def clear_job_thread(s: Session, app_id: int) -> CopilotThread:
    """Start over on a job: the old conversation is kept (archived), a new one begins."""
    for t in s.exec(select(CopilotThread).where(CopilotThread.application_id == app_id,
                                                col(CopilotThread.archived).is_(False))).all():
        t.archived = True
        s.add(t)
    s.commit()
    return job_thread(s, app_id)


def messages(s: Session, thread_id: int) -> list[CopilotMessage]:
    return list(s.exec(select(CopilotMessage).where(CopilotMessage.thread_id == thread_id)
                       .order_by(col(CopilotMessage.id))).all())


# ------------------------------------------------------------------------------------ context


def _cv_text(cv: CVVersion) -> str:
    doc = cv.content or {}
    lines = [f"Summary: {doc.get('summary', '')}"]
    for g in doc.get("skills") or []:
        lines.append(f"Skills, {g.get('category')}: {', '.join(g.get('items') or [])}")
    for kind in ("roles", "projects", "volunteering"):
        for e in doc.get(kind) or []:
            head = " · ".join(x for x in (e.get("title"), e.get("org"), e.get("start"),
                                          e.get("end")) if x)
            lines.append(f"{kind[:-1].title()}: {head}")
            lines += [f"  - {b}" for b in e.get("bullets") or []]
    for e in doc.get("education") or []:
        school = e.get("school") or e.get("org")
        lines.append(f"Education: {e.get('degree') or e.get('title')} · {school}")
    return "\n".join(lines)


def _profile_text(s: Session, pool: Pool) -> str:
    from app.services.cv_service import _tracks

    p = pool.profile
    langs = ", ".join(f"{x.get('language')} ({x.get('level')})" for x in p.get("languages") or [])
    statement = exact_statement(years_facts(pool, _tracks(s)))
    return "\n".join(x for x in (
        f"Name: {p.get('full_name', '')}", f"Based in: {p.get('based_in', '')}",
        f"Work authorization: {p.get('work_authorization', '')}", f"Languages: {langs}",
        f"Years of experience (say it exactly like this): {statement}" if statement else "",
        f"Headline: {p.get('headline', '')}" if p.get("headline") else "") if x)


def context(s: Session, app: Application | None, pool: Pool | None = None) -> tuple[str, str]:
    """(context text for the model, source text the answer is checked against)."""
    from app.services.tracks import for_app, stage_label

    pool = pool or load_pool(s)
    parts = ["PROFILE", _profile_text(s, pool),
             "EXPERIENCE POOL (JSON)", json.dumps(prompt_pool(pool), ensure_ascii=False)]
    source = ""
    if app is not None:
        job = s.get(Job, app.job_id)
        company = s.get(Company, job.company_id)
        tracks = for_app(s, app)
        listing = (job.description or "")[:LISTING_CHARS]
        source = f"{job.title}\n{company.name}\n{listing}"
        parts += ["JOB", f"Job: {job.title} at {company.name}", f"Location: {job.location}",
                  f"Status: {stage_label(app.stage, tracks)} · web application: "
                  f"{tracks.application} · email: {tracks.outreach}"
                  + (f" (contact: {tracks.contact_name})" if tracks.contact_name else ""),
                  "Listing:", listing]
        fit = s.exec(select(FitScore).where(FitScore.job_id == job.id)
                     .order_by(col(FitScore.created_at).desc())).first()
        if fit and fit.score is not None:
            reasons = [f"- {k}: {v.get('score')}/10, {v.get('reason', '')}"
                       for k, v in (fit.sub_scores or {}).items() if isinstance(v, dict)]
            parts += ["FIT", f"Score {fit.score}/100. {fit.summary}", *reasons,
                      f"Strengths: {'; '.join(fit.strengths)}", f"Gaps: {'; '.join(fit.gaps)}"]
        cv = s.exec(select(CVVersion).where(CVVersion.application_id == app.id,
                                            CVVersion.status == CVStatus.approved)
                    .order_by(col(CVVersion.version).desc())).first()
        if cv:
            parts += [f"APPROVED CV (v{cv.version})", _cv_text(cv)]
        letter = s.exec(select(CoverLetter).where(CoverLetter.application_id == app.id,
                                                  CoverLetter.status != CVStatus.superseded)
                        .order_by(col(CoverLetter.id).desc())).first()
        if letter and letter.text:
            parts += [f"COVER LETTER ({letter.format}, v{letter.version}, {letter.status})",
                      letter.text]
    return "\n\n".join(parts), source


# Architecture/method claims the pool must mention before a message says you have them.
_CLAIMS = ["MVC", "microservices", "clean architecture", "domain-driven design", "DDD", "TDD",
           "event-driven", "hexagonal"]


def warnings(answer: str, pool: Pool, source: str,
             statements: tuple[str | None, str | None] = (None, None)) -> list[dict[str, str]]:
    """What to check before using the answer: numbers and tools in neither your experience nor
    the listing, method claims your experience doesn't mention, clichés the letters ban, and
    years wording other than yours."""
    from app.services import letter_check as lc

    ctx = oc.Context(pool=pool, allowed_years=set(), job_text=source, company="",
                     first_name="")
    out = [{"type": "unsupported", "message": p.replace(
        "isn't in your experience or the listing",
        "isn't in your experience or the listing: check before using it")}
        for p in oc._source_problems(answer, ctx)]
    pool_text = oc.fold(pool.all_text())
    for claim in _CLAIMS:
        if re.search(rf"\b{re.escape(claim)}\b", answer, re.I) and \
                oc.fold(claim) not in pool_text:
            out.append({"type": "unsupported", "message": f"“{claim}” isn't in your experience: "
                        "fine as a gap to discuss, not as something you did"})
    folded = oc.fold(answer.replace("’", "'"))
    for phrase in [*lc.DEFAULT_BANNED["fr"], *lc.DEFAULT_BANNED["en"], *oc.DEFAULT_BANNED]:
        key = oc.fold(phrase.replace("’", "'"))
        if key and re.search(rf"\b{re.escape(key)}\b", folded):
            out.append({"type": "style", "message": f"Cliché “{phrase}”: rephrase before sending"})
    english, french = statements
    if english:
        lctx = lc.Context(pool=pool, allowed_years=set(), job_text=source, company="",
                          years_statement=english, years_statement_fr=french)
        out += [{"type": "years", "message": f"Years wording “{c}”: yours is “{english}”"
                 + (f" (“{french}”)" if french else "")} for c in lc.years_problems(answer, lctx)]
    seen, unique = set(), []
    for w in out:
        if w["message"] not in seen:
            seen.add(w["message"])
            unique.append(w)
    return unique


def statements(s: Session, pool: Pool) -> tuple[str | None, str | None]:
    from app.services.cover_letter import _statements

    _facts, english, french = _statements(s, pool)
    return english, french


# ---------------------------------------------------------------------------------------- ask


def ask(engine: Engine, thread_id: int, question: str, model: Copilot) -> Iterator[str]:
    """Save the question, stream the answer, then save it with its warnings."""
    question = question.strip()
    if not question:
        raise CopilotError("Type a question")
    version, system = prompt_version()
    with Session(engine) as s:
        thread = s.get(CopilotThread, thread_id)
        if thread is None:
            raise CopilotError("Conversation not found")
        app = s.get(Application, thread.application_id) if thread.application_id else None
        pool = load_pool(s)
        text, source = context(s, app, pool)
        history = [{"role": m.role, "content": m.content} for m in messages(s, thread_id)
                   if m.content and not m.error][-HISTORY:]
        s.add(CopilotMessage(thread_id=thread_id, role="user", content=question))
        if thread.application_id is None and not thread.title:
            thread.title = question[:60]
            s.add(thread)
        s.commit()
    chat = [{"role": "system", "content": f"{system}\n\nCONTEXT\n\n{text}"}, *history,
            {"role": "user", "content": question}]

    def run() -> Iterator[str]:
        started, chunks, error = time.monotonic(), [], None
        try:
            for chunk in model.stream(chat):
                chunks.append(chunk)
                yield chunk
        except Exception as exc:  # noqa: BLE001 (shown to the user, saved on the message)
            error = str(exc)
            yield f"\n\n[Copilot error] {error}"
        answer = "".join(chunks).strip()
        with Session(engine) as s:
            fresh = load_pool(s)
            found = warnings(answer, fresh, source, statements(s, fresh)) if answer else []
            s.add(CopilotMessage(thread_id=thread_id, role="assistant", content=answer,
                                 model=f"{model.model} ({version})", error=error,
                                 warnings=found,
                                 duration_ms=int((time.monotonic() - started) * 1000)))
            thread = s.get(CopilotThread, thread_id)
            s.add(thread)  # bumps updated_at: the thread list is newest first
            s.commit()

    return run()



# ------------------------------------------------------------------------------------ rewrite


class Rewriter(Protocol):
    model: str

    def rewrite(self, system: str, message: str) -> str: ...


def rewrite(engine: Engine, message_id: int, rewriter: Rewriter) -> CopilotMessage:
    """A text you'll send to people, rewritten by Claude (the same rules, your facts only), saved
    as a new answer under the original. The local model stays the default."""
    version, sections = prompt_sections()
    with Session(engine) as s:
        original = s.get(CopilotMessage, message_id)
        if original is None or original.role != "assistant" or not original.content.strip():
            raise CopilotError("Pick an answer to rewrite")
        thread = s.get(CopilotThread, original.thread_id)
        app = s.get(Application, thread.application_id) if thread.application_id else None
        question = next((m.content for m in reversed(messages(s, thread.id))
                         if m.role == "user" and m.id < original.id), "")
        pool = load_pool(s)
        text, source = context(s, app, pool)
        thread_id = thread.id
    started = time.monotonic()
    message = f"QUESTION\n{question}\n\nORIGINAL\n{original.content}\n\nCONTEXT\n\n{text}"
    try:
        out = rewriter.rewrite(sections["rewrite"], message).strip()
        error = None
    except Exception as exc:  # noqa: BLE001 (shown to the user)
        out, error = "", str(exc)
    with Session(engine) as s:
        fresh = load_pool(s)
        row = CopilotMessage(
            thread_id=thread_id, role="assistant", content=out,
            model=f"{rewriter.model} via claude -p, rewrite ({version})", error=error,
            warnings=warnings(out, fresh, source, statements(s, fresh)) if out else [],
            duration_ms=int((time.monotonic() - started) * 1000))
        s.add(row)
        s.commit()
        s.refresh(row)
        if error:
            raise CopilotError(error)
        return row
