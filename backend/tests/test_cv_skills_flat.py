"""A job CV prints a flat, listing-ordered skills line; no listing keeps the grouped list."""
import shutil
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Job
from app.providers.base import CVPlan, PlanSkillGroup
from app.services import cv_build, cv_check, cv_render, cv_service
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
    assert r"\section{Technical Skills}" in out
    assert "Python, SQL, Airflow" in out
    body = out.split(r"\section{Technical Skills}")[1].split(r"\end{itemize}")[0]
    assert r"\textbf" not in body and "\\\\" not in body  # no category, no line break


def test_the_grouped_list_still_renders_as_before() -> None:
    doc = CVDocument(skills=[CVSkillGroup(category="Languages", items=["Python", "SQL"]),
                             CVSkillGroup(category="Cloud", items=["AWS"])])
    body = tex(doc).split(r"\section{Technical Skills}")[1].split(r"\end{itemize}")[0]
    assert r"\textbf{Languages}{: Python, SQL}" in body and r"\textbf{Cloud}{: AWS}" in body


def test_flat_skills_are_escaped_like_any_text() -> None:
    assert r"R\&D" in tex(CVDocument(skills_flat=["R&D tooling", "C#"]))


def test_a_template_without_flat_support_gets_one_group_instead(tmp_path: Path) -> None:
    src = load_template("default")
    path = tmp_path / "old"
    shutil.copytree(src.path, path)
    text = (path / "cv.tex.j2").read_text().replace("skills_flat", "no_flat_here")
    (path / "cv.tex.j2").write_text(text)
    old = cv_render.CVTemplate(name="old", path=path, config=src.config, builtin=False)
    ctx = cv_render.build_context(CVDocument(skills_flat=["Python", "SQL"]), cv_profile(
        pool_stub()), old)
    assert ctx["skills"] == [{"category": "Skills", "items": ["Python", "SQL"]}]
    assert ctx["skills_flat"] == []


def test_a_section_with_only_a_flat_list_is_not_empty() -> None:
    assert r"\section{Technical Skills}" in tex(CVDocument(skills_flat=["Python"]))
    assert r"\section{Technical Skills}" not in tex(CVDocument())


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
    assert doc.skills == [] and doc.skills_flat == ["Zed", "Alpha"]  # tiers are not printed
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
    assert out.skills_mode == "flat" and len(out.skill_list) == 14  # the default target
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
    assert len(full) == 14
    save({"skills_target": 6, "skills_min": 6})
    assert [x["skill"] for x in run().skill_list] == full[:6]  # the fill stops at the target
    save({"skills_target": 6})  # a target under the minimum is raised to it
    assert len(run().skill_list) == 10
    save({"skills_max": 2, "skills_min": 0, "skills_target": 0})
    assert [x["skill"] for x in run().skill_list] == full[:2]  # the most relevant two
    # one listing skill and no pins: the fill still reaches the target, from your groups only
    save({"skills_max": 18, "skills_min": 10, "skills_target": 14})
    short = run(("Data engineer wanted. " * 12) + "You know Python.", track="no-pins")
    assert short.skill_list[0]["skill"] == "python" and len(short.skill_list) == 14
    # a pinned skill goes ahead of the same-group fill
    save({}, {"data-ai": {"Cloud": ["terraform"]}})
    pinned = run(("Data engineer wanted. " * 12) + "You know Python.", track="data-ai")
    assert [x["reason"] for x in pinned.skill_list[:2]] == ["jd", "pin"]
    assert pinned.skill_list[1]["skill"] == "terraform"
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


@pytest.mark.parametrize("title", ["LLM Engineer"])
def test_generating_a_job_cv_prints_a_flat_one_page_list(client, title: str) -> None:
    items = client.get("/api/jobs?stage=all").json()["items"]
    job_row = next(i for i in items if i["title"] == title)
    app_id = job_row["application"]["id"]
    new = client.post(f"/api/applications/{app_id}/cv/generate", json={}).json()
    assert new["page_count"] == 1
    content = new["content"]
    plan = client.get(f"/api/applications/{app_id}/cv").json()["versions"][0]
    assert plan["id"] == new["id"]
    assert content["skills_flat"] and content["skills"] == []
    # every printed skill is one of your own spellings
    with Session(engine) as s:
        pool = load_pool(s)
        own = {t for i in pool.items.values() for t in i.tags}
    assert set(content["skills_flat"]) <= own
