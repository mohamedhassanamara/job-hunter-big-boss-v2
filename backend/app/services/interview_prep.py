"""Interview preparation per job (Phase 12b): a "tell me about yourself" pitch, STAR stories, likely
questions and questions to ask, written from YOUR experience pool only. One job at a time.

Nothing about the candidate is stated without citing pool items: code checks every sentence like
a cover letter's (numbers, tools and scope must be in the cited items, years only as your exact
statement, the honesty rules) and the Claude claim verifier (services/verifier.py) judges every
sentence before the prep can be approved. A story whose items state no outcome has no result:
never an invented one. Errors block approval; you can edit any sentence (a new check runs).
"""

import threading
import time
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import Application, Company, InterviewPrep, Job
from app.models.enums import CVStatus, EventKind
from app.providers.base import (
    DraftFailed,
    EmailSentence,
    InterviewDrafter,
    InterviewPrepPlan,
    InterviewRequest,
)
from app.services import cover_letter, honesty, pipeline
from app.services.cv_check import sentence_problems, violation
from app.services.cv_pool import Pool, load_pool, prompt_pool

LANGUAGES = ("fr", "en")
MAX_STORIES = 5
_one_at_a_time = threading.Lock()


class InterviewError(ValueError):
    pass


def versions(s: Session, app_id: int) -> list[InterviewPrep]:
    return list(s.exec(select(InterviewPrep).where(InterviewPrep.application_id == app_id)
                       .order_by(col(InterviewPrep.version).desc())).all())


def current(s: Session, app_id: int) -> InterviewPrep | None:
    return next((p for p in versions(s, app_id) if p.status != CVStatus.superseded), None)


def build_request(s: Session, app: Application, pool: Pool, language: str) -> InterviewRequest:
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    facts, english, french = cover_letter._statements(s, pool)
    job_text = f"{job.title}\n{job.description or ''}"
    role = cover_letter.current_role(pool, job_text)
    cfg = cover_letter.letter_settings(s)
    full = {k: v for k, v in prompt_pool(pool).items() if k != "summary_snippets"}
    return InterviewRequest(
        job={"title": job.title, "company": company.name, "location": job.location,
             "description": (job.description or "")[:8000]},
        candidate={"years": facts, "years_statement": english, "years_statement_fr": french,
                   **honesty.prompt_facts(honesty.rules(s)),
                   "current_role": {"id": role.id, "title": role.title, "org": role.org}
                   if role else None},
        pool=full,
        rules={"language": language, "banned_phrases": list(cfg["banned_phrases"].get(language)
                                                              or []),
               "mention_work_authorization": cover_letter.mention_authorization(s, job_text)})


# ------------------------------------------------------------------------------------ content


def content_from_plan(plan: InterviewPrepPlan) -> dict[str, Any]:
    return plan.model_dump()


PARTS = ("situation", "task", "action", "result")


