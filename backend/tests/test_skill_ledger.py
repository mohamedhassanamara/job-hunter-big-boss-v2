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


def jd_only(pool: Pool, index: int = 9):  # noqa: ANN201
    """Only the listing's matches: no fill."""
    return pick(pool, index, min_items=0, target_items=0)


def pick(pool: Pool, index: int, **kw):  # noqa: ANN003, ANN201
    title, text, company = listing(index)
    return sl.select_skills(pool, title=title, description=text, company=company, **kw)


# Arbeitnow #9: "Senior Data Engineer … Microsoft Fabric": Python, SQL, Spark/PySpark, Power BI,
# Azure, Microsoft Fabric, OneLake, CI/CD, Data Pipelines, ETL.


def test_only_skills_the_listing_names_are_shown_in_listing_order() -> None:
    pool = make_pool(groups=[["SQL", "Python", "Haskell", "COBOL", "Power BI"]])
    out = jd_only(pool)
    shown = out.display
    assert set(shown) == {"SQL", "Python", "Power BI"}  # Haskell and COBOL: not in the listing
    assert "Haskell" not in shown and "COBOL" not in shown
    # most relevant first: Power BI is named on two requirement lines, Python and SQL once each
    assert shown == ["Power BI", "Python", "SQL"]
    assert all(s.reason == "jd" and s.score > 0 for s in out.skills)


def test_a_listing_only_skill_is_never_shown_and_is_reported_as_a_gap() -> None:
    pool = make_pool(groups=[["Python", "SQL"]])
    out = jd_only(pool)
    names = {s.lower() for s in out.display}
    for term in ("azure", "power bi", "microsoft fabric", "onelake", "pyspark"):
        assert term not in names
    gaps = {g.lower() for g in out.gaps}
    assert "azure" in gaps and "python" not in gaps and "sql" not in gaps
    # German nouns and hyphenated compounds are not tools, so they are not gaps
    assert not {"rolle", "punkten", "entwicklung", "data-teams", "it-lösungen"} & gaps


def test_the_listing_never_changes_the_spelling() -> None:
    pool = make_pool(groups=[["python 3", "Postgres SQL"]])
    # "python 3" is not "Python": no inference
    assert jd_only(pool).display == []
    pool = make_pool(groups=[["Spark (PySpark, Delta)"]])
    assert jd_only(pool).display == ["Spark (PySpark, Delta)"]  # whole, as written


def test_tiers_are_assigned_and_the_best_tier_wins() -> None:
    pool = make_pool(groups=[["Python", "SQL"]], proofs=[["Azure", "SQL"]],
                     study=[["Power BI", "Azure", "Python"]])
    out = {s.skill: s for s in jd_only(pool).skills}
    assert out["Python"].tier == 1 and out["SQL"].tier == 1  # your skills beat a proof
    assert out["Azure"].tier == 2  # a proof beats a certification
    assert out["Power BI"].tier == 3  # a certification alone
    assert len(out) == 4  # no duplicates


def test_free_form_tags_on_jobs_and_projects_are_not_skills() -> None:
    pool = make_pool(groups=[["Python"]], jobs=[["SQL", "mentoring", "web"]])
    assert jd_only(pool).display == ["Python"]  # SQL only on a job tag: not read


def test_certification_and_proof_skills_enter_only_when_the_listing_names_them() -> None:
    pool = make_pool(groups=[["Python"]], proofs=[["Zebra Stack"]], study=[["Quokka DB"]])
    shown = jd_only(pool).display
    assert "Zebra Stack" not in shown and "Quokka DB" not in shown


GROUPS = [["Python", "SQL", "Power BI", "Azure"], ["Docker", "Kafka", "Go", "Terraform"],
          ["Flutter", "Dart", "Swift", "Kotlin"]]


def sel(pool, **kw):  # noqa: ANN001, ANN003, ANN201
    return pick(pool, 9, **kw)


def test_a_short_match_is_filled_to_the_target_from_your_skill_groups() -> None:
    pool = make_pool(groups=GROUPS, proofs=[["Zebra Stack"]], study=[["Quokka DB"]],
                     jobs=[["mentoring", "web"]])
    out = sel(pool)  # the listing names Azure, Power BI, Python and SQL only
    assert [(s.skill, s.reason) for s in out.skills] == [
        ("Azure", "jd"), ("Power BI", "jd"), ("Python", "jd"), ("SQL", "jd"),
        ("Docker", "fill"), ("Kafka", "fill"), ("Go", "fill"), ("Terraform", "fill"),
        ("Flutter", "fill"), ("Dart", "fill"), ("Swift", "fill"), ("Kotlin", "fill")]
    assert out.enough  # 12 skills exist in total: above the minimum of 10
    shown = set(out.display)
    assert shown <= {s for g in GROUPS for s in g}  # never a tag, a proof or a certification
    assert {"Zebra Stack", "Quokka DB", "mentoring", "web"}.isdisjoint(shown)


