"""CV structure rules: role types and bullet allowances, the fill loop (98% target, never
filler, never a 1-bullet project), generic bullets last, skill shaping, summary checks and the
retry, and the guide/exemplar/layout sent to the model."""

from datetime import date
from pathlib import Path

import pytest

from app.models import ExperienceItem
from app.providers.base import (
    CVPlan,
    CVRequest,
    PlanBullet,
    PlanEntry,
    PlanProject,
    SummaryDraft,
    SummarySentence,
)
from app.services import cv_build, cv_rules, cv_service
from app.services.cv_build import build_document, fit_to_page, initial_state, layout
from app.services.cv_pool import Pool
from app.services.cv_render import CVProfile, load_template
from tests.test_cv import fake_compiler

TODAY = date(2026, 9, 28)
RULES = dict(cv_rules.DEFAULT_STRUCTURE)


def item(id_: int, kind: str, title: str, start: date | None = None, end: date | None = None,
         n: int = 5, org: str = "Org", tags: list[str] | None = None) -> ExperienceItem:
    return ExperienceItem(id=id_, kind=kind, title=title, org=org, start_date=start,
                          end_date=end, bullets=[f"{title} fact {i}" for i in range(n)],
                          tags=tags or [])


CURRENT = item(1, "job", "Software Engineer", date(2025, 9, 1), None, org="Reality Sports")
GRAD = item(2, "job", "AI Engineer (Graduation Project)", date(2025, 2, 1), date(2025, 8, 31),
            4)
MOBILE = item(3, "job", "Mobile Developer", date(2022, 10, 1), date(2025, 2, 28), 4)
INTERN = item(4, "job", "Software Engineer Intern", date(2024, 7, 1), date(2024, 11, 30),
              org="Orange Digital Center")
SHORT = item(5, "job", "Backend Developer", date(2021, 1, 1), date(2021, 6, 30), 3)
P1 = item(6, "project", "Lakehouse", n=3)
P2 = item(7, "project", "Weather Station", n=2)
P3 = item(8, "project", "Tiny", n=1)
P4 = item(9, "project", "Other", n=3)
CERT = item(10, "certification", "Data Engineering Professional Certificate", n=0,
            org="DeepLearning.AI")
ITEMS = [CURRENT, GRAD, MOBILE, INTERN, SHORT, P1, P2, P3, P4, CERT]


def make_pool() -> Pool:
    pool = Pool(items={i.id: i for i in ITEMS}, profile={})
    for i in ITEMS:
        pool.by_kind.setdefault(i.kind, []).append(i)
    return pool


def entry(i: ExperienceItem, relevance: int, cls: type = PlanEntry, generic_first: bool = False):
    bullets = [PlanBullet(source_index=n, text=b, priority=n + 1) for n, b in enumerate(i.bullets)]
    if generic_first and bullets:
        bullets[0] = PlanBullet(source_index=0, text="Collaborated in Agile sprints", priority=1,
                                strength=1)
    return cls(item_id=i.id, relevance=relevance, bullets=bullets)


def make_plan(**kw) -> CVPlan:  # noqa: ANN003
    return CVPlan(summary="Engineer.", summary_short="Engineer.", roles=[
        entry(CURRENT, 6), entry(GRAD, 9), entry(MOBILE, 4), entry(INTERN, 10),
        entry(SHORT, 3)], projects=[entry(P1, 9, PlanProject), entry(P2, 7, PlanProject),
                                    entry(P3, 10, PlanProject), entry(P4, 6, PlanProject)], **kw)


# ------------------------------------------------------------------------ role types


@pytest.mark.parametrize(("it", "expected"), [
    (CURRENT, "current"), (GRAD, "graduation"), (MOBILE, "long_role"), (INTERN, "internship"),
    (SHORT, "short_role"),
    (item(20, "job", "Stagiaire Data", date(2024, 1, 1), date(2024, 6, 1)), "internship"),
    (item(21, "job", "Projet de fin d'études", date(2024, 1, 1), date(2024, 6, 1)),
     "graduation"),
])
def test_role_types(it: ExperienceItem, expected: str) -> None:
    assert cv_rules.role_type(it, RULES, TODAY) == expected