def candidate_sentences(content: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(where, sentence) for everything said about the candidate: the pitch and the STAR parts."""
    out = [(f"pitch {i + 1}", x) for i, x in enumerate(content.get("pitch") or [])]
    for n, story in enumerate(content.get("stories") or [], 1):
        for part in PARTS:
            out += [(f"story {n} {part}", x) for x in story.get(part) or []]
    return out


def plain_text(content: dict[str, Any]) -> str:
    """What the candidate would say, one sentence per line: exactly what the verifier reads."""
    return "\n".join(str(x.get("text", "")).strip() for _w, x in candidate_sentences(content)
                     if str(x.get("text", "")).strip())


def check(s: Session, content: dict[str, Any], pool: Pool | None = None) -> list[dict[str, str]]:
    pool = pool or load_pool(s)
    facts, english, _french = cover_letter._statements(s, pool)
    allowed = {int(f["years"]) for f in facts}
    rules = honesty.rules(s)
    out: list[dict[str, str]] = []
    for where, raw in candidate_sentences(content):
        sentence = EmailSentence.model_validate(raw)
        if sentence.about_job or sentence.about_candidate:
            out.append(violation("uncited", "Nothing about you is stated without citing your "
                                 "experience", where, "error"))
        for problem in sentence_problems(sentence, pool, allowed, english):
            out.append(violation("grounding", f"“{sentence.text}”: {problem}", where, "error"))
        for kind, _sent, message in honesty.problems(sentence.text, rules):
            out.append(violation(kind, message, where, "error"))
        if "!" in sentence.text:
            out.append(violation("tone", "No exclamation marks", where, "warning"))
    stories = content.get("stories") or []
    if not stories:
        out.append(violation("stories", "No STAR story: the pool had nothing to build one from",
                             "stories", "error"))
    if len(stories) > MAX_STORIES:
        out.append(violation("stories", f"At most {MAX_STORIES} stories", "stories", "warning"))
    for n, story in enumerate(stories, 1):
        for part in ("situation", "task", "action"):
            if not story.get(part):
                out.append(violation("star", f"No {part} written", f"story {n}", "error"))
        if not story.get("result"):
            out.append(violation("star", "No result stated: your experience doesn't say what came "
                                 "of it, so none is invented (add it yourself if you know it)",
                                 f"story {n}", "warning"))
    for i, q in enumerate(content.get("questions") or [], 1):
        index = q.get("story", -1)
        if not str(q.get("question", "")).strip():
            out.append(violation("question", "An empty question", f"question {i}", "error"))
        if index != -1 and not 0 <= index < len(stories):
            out.append(violation("question", "Points to a story that doesn't exist",
                                 f"question {i}", "error"))
    return out


def errors(found: list[dict[str, str]]) -> list[dict[str, str]]:
    return [v for v in found if v.get("severity") == "error"]


def feedback(found: list[dict[str, str]]) -> str:
    return "\n".join(f"- {v['where']}: {v['message']}" for v in errors(found))


# ------------------------------------------------------------------------------ generating


def generate(engine: Engine, app_id: int, drafter: InterviewDrafter,
             language: str | None = None) -> InterviewPrep:
    """Write the preparation for one job (never in bulk: one at a time)."""
    if not _one_at_a_time.acquire(blocking=False):
        raise InterviewError("Another preparation is being written; one at a time")
    try:
        with Session(engine) as s:
            app = s.get(Application, app_id)
            if app is None:
                raise InterviewError("Application not found")
            job = s.get(Job, app.job_id)
            pool = load_pool(s)
            if not any(i.kind in ("job", "project") and pool.facts(i) for i in pool.items.values()):
                raise InterviewError("Add your experience first: the stories come only from it")
            language = language if language in LANGUAGES else cover_letter.resolve_language(
                s, app, job)
            request = build_request(s, app, pool, language)
        started = time.monotonic()
        try:
            plan = drafter.prepare(request)
            found, attempts = [], 1
            with Session(engine) as s:
                found = check(s, content_from_plan(plan), load_pool(s))
            if errors(found):  # one retry with the problems as feedback
                retry = drafter.prepare(request, feedback(found))
                with Session(engine) as s:
                    retry_found = check(s, content_from_plan(retry), load_pool(s))
                attempts = 2
                if len(errors(retry_found)) <= len(errors(found)):
                    plan = retry
        except DraftFailed as exc:
            raise InterviewError(str(exc)) from exc
        with Session(engine) as s:
            app = s.get(Application, app_id)
            existing = versions(s, app_id)
            for old in existing:
                if old.status == CVStatus.draft:
                    old.status = CVStatus.superseded
                    s.add(old)
            content = content_from_plan(plan)
            prep = InterviewPrep(
                application_id=app_id, version=(existing[0].version + 1) if existing else 1,
                language=language, content=content,
                violations=check(s, content), generator_model=drafter.model,
                prompt_version=drafter.prompt_version,
                plan={"plan": plan.model_dump(), "attempts": attempts},
                duration_ms=int((time.monotonic() - started) * 1000))
            s.add(prep)
            s.flush()
            problems = len(errors(prep.violations))
            pipeline.log_event(s, app, EventKind.interview_prep_generated,
                               f"Interview preparation v{prep.version} ({language}) written"
                               + (f" ({problems} problem{'s' if problems > 1 else ''} to review)"
                                  if problems else ""))
            s.commit()
            s.refresh(prep)
            return prep
    finally:
        _one_at_a_time.release()


def edit(engine: Engine, prep_id: int, content: dict[str, Any]) -> InterviewPrep:
    """Your edits replace the content (any sentence's text; citations stay). It is re-checked and
    its verification no longer matches, so it must pass the verifier again."""
    try:
        valid = InterviewPrepPlan.model_validate(content).model_dump()
    except ValueError as exc:
        raise InterviewError("That isn't a valid preparation") from exc
    with Session(engine) as s:
        prep = s.get(InterviewPrep, prep_id)
        if prep is None:
            raise InterviewError("Preparation not found")
        if prep.status == CVStatus.superseded:
            raise InterviewError("That version was replaced by a newer one")
        prep.content = valid
        prep.status = CVStatus.draft
        prep.violations = check(s, valid)
        s.add(prep)
        s.commit()
        s.refresh(prep)
        return prep


def approve(engine: Engine, prep_id: int) -> InterviewPrep:
    with Session(engine) as s:
        prep = s.get(InterviewPrep, prep_id)
        if prep is None:
            raise InterviewError("Preparation not found")
        found = check(s, prep.content)
        prep.violations = found
        if errors(found):
            s.add(prep)
            s.commit()
            raise InterviewError(f"{len(errors(found))} problem(s) to fix before approving")
        app = s.get(Application, prep.application_id)
        for other in versions(s, prep.application_id):
            if other.id != prep.id and other.status == CVStatus.approved:
                other.status = CVStatus.superseded
                s.add(other)
        prep.status = CVStatus.approved
        s.add(prep)
        pipeline.log_event(s, app, EventKind.interview_prep_approved,
                           f"Interview preparation v{prep.version} approved")
        s.commit()
        s.refresh(prep)
        return prep
