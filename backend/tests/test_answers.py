"""Application questions: grounded answers, the character limit (retry, then flagged, never cut),
edits re-checked at text level, and the API. No model calls."""

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import ApplicationAnswer, CVVersion
from app.models.enums import CVStatus
from app.providers.base import AnswerDraft, AnswersPlan, AnswersRequest, EmailSentence
from app.services import answers
from tests.test_cover_letter import web_job  # noqa: F401 (fixture)


class Script:
    model, prompt_version = "script", "cover_letter/test"

    def __init__(self, *plans):  # noqa: ANN002
        self.plans, self.requests, self.feedback = list(plans), [], []

    def answer(self, request: AnswersRequest, feedback: str = "") -> AnswersPlan:
        self.requests.append(request)
        self.feedback.append(feedback)
        plan = self.plans.pop(0)
        return plan(request) if callable(plan) else plan


def fact_answer(info: dict, qid: int, repeat: int = 1) -> AnswerDraft:
    item = info["items"][0]
    return AnswerDraft(question_id=qid, sentences=[
        EmailSentence(text=item.bullets[0], citations=[item.id]) for _ in range(repeat)])


def test_answers_are_grounded_and_saved_in_order(web_job: dict) -> None:  # noqa: F811
    drafter = Script(AnswersPlan(answers=[fact_answer(web_job, 1), fact_answer(web_job, 2)]))
    rows = answers.generate(engine, web_job["app"], drafter, [
        {"question": "Why this role?"},
        {"question": "A project you're proud of", "char_limit": 900}])
    assert [r.question for r in rows] == ["Why this role?", "A project you're proud of"]
    assert all(r.violations == [] for r in rows), [r.violations for r in rows]
    assert drafter.requests[0].questions[1]["char_limit"] == 900
    assert drafter.requests[0].rules["language"] == "fr"  # the listing's language
    assert len(drafter.requests) == 1  # one call for the batch


def test_over_the_limit_retries_once_then_is_flagged_never_cut(web_job: dict) -> None:  # noqa: F811
    long = fact_answer(web_job, 1, repeat=6)
    limit = len(web_job["items"][0].bullets[0]) + 10
    drafter = Script(AnswersPlan(answers=[long]), AnswersPlan(answers=[long]))
    [row] = answers.generate(engine, web_job["app"], drafter,
                             [{"question": "Summarise", "char_limit": limit}])
    assert "question 1" in drafter.feedback[1] and f"/{limit} characters" in drafter.feedback[1]
    assert len(row.answer) > limit  # kept whole
    assert any(v["type"] == "length" and v["message"] == f"{len(row.answer)}/{limit} characters"
               for v in row.violations)

    fixed = Script(AnswersPlan(answers=[long]), AnswersPlan(answers=[fact_answer(web_job, 1)]))
    [row] = answers.generate(engine, web_job["app"], fixed,
                             [{"question": "Summarise", "char_limit": limit}])
    assert row.violations == [] and len(row.answer) <= limit


def test_edits_are_rechecked_at_text_level(web_job: dict) -> None:  # noqa: F811
    [row] = answers.generate(engine, web_job["app"],
                             Script(AnswersPlan(answers=[fact_answer(web_job, 1)])),
                             [{"question": "Why?", "char_limit": 400}])
    with Session(engine) as s:
        a = s.get(ApplicationAnswer, row.id)
        a = answers.update(s, a, text="I cut costs by 73% with Snowflake.")
        assert a.edited and {v["type"] for v in a.violations} == {"grounding"}
        a = answers.update(s, a, char_limit=20)
        assert any(v["type"] == "length" for v in a.violations)


def test_answers_need_an_approved_cv_and_valid_questions(web_job: dict) -> None:  # noqa: F811
    with pytest.raises(answers.AnswerError, match="at least one"):
        answers.generate(engine, web_job["app"], Script(), [{"question": "  "}])
    with pytest.raises(answers.AnswerError, match="at least 20"):
        answers.generate(engine, web_job["app"], Script(), [{"question": "Q", "char_limit": 5}])
    with Session(engine) as s:
        s.get(CVVersion, web_job["cv"]).status = CVStatus.draft
        s.commit()
    with pytest.raises(answers.AnswerError, match="Approve the CV"):
        answers.generate(engine, web_job["app"], Script(), [{"question": "Why?"}])


def test_answers_api(web_job: dict, client) -> None:  # noqa: F811, ANN001
    app_id = web_job["app"]
    assert client.get(f"/api/applications/{app_id}/answers").json() == []
    r = client.post(f"/api/applications/{app_id}/answers",
                    json={"questions": [{"question": "Why us?", "char_limit": 300}]})
    assert r.status_code == 201, r.text
    [a] = r.json()
    assert a["length"] <= 300 and a["sources"] and a["sentences"]
    patched = client.patch(f"/api/answers/{a['id']}", json={"answer": "I built pipelines."}).json()
    assert patched["edited"] and patched["sentences"] == [] and patched["char_limit"] == 300
    cleared = client.patch(f"/api/answers/{a['id']}", json={"clear_limit": True}).json()
    assert cleared["char_limit"] is None
    assert client.patch(f"/api/answers/{a['id']}", json={"char_limit": 3}).status_code == 422
    assert client.delete(f"/api/answers/{a['id']}").status_code == 204
    assert client.get(f"/api/applications/{app_id}/answers").json() == []
