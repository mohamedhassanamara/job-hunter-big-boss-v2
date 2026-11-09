"""A job CV prints a flat, listing-ordered skills line; no listing keeps the grouped list."""
import shutil
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Job
from app.providers.base import CVPlan, PlanSkillGroup
from app.services import cv_build, cv_check, cv_render, cv_rules, cv_service
from app.services.cv_pool import cv_profile, load_pool
from app.services.cv_render import CVDocument, CVSkillGroup, load_template, render_tex

LISTING = ("We are hiring a data engineer. You have strong experience with Python and SQL, "
           "build pipelines in Airflow, and know Azure and Databricks. Experience with Kubernetes "
           "is a plus. You work in a small team, own your delivery, and talk to stakeholders. ")


def tex(doc: CVDocument, name: str = "default") -> str:
    return render_tex(doc, cv_profile(pool_stub()), load_template(name))


def pool_stub():  # noqa: ANN201
    from app.services.cv_pool import Pool

    return Pool(items={}, profile={"full_name": "Ada Lovelace", "email": "a@example.com"})


# ------------------------------------------------------------------------------------ render


def test_a_flat_list_is_one_ungrouped_line() -> None:
    out = tex(CVDocument(skills_flat=["Python", "SQL", "Airflow"]))
    assert r"\section{Skills}" in out
    assert r"\mbox{Python}, \mbox{SQL}, \mbox{Airflow}" in out
    body = out.split(r"\section{Skills}")[1].split(r"\end{itemize}")[0]
    assert r"\textbf" not in body and "\\\\" not in body  # no category, no line break


def test_the_grouped_list_still_renders_as_before() -> None:
    doc = CVDocument(skills=[CVSkillGroup(category="Languages", items=["Python", "SQL"]),
                             CVSkillGroup(category="Cloud", items=["AWS"])])
    body = tex(doc).split(r"\section{Skills}")[1].split(r"\end{itemize}")[0]
    assert r"\textbf{Languages}{: Python, SQL}" in body and r"\textbf{Cloud}{: AWS}" in body


def test_flat_skills_are_escaped_like_any_text() -> None:
    assert r"R\&D" in tex(CVDocument(skills_flat=["R&D tooling", "C#"]))


def test_a_template_without_flat_support_prints_the_grouped_skills(tmp_path: Path) -> None:
    src = load_template("default")
    path = tmp_path / "old"
    shutil.copytree(src.path, path)
    text = (path / "cv.tex.j2").read_text().replace("skills_flat", "no_flat_here")
    (path / "cv.tex.j2").write_text(text)
    old = cv_render.CVTemplate(name="old", path=path, config=src.config, builtin=False)
    doc = CVDocument(skills=[CVSkillGroup(category="Languages", items=["Python"])],
                     skills_flat=["Python", "SQL"])
    ctx = cv_render.build_context(doc, cv_profile(pool_stub()), old)
    assert ctx["skills"] == [{"category": "Languages", "items": ["Python"]}]  # as before
    assert ctx["skills_flat"] == []
    new = cv_render.build_context(doc, cv_profile(pool_stub()), src)
    assert new["skills"] == [] and new["skills_flat"] == ["Python", "SQL"]


def test_a_section_with_only_a_flat_list_is_not_empty() -> None:
    assert r"\section{Skills}" in tex(CVDocument(skills_flat=["Python"]))
    assert r"\section{Skills}" not in tex(CVDocument())


# -------------------------------------------------------------------------- build_document


def make_plan(mode: str = "grouped", **kw) -> CVPlan:  # noqa: ANN003
    return CVPlan(summary="S", summary_short="S", roles=[], education_ids=[], skills_mode=mode,
                  **kw)


def test_build_document_prints_the_flat_list_in_order_and_no_groups(seeded: None) -> None:
    with Session(engine) as s:
        pool = load_pool(s)
    group = pool.of("skill")[0]
    plan = make_plan("flat", skills=[PlanSkillGroup(item_id=group.id, items=group.tags[:2])],
                     skill_list=[{"skill": "Zed", "tier": 3, "item_ids": [], "reason": "jd"},
                                 {"skill": "Alpha", "tier": 1, "item_ids": [1], "reason": "jd"}])
    doc = cv_build.build_document(plan, pool, cv_build.FitState())
    assert doc.skills_flat == ["Zed", "Alpha"]  # tiers are not printed; no cut: all of them
    assert doc.skills  # the grouped skills stay for a template without a flat branch
    grouped = cv_build.build_document(plan.model_copy(update={"skills_mode": "grouped"}), pool,
                                      cv_build.FitState())
    assert grouped.skills and grouped.skills_flat == []