def test_allowances_follow_recency_and_duration_not_relevance() -> None:
    lay = layout(make_plan(), make_pool(), RULES, today=TODAY)
    b = lay.bounds
    assert b["role:1"] == (3, 5)  # current, even with modest relevance
    assert b["role:3"] == (2, 4)  # 2.5-year role, relevance 4
    assert b["role:4"] == (1, 2)  # internship, relevance 10: still max 2
    assert b["role:2"] == (2, 3)  # graduation project, highly relevant: starts at 2
    assert b["role:5"] == (1, 1)  # short, barely relevant
    assert b["project:6"] == (2, 3) and b["project:8"] == (1, 1)


def test_initial_state_minimums_two_projects_never_one_bullet() -> None:
    plan = make_plan()
    state = initial_state(plan, layout(plan, make_pool(), RULES, today=TODAY))
    c = state.counts
    assert (c["role:1"], c["role:3"], c["role:4"], c["role:2"]) == (3, 2, 1, 2)
    shown = [k for k in c if k.startswith("project:") and c[k]]
    assert shown == ["project:6", "project:7", "project:9"] and c["project:8"] == 0  # "Tiny" has 1 fact
    doc = build_document(plan, make_pool(), state, lay=layout(plan, make_pool(), RULES,
                                                              today=TODAY))
    assert all(len(p.bullets) >= 2 for p in doc.projects)


def test_generic_bullets_come_last() -> None:
    plan = make_plan()
    plan.roles[0] = entry(CURRENT, 6, generic_first=True)
    lay = layout(plan, make_pool(), RULES, today=TODAY)
    doc = build_document(plan, make_pool(), initial_state(plan, lay), lay=lay)
    assert "Agile" not in " ".join(doc.roles[0].bullets)


# --------------------------------------------------------------------------- fit loop


def fit(plan: CVPlan, capacity: int, monkeypatch, tmp_path: Path):  # noqa: ANN001, ANN201
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=capacity, calls=[]))
    lay = layout(plan, make_pool(), RULES, today=TODAY)
    return fit_to_page(plan, make_pool(), CVProfile(full_name="Ada"), load_template("default"),
                       tmp_path, lay=lay), lay


