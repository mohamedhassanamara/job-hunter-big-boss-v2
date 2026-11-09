"""The skills list of a job CV: JD terms ∩ your evidence, by tier. Real listings from the
recorded Arbeitnow fixture; no model, no network."""
import html
import json
import re
from pathlib import Path

import pytest

from app.models import ExperienceItem
from app.services import skill_ledger as sl
from app.services.cv_pool import Pool

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "arbeitnow.json"


def listing(index: int) -> tuple[str, str, str]:
    job = json.loads(FIXTURE.read_text())["data"][index]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(job["description"])))
    return job["title"], text, job["company_name"]


_ids = iter(range(1, 1000))


def item(kind: str, title: str, tags: list[str]) -> ExperienceItem:
    return ExperienceItem(id=next(_ids), kind=kind, title=title, org="X", bullets=[], tags=tags,
                          tracks=[], position=0)


def make_pool(*, groups=(), jobs=(), proofs=(), study=()) -> Pool:  # noqa: ANN001
    items = [item("skill", f"g{n}", list(t)) for n, t in enumerate(groups)]
    items += [item("job", f"j{n}", list(t)) for n, t in enumerate(jobs)]
    pool = Pool(items={i.id: i for i in items}, profile={})
    for i in items:
        pool.by_kind.setdefault(i.kind, []).append(i)
    pool.skill_proofs = [item("skill_proof", f"p{n}", list(t)) for n, t in enumerate(proofs)]
    pool.study_tags = {next(_ids): list(t) for t in study}
    return pool


def pick(pool: Pool, index: int, **kw):  # noqa: ANN003, ANN201
    title, text, company = listing(index)
    return sl.select_skills(pool, title=title, description=text, company=company, **kw)


# Arbeitnow #9: "Senior Data Engineer … Microsoft Fabric": Python, SQL, Spark/PySpark, Power BI,
# Azure, Microsoft Fabric, OneLake, CI/CD, Data Pipelines, ETL.


def test_only_skills_the_listing_names_are_shown_in_listing_order() -> None:
    pool = make_pool(groups=[["SQL", "Python", "Haskell", "COBOL", "Power BI"]])
    out = pick(pool, 9, min_items=0)
    shown = out.display
    assert set(shown) == {"SQL", "Python", "Power BI"}  # Haskell and COBOL: not in the listing
    assert "Haskell" not in shown and "COBOL" not in shown
    # most relevant first: Power BI is named on two requirement lines, Python and SQL once each
    assert shown == ["Power BI", "Python", "SQL"]
    assert all(s.reason == "jd" and s.score > 0 for s in out.skills)


def test_a_listing_only_skill_is_never_shown_and_is_reported_as_a_gap() -> None:
    pool = make_pool(groups=[["Python", "SQL"]])
    out = pick(pool, 9, min_items=0)
    names = {s.lower() for s in out.display}
    for jd_only in ("azure", "power bi", "microsoft fabric", "onelake", "pyspark"):
        assert jd_only not in names
    gaps = {g.lower() for g in out.gaps}
    assert "azure" in gaps and "python" not in gaps and "sql" not in gaps
    # German nouns and hyphenated compounds are not tools, so they are not gaps
    assert not {"rolle", "punkten", "entwicklung", "data-teams", "it-lösungen"} & gaps


def test_the_listing_never_changes_the_spelling() -> None:
    pool = make_pool(groups=[["python 3", "Postgres SQL"]])
    assert pick(pool, 9, min_items=0).display == []  # "python 3" is not "Python": no inference
    pool = make_pool(groups=[["Spark (PySpark, Delta)"]])
    assert pick(pool, 9, min_items=0).display == ["Spark (PySpark, Delta)"]  # whole, as written


def test_tiers_are_assigned_and_the_best_tier_wins() -> None:
    pool = make_pool(groups=[["Python"]], jobs=[["SQL"]], proofs=[["Azure", "SQL"]],
                     study=[["Power BI", "Azure", "Python"]])
    out = {s.skill: s for s in pick(pool, 9, min_items=0).skills}
    assert out["Python"].tier == 1 and out["SQL"].tier == 1  # a job beats a proof
    assert out["Azure"].tier == 2  # a proof beats a certification
    assert out["Power BI"].tier == 3  # a certification alone
    assert len(out) == 4  # no duplicates


def test_certification_and_proof_skills_enter_only_when_the_listing_names_them() -> None:
    pool = make_pool(groups=[["Python"]], proofs=[["Zebra Stack"]], study=[["Quokka DB"]])
    shown = pick(pool, 9, min_items=0).display
    assert "Zebra Stack" not in shown and "Quokka DB" not in shown


