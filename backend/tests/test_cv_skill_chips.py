"""CV Studio's skills chips: remove or put back skills from the ledger only, and the line rule
is re-checked on the real page. No model calls."""
import shutil

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import CVVersion, ExperienceItem
from app.services import experience_write, skill_fit
from app.services.cv_pool import load_pool
from app.services.cv_render import load_template

pytestmark = pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")

EXTRA = ["Apache Spark", "Apache Kafka", "Kubernetes", "Terraform", "PostgreSQL", "Snowflake",
         "Data Modeling", "ETL Pipelines", "Unit Testing", "Code Review", "REST APIs", "GraphQL",
         "Clean Architecture", "Domain-Driven Design", "Event Sourcing", "Observability",
         "Infrastructure as Code", "Continuous Delivery", "Feature Flags", "Load Testing",
         "Message Queues", "Caching Strategies", "API Gateways", "Service Meshes"]


def seed_pool(extra_soft: bool = False) -> None:
    with Session(engine) as s:
        experience_write.create(s, {"kind": "skill", "title": "Extra", "tags": EXTRA,
                                    "bullets": []})
        experience_write.create(s, {"kind": "skill_proof", "title": "Tiny tool",
                                    "tags": ["Proof Tool"], "bullets": []})
        experience_write.create(s, {"kind": "certification", "title": "Cert", "org": "Acme",
                                    "tags": ["Study Topic"], "bullets": []})
        if extra_soft:
            experience_write.create(s, {"kind": "volunteering", "title": "Club", "org": "Y",
                                        "bullets": ["Coordinated eight volunteers."],
                                        "soft_skills": ["Teamwork"], "tags": []})
        s.commit()


def flat_cv(client, skills: list[str] | None = None) -> int:  # noqa: ANN001
    """A generated CV whose plan is flat (the seeded skills are too short to make two lines on
    their own, so the automatic fit would print the groups)."""
    items = client.get("/api/jobs?stage=all").json()["items"]
    app_id = next(i for i in items if i["title"] == "LLM Engineer")["application"]["id"]
    cv_id = client.post(f"/api/applications/{app_id}/cv/generate", json={}).json()["id"]
    listing = skills or ["python", "sql"]
    with Session(engine) as s:
        v = s.get(CVVersion, cv_id)
        plan = {**v.plan["plan"], "skills_mode": "flat", "skills_target": len(listing),
                "skill_list": [{"skill": x, "tier": 1, "item_ids": [], "reason": "fill",
                                "kind": "technical"} for x in listing],
                "skill_cut_order": list(range(len(listing) - 1, -1, -1))}
        v.plan = {**v.plan, "plan": plan}
        s.add(v)
        s.commit()
    return cv_id


def fitting_list(n_min: int = 12) -> list[str]:
    """A list of your skills that the line rule accepts in the default template."""
    with Session(engine) as s:
        names = [e.display for e in __import__("app.services.skill_ledger", fromlist=["x"])
                 .build_ledger(load_pool(s)) if e.tier == 1]
    m = skill_fit.metrics_for(load_template("default"), names)
    pick = skill_fit.choose(names, list(range(len(names) - 1, -1, -1)), 20, m, floor=n_min)
    assert pick is not None
    return pick.skills


def chips(client, cv_id: int) -> dict:  # noqa: ANN001
    return client.get(f"/api/cv/{cv_id}/skills").json()


def set_list(client, cv_id: int, names: list[str]):  # noqa: ANN001, ANN201
    """Replace whatever prints with exactly `names` (take everything off, put these on)."""
    current = [c["skill"] for c in chips(client, cv_id)["printed"]]
    return client.patch(f"/api/cv/{cv_id}", json={"skills": {"remove": current, "add": names}})


def make_grouped(cv_id: int) -> None:
    with Session(engine) as s:
        v = s.get(CVVersion, cv_id)
        v.plan = {**v.plan, "plan": {**v.plan["plan"], "skills_mode": "grouped",
                                     "skill_list": []}}
        s.add(v)
        s.commit()