# ------------------------------------------------------------------------- with_job_skills


def job(description: str, track: str = "") -> Job:
    return Job(title="Data Engineer", company_id=1, location="Berlin", description=description,
               matched_track=track)


def test_a_job_with_a_listing_gets_a_flat_list_from_your_evidence(seeded: None) -> None:
    with Session(engine) as s:
        pool = load_pool(s)
        out = cv_service.with_job_skills(s, make_plan(), pool, job(LISTING), "Acme")
        groups = {t for g in pool.of("skill") for t in g.tags}
    # every candidate up to the ceiling (30; the seeded pool has 26 skills); the page prints the
    # target (14) before the line fit
    assert out.skills_mode == "flat" and len(out.skill_list) == 26 and out.skills_target == 14
    jd = [x["skill"] for x in out.skill_list if x["reason"] == "jd"]
    assert set(jd) == {"python", "sql", "airflow", "kubernetes"}
    assert [x["reason"] for x in out.skill_list[:4]] == ["jd"] * 4  # matches come first
    assert all(x["tier"] == 1 for x in out.skill_list)
    assert {x["skill"] for x in out.skill_list} <= groups  # the fill is only your skill groups
    # the listing names Azure and Databricks; the seeded pool has neither: never shown, reported
    assert set(out.skill_gaps) == {"Azure", "Databricks"}
    assert not {"Azure", "Databricks"} & {x["skill"] for x in out.skill_list}


def test_no_listing_text_keeps_the_grouped_list(seeded: None) -> None:
    with Session(engine) as s:
        pool = load_pool(s)
        plan = make_plan()
        assert cv_service.with_job_skills(s, plan, pool, None) is plan
        assert cv_service.with_job_skills(s, plan, pool, job("Data engineer, Berlin.")) is plan
        assert cv_service.with_job_skills(s, plan, pool, job("")) is plan


def test_the_cap_target_and_minimum_come_from_settings(seeded: None) -> None:
    from app.models import AppSetting

    def save(structure: dict, keep: dict | None = None) -> None:
        with Session(engine) as s:
            row = s.exec(select(AppSetting).where(AppSetting.key == "cv")).first()
            if row is None:
                row = AppSetting(key="cv", value={})
            row.value = {**row.value, "structure": structure,
                         **({"skill_keep": keep} if keep is not None else {})}
            s.add(row)
            s.commit()

    def run(description: str = LISTING, track: str = "") -> CVPlan:
        with Session(engine) as s:
            return cv_service.with_job_skills(s, make_plan(), load_pool(s),
                                              job(description, track))

    full = [x["skill"] for x in run().skill_list]
    assert len(full) == 26 and run().skills_target == 14
    save({"skills_target": 6, "skills_min": 6})
    assert run().skills_target == 6  # what prints before the line fit
    assert [x["skill"] for x in run().skill_list] == full  # the candidates are unchanged
    save({"skills_target": 6})  # a target under the minimum is raised to it
    assert run().skills_target == 10
    save({"skills_max": 2, "skills_min": 0, "skills_target": 0})
    assert [x["skill"] for x in run().skill_list] == full[:2]  # the most relevant two
    # one listing skill and no pins: the fill still reaches the target, from your groups only
    save({"skills_max": 18, "skills_min": 10, "skills_target": 14})
    short = run(("Data engineer wanted. " * 12) + "You know Python.", track="no-pins")
    assert short.skill_list[0]["skill"] == "python" and len(short.skill_list) == 18
    assert short.skills_target == 14
    # the order is: the listing's matches, co-occurring skills, pins, the rest
    save({}, {"data-ai": {"Cloud": ["gcp"]}})
    pinned = run(("Data engineer wanted. " * 12) + "You know Python.", track="data-ai")
    reasons = [x["reason"] for x in pinned.skill_list]
    assert reasons == sorted(reasons, key=["jd", "cooc", "pin", "fill"].index)
    assert {x["skill"]: x["reason"] for x in pinned.skill_list}["gcp"] == "pin"
    assert reasons[0] == "jd" and "cooc" in reasons and "fill" in reasons
    # a listing that names none of your skills: nothing to rank by, the grouped list is kept
    none = run("Marketing manager wanted for brand campaigns and events. " * 6)
    assert none.skills_mode == "grouped" and none.skill_list == []
    # under the minimum even after the fill: the grouped list is kept
    save({"skills_min": 30})
    assert run().skills_mode == "grouped" and run().skill_list == []


