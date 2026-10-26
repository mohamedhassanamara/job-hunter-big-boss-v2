"""APInex as the CV model: one routing helper, rated leftovers, no invented summary, and
APInex never reaches a step that runs through claude -p. Offline: a fake client."""

import pytest

from app.providers import registry
from app.providers.apinex_cv import APInexCVGenerator
from app.providers.apinex_models import is_apinex
from app.providers.base import CVRequest, ScoringFailed
from app.providers.gemini_generate import GenerationFailed, generation_failure
from app.services.cv_service import CVError

POOL = {
    "roles": [{"id": 1, "title": "Engineer", "org": "Acme",
               "facts": {"0": "Built ETL", "1": "Cut costs 20%", "2": "Wrote docs"}}],
    "projects": [{"id": 5, "title": "Lake", "tags": ["dbt"],
                  "facts": {"0": "Modelled", "1": "Orchestrated"}},
                 {"id": 6, "title": "Other", "tags": [], "facts": {"0": "A", "1": "B", "2": "C"}}],
    "skill_groups": [{"id": 9, "category": "Data", "skills": ["SQL"]}],
}
REQUEST = CVRequest(job={"title": "DE"}, pool=POOL)
SUMMARY = {"summary_sentences": [{"text": "I build data systems.", "citations": [1]}],
           "summary_short_sentences": [{"text": "Data.", "citations": [1]}]}


class FakeClient:
    def __init__(self, *answers: object):
        self.answers, self.calls = list(answers), 0

    def complete_sync(self, system: str, user: str, model: str | None = None) -> dict:
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer  # type: ignore[return-value]


@pytest.mark.parametrize(("model", "expected"), [
    ("free/minimax-m3.1-flash", True), ("free/glm-5.3-flash", True), ("apinex", True),
    ("minimax-m3", True), ("gemini-3.5-flash-lite", False), ("claude-sonnet-5", False),
    ("deepseek-r1:8b", False), ("gemma4:12b", False), ("", False), (None, False)])
def test_is_apinex(model: str | None, expected: bool) -> None:
    assert is_apinex(model) is expected


def test_apinex_never_reaches_email_letters_or_claude_p() -> None:
    from app.providers.claude_cv import ClaudeCVGenerator
    from app.providers.claude_verify import ClaudeVerifier

    m = "free/minimax-m3.1-flash"
    for call in (lambda: registry.email_drafter(model=m), lambda: registry.letter_drafter(model=m),
                 lambda: registry.email_drafter(mock=True, model=m),
                 lambda: ClaudeCVGenerator(m), lambda: ClaudeVerifier(m),
                 lambda: registry._claude_cv(m)):
        with pytest.raises(ValueError, match="APInex"):
            call()
    assert isinstance(registry.cv_generator(mock=False, model=m), APInexCVGenerator)


def planner(ratings: list | None = None) -> dict:
    return {"selected_roles": [{"id": 1, "fact_indices": [0, 1]}],
            "selected_projects": [{"id": 5, "fact_indices": [0, 1]}],
            "selected_skills": [{"category": "Data", "skills": ["SQL"]}],
            **({"ratings": ratings} if ratings is not None else {})}


def test_pass_1_returns_every_unused_item_rated_and_never_pads_the_plan() -> None:
    ratings = [{"kind": "role", "id": 1, "fact_index": 2, "relevance": 7},
               {"kind": "project", "id": 6, "fact_index": None, "relevance": 9},
               {"kind": "role", "id": 99, "fact_index": 0, "relevance": 10},  # not a real id
               {"kind": "role", "id": 1, "fact_index": 1, "relevance": 5}]  # already essential
    gen = APInexCVGenerator(client=FakeClient(planner(ratings)))  # type: ignore[arg-type]
    out = gen._run_pass1_planner(REQUEST)
    assert out["selected_roles"] == [{"id": 1, "fact_indices": [0, 1]}]  # fact 2 NOT appended
    extras = {(e.kind, e.item_id, e.source_index): e.relevance for e in out["extras"]}
    assert extras == {("role", 1, 2): 7, ("project", 6, None): 9}


def test_an_unrated_item_is_tried_last_with_relevance_0_and_no_project_is_injected() -> None:
    ans = {**planner([]), "selected_projects": []}
    out = APInexCVGenerator(client=FakeClient(ans))._run_pass1_planner(REQUEST)  # type: ignore[arg-type]
    assert out["selected_projects"] == []  # the first pool project is no longer slipped in
    assert {(e.item_id, e.source_index): e.relevance for e in out["extras"]}[(1, 2)] == 0
    assert {e.item_id for e in out["extras"] if e.kind == "project"} == {5, 6}


def test_a_gateway_failure_is_a_generation_failure_the_page_can_retry() -> None:
    gen = APInexCVGenerator(client=FakeClient(ScoringFailed("429")))  # type: ignore[arg-type]
    with pytest.raises(GenerationFailed):
        gen.generate(REQUEST)
    err = CVError("x")
    err.__cause__ = GenerationFailed("down")
    assert generation_failure(err) is not None  # → HTTP 503, Retry panel


