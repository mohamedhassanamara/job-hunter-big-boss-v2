"""The flat skills block: 2-3 lines, the last one at least 75% full, no skill split across lines.
Unit tests on synthetic metrics, and real LaTeX/PDF runs in the default template and a Source
Sans copy of it. No model calls."""
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pymupdf
import pytest
import yaml
from sqlmodel import Session

from app.db import engine
from app.models import ExperienceItem, Job
from app.services import cv_service
from app.services import skill_fit as sf
from app.services.cv_build import FitState, fit_to_page
from app.services.cv_pool import cv_profile, load_pool
from app.services.cv_render import CVTemplate, load_template
from tests.test_cv import plan_for

LISTINGS = Path(__file__).parent / "fixtures" / "sources" / "arbeitnow.json"


def metrics(width: float = 540.0, ragged: bool = True, per_skill: float = 100.0,
            skills: list[str] | None = None) -> sf.Metrics:
    return sf.Metrics(linewidth=width, space=4.0, stretch=2.0, shrink=1.0, comma=3.0,
                      widths={s: per_skill for s in skills or []}, rs_fil=ragged)


# ----------------------------------------------------------------------- line breaking


def test_ragged_right_fills_lines_and_leaves_the_last_one_short() -> None:
    m = metrics()
    lines = sf.break_lines([100.0] * 12, m)  # 5 skills fit (5*103+4*4=531): 5 + 5 + 2
    assert [(ln.first, ln.last) for ln in lines] == [(0, 4), (5, 9), (10, 11)]
    assert all(ln.natural <= m.linewidth for ln in lines)
    assert lines[-1].natural == pytest.approx(100 * 2 + 3 + 4)  # the last skill has no comma


def test_a_skill_wider_than_the_line_cannot_be_set() -> None:
    assert sf.break_lines([600.0], metrics()) is None


def test_justified_text_rejects_lines_it_cannot_stretch() -> None:
    m = metrics(ragged=False)
    # 5 x 100 + commas and spaces = 531: 9pt to stretch over 4 gaps (stretch 2.5 each): feasible
    lines = sf.break_lines([100.0] * 10, m)
    assert lines is not None and len(lines) == 2
    # a width no choice of breaks can fill (single skill per line, no glue to stretch)
    assert sf.break_lines([300.0, 300.0], metrics(width=500.0, ragged=False)) is None


def test_the_rule() -> None:
    m = metrics()
    assert sf.satisfies(sf.break_lines([100.0] * 14, m), m.linewidth)  # 5 + 5 + 4: last 80%
    assert not sf.satisfies(sf.break_lines([100.0] * 12, m), m.linewidth)  # last line 38%
    assert not sf.satisfies(sf.break_lines([100.0] * 4, m), m.linewidth)  # one line
    assert not sf.satisfies(sf.break_lines([100.0] * 18, m), m.linewidth)  # four lines


# -------------------------------------------------------------------------------- choice


def names(n: int) -> list[str]:
    return [f"S{i}" for i in range(n)]


def test_the_target_is_tried_first_then_one_more_or_fewer() -> None:
    assert sf.candidates(18, 14, 1)[:5] == [4, 3, 5, 2, 6]  # cut counts around 18 - 14
    assert sf.candidates(18, 14, 15) == [3, 2, 1, 0]  # a floor of 15 keeps at least 15


def test_it_cuts_from_the_tail_so_listing_matches_stay() -> None:
    skills = names(18)  # S0-S3 are the listing's matches, the rest filler; cut order = the tail
    m = metrics(skills=skills)
    pick = sf.choose(skills, list(range(17, -1, -1)), 12, m)
    # 12 would be 5+5+2 (last line 38%): 14 gives 5+5+4
    assert pick is not None and pick.skills == skills[:14] and pick.lines == 3
    assert pick.last_fill >= 0.75
    assert set(skills[:4]) <= set(pick.skills)


