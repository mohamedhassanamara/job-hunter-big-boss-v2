# ruff: noqa: F811
"""Interview preparation: stories from the pool only, code checks (grounding, honesty, STAR parts),
one retry with feedback, the claim verifier gate on approval, edits, and the endpoints. Offline."""

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import ExperienceItem, InterviewPrep
from app.models.enums import CVStatus
from app.providers.base import (
    DraftFailed,
    EmailSentence,
    InterviewPrepPlan,
    PrepQuestion,
    StarStory,
    VerifyPlan,
)
from app.providers.mock import MockInterviewDrafter
from app.services import interview_prep as ip
from app.services import verifier
from tests.test_outreach import job_ready  # noqa: F401 (fixture)
from tests.test_verifier import Scripted, claim


def role(s: Session, item_id: int) -> ExperienceItem:
    return s.get(ExperienceItem, item_id)


def one_story_plan(info: dict, **kw) -> InterviewPrepPlan:  # noqa: ANN003
    """A plan whose sentences are the role's own bullets (always grounded)."""
    with Session(engine) as s:
        item = role(s, info["role"])
        bullets = list(item.bullets)
    cite = [info["role"]]
    sentence = lambda t: EmailSentence(text=t, citations=cite)  # noqa: E731
    story = StarStory(requirement="data pipelines", title="Pipelines",
                      situation=[sentence(f"I worked as {item.title} at {item.org}.")],
                      task=[sentence(bullets[0])], action=[sentence(bullets[-1])],
                      result=kw.pop("result", []))
    return InterviewPrepPlan(
        pitch=[sentence(f"I am {item.title} at {item.org}.")], stories=[story],
        questions=[PrepQuestion(question="Tell me about your pipelines.", probes="depth",
                                story=0)],
        ask_them=["What does success look like?"], **kw)


class Script:
    model, prompt_version = "script", "interview_prep/test"

    def __init__(self, *plans: InterviewPrepPlan):
        self.plans, self.feedback = list(plans), []

    def prepare(self, request, feedback: str = ""):  # noqa: ANN001, ANN201
        self.feedback.append(feedback)
        assert request.pool["roles"], "stories come from the whole pool"
        return self.plans.pop(0)


def kinds(found: list[dict]) -> set[str]:
    return {v["type"] for v in found}


def test_the_mock_builds_grounded_stories_from_the_pool(job_ready: dict) -> None:
    prep = ip.generate(engine, job_ready["app"], MockInterviewDrafter())
    assert prep.version == 1 and prep.status == CVStatus.draft
    assert ip.errors(prep.violations) == [], prep.violations
    stories = prep.content["stories"]
    assert 1 <= len(stories) <= 4 and all(s["action"] and s["situation"] for s in stories)
    assert all(x["citations"] for _w, x in ip.candidate_sentences(prep.content))


def test_numbers_tools_and_years_must_be_in_the_cited_items(job_ready: dict) -> None:
    plan = one_story_plan(job_ready)
    plan.stories[0].result = [EmailSentence(text="It cut costs by 91% using Snowflake.",
                                            citations=[job_ready["role"]])]
    with Session(engine) as s:
        found = ip.check(s, plan.model_dump())
    messages = " ".join(v["message"] for v in ip.errors(found))
    assert "91" in messages and kinds(found) >= {"grounding"}
    uncited = one_story_plan(job_ready)
    uncited.pitch = [EmailSentence(text="I am a great engineer.", citations=[])]
    with Session(engine) as s:
        assert "grounding" in kinds(ip.check(s, uncited.model_dump()))
    flagged = one_story_plan(job_ready)
    flagged.pitch[0].about_job = True
    with Session(engine) as s:
        assert "uncited" in kinds(ip.check(s, flagged.model_dump()))


def test_a_story_without_a_stated_result_is_a_warning_never_an_invented_outcome(
        job_ready: dict) -> None:
    plan = one_story_plan(job_ready)
    with Session(engine) as s:
        found = ip.check(s, plan.model_dump())
    assert ip.errors(found) == []
    assert any("No result stated" in v["message"] and v["severity"] == "warning" for v in found)
    broken = plan.model_copy(deep=True)
    broken.stories[0].action = []
    broken.questions[0].story = 5
    with Session(engine) as s:
        errs = ip.errors(ip.check(s, broken.model_dump()))
    assert {"star", "question"} <= kinds(errs)


def test_one_retry_with_the_problems_as_feedback(job_ready: dict) -> None:
    bad = one_story_plan(job_ready)
    bad.pitch = [EmailSentence(text="I scaled it to 40 million users.",
                               citations=[job_ready["role"]])]
    drafter = Script(bad, one_story_plan(job_ready))
    prep = ip.generate(engine, job_ready["app"], drafter)
    assert drafter.feedback[0] == "" and "pitch 1" in drafter.feedback[1]
    assert prep.plan["attempts"] == 2 and ip.errors(prep.violations) == []