def test_a_cv_with_no_listing_match_has_no_line_to_edit(client) -> None:  # noqa: ANN001
    items = client.get("/api/jobs?stage=all").json()["items"]
    app_id = next(i for i in items if i["title"] == "LLM Engineer")["application"]["id"]
    cv_id = client.post(f"/api/applications/{app_id}/cv/generate", json={}).json()["id"]
    make_grouped(cv_id)
    out = chips(client, cv_id)
    assert out["mode"] == "grouped" and out["printed"] == [] and out["available"] == []
    assert out["fit"]["grouped"] and not out["fit"]["ok"]
    r = client.patch(f"/api/cv/{cv_id}", json={"skills": {"add": ["python"]}})
    assert r.status_code == 422 and "grouped" in r.json()["detail"]


def test_when_no_automatic_length_fits_you_can_still_build_the_line(
        client, seeded: None) -> None:  # noqa: ANN001
    cv_id = flat_cv(client)  # the groups print: the seeded skills are too short for two lines
    out = chips(client, cv_id)
    assert out["mode"] == "flat" and out["printed"] == [] and out["fit"]["grouped"]
    assert "python" in [c["skill"] for c in out["available"]]
    r = client.patch(f"/api/cv/{cv_id}", json={"skills": {"add": ["python", "sql"]}})
    assert r.status_code == 200 and r.json()["content"]["skills_flat"] == ["python", "sql"]