def test_a_summary_request_with_no_summary_fails_instead_of_inventing_one() -> None:
    gen = APInexCVGenerator(client=FakeClient({"summary_sentences": []}))  # type: ignore[arg-type]
    with pytest.raises(GenerationFailed, match="no summary"):
        gen.generate_summary(REQUEST, "")
    ok = APInexCVGenerator(client=FakeClient(SUMMARY)).generate_summary(REQUEST, "")  # type: ignore[arg-type]
    assert ok.summary_sentences[0].text == "I build data systems."
    down = APInexCVGenerator(client=FakeClient(ScoringFailed("x")))  # type: ignore[arg-type]
    with pytest.raises(GenerationFailed):
        down.generate_summary(REQUEST, "")


class SummaryGen:
    model = "x"

    def __init__(self, *drafts):  # noqa: ANN002
        self.drafts, self.calls = list(drafts), 0

    def generate_summary(self, request, feedback, **kw):  # noqa: ANN001, ANN003, ANN201
        from app.providers.base import SummaryDraft

        self.calls += 1
        return SummaryDraft(summary_sentences=self.drafts.pop(0), summary_short_sentences=[])


def _empty_plan():  # noqa: ANN202
    from app.providers.base import CVPlan

    return CVPlan(summary="", summary_short="")


def test_no_summary_is_retried_once_then_fails_and_is_never_a_snippet() -> None:
    from app.providers.base import SummarySentence
    from app.services import cv_service
    from tests.test_cv_rules import make_pool

    pool, request = make_pool(), CVRequest(job={}, pool={})
    gen = SummaryGen([])
    with pytest.raises(GenerationFailed, match="no summary"):
        cv_service.ground_summary(_empty_plan(), pool, request, gen)  # type: ignore[arg-type]
    assert gen.calls == 1  # asked once more, then gave up
    gen = SummaryGen([SummarySentence(text="Software Engineer at Reality Sports.",
                                      citations=[1])])
    plan, issues, report = cv_service.ground_summary(
        _empty_plan(), pool, request, gen)  # type: ignore[arg-type]
    assert plan.summary == "Software Engineer at Reality Sports." and gen.calls == 1
    assert report["attempts"] == 2 and not any(i["type"] == "summary_fallback" for i in issues)


# ------------------------------------------------------- HTTP 402: the daily check-in


def _client_402():  # noqa: ANN202
    import httpx

    from app.providers.apinex_client import APInexClient, RollingRateLimiter

    body = {"error": {"message": "Daily check-in required to use free models."}}
    return APInexClient(
        api_key="k", sleep_fn=lambda s: None,
        limiter=RollingRateLimiter(limit=100, window=60.0, sleep_fn=lambda s: None),
        transport=httpx.MockTransport(lambda request: httpx.Response(402, json=body)))


def test_a_402_is_remembered_shown_and_cleared_without_calling_apinex(client) -> None:  # noqa: ANN001
    from app.providers.base import QuotaExceeded

    assert client.get("/api/scoring/apinex").json()["needs_checkin"] is False
    with pytest.raises(QuotaExceeded, match="daily check-in"):
        _client_402().complete_sync("s", "u")
    seen = client.get("/api/scoring/apinex").json()
    assert seen["needs_checkin"] is True and "check-in" in seen["message"]
    assert seen["url"].startswith("https://apinex.bond/")
    assert client.post("/api/scoring/apinex/checked-in").json()["needs_checkin"] is False


def test_a_good_apinex_answer_clears_the_notice(client) -> None:  # noqa: ANN001
    import httpx

    from app.providers.apinex_client import APInexClient, RollingRateLimiter
    from app.providers.base import QuotaExceeded

    with pytest.raises(QuotaExceeded):
        _client_402().complete_sync("s", "u")
    answer = {"choices": [{"message": {"content": "{\"ok\": 1}"}}]}
    ok = APInexClient(api_key="k", sleep_fn=lambda s: None,
                      limiter=RollingRateLimiter(limit=100, window=60.0, sleep_fn=lambda s: None),
                      transport=httpx.MockTransport(lambda r: httpx.Response(200, json=answer)))
    assert ok.complete_sync("s", "u") == {"ok": 1}
    assert client.get("/api/scoring/apinex").json()["needs_checkin"] is False


def test_a_402_on_the_cv_is_a_single_non_retryable_failure_with_the_retry_panel() -> None:
    gen = APInexCVGenerator(client=_client_402())  # type: ignore[arg-type]
    with pytest.raises(GenerationFailed) as err:
        gen.generate(REQUEST)
    assert err.value.retryable is False and "check-in" in str(err.value)
    with pytest.raises(GenerationFailed) as err2:
        gen.generate_summary(REQUEST, "")
    assert err2.value.retryable is False  # the background worker marks it failed once, no loop


def test_generate_with_gemini_is_a_one_shot_choice_and_never_automatic(seeded: None) -> None:
    from sqlmodel import Session

    from app.db import engine
    from app.services import model_choice

    with Session(engine) as s:
        pick = model_choice.choice(s, "cv", "gemini")
        assert pick["provider"] == "gemini" and pick["model"].startswith("gemini-")
        assert model_choice.choice(s, "cv")["provider"] == "apinex"  # the setting is unchanged


def test_the_cv_endpoints_accept_only_known_one_shot_choices(client) -> None:  # noqa: ANN001
    app_id = client.get("/api/jobs?stage=all").json()["items"][0]["application"]["id"]
    assert client.post(f"/api/applications/{app_id}/cv/generate",
                       json={"use": "gpt"}).status_code == 422
    cv_id = client.get("/api/jobs?stage=all").json()["items"][0]["id"]  # any id: validated first
    assert client.post(f"/api/cv/{cv_id}/summary", json={"use": "gpt"}).status_code in (404, 422)