# ------------------------------------------------------------- summary checks and gaps


def test_the_summary_may_not_name_a_listing_gap(seeded: None) -> None:
    with Session(engine) as s:
        pool = load_pool(s)
    plan = make_plan(skill_gaps=["Databricks"])
    problems = cv_check.summary_support("Built Databricks pipelines.", plan, pool, [])
    assert any("Databricks" in p and "transferable" in p for p in problems)
    assert not any("Databricks" in p for p in
                   cv_check.summary_support("Built data pipelines.", plan, pool, []))


def test_only_tier_one_skills_count_as_things_you_did() -> None:
    plan = make_plan("flat", skill_list=[
        {"skill": "Python", "tier": 1, "item_ids": [], "reason": "jd"},
        {"skill": "Azure", "tier": 2, "item_ids": [], "reason": "jd"},
        {"skill": "Spark", "tier": 3, "item_ids": [], "reason": "jd"}])
    assert cv_check.shown_skills(plan) == ["Python"]
    grouped = make_plan(skills=[PlanSkillGroup(item_id=1, items=["Go", "SQL"])])
    assert cv_check.shown_skills(grouped) == ["Go", "SQL"]


# ------------------------------------------------------------------------------ end to end


def new_tex_skills(client, app_id: int) -> str:  # noqa: ANN001
    version = client.get(f"/api/applications/{app_id}/cv").json()["versions"][0]
    with Session(engine) as s:
        from app.models import CVVersion

        tex = s.get(CVVersion, version["id"]).tex
    return tex.split(r"\section{Skills}")[1].split(r"\end{itemize}")[0]


@pytest.mark.parametrize("title", ["LLM Engineer"])
def test_generating_a_job_cv_prints_a_flat_one_page_list(client, title: str,
                                                          monkeypatch) -> None:  # noqa: ANN001
    # the 2-3 line rule needs room: with the default max of 18, short skills can't fill two lines
    monkeypatch.setitem(cv_rules.DEFAULT_STRUCTURE, "skills_max", 30)
    items = client.get("/api/jobs?stage=all").json()["items"]
    job_row = next(i for i in items if i["title"] == title)
    app_id = job_row["application"]["id"]
    new = client.post(f"/api/applications/{app_id}/cv/generate", json={}).json()
    assert new["page_count"] == 1
    content = new["content"]
    plan = client.get(f"/api/applications/{app_id}/cv").json()["versions"][0]
    assert plan["id"] == new["id"]
    with Session(engine) as s:
        from app.models import CVVersion

        row = s.get(CVVersion, new["id"])
        report = next(h["skill_fit"] for h in row.plan["history"] if "skill_fit" in h)
    if content["skills_flat"]:  # a length met the rule: 2-3 lines, the last one 75% full
        assert not report[-1]["grouped"]
        lines, last = report[-1]["measured"]
        assert 2 <= lines <= 3 and last >= 0.74
        assert r"\mbox{" in new_tex_skills(client, app_id)
    else:  # the seeded skills are very short: no length fits two lines, the groups print
        assert report[-1]["grouped"] and content["skills"]
        assert r"\textbf" in new_tex_skills(client, app_id)
    # every printed skill is one of your own spellings
    with Session(engine) as s:
        own = {t for g in load_pool(s).of("skill") for t in g.tags}
    assert set(content["skills_flat"]) <= own


def test_validation_warns_about_a_template_without_the_flat_branch() -> None:
    from app.services import cv_templates
    from app.services.cv_render import ROOT

    default = (ROOT / "templates/default/cv.tex.j2").read_text()
    assert cv_templates.NO_FLAT_SKILLS_MESSAGE not in cv_templates.template_warnings(default)
    old = default.replace("skills_flat", "no_flat_here")
    assert cv_templates.NO_FLAT_SKILLS_MESSAGE in cv_templates.template_warnings(old)
    # a template with no skills section has nothing to warn about
    assert cv_templates.template_warnings(r"\section{Summary}") == []