def test_underfill_grows_only_within_allowances_never_padding(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    result, lay = fit(make_plan(), capacity=500, monkeypatch=monkeypatch, tmp_path=tmp_path)
    for key, count in result.state.counts.items():
        lo, hi = lay.bounds[key]
        assert count <= hi, key
    assert result.state.counts["role:4"] <= 2  # the internship never beyond 2
    assert result.compiled.fill < RULES["fill_min"]  # stays short rather than padded


def test_growth_stops_at_the_fill_target(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    result, _ = fit(make_plan(), capacity=46, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert result.compiled.pages == 1 and result.compiled.fill >= RULES["fill_min"]


def test_overflow_trims_to_minimums_then_drops_a_project(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    result, lay = fit(make_plan(), capacity=30, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert result.compiled.pages == 1
    assert result.state.counts["role:1"] >= 1
    projects = [k for k, v in result.state.counts.items() if k.startswith("project:") and v]
    assert all(result.state.counts[k] >= 2 for k in projects)


# ----------------------------------------------------------------------------- skills


def test_skills_are_capped_merged_and_not_repeated() -> None:
    groups = [("AI", ["LLM", "NLP", "Mistral", "Ollama", "spaCy", "YOLOv8", "RAG", "MLflow",
                      "OpenAI", "TF-IDF"]),
              ("Data", ["Python", "SQL", "dbt", "Airflow", "DuckDB"]),
              ("Tools", ["Git", "LocalStack", "S3", "Linux", "Bash", "Python"]),
              ("Mobile", ["Flutter"]), ("Extra", ["Excel"])]
    out = cv_rules.shape_skills(groups, RULES, cv_rules.DEFAULT_SKILL_MERGES)
    assert len(out) == 4 and all(len(items) <= 8 for _, items in out)
    ai = out[0][1]
    assert ai[0] == "LLMs (Mistral, Ollama, OpenAI)" and "LLM" not in ai and "Mistral" not in ai
    tools = dict(out)["Tools"]
    assert "LocalStack (S3)" in tools and "Linux/Bash" in tools and "Python" not in tools


def test_skill_slugs_are_displayed_with_their_usual_spelling() -> None:
    assert cv_rules.display("sql") == "SQL" and cv_rules.display("github-actions") == \
        "GitHub Actions"
    assert cv_rules.display("dbt", "dbt") == "dbt"  # the pool's own spelling wins
    assert cv_rules.display("postgres", "Postgres") == "Postgres"
    assert cv_rules.display("someunknowntool") == "someunknowntool"


def test_a_certificate_titled_like_a_role_is_not_a_certification_mention() -> None:
    cert = item(30, "certification", "Data Engineer", n=0, org="DataCamp")
    ok = cv_rules.summary_problems("Software engineer moving into data engineering.",
                                   rules=RULES, bullet_texts=[], certifications=[cert],
                                   internships=[], tools=set())
    assert ok == []
    assert cv_rules.summary_problems("Engineer certified by DataCamp.", rules=RULES,
                                     bullet_texts=[], certifications=[cert], internships=[],
                                     tools=set())


# ---------------------------------------------------------------------------- summary


def problems(text: str) -> list[str]:
    return cv_rules.summary_problems(
        text, rules=RULES, bullet_texts=["Ingested 140K+ records into S3", "Cut costs by 40%"],
        certifications=[CERT], internships=[INTERN], tools={"dbt", "Airflow", "DuckDB", "Python"})


def test_a_guide_following_summary_passes() -> None:
    assert problems("Software engineer building data pipelines and backend services. His "
                    "recent work pairs production Python with careful testing.") == []


@pytest.mark.parametrize(("text", "expected"), [
    ("One. Two. Three.", "3 sentences"),
    ("word " * 60, "words"),
    ("Engineer who ingested 140K+ records.", "repeats numbers"),
    ("Engineer backed by a DeepLearning.AI certificate.", "certifications"),
    ("Engineer who trained models during an internship at Orange Digital Center.", "internship"),
    ("Engineer who works with dbt, Airflow, DuckDB and Python.", "lists tools"),
])
def test_summary_rules(text: str, expected: str) -> None:
    assert any(expected in p for p in problems(text))


@pytest.mark.parametrize("text", [
    "3 years of software engineering experience spans Flutter and Spring Boot. It works well.",
    "Over 3 years of experience in backend services. Projects include a lakehouse.",
    "Built a resume parser on a local model. Projects include a lakehouse.",
])
def test_a_summary_without_a_subject_is_a_hard_problem(text: str) -> None:
    hard = [p for p in problems(text) if isinstance(p, cv_rules.HardProblem)]
    assert hard and "has no subject" in hard[0]


def test_a_summary_with_a_subject_has_no_hard_problem() -> None:
    assert not [p for p in problems("Software engineer with 3 years of experience in backend "
                                    "and mobile. Projects include a lakehouse.")
                if isinstance(p, cv_rules.HardProblem)]


def v5(text: str, cited: list[str] | None = None, openings: list[str] | None = None):  # noqa: ANN201
    return cv_rules.summary_problems(
        text, rules=RULES, bullet_texts=[], certifications=[], internships=[], tools=set(),
        banned_phrases=cv_rules.DEFAULT_CV_BANNED, cited_texts=cited, other_openings=openings)


@pytest.mark.parametrize(("text", "expected"), [
    ("Engineer with hands-on experience in data. It ships.", "banned phrase “hands-on experience”"),
    ("Engineer building pipelines. I love data.", "first person"),
    ("Engineer building pipelines. Brings experience in data.", "no subject"),
    ("Engineer building pipelines. Built a resume parser on Mistral.", "no subject"),
    ("Engineer building pipelines. At Nexaminds, built a resume parser.", "no subject"),
])
def test_v5_summary_rules(text: str, expected: str) -> None:
    assert any(expected in p for p in v5(text))


def test_summary_must_name_something_concrete_from_the_cited_items() -> None:
    cited = ["FPL Batch Data Lakehouse", "Built an end-to-end local lakehouse ingesting Premier "
             "League data into LocalStack S3"]
    vague = "Software engineer building data systems. The work spans many domains and teams."
    concrete = ("Software engineer building data pipelines. Recent work includes a local "
                "lakehouse for Premier League data.")
    assert any("concrete" in p for p in v5(vague, cited))
    assert not any("concrete" in p for p in v5(concrete, cited))


def test_tools_inside_a_description_are_not_a_tool_list() -> None:
    tools = {"dbt", "Airflow", "Mistral", "LLM", "Python", "SQL"}
    assert cv_rules.tool_list("Recent work includes a dbt/Airflow lakehouse for football data "
                              "and a resume parser on a local Mistral LLM.", tools) == []
    assert cv_rules.tool_list("Skilled in Python, SQL, dbt and Airflow.", tools)


def test_data_ai_summaries_may_frame_a_move() -> None:
    text = ("Software engineer with 3 years of experience in mobile and backend development, "
            "now focused on data engineering. Projects include a lakehouse.")
    got = cv_rules.summary_problems(text, rules=RULES, bullet_texts=[], certifications=[],
                                    internships=[], tools=set())
    assert not any("career change" in p for p in got)
    moving = "Software engineer moving into data engineering. It works."
    assert not any("career change" in p for p in cv_rules.summary_problems(
        moving, rules=RULES, bullet_texts=[], certifications=[], internships=[], tools=set()))


def test_summary_openings_must_vary_between_cvs() -> None:
    text = "Software engineer transitioning into data engineering. It works."
    assert any("opens like another CV" in p
               for p in v5(text, openings=[cv_rules.opening(text)]))
    assert not any("opens like" in p for p in v5(text, openings=["something else entirely"]))


class SummaryScript:
    model = "t"

    def __init__(self, text: str):
        self.text, self.feedback = text, []

    def generate_summary(self, request: CVRequest, feedback: str) -> SummaryDraft:
        self.feedback.append(feedback)
        s = [SummarySentence(text=self.text, citations=[1])]
        return SummaryDraft(summary_sentences=s, summary_short_sentences=s)


def test_a_summary_breaking_the_guide_is_regenerated_once(monkeypatch) -> None:  # noqa: ANN001
    pool = make_pool()
    long = ("Software Engineer with Reality Sports fact 0 and Software Engineer fact 1 and "
            "Software Engineer fact 2. Software Engineer fact 3. Software Engineer fact 4.")
    plan = make_plan(summary_sentences=[SummarySentence(text=long, citations=[1])],
                     summary_short_sentences=[SummarySentence(text="Software Engineer fact 0.",
                                                              citations=[1])])
    monkeypatch.setattr(cv_service, "ground_sentences",
                        lambda sentences, pool, allowed, *a: (list(sentences), []))
    gen = SummaryScript("Software Engineer fact 0.")
    out, issues, report = cv_service.ground_summary(plan, pool, CVRequest(job={}, pool={}), gen,
                                                    RULES)
    assert report["attempts"] == 2 and "sentences" in gen.feedback[0]
    assert out.summary == "Software Engineer fact 0." and not issues


def test_a_subjectless_summary_left_after_the_retry_is_a_warning(monkeypatch) -> None:  # noqa: ANN001
    bad = "3 years of software engineering experience spans Reality Sports fact 0."
    plan = make_plan(summary_sentences=[SummarySentence(text=bad, citations=[1])],
                     summary_short_sentences=[SummarySentence(text=bad, citations=[1])])
    monkeypatch.setattr(cv_service, "ground_sentences",
                        lambda sentences, pool, allowed, *a: (list(sentences), []))
    _out, issues, _report = cv_service.ground_summary(plan, make_pool(), CVRequest(job={}, pool={}),
                                                      SummaryScript(bad), RULES)
    assert not [v for v in issues if v["severity"] == "error"]  # summary checks never block
    rule = next(v for v in issues if v["type"] == "summary_rule")
    assert rule["severity"] == "warning" and "no subject" in rule["message"] and rule["rule"]


# --------------------------------------------------------------------- model request


def test_request_carries_guide_exemplar_and_layout() -> None:
    style = cv_rules.style_exemplar()
    assert style["summary"] and len(style["summary"].split()) < 50 and style["bullets"]
    assert "\\" not in style["summary"] and "\\" not in style["bullets"][0]
    hints = cv_service.layout_hints(make_pool(), RULES)
    assert hints["roles"]["4"] == "internship: 1-2 bullets"
    assert "at most 3 projects" in hints["projects"]
    from app.providers.claude_cv import user_message

    msg = user_message(CVRequest(job={}, pool={}, guide="GUIDE TEXT", style=style, layout=hints))
    assert "WRITING GUIDE" in msg and "STYLE EXEMPLAR" in msg and "LAYOUT" in msg


def test_cv_settings_structure_is_validated(client) -> None:  # noqa: ANN001
    cv = client.get("/api/settings").json()["values"]["cv"]
    bad = client.put("/api/settings/cv",
                     json={"value": {**cv, "structure": {"internship": [3, 1]}}})
    assert bad.status_code == 422
    bad = client.put("/api/settings/cv", json={"value": {**cv, "skill_merges": ["nonsense"]}})
    assert bad.status_code == 422
    ok = client.put("/api/settings/cv", json={"value": {**cv, "structure": {"internship": [1, 1]},
                                                         "writing_guide": "Be brief."}})
    assert ok.status_code == 200


def test_regenerating_the_summary_keeps_bullets_layout_and_status(seeded: None, monkeypatch,
                                                                  tmp_path) -> None:  # noqa: ANN001
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Application, AppSetting, CVVersion
    from app.models.enums import CVStatus
    from app.providers.mock import MockCVGenerator

    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=60, calls=[]))
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
        row.value = {**row.value, "full_name": "Ada"}
        s.add(row)
        s.commit()
        app_id = s.exec(select(Application.id)).first()
    v = cv_service.generate(engine, app_id, MockCVGenerator())
    before = (v.content["roles"], v.content["projects"], v.plan["fit"]["counts"], v.version)
    after = cv_service.regenerate_summary(engine, v.id, MockCVGenerator())
    assert (after.content["roles"], after.content["projects"], after.plan["fit"]["counts"],
            after.version) == before
    assert after.status == CVStatus.draft and after.plan["summary_history"]
    with Session(engine) as s:
        s.get(CVVersion, v.id).status = CVStatus.approved
        s.commit()
    with pytest.raises(cv_service.CVError, match="draft"):
        cv_service.regenerate_summary(engine, v.id, MockCVGenerator())
    monkeypatch.setattr(cv_service, "compile_tex", fake_compiler(capacity=60, calls=[]))
    copy = cv_service.revise_summary(engine, v.id, MockCVGenerator())  # approved → a new draft
    assert copy.status == CVStatus.draft and copy.version == v.version + 1
    assert (copy.content["roles"], copy.content["projects"]) == before[:2]
    assert copy.plan["revised_from"]["id"] == v.id and copy.plan["kept_document"]
    assert copy.content["summary"] == copy.plan["plan"]["summary"]
    with Session(engine) as s:
        assert s.get(CVVersion, v.id).status == CVStatus.approved  # untouched until you approve
    with pytest.raises(cv_service.CVError, match="already a draft"):
        cv_service.revise_summary(engine, copy.id, MockCVGenerator())


def test_data_ai_summaries_never_state_track_years_under_two() -> None:
    facts = [{"label": "Data/AI experience (Settings)", "years": 1, "kind": "track"},
             {"label": "Mobile experience (Settings)", "years": 3, "kind": "track"},
             {"label": "professional experience", "years": 3, "kind": "total"}]
    assert [f["years"] for f in cv_service.summary_years(facts, "Data/AI")] == [3, 3]
    assert len(cv_service.summary_years(facts, "Mobile")) == 3  # other tracks unchanged
    from app.services.cv_claims import bad_years

    allowed = {int(f["years"]) for f in cv_service.summary_years(facts, "Data/AI")}
    assert bad_years("Engineer with 1+ year of AI work", allowed) == ["1+ year"]
    assert bad_years("Engineer with 3+ years of experience", allowed) == []


def test_transition_phrases_are_not_banned_even_if_a_saved_list_has_them() -> None:
    for phrase in ("aspiring", "moving into", "moving from", "transitioning into",
                   "career change"):
        assert phrase not in cv_rules.DEFAULT_CV_BANNED
    saved = {"banned_phrases": ["passionate", "Moving into", "aspiring", "leveraging"]}
    assert cv_rules.banned(saved) == ["passionate", "leveraging"]
    assert not any("banned phrase" in p for p in v5("Engineer moving into data. It works."))


def test_a_layout_from_an_older_version_is_clamped_to_the_allowances(monkeypatch,
                                                                     tmp_path) -> None:  # noqa: ANN001
    """EY v2 was copied from v1 (older rules: Mobile 4, internship 3, a 1-bullet project)."""
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=500, calls=[]))
    plan = make_plan()
    lay = layout(plan, make_pool(), RULES, today=TODAY)
    old = cv_build.FitState(counts={"role:1": 4, "role:2": 3, "role:3": 4, "role:4": 3,
                                    "role:5": 3, "project:6": 3, "project:7": 1, "project:9": 3})
    result = fit_to_page(plan, make_pool(), CVProfile(full_name="Ada"), load_template("default"),
                         tmp_path, state=old, lay=lay)
    c = result.state.counts
    assert c["role:3"] <= 4 and c["role:4"] <= 2 and c["role:5"] <= 1
    assert c["project:7"] in (0, 2, 3, 4) and c["project:7"] != 1
    assert sum(1 for k, v in c.items() if k.startswith("project:") and v) <= 3
    for key, count in c.items():
        assert count <= lay.bounds[key][1], key


def test_pdf_responses_are_never_cached(client, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import CVVersion

    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4 current")
    with Session(engine) as s:
        v = s.exec(select(CVVersion)).first()
        v.pdf_path = str(pdf)
        s.add(v)
        s.commit()
        cv_id = v.id
    r = client.get(f"/api/cv/{cv_id}/pdf", params={"download": True})
    assert r.status_code == 200 and "no-store" in r.headers["cache-control"]


def test_repeating_software_engineer_with_the_full_statement_is_flagged() -> None:
    statement = "3 years of software engineering experience"
    got = cv_rules.summary_problems(f"Software engineer with {statement}. It works.",
                                    rules=RULES, bullet_texts=[], certifications=[],
                                    internships=[], tools=set(), years_statement=statement)
    assert any("instead of repeating" in p for p in got)
    fine = cv_rules.summary_problems(f"Mobile engineer with {statement}. It works.", rules=RULES,
                                     bullet_texts=[], certifications=[], internships=[],
                                     tools=set(), years_statement=statement)
    assert not any("repeating" in p for p in fine)