def test_a_custom_cut_order_decides_what_goes_first() -> None:
    skills = names(18)
    m = metrics(skills=skills)
    order = [0, 1, 2, 3, *range(17, 3, -1)]  # S0-S3 first (like soft skills, then filler)
    pick = sf.choose(skills, order, 14, m)
    assert pick is not None and "S0" not in pick.skills and "S17" in pick.skills


def test_matches_are_dropped_only_when_they_alone_are_too_long() -> None:
    skills = names(20)  # 20 listing matches, no filler: 15 fit in 3 lines
    m = metrics(skills=skills)
    pick = sf.choose(skills, list(range(19, -1, -1)), 20, m)
    assert pick is not None and pick.skills == skills[:15]  # the least relevant five go


def test_no_length_that_satisfies_the_rule_is_none() -> None:
    skills = names(6)  # six skills: one line, never two
    assert sf.choose(skills, list(range(5, -1, -1)), 6, metrics(skills=skills)) is None
    wide = {"A": 700.0, "B": 700.0}  # wider than a line: unusable
    assert sf.choose(["A", "B"], [1, 0], 2, sf.Metrics(540.0, 4, 2, 1, 3, wide, 0, True)) is None


def test_the_floor_is_respected() -> None:
    skills = names(18)
    m = metrics(skills=skills)
    pick = sf.choose(skills, list(range(17, -1, -1)), 14, m, floor=15)
    assert pick is not None and len(pick.skills) == 15  # 5+5+5


def test_a_rejected_length_is_skipped() -> None:
    skills = names(18)
    m = metrics(skills=skills)
    first = sf.choose(skills, list(range(17, -1, -1)), 14, m)
    again = sf.choose(skills, list(range(17, -1, -1)), 14, m, rejected={first.cut})
    assert again is not None and again.cut != first.cut


# ----------------------------------------------------------------------------- the cache


def template_copy(tmp_path: Path, extra: str = "") -> CVTemplate:
    src = load_template("default")
    path = tmp_path / f"t{len(extra)}"
    shutil.copytree(src.path, path)
    (path / "cv.tex.j2").write_text((src.path / "cv.tex.j2").read_text() + extra)
    return CVTemplate(name="t", path=path, config=src.config, builtin=False)


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
def test_metrics_are_measured_once_and_again_when_the_template_changes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    real = sf._run_metrics
    monkeypatch.setattr(sf, "_run_metrics", lambda t, s: calls.append(list(s)) or real(t, s))
    cache = tmp_path / "cache"
    t1 = template_copy(tmp_path)
    m1 = sf.metrics_for(t1, ["Python", "SQL"], cache)
    sf.metrics_for(t1, ["Python", "SQL"], cache)
    assert calls == [["Python", "SQL"]]  # the second call is a cache hit
    sf.metrics_for(t1, ["Python", "Rust"], cache)
    assert calls[-1] == ["Rust"]  # only the skill that is new is measured
    t2 = template_copy(tmp_path, "\n% edited\n")
    assert sf.template_key(t2) != sf.template_key(t1)
    m2 = sf.metrics_for(t2, ["Python", "SQL"], cache)
    assert calls[-1] == ["Python", "SQL"]  # a changed template is measured again
    assert m1 and m2 and m1.widths["Python"] == pytest.approx(m2.widths["Python"])


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
def test_measured_metrics_are_plausible_and_the_block_is_ragged() -> None:
    t = load_template("default")
    m = sf.metrics_for(t, ["Python", "GitHub Actions (CI/CD)"], Path("/nonexistent/cache-dir"))
    assert 400 < m.linewidth < 700 and m.rs_fil  # \raggedright: infinite stretch on the right
    assert m.widths["Python"] < m.widths["GitHub Actions (CI/CD)"] < m.linewidth


# ----------------------------------------------------------------------- real PDF runs