def test_same_group_skills_come_before_the_rest() -> None:
    pool = make_pool(groups=[["Rust", "Haskell"], ["Python", "SQL", "Go"], ["Dart", "Swift"]])
    out = sel(pool, target_items=5, min_items=1)
    assert [(s.skill, s.reason) for s in out.skills] == [
        ("Python", "jd"), ("SQL", "jd"), ("Go", "group"), ("Rust", "fill"), ("Haskell", "fill")]


def test_pins_boost_ahead_of_the_fill() -> None:
    out = sel(make_pool(groups=GROUPS), target_items=6, min_items=1,
              keep={"x": ["Kotlin", "Zebra", "Terraform"]})
    assert [(s.skill, s.reason) for s in out.skills][4:] == [("Kotlin", "pin"),
                                                              ("Terraform", "pin")]


def test_a_track_without_pins_still_fills() -> None:
    out = sel(make_pool(groups=GROUPS), keep={})
    assert len(out.skills) == 12 and out.enough
    assert not [s for s in out.skills if s.reason == "pin"]


def test_a_listing_gap_is_never_in_the_list() -> None:
    pool = make_pool(groups=[["Python", "SQL", "Docker", "Git", "Bash", "Linux", "Go", "Java",
                              "Kotlin", "Swift", "Dart"]])
    out = sel(pool)  # listing 9 names Azure, Power BI, OneLake, Spark... none of them yours here
    assert not {"Azure", "Power BI", "OneLake", "Spark", "REST"} & set(out.display)
    assert "Azure" in out.gaps and len(out.display) == 11


def test_below_the_minimum_after_the_fill_is_not_enough() -> None:
    pool = make_pool(groups=[["Python", "SQL", "Git"]])
    out = sel(pool, min_items=10)
    assert out.display == ["Python", "SQL", "Git"] and not out.enough


def test_matches_beyond_the_target_are_kept_up_to_the_cap() -> None:
    pool = make_pool(groups=[["Python", "SQL", "Power BI", "Azure"]])
    out = sel(pool, target_items=2, min_items=1)
    assert len(out.skills) == 4 and all(s.reason == "jd" for s in out.skills)  # no fill needed


def test_the_cap_keeps_the_most_relevant() -> None:
    pool = make_pool(groups=[["Python", "SQL", "Power BI", "Azure", "Spark", "CI/CD"]])
    capped = pick(pool, 9, max_items=2, min_items=0, target_items=0)
    full = pick(pool, 9, max_items=18, min_items=0, target_items=0)
    assert capped.display == full.display[:2] and len(full.display) > 2


def test_an_ambiguous_word_is_not_matched_inside_ordinary_prose() -> None:
    # Arbeitnow #22 is a sales role: "Sales and Go-to-Market" must not give you Go.
    pool = make_pool(groups=[["Go", "Python"]])
    assert "Go" not in pick(pool, 22, min_items=0, target_items=0).display
    pool = make_pool(groups=[["Go"]])
    out = sl.select_skills(pool, title="Backend Engineer", description="You write Go services. "
                           "Experience with Go is required.", min_items=0, target_items=0)
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
    pool = make_pool(groups=[own[:4], own[4:]])
    for index in (1, 3, 8, 9, 10, 11, 16, 26):
        out = pick(pool, index, min_items=0, target_items=0)
        assert set(out.display) <= set(own)
        title, text, _ = listing(index)
        for skill in out.display:
            assert re.search(rf"(?<![A-Za-z0-9]){re.escape(skill)}(?![A-Za-z0-9])",
                             f"{title} {text}", re.I), (index, skill)


@pytest.mark.parametrize("index", [9, 8, 10])
def test_selection_dict_is_storable(index: int) -> None:
    pool = make_pool(groups=[["Python", "SQL", "Airflow", "dbt"]], study=[["Spark"]])
    out = pick(pool, index, min_items=0, target_items=0)
    stored = [s.to_dict() for s in out.skills]
    assert json.loads(json.dumps(stored)) == stored
    assert all(set(d) == {"skill", "tier", "item_ids", "reason"} for d in stored)


@pytest.mark.parametrize("word", ["S3", "C++", "C#", "Node.js", "D3.js", ".NET", "DP-600",
                                  "Azure", "SQL", "Python3", "Kafka", "AWS", "REST", "S3", "EC2"])
def test_tool_shaped_words(word: str) -> None:
    assert sl._tool_shaped(word)


@pytest.mark.parametrize("word", ["5+", "21st", "70-20-10", "Rolle", "Cars", "ABOUT", "READY",
                                  "Data-Teams", "traceability.Join", "AI", "ETL", "OneLake",
                                  "TRY", "SIM", "DAG", "CPU", "KPIs", "a1mobilea1mobile",
                                  "a1mobileOur"])
def test_ordinary_or_ambiguous_words_are_not_gaps(word: str) -> None:
    assert not sl._tool_shaped(word)


def test_gaps_of_a_real_listing_are_tools_only() -> None:
    out = jd_only(make_pool(groups=[["Python", "SQL"]]), 10)  # Data Analyst, dbt
    assert {"Snowflake", "BigQuery", "Tableau"} <= set(out.gaps)
    assert not {"ABOUT", "READY", "IMPACT", "traceability.Join"} & set(out.gaps)