def test_a_still_failing_prep_is_kept_with_its_problems_and_cannot_be_approved(
        job_ready: dict, client) -> None:  # noqa: ANN001
    bad = one_story_plan(job_ready)
    bad.pitch = [EmailSentence(text="I scaled it to 40 million users.",
                               citations=[job_ready["role"]])]
    prep = ip.generate(engine, job_ready["app"], Script(bad, bad.model_copy(deep=True)))
    assert ip.errors(prep.violations)
    r = client.post(f"/api/interview-prep/{prep.id}/approve")
    assert r.status_code == 409 and "problem" in r.json()["detail"]


def test_regenerating_supersedes_the_draft_and_one_runs_at_a_time(
        job_ready: dict) -> None:
    first = ip.generate(engine, job_ready["app"], MockInterviewDrafter())
    second = ip.generate(engine, job_ready["app"], MockInterviewDrafter())
    assert second.version == first.version + 1
    with Session(engine) as s:
        assert s.get(InterviewPrep, first.id).status == CVStatus.superseded
        assert ip.current(s, job_ready["app"]).id == second.id
    assert ip._one_at_a_time.acquire(blocking=False)
    try:
        with pytest.raises(ip.InterviewError, match="one at a time"):
            ip.generate(engine, job_ready["app"], MockInterviewDrafter())
    finally:
        ip._one_at_a_time.release()


def test_a_failing_model_is_an_error_not_a_crash(job_ready: dict) -> None:
    class Down:
        model, prompt_version = "down", "interview_prep/test"

        def prepare(self, request, feedback=""):  # noqa: ANN001, ANN201
            raise DraftFailed("the claude CLI isn't signed in")

    with pytest.raises(ip.InterviewError, match="signed in"):
        ip.generate(engine, job_ready["app"], Down())


# ---------------------------------------------------------------- the claim verifier gate


def judged(text: str, source: str, verdict: str = "supported") -> VerifyPlan:
    lines = [x for x in text.split("\n") if x.strip()]
    return VerifyPlan(claims=[claim(x, verdict=verdict, source_id=source,
                                    quote=_quote(source, x)) for x in lines])


def _quote(source: str, sentence: str) -> str:
    with Session(engine) as s:
        item_id = int(source.split(":")[1])
        text = verifier._item_text(role(s, item_id))
    word = next((w for w in sentence.split() if len(w) > 3 and w in text), text.split()[0])
    return word


def test_approval_needs_the_verifier_and_an_edit_needs_it_again(
        job_ready: dict, monkeypatch: pytest.MonkeyPatch, client) -> None:  # noqa: ANN001
    prep = ip.generate(engine, job_ready["app"], MockInterviewDrafter())
    source = f"pool:{job_ready['role']}"
    bad = Scripted(judged(ip.plain_text(prep.content), source, "unsupported"))
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: bad)
    r = client.post(f"/api/interview-prep/{prep.id}/approve")
    assert r.status_code == 409 and len(bad.calls) == 1
    assert client.get(f"/api/applications/{job_ready['app']}/interview-prep").json()[
        "prep"]["verification_state"] == "failed"
    good = Scripted(judged(ip.plain_text(prep.content), source))
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: good)
    ok = client.post(f"/api/interview-prep/{prep.id}/approve")
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert set(good.calls[0]) == {"kind", "text", "sources"}
    assert "interview preparation" in good.calls[0]["kind"]
    assert "listing" in good.calls[0]["sources"] and source in good.calls[0]["sources"]
    # an edit invalidates the verification: it must pass again before it can be approved
    content = ok.json()["content"]
    content["pitch"][0]["text"] += " I enjoy it."
    edited = client.patch(f"/api/interview-prep/{prep.id}", json={"content": content}).json()
    assert edited["status"] == "draft" and edited["verification_state"] == "stale"


def test_endpoints_empty_state_and_generate(job_ready: dict, client) -> None:  # noqa: ANN001
    studio = client.get(f"/api/applications/{job_ready['app']}/interview-prep").json()
    assert studio["prep"] is None and studio["has_experience"] and studio["versions"] == 0
    made = client.post(f"/api/applications/{job_ready['app']}/interview-prep/generate", json={})
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["status"] == "draft" and body["content"]["stories"] and body["sources"]
    assert all(v["severity"] != "error" for v in body["violations"])
    again = client.get(f"/api/applications/{job_ready['app']}/interview-prep").json()
    assert again["prep"]["id"] == body["id"]
    only = client.post(f"/api/interview-prep/{body['id']}/verify")
    assert only.status_code == 200 and only.json()["verification_state"] == "passed"  # mock
    assert client.post("/api/applications/999999/interview-prep/generate", json={}
                       ).status_code == 404


def test_no_experience_means_no_stories(job_ready: dict) -> None:
    from app.services import experience_write

    with Session(engine) as s, experience_write.writing():
        for item in s.exec(select(ExperienceItem)).all():
            item.is_active = False
            s.add(item)
        s.commit()
    with pytest.raises(ip.InterviewError, match="experience"):
        ip.generate(engine, job_ready["app"], MockInterviewDrafter())