GROUPS = {
    "Languages": ["Python", "SQL", "Java", "Go", "Rust", "TypeScript", "Bash", "Kotlin"],
    "Data": ["Apache Spark", "Apache Airflow", "dbt", "Kafka", "PostgreSQL", "Snowflake",
             "DuckDB", "Power BI", "Data Modeling", "ETL Pipelines"],
    "Cloud": ["AWS", "Azure", "Docker", "Kubernetes", "Terraform", "GitHub Actions (CI/CD)",
              "Linux"],
    "ML": ["PyTorch", "scikit-learn", "LLMs (Mistral 7B, Ollama)", "RAG",
           "NLP (spaCy, TF-IDF)", "MLflow"],
    "Practice": ["Unit Testing", "Code Review", "REST APIs", "GraphQL", "Clean Architecture"],
}
SCENARIOS = [9, 8, 10, 3, 7]  # real listings of the Arbeitnow fixture
HAS_SANS = bool(shutil.which("kpsewhich")) and bool(
    subprocess.run(["kpsewhich", "sourcesanspro.sty"], capture_output=True,
                   text=True).stdout.strip()) if shutil.which("kpsewhich") else False


def sans_template(tmp_path: Path) -> CVTemplate:
    """The default template in Source Sans Pro (as a user template like updated1 does it)."""
    src = load_template("default")
    path = tmp_path / "sans"
    shutil.copytree(src.path, path)
    text = (src.path / "cv.tex.j2").read_text()
    anchor = text.index("\n", text.index("\\documentclass")) + 1
    (path / "cv.tex.j2").write_text(
        text[:anchor] + "\\usepackage[T1]{fontenc}\n\\usepackage[default]{sourcesanspro}\n"
        + text[anchor:])
    (path / "cv.config.yaml").write_text(yaml.safe_dump(src.config))
    return CVTemplate(name="sans", path=path, config=src.config, builtin=False)


def listing(index: int) -> tuple[str, str]:
    job = json.loads(LISTINGS.read_text())["data"][index]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(job["description"])))
    return job["title"], text