def test_chips_come_from_the_ledger_only(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool(extra_soft=True)
    cv_id = flat_cv(client)
    r = set_list(client, cv_id, ["python", "Apache Spark"])
    assert r.status_code == 200 and r.json()["content"]["skills_flat"] == ["python",
                                                                          "Apache Spark"]
    out = chips(client, cv_id)
    assert out["mode"] == "flat"
    assert [c["skill"] for c in out["printed"]] == ["python", "Apache Spark"]
    shown = {c["skill"]: c for c in out["available"]}
    assert "python" not in shown and "Apache Spark" not in shown  # already on the line
    assert shown["Proof Tool"]["tier"] == 2 and shown["Study Topic"]["tier"] == 3
    assert shown["Teamwork"]["kind"] == "soft" and shown["sql"]["kind"] == "technical"
    # free text is refused, in any spelling that is not yours
    for bad in ("COBOL", "Haskell", "  ", "pythons"):
        refused = client.patch(f"/api/cv/{cv_id}", json={"skills": {"add": [bad]}})
        assert refused.status_code == 422 and "not one of your skills" in refused.json()["detail"]
    assert chips(client, cv_id)["printed"] == out["printed"]  # a refused edit changes nothing


def test_a_removed_chip_can_be_put_back_and_the_order_is_yours(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool()
    cv_id = flat_cv(client)
    # "Kubernetes" is already in your pool as "kubernetes": the line prints your spelling
    set_list(client, cv_id, ["python", "sql", "Kubernetes"])
    done = client.patch(f"/api/cv/{cv_id}", json={"skills": {"remove": ["sql"]}}).json()
    assert done["content"]["skills_flat"] == ["python", "kubernetes"]
    assert "sql" in [c["skill"] for c in chips(client, cv_id)["available"]]
    back = client.patch(f"/api/cv/{cv_id}", json={"skills": {"add": ["sql"]}}).json()
    assert back["content"]["skills_flat"] == ["python", "kubernetes", "sql"]  # appended
    twice = client.patch(f"/api/cv/{cv_id}", json={"skills": {"add": ["SQL"]}}).json()
    assert twice["content"]["skills_flat"].count("sql") == 1  # never a duplicate


def test_the_last_chip_cannot_be_removed(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool()
    cv_id = flat_cv(client)
    set_list(client, cv_id, ["python"])
    r = client.patch(f"/api/cv/{cv_id}", json={"skills": {"remove": ["python"]}})
    assert r.status_code == 422 and "at least one" in r.json()["detail"]


def test_removing_a_chip_reports_the_minimum_and_the_last_line(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool()
    good = fitting_list()
    cv_id = flat_cv(client)
    set_list(client, cv_id, good)
    fit = chips(client, cv_id)["fit"]
    assert fit["ok"] and fit["manual"] and fit["problems"] == []
    assert 2 <= fit["lines"] <= 3 and fit["last_fill"] >= 0.74 and fit["count"] == len(good)
    # take chips off until the line is short: every rule that breaks is named
    for name in good[8:]:
        client.patch(f"/api/cv/{cv_id}", json={"skills": {"remove": [name]}})
    short = chips(client, cv_id)["fit"]
    assert not short["ok"] and short["count"] == 8
    assert any("under the minimum of 10" in p for p in short["problems"])
    assert any(p.startswith("1 line") for p in short["problems"])  # eight skills, one line
    # the page still prints exactly what is left: your edit is never undone behind your back
    assert len(chips(client, cv_id)["printed"]) == 8
    # a last line under 75% is named, too
    with_two = chips(client, cv_id)
    assert with_two["fit"]["manual"] and with_two["fit"]["lines"] == 1


def test_the_last_line_rule_is_reported_when_it_breaks(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool()
    good = fitting_list()
    cv_id = flat_cv(client)
    # one skill fewer or more eventually leaves a short last line: find such a list
    m = skill_fit.metrics_for(load_template("default"), good + EXTRA)
    names = list(dict.fromkeys(good + EXTRA))
    bad = None
    for n in range(12, len(names)):
        lines = skill_fit.break_lines([m.widths[x] for x in names[:n]], m)
        if lines and 2 <= len(lines) <= 3 and lines[-1].natural / m.linewidth < 0.7:
            bad = names[:n]
            break
    assert bad is not None
    set_list(client, cv_id, bad)
    fit = chips(client, cv_id)["fit"]
    assert not fit["ok"] and any("last line" in p and "under 75%" in p for p in fit["problems"])


def test_back_to_automatic_removes_your_edit(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool()
    cv_id = flat_cv(client)
    set_list(client, cv_id, ["python", "sql"])
    assert chips(client, cv_id)["fit"]["manual"]
    reset = client.patch(f"/api/cv/{cv_id}", json={"skills": {"reset": True}})
    assert reset.status_code == 200
    with Session(engine) as s:
        assert "skills" not in (s.get(CVVersion, cv_id).overrides or {})
    assert not chips(client, cv_id)["fit"]["manual"]  # the automatic fit decides again


def test_your_list_survives_a_template_switch(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool()
    cv_id = flat_cv(client)
    set_list(client, cv_id, ["python", "Kubernetes"])
    templates = [t["name"] for t in client.get("/api/cv/templates").json() if t["valid"]]
    other = next((t for t in templates if t != "default"), "default")
    out = client.patch(f"/api/cv/{cv_id}", json={"template": other}).json()
    assert out["content"]["skills_flat"] == ["python", "kubernetes"]


def test_a_soft_skill_chip_prints_at_the_end_like_any_other(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool(extra_soft=True)
    cv_id = flat_cv(client)
    out = set_list(client, cv_id, ["python", "Teamwork", "sql"]).json()
    assert out["content"]["skills_flat"] == ["python", "Teamwork", "sql"]  # your order
    printed = {c["skill"]: c for c in chips(client, cv_id)["printed"]}
    assert printed["Teamwork"]["kind"] == "soft" and printed["python"]["kind"] == "technical"
    with Session(engine) as s:
        tex = s.get(CVVersion, cv_id).tex
    assert "\\mbox{Teamwork}" in tex and "Soft" not in tex


def test_chips_never_write_to_the_pool(client, seeded: None) -> None:  # noqa: ANN001
    seed_pool(extra_soft=True)
    before = _pool_rows()
    cv_id = flat_cv(client)
    client.patch(f"/api/cv/{cv_id}", json={"skills": {"add": ["python", "Teamwork"]}})
    client.patch(f"/api/cv/{cv_id}", json={"skills": {"remove": ["python"]}})
    client.patch(f"/api/cv/{cv_id}", json={"skills": {"reset": True}})
    assert _pool_rows() == before


def _pool_rows() -> list:
    with Session(engine) as s:
        rows = s.query(ExperienceItem).order_by(ExperienceItem.id).all()
        return [experience_write.snapshot(r) for r in rows]
