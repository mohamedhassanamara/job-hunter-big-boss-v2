"""Light tailoring: what an adapted bullet may change, and the fallback to the pool original."""

from datetime import date

import pytest

from app.models import ExperienceItem
from app.providers.base import CVPlan, PlanBullet, PlanEntry
from app.services import bullet_tailor as bt
from app.services.cv_pool import Pool

ORIGINAL = ("Architected custom Backend-for-Frontend (BFF) endpoints in Spring Boot to streamline "
            "mobile API integration, reducing integration time by 40% and unblocking parallel "
            "development cycles")


def make_pool() -> Pool:
    job = ExperienceItem(id=1, kind="job", title="Software Engineer", org="Acme",
                         start_date=date(2024, 1, 1),
                         bullets=[ORIGINAL, "Mentored a junior developer on Flutter"],
                         tags=["spring-boot", "flutter", "bff"])
    skill = ExperienceItem(id=2, kind="skill", title="Backend", tags=["Spring Boot", "REST APIs",
                                                                       "LLMs (Mistral 7B, Ollama)"])
    return Pool(items={1: job, 2: skill}, profile={}, by_kind={"job": [job], "skill": [skill]})


@pytest.mark.parametrize("adapted,expected", [
    # allowed: another verb, reordered clauses
    (ORIGINAL.replace("Architected", "Designed"), []),
    ("Built custom Backend-for-Frontend (BFF) endpoints in Spring Boot, reducing integration time "
     "by 40% and unblocking parallel development cycles, to streamline mobile API integration", []),
    # not allowed
    (ORIGINAL.replace("40%", "50%"), ["number"]),
    (ORIGINAL.replace(", reducing integration time by 40% and", " and"), ["number"]),
    (ORIGINAL.replace("Spring Boot", "backend framework"), ["drops Spring Boot"]),
    (ORIGINAL.replace("Spring Boot", "Spring Boot and Kafka"), ["Kafka"]),
    (ORIGINAL[: int(len(ORIGINAL) * 0.7)], ["length"]),
    (ORIGINAL + ", delivering results for a large organisation across several regions", ["length"]),
])
def test_adaptation_rules(adapted: str, expected: list[str]) -> None:
    found = bt.problems(ORIGINAL, adapted, make_pool())
    assert bool(found) == bool(expected), found
    for word in expected:
        assert any(word in p for p in found), found


def test_the_listings_term_for_what_you_did_is_allowed() -> None:
    original = ("Built RESTful backend services with Spring Boot for the mobile client app and the "
                "partner portal, used every day by the whole field team")
    assert bt.problems(original, original.replace("RESTful backend services", "REST APIs"),
                       make_pool()) == []


def plan_with(text: str) -> CVPlan:
    return CVPlan(summary="", summary_short="", roles=[PlanEntry(
        item_id=1, relevance=5, bullets=[PlanBullet(source_index=0, text=text, priority=1)])])


def test_enforce_falls_back_to_the_original_and_says_why() -> None:
    pool = make_pool()
    plan, issues, report = bt.enforce(plan_with(ORIGINAL.replace("40%", "50%")), pool)
    b = plan.roles[0].bullets[0]
    assert b.text == ORIGINAL and not b.adapted and "number" in (b.fallback or "")
    assert issues[0]["type"] == "tailoring" and issues[0]["severity"] == "warning"
    assert report["fallbacks"] and report["original"] == 1


def test_enforce_keeps_a_valid_adaptation_and_original_only_discards_it() -> None:
    pool = make_pool()
    adapted = ORIGINAL.replace("Architected", "Designed")
    plan, issues, report = bt.enforce(plan_with(adapted), pool)
    assert plan.roles[0].bullets[0].text == adapted and plan.roles[0].bullets[0].adapted
    assert not issues and report["adapted"] == 1
    plan, _, _ = bt.enforce(plan_with(adapted), pool, original_only=True)
    assert plan.roles[0].bullets[0].text == ORIGINAL


def test_verifier_failures_fall_back_and_an_unjudged_bullet_does_too() -> None:
    from app.providers.base import VerifyClaim, VerifyPlan

    class Verifier:
        model, prompt_version, via, auth_source = "v", "verify/t", "test", None

        def __init__(self, verdict: str, judge: bool = True) -> None:
            self.verdict, self.judge = verdict, judge

        def verify(self, request: dict) -> VerifyPlan:
            if not self.judge:
                return VerifyPlan(claims=[])
            key, source = next(iter(request["sources"].items()))
            return VerifyPlan(claims=[VerifyClaim(
                sentence=request["text"], claim=request["text"], about="candidate",
                verdict=self.verdict, source_id=key, source_quote=source[:30],
                reason="says more")])

    pool = make_pool()
    adapted = ORIGINAL.replace("Architected", "Designed")
    plan, _, _ = bt.enforce(plan_with(adapted), pool)
    ok, issues, record = bt.verify(plan, pool, Verifier("supported"))
    assert ok.roles[0].bullets[0].adapted and not issues and record["status"] == "passed"
    for verifier in (Verifier("exaggerated"), Verifier("supported", judge=False)):
        out, issues, _ = bt.verify(plan, pool, verifier)
        b = out.roles[0].bullets[0]
        assert b.text == ORIGINAL and not b.adapted and issues[0]["type"] == "tailoring"


def test_skills_are_selected_verbatim_from_the_pool() -> None:
    from app.providers.base import PlanSkillGroup
    from app.services.cv_check import verbatim_skills

    pool = make_pool()
    plan = CVPlan(summary="", summary_short="", skills=[PlanSkillGroup(
        item_id=2, items=["spring boot", "Mistral 7B", "rest apis", "Kafka", "Spring Boot"])])
    out = verbatim_skills(plan, pool)
    assert out.skills[0].items == ["Spring Boot", "LLMs (Mistral 7B, Ollama)", "REST APIs"]


def test_code_ticks_are_formatting_not_an_adaptation() -> None:
    from app.services.cv_render import latex_escape

    original = ORIGINAL.replace("Spring Boot", "`Spring Boot`")
    assert bt.problems(original, ORIGINAL, make_pool()) == []
    assert "`" not in latex_escape(original)
    assert latex_escape("won **2nd Place** here") == "won 2nd Place here"
