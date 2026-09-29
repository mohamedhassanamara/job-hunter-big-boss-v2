"""Summary grounding, years claims, canonical spelling, false positives, capability phrases."""

from datetime import date

import pytest

from app.models import ExperienceItem
from app.providers.base import (
    CVPlan,
    CVRequest,
    PlanBullet,
    PlanEntry,
    PlanSkillGroup,
    SummaryDraft,
    SummarySentence,
)
from app.services import cv_service
from app.services.cv_check import canonicalize, check_plan, ground_sentences, new_tools
from app.services.cv_claims import (
    Vocabulary,
    bad_years,
    capability_gaps,
    scope_inflation,
    years_claims,
)
from app.services.cv_pool import Pool, role_years, years_facts


def item(id_: int, kind: str, title: str, **kw) -> ExperienceItem:
    return ExperienceItem(id=id_, kind=kind, title=title, org=kw.pop("org", None),
                          bullets=kw.pop("bullets", []), tags=kw.pop("tags", []),
                          summary=kw.pop("summary", None), **kw)


def make_pool(*items: ExperienceItem) -> Pool:
    pool = Pool(items={i.id: i for i in items}, profile={})
    for i in items:
        pool.by_kind.setdefault(i.kind, []).append(i)
    return pool


ROLE = item(1, "job", "Software Engineer", org="Acme", start_date=date(2022, 10, 1), bullets=[
    "Architected BFF endpoints in Spring Boot, reducing integration time by 40%",
    "Refactored the app to Riverpod while mentoring a junior developer",
    "Built data-driven user interfaces in Flutter (UI/UX workshops)",
])
PROJECT = item(2, "project", "Lakehouse", org="Personal project", tags=["dbt", "duckdb"],
               bullets=["Designed a dbt star schema on DuckDB reconciling 2,000 identities"])
SKILLS = item(3, "skill", "Backend", tags=["python", "spring-boot", "rest-api", "spacy"])
NLP = item(4, "job", "AI Engineer", org="Lab", start_date=date(2025, 2, 1),
           end_date=date(2025, 8, 1), bullets=["Built an NLP pipeline with spaCy and YOLOv8"])
SNIPPET = item(5, "summary", "Main", summary="Software engineer building Flutter apps and data "
               "pipelines.")
POOL = make_pool(ROLE, PROJECT, SKILLS, NLP)


def s(text: str, *cites: int) -> SummarySentence:
    return SummarySentence(text=text, citations=list(cites))


# ------------------------------------------------------------------------ 1. grounding


def test_sentences_need_valid_citations_and_grounded_claims() -> None:
    good, bad = ground_sentences([
        s("Architected BFF endpoints in Spring Boot, cutting integration time by 40%.", 1),
        s("Designed a dbt star schema on DuckDB.", 2),
        s("Experienced engineer."),  # no citation
        s("Built pipelines.", 99),  # unknown id
        s("Deployed services on Kubernetes.", 1),  # not in the cited role
        s("Cut costs by 70% with Spring Boot.", 1),  # number not in the cited role
        s("Mentored other developers.", 1),  # scope inflated
    ], POOL, set())
    assert [x.citations for x in good] == [[1], [2]]
    reasons = {x.text: r for x, r in bad}
    assert reasons["Experienced engineer."] == ["no citations"]
    assert "unknown ids" in reasons["Built pipelines."][0]
    assert any("Kubernetes" in r for r in reasons["Deployed services on Kubernetes."])
    assert any("70%" in r for r in reasons["Cut costs by 70% with Spring Boot."])
    assert any("overstates" in r for r in reasons["Mentored other developers."])


class SummaryScript:
    """A generator whose summary regeneration returns scripted drafts."""

    model = "test"

    def __init__(self, retries: list[list[SummarySentence]]):
        self.retries = retries
        self.feedback: list[str] = []

    def generate_summary(self, request: CVRequest, feedback: str) -> SummaryDraft:
        self.feedback.append(feedback)
        sentences = self.retries.pop(0)
        return SummaryDraft(summary_sentences=sentences, summary_short_sentences=sentences[:1])