def scenario(index: int, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """The seeded pool with a realistic skills inventory, and a job CV plan for the listing."""
    monkeypatch.setitem(cv_service.cv_rules.DEFAULT_STRUCTURE, "skills_max", 30)
    with Session(engine) as s:
        pool = load_pool(s)
        groups = [ExperienceItem(id=9000 + n, kind="skill", title=title, tags=tags, bullets=[],
                                 tracks=[], position=n)
                  for n, (title, tags) in enumerate(GROUPS.items())]
        pool.by_kind["skill"] = groups
        pool.items = {**{i: x for i, x in pool.items.items() if x.kind != "skill"},
                      **{g.id: g for g in groups}}
        title, text = listing(index)
        job = Job(title=title, company_id=1, location="Berlin", description=text)
        plan = cv_service.with_job_skills(s, plan_for(pool), pool, job, "Acme")
    return plan, pool


def measured(result, template: CVTemplate) -> tuple[int, float]:  # noqa: ANN001
    metrics_ = sf.metrics_for(template, ["Python"])
    return sf.measure_block(result.compiled.pdf_path, template, metrics_.linewidth)


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
@pytest.mark.parametrize("index", SCENARIOS)
@pytest.mark.parametrize("which", ["default", "sans"])
def test_the_printed_skills_block_meets_the_rule_on_the_real_page(
        index: int, which: str, seeded: None, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    if which == "sans" and not HAS_SANS:
        pytest.skip("Source Sans Pro is not installed")
    template = load_template("default") if which == "default" else sans_template(tmp_path)
    plan, pool = scenario(index, monkeypatch)
    assert plan.skills_mode == "flat" and len(plan.skill_list) > 18
    result = fit_to_page(plan, pool, cv_profile(pool), template, tmp_path / "out",
                         state=FitState(), lay=None)
    assert result.compiled.ok and result.compiled.pages == 1
    printed = result.document.skills_flat
    assert printed, "a length should satisfy the rule with this inventory"
    lines, last = measured(result, template)
    assert 2 <= lines <= 3 and last >= 0.74  # the real PDF, not the simulation
    report = next(h["skill_fit"] for h in result.history if "skill_fit" in h)
    assert len(report) <= 3  # the first fit plus at most two corrections
    sim = report[-1]["simulated"]
    assert sim[0] == lines and sim[1] == pytest.approx(last, abs=0.03)
    # what is cut goes in the plan's cut order (filler, then soft skills, then matches): every
    # skill that prints is later in that order than every skill that was cut
    ranked = [x["skill"] for x in plan.skill_list]
    assert_cut_in_order(plan, printed)
    assert [s for s in ranked if s in printed] == printed  # display order is kept
    # no skill is split across lines: each prints whole inside one PDF line
    with pymupdf.open(result.compiled.pdf_path) as pdf:
        rows = [" ".join("".join(sp["text"] for sp in ln["spans"]).split())
                for b in pdf[0].get_text("dict")["blocks"] for ln in b.get("lines", [])]
    for skill in printed:
        assert any(skill in row for row in rows), skill


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
def test_no_length_that_fits_prints_the_grouped_skills(
        seeded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, pool = scenario(9, monkeypatch)
    plan = plan.model_copy(update={"skill_list": plan.skill_list[:4],
                                   "skill_cut_order": [3, 2, 1, 0], "skills_target": 4})
    result = fit_to_page(plan, pool, cv_profile(pool), load_template("default"),
                         tmp_path / "out", state=FitState())
    assert result.document.skills_flat == []  # four skills never make two lines
    assert report_of(result)[-1]["grouped"]


def assert_cut_in_order(plan, printed: list[str]) -> None:  # noqa: ANN001
    position = {plan.skill_list[i]["skill"]: n for n, i in enumerate(plan.skill_cut_order)}
    cut = [position[s["skill"]] for s in plan.skill_list if s["skill"] not in printed]
    kept = [position[s] for s in printed]
    assert not cut or not kept or max(cut) < min(kept)


def report_of(result):  # noqa: ANN001, ANN201
    return next(h["skill_fit"] for h in result.history if "skill_fit" in h)


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
def test_switching_template_measures_the_skills_again(
        seeded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not HAS_SANS:
        pytest.skip("Source Sans Pro is not installed")
    plan, pool = scenario(9, monkeypatch)
    out = {}
    for which, template in (("default", load_template("default")),
                            ("sans", sans_template(tmp_path))):
        res = fit_to_page(plan.model_copy(deep=True), pool, cv_profile(pool), template,
                          tmp_path / which, state=FitState())
        out[which] = res.document.skills_flat
        assert sf.template_key(template) in {p.stem for p in sf.CACHE_DIR.glob("*.json")}
    assert out["default"] and out["sans"]  # each template got a list that fits its own font


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
@pytest.mark.parametrize("which", ["default", "sans"])
def test_the_relevance_order_still_meets_the_line_rule(
        which: str, seeded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests import test_skill_cooccurrence as co

    if which == "sans" and not HAS_SANS:
        pytest.skip("Source Sans Pro is not installed")
    monkeypatch.setitem(cv_service.cv_rules.DEFAULT_STRUCTURE, "skills_max", 30)
    template = load_template("default") if which == "default" else sans_template(tmp_path)
    with Session(engine) as s:
        pool = load_pool(s)
        job = Job(title="Developer", company_id=1, location="Berlin",
                  description=co.BACKEND_LISTING * 3)
        # the roles come from the seeded pool; the skills from the co-occurrence pool
        plan = cv_service.with_job_skills(s, plan_for(pool), co.pool(), job, "Acme")
    assert plan.skills_mode == "flat"
    assert [x["reason"] for x in plan.skill_list][:3] == ["jd", "jd", "jd"]
    result = fit_to_page(plan, pool, cv_profile(pool), template, tmp_path / "out",
                         state=FitState())
    assert result.compiled.ok and result.compiled.pages == 1
    printed = result.document.skills_flat
    assert_cut_in_order(plan, printed)
    lines, last = measured(result, template)
    assert 2 <= lines <= 3 and last >= 0.74