def test_padding_uses_pinned_tier_one_skills_only() -> None:
    pool = make_pool(groups=[["Python", "Docker", "Kafka", "Go"]], proofs=[["Terraform"]],
                     study=[["Redis"]])
    keep = {"Backend": ["Docker", "Terraform", "Redis", "Kafka", "NotInPool"]}
    out = pick(pool, 9, keep=keep, min_items=3, max_items=10)
    padded = [s for s in out.skills if s.reason == "pad"]
    assert [s.skill for s in out.skills] == ["Python", "Docker", "Kafka"]  # jd match, then pins
    assert [s.skill for s in padded] == ["Docker", "Kafka"]
    assert all(s.tier == 1 for s in padded)  # Terraform (proof) and Redis (study) never pad
    assert {"Terraform", "Redis", "NotInPool"}.isdisjoint(out.display)
    assert len(out.skills) == 3  # padded up to the minimum, no further


def test_no_padding_when_the_listing_already_matches_enough() -> None:
    pool = make_pool(groups=[["Python", "SQL", "Power BI", "Azure", "Docker"]])
    out = pick(pool, 9, keep={"x": ["Docker"]}, min_items=3)
    assert "Docker" not in out.display and all(s.reason == "jd" for s in out.skills)


def test_the_cap_keeps_the_most_relevant() -> None:
    pool = make_pool(groups=[["Python", "SQL", "Power BI", "Azure", "Spark", "CI/CD"]])
    capped = pick(pool, 9, max_items=2, min_items=0)
    full = pick(pool, 9, max_items=18, min_items=0)
    assert capped.display == full.display[:2] and len(full.display) > 2


def test_an_ambiguous_word_is_not_matched_inside_ordinary_prose() -> None:
    # Arbeitnow #22 is a sales role: "Sales and Go-to-Market" must not give you Go.
    pool = make_pool(groups=[["Go", "Python"]])
    assert "Go" not in pick(pool, 22, min_items=0).display
    pool = make_pool(groups=[["Go"]])
    out = sl.select_skills(pool, title="Backend Engineer", description="You write Go services. "
                           "Experience with Go is required.", min_items=0)
    assert out.display == ["Go"]


def test_empty_listing_only_pads() -> None:
    pool = make_pool(groups=[["Python", "SQL"]])
    out = sl.select_skills(pool, title="", description="", keep={"x": ["SQL", "Python"]},
                           min_items=2)
    assert out.display == ["SQL", "Python"] and out.gaps == []


def test_nothing_in_the_ledger_leaks_from_the_listing_text() -> None:
    """Property over several real listings: every JD-chosen skill is one of YOUR spellings and
    every term in the listing text that is not one of yours is absent from the list."""
    own = ["Python", "SQL", "Docker", "AWS", "Airflow", "dbt", "Kubernetes", "TypeScript"]
    pool = make_pool(groups=[own[:4]], jobs=[own[4:]])
    for index in (1, 3, 8, 9, 10, 11, 16, 26):
        out = pick(pool, index, min_items=0)
        assert set(out.display) <= set(own)
        title, text, _ = listing(index)
        for skill in out.display:
            assert re.search(rf"(?<![A-Za-z0-9]){re.escape(skill)}(?![A-Za-z0-9])",
                             f"{title} {text}", re.I), (index, skill)


@pytest.mark.parametrize("index", [9, 8, 10])
def test_selection_dict_is_storable(index: int) -> None:
    pool = make_pool(groups=[["Python", "SQL", "Airflow", "dbt"]], study=[["Spark"]])
    out = pick(pool, index, min_items=0)
    stored = [s.to_dict() for s in out.skills]
    assert json.loads(json.dumps(stored)) == stored
    assert all(set(d) == {"skill", "tier", "item_ids", "reason"} for d in stored)


@pytest.mark.parametrize("word", ["S3", "C++", "C#", "Node.js", "D3.js", ".NET", "DP-600",
                                  "Azure", "SQL", "Python3", "Kafka"])
def test_tool_shaped_words(word: str) -> None:
    assert sl._tool_shaped(word)


@pytest.mark.parametrize("word", ["5+", "21st", "70-20-10", "Rolle", "Cars", "ABOUT", "READY",
                                  "Data-Teams", "traceability.Join", "AI", "ETL", "OneLake"])
def test_ordinary_or_ambiguous_words_are_not_gaps(word: str) -> None:
    assert not sl._tool_shaped(word)


def test_gaps_of_a_real_listing_are_tools_only() -> None:
    out = pick(make_pool(groups=[["Python", "SQL"]]), 10, min_items=0)  # Data Analyst, dbt
    assert {"Snowflake", "BigQuery", "Tableau"} <= set(out.gaps)
    assert not {"ABOUT", "READY", "IMPACT", "traceability.Join"} & set(out.gaps)
