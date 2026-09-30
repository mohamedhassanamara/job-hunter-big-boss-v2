"""Answers to application-form questions, grounded like the cover letter: one Claude call for a
batch of questions, checks per answer (grounding, banned phrases, years, the character limit),
one retry for the answers that fail, then everything is kept with its problems listed. An answer
over its limit is never cut: you shorten it (or regenerate)."""

import threading

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import Application, ApplicationAnswer, Company, Job
from app.providers.base import AnswerDraft, AnswersRequest, DraftFailed, LetterDrafter
from app.services import cover_letter as cl
from app.services import letter_check as lc
from app.services.cv_pool import load_pool

MAX_QUESTIONS = 10
_one_at_a_time = threading.Lock()


class AnswerError(ValueError):
    """Shown to the user."""


def answers(s: Session, app_id: int) -> list[ApplicationAnswer]:
    return list(s.exec(select(ApplicationAnswer)
                       .where(ApplicationAnswer.application_id == app_id)
                       .order_by(col(ApplicationAnswer.position), col(ApplicationAnswer.id))).all())


def text_of(draft: AnswerDraft) -> str:
    return " ".join(x.text.strip() for x in draft.sentences).strip()


def _check(draft: AnswerDraft | None, text: str, limit: int | None,
           ctx: lc.Context) -> list[dict[str, str]]:
    return lc.check_answer(draft.sentences if draft else None, text, limit, ctx)


def generate(engine: Engine, app_id: int, drafter: LetterDrafter,
             questions: list[dict]) -> list[ApplicationAnswer]:
    """Answer new questions for one job: `questions` = [{question, char_limit}]."""
    questions = [{"question": str(q.get("question") or "").strip(),
                  "char_limit": int(q["char_limit"]) if q.get("char_limit") else None}
                 for q in questions if str(q.get("question") or "").strip()]
    if not questions:
        raise AnswerError("Add at least one question")
    if len(questions) > MAX_QUESTIONS:
        raise AnswerError(f"At most {MAX_QUESTIONS} questions at a time")
    if any(q["char_limit"] is not None and q["char_limit"] < 20 for q in questions):
        raise AnswerError("A character limit must be at least 20")
    if not _one_at_a_time.acquire(blocking=False):
        raise AnswerError("Answers are already being written; one batch at a time")
    try:
        with Session(engine) as s:
            app = s.get(Application, app_id)
            if app is None:
                raise AnswerError("Application not found")
            cv = cl.approved_cv(s, app)
            if cv is None:
                raise AnswerError("Approve the CV first: answers are written from it")
            job = s.get(Job, app.job_id)
            company = s.get(Company, job.company_id)
            language = cl.resolve_language(s, app, job)
            pool = load_pool(s)
            letter_request = cl.build_request(s, app, cv, pool, language)
            ctx = cl.context(s, app, language, pool)
            start = len(answers(s, app_id))
        indexed = [{"id": i, **q} for i, q in enumerate(questions, 1)]
        request = AnswersRequest(
            job=letter_request.job | {"company": company.name}, candidate=letter_request.candidate,
            pool=letter_request.pool, questions=indexed,
            rules={"language": language, "banned_phrases": ctx.banned})
        try:
            got = {a.question_id: a for a in drafter.answer(request).answers}
            found = {q["id"]: _check(got.get(q["id"]), text_of(got[q["id"]]) if q["id"] in got
                                     else "", q["char_limit"], ctx) for q in indexed}
            failing = [q for q in indexed if lc.errors(found[q["id"]])]
            attempts = 1
            if failing:  # one retry, only for the answers that failed
                feedback = "\n".join(f"- question {q['id']}: {v['message']}" for q in failing
                                     for v in lc.errors(found[q["id"]]))
                retry = {a.question_id: a for a in drafter.answer(
                    request.model_copy(update={"questions": failing}), feedback).answers}
                attempts = 2
                for q in failing:
                    if q["id"] not in retry:
                        continue
                    again = _check(retry[q["id"]], text_of(retry[q["id"]]), q["char_limit"], ctx)
                    if len(lc.errors(again)) <= len(lc.errors(found[q["id"]])):
                        got[q["id"]], found[q["id"]] = retry[q["id"]], again
        except DraftFailed as exc:
            raise AnswerError(str(exc)) from exc
        with Session(engine) as s:
            rows = []
            for q in indexed:
                draft = got.get(q["id"])
                row = ApplicationAnswer(
                    application_id=app_id, question=q["question"], char_limit=q["char_limit"],
                    answer=text_of(draft) if draft else "", language=language,
                    position=start + q["id"], generator_model=drafter.model,
                    prompt_version=drafter.prompt_version,
                    plan={"sentences": [x.model_dump() for x in draft.sentences] if draft else [],
                          "attempts": attempts},
                    violations=found[q["id"]])
                s.add(row)
                rows.append(row)
            s.commit()
            for row in rows:
                s.refresh(row)
            return rows
    finally:
        _one_at_a_time.release()


def update(s: Session, answer: ApplicationAnswer, *, text: str | None = None,
           question: str | None = None, char_limit: int | None | str = "keep") -> ApplicationAnswer:
    """Your edits: the answer is re-checked at text level (its citations no longer apply)."""
    if question is not None:
        answer.question = question.strip()
    if char_limit != "keep":
        answer.char_limit = int(char_limit) if char_limit else None
    if text is not None and text.strip() != answer.answer.strip():
        answer.answer = text.strip()
        answer.edited = True
    app = s.get(Application, answer.application_id)
    ctx = cl.context(s, app, answer.language)
    sentences = None
    if not answer.edited:
        from app.providers.base import EmailSentence

        sentences = [EmailSentence.model_validate(x) for x in (answer.plan or {}).get("sentences")
                     or []]
    answer.violations = lc.check_answer(sentences, answer.answer, answer.char_limit, ctx)
    s.add(answer)
    s.commit()
    s.refresh(answer)
    return answer