def plan_with(sentences: list[SummarySentence]) -> CVPlan:
    return CVPlan(summary=" ".join(x.text for x in sentences), summary_short="",
                  summary_sentences=sentences, summary_short_sentences=sentences[:1])


REQUEST = CVRequest(job={}, pool={}, facts={"years": [{"label": "Mobile", "years": 3}]})


def test_rejected_summary_is_regenerated_once_and_passes() -> None:
    gen = SummaryScript([[s("The engineer architected BFF endpoints in Spring Boot.", 1)]])
    plan, issues, report = cv_service.ground_summary(
        plan_with([s("Expert in Kubernetes.", 1)]), POOL, REQUEST, gen)
    assert len(gen.feedback) == 1 and "Kubernetes" in gen.feedback[0]
    assert plan.summary == "The engineer architected BFF endpoints in Spring Boot."
    assert report["attempts"] == 2 and report["fallback"] is None and not issues


def test_second_failure_falls_back_to_the_snippet_verbatim() -> None:
    pool = make_pool(ROLE, PROJECT, SKILLS, NLP, SNIPPET)
    gen = SummaryScript([[s("Unix wizard with 9 years of experience.", 1)]])
    plan, issues, report = cv_service.ground_summary(
        plan_with([s("Expert in Kubernetes.", 1)]), pool, REQUEST, gen)
    assert plan.summary == SNIPPET.summary
    assert plan.summary_sentences[0].citations == [SNIPPET.id]
    assert report["fallback"] == f"snippet {SNIPPET.id}"
    assert issues[0]["type"] == "summary_fallback"


def test_without_a_snippet_only_grounded_sentences_stay() -> None:
    gen = SummaryScript([[s("Unix wizard.", 1)]])
    plan, issues, report = cv_service.ground_summary(
        plan_with([s("Designed a dbt star schema on DuckDB.", 2), s("Kubernetes guru.", 1)]),
        POOL, REQUEST, gen)
    assert plan.summary == "Designed a dbt star schema on DuckDB."
    assert report["fallback"] == "grounded sentences only"


# ----------------------------------------------------------------------------- 2. years


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("3+ years of mobile development", []),
        ("over three years building apps", []),
        ("2+ years of experience", ["2+ years"]),
        ("5 years in data", ["5 years"]),
        ("3.5 years", ["3.5 years"]),
    ],
)
def test_years_claims_must_match_the_allowed_facts(text: str, bad: list[str]) -> None:
    assert bad_years(text, {3, 1}) == bad


def test_years_facts_come_from_settings_tracks_and_role_dates() -> None:
    overlapping = make_pool(ROLE, NLP)  # the AI role overlaps the ongoing one
    assert role_years(overlapping, today=date(2026, 10, 1)) == pytest.approx(4.0, abs=0.01)
    facts = years_facts(overlapping, [{"name": "Mobile", "years_experience": 3},
                                      {"name": "Data/AI", "years_experience": 0.5}],
                        today=date(2026, 10, 1))
    assert [(f["label"], f["years"], f["wording"]) for f in facts] == [
        ("Mobile experience (Settings)", 3, "3+ years"),
        ("professional experience (from role dates)", 4, "4+ years"),
    ]


def test_years_claim_in_a_bullet_keeps_the_source_fact() -> None:
    plan = CVPlan(summary="", summary_short="", roles=[PlanEntry(item_id=1, relevance=9, bullets=[
        PlanBullet(source_index=0, text="With 5 years of Spring Boot, architected BFF endpoints",
                   priority=1)])])
    repaired, issues = check_plan(plan, make_pool(ROLE))
    assert repaired.roles[0].bullets[0].text == ROLE.bullets[0]
    assert any(i["type"] == "years" for i in issues)
    assert years_claims("5 yrs") == [("5 yrs", 5.0)]


# ------------------------------------------------------------------ 3. canonical spelling


def test_skills_and_tools_use_the_pool_spelling() -> None:
    plan = CVPlan(
        summary="Built DBT models and SPACY pipelines with spring boot.", summary_short="",
        summary_sentences=[s("Built DBT models and SPACY pipelines with spring boot.", 2)],
        skills=[PlanSkillGroup(item_id=3, items=["PYTHON", "Spring boot", "DBT", "PostgreSQL"])],
        projects=[{"item_id": 2, "relevance": 8, "stack": ["DBT", "DUCKDB"], "bullets": [
            {"source_index": 0, "text": "Designed a DBT star schema on duckdb", "priority": 1}]}],
    )
    out = canonicalize(plan, POOL)
    assert out.skills[0].items == ["PYTHON", "Spring Boot", "dbt", "PostgreSQL"]
    assert out.projects[0].stack == ["dbt", "DuckDB"]
    assert out.projects[0].bullets[0].text == "Designed a dbt star schema on DuckDB"
    assert out.summary == "Built dbt models and spaCy pipelines with Spring Boot."
    assert out.summary_sentences[0].text == out.summary


# --------------------------------------------------------------------- 4. false positives


def test_plurals_and_word_parts_are_not_new_tools() -> None:
    vocab = Vocabulary("Built user interfaces (UI/UX)", extra=["rest-api"])
    assert new_tools("Shipped UIs and REST APIs", vocab) == []
    assert new_tools("Shipped Kubernetes operators", vocab) == ["Kubernetes"]


# ---------------------------------------------------------------- 5. capability phrases


def test_capability_phrases_not_in_the_pool_are_flagged() -> None:
    pool_text = "Refactored the app while mentoring a junior developer. Linux, Bash, GitHub."
    claims = ("Strong object-oriented programming, Unix and CI/CD skills; experienced in "
              "microservices.")
    assert capability_gaps(claims, pool_text) == [
        "object-oriented programming", "Unix", "CI/CD", "microservices"]
    assert capability_gaps("Comfortable with mentoring.", pool_text) == []
    assert scope_inflation("mentoring other developers", pool_text) == [
        "mentoring other developers"]
    assert scope_inflation("mentoring a junior developer", pool_text) == []
    assert scope_inflation("led a team of engineers", pool_text)


def test_total_years_override_replaces_role_dates() -> None:
    pool = make_pool(ROLE, NLP)
    pool.profile["total_years_override"] = 2
    facts = years_facts(pool, [{"name": "Mobile", "years_experience": 3}],
                        today=date(2026, 10, 1))
    assert facts == [{"label": "total experience (Settings)", "years": 2, "kind": "total",
                      "wording": "2 years of software engineering experience", "exact": True}]
    pool.profile["experience_statement"] = "two years building software"
    assert years_facts(pool, [])[0]["wording"] == "two years building software"
    pool.profile["experience_statement"] = ""
    pool.profile["total_years_override"] = ""
    assert years_facts(pool, [], today=date(2026, 10, 1))[0]["years"] == 4


def test_override_is_what_the_checks_allow() -> None:
    pool = make_pool(ROLE, NLP)
    pool.profile["total_years_override"] = 2
    allowed = {f["years"] for f in years_facts(pool, [], today=date(2026, 10, 1))}
    assert bad_years("2+ years building software", allowed) == []
    assert bad_years("4+ years building software", allowed) == ["4+ years"]


def test_with_an_exact_statement_every_other_years_claim_is_rejected() -> None:
    from app.services.cv_claims import exact_statement

    statement = "3 years of software engineering experience"
    assert exact_statement([{"wording": statement, "exact": True}]) == statement
    assert bad_years(f"Engineer with {statement}.", {3}, statement) == []
    assert bad_years("Engineer with 3+ years of experience.", {3}, statement) == ["3+ years"]
    assert bad_years(f"{statement}, including 1 year of AI.", {3}, statement) == ["1 year"]
    assert bad_years("over three years of work", {3}, statement)
