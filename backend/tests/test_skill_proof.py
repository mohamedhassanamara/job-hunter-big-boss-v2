"""Skill proofs (small real projects) and certification topics: evidence for the skills list
only. They never reach Experience, citations, fills, checks or the model's pool."""
import json

from sqlmodel import Session, select

from app.db import engine
from app.models import ExperienceItem
from app.providers.base import CVPlan, PlanEntry, PlanProject, PlanSkillGroup
from app.services import cv_check, experience_write, master_import
from app.services.cv_pool import load_pool, prompt_pool, role_years

PROOF = {"kind": "skill_proof", "title": "Zephyrite ingestion script", "org": None,
         "summary": "Wrote a Zephyrite ingestion script for a side project.",
         "bullets": ["Loaded 12k rows with Zephyrite"], "tags": ["Zephyrite", "Quokka"]}


def add_proof() -> int:
    with Session(engine) as s:
        item = experience_write.create(s, dict(PROOF))
        s.commit()
        return item.id


def add_cert(tags: list[str]) -> int:
    with Session(engine) as s:
        item = experience_write.create(s, {
            "kind": "certification", "title": "Frobnicate Pro", "org": "Acme Academy",
            "tags": tags, "bullets": []})
        s.commit()
        return item.id


def pool_now():  # noqa: ANN201
    with Session(engine) as s:
        return load_pool(s)


def test_a_skill_proof_is_a_valid_kind_through_the_api(client, seeded: None) -> None:
    r = client.post("/api/experience", json={"kind": "skill_proof", "title": "Tiny tool",
                                             "tags": ["Zephyrite"]})
    assert r.status_code == 201 and r.json()["kind"] == "skill_proof"
    client.delete(f"/api/experience/{r.json()['id']}")


def test_a_skill_proof_is_invisible_to_every_pool_reader(seeded: None) -> None:
    before = pool_now()
    proof_id = add_proof()
    pool = pool_now()
    assert [i.id for i in pool.skill_proofs] == [proof_id]
    assert proof_id not in pool.items and pool.get(proof_id) is None
    assert all(i.kind != "skill_proof" for items in pool.by_kind.values() for i in items)
    assert "skill_proof" not in pool.by_kind
    text = pool.all_text()
    assert "Zephyrite" not in text and "Quokka" not in text
    assert "zephyrite" not in {t for t in pool.skill_terms()}
    # the model never sees it, and nothing else about the pool changed
    assert json.dumps(prompt_pool(pool), default=str) == json.dumps(prompt_pool(before),
                                                                    default=str)
    assert "Zephyrite" not in json.dumps(prompt_pool(pool), default=str)
    assert role_years(pool) == role_years(before)


def test_a_skill_proof_cannot_be_cited_anywhere(seeded: None) -> None:
    proof_id = add_proof()
    pool = pool_now()
    plan = CVPlan(summary="S", summary_short="S", education_ids=[],
                  roles=[PlanEntry(item_id=proof_id, relevance=9, bullets=[])],
                  projects=[PlanProject(item_id=proof_id, relevance=9, bullets=[])],
                  skills=[PlanSkillGroup(item_id=proof_id, items=["Zephyrite"])])
    repaired, issues = cv_check.check_plan(plan, pool)
    unknown = [i for i in issues if i["type"] == "unknown_item"]
    assert len(unknown) >= 3  # role, project and skill group ids are all unknown
    assert proof_id not in {e.item_id for e in repaired.roles}
    assert proof_id not in {e.item_id for e in repaired.projects}
    assert proof_id not in {g.item_id for g in repaired.skills}
    # the page fill (fill_by_relevance → check_extra) can't take its bullets either
    for kind in ("role", "project"):
        assert cv_check.check_extra(pool, kind, proof_id, 0) == (None, "unknown item")


def test_certification_topics_are_not_things_you_did(seeded: None) -> None:
    cert_id = add_cert(["Frobnicate", "Quux Lakes"])
    pool = pool_now()
    cert = pool.get(cert_id, "certification")
    assert cert is not None and cert.title == "Frobnicate Pro"  # still printable as a credential
    assert cert.tags == [] and pool.study_tags[cert_id] == ["Frobnicate", "Quux Lakes"]
    assert "Frobnicate" not in pool.all_text().replace("Frobnicate Pro", "")
    assert "quuxlakes" not in pool.skill_terms()
    with Session(engine) as s:  # the stored row keeps its topics, and loading wrote nothing
        stored = s.get(ExperienceItem, cert_id)
        assert stored.tags == ["Frobnicate", "Quux Lakes"]
        s.commit()


def test_master_import_leaves_proofs_and_certification_topics_alone(seeded: None) -> None:
    proof_id = add_proof()
    with Session(engine) as s:
        doc = master_import.parse(
            "## Certifications\n- **Frobnicate Pro** — Acme Academy *(ID: Z1)*\n")
    cert_id = add_cert(["Frobnicate"])
    with Session(engine) as s:
        plan = master_import.plan(s, doc, {})
        assert proof_id not in {i.id for i in plan["archive"]}
        counts = master_import.apply(s, doc, {})
        s.commit()
        assert counts["created"] + counts["updated"] == len(doc)
        proof = s.get(ExperienceItem, proof_id)
        assert proof.is_active and proof.tags == PROOF["tags"]
        cert = s.get(ExperienceItem, cert_id)
        assert cert.is_active and cert.tags == ["Frobnicate"]  # the hand-added topics survive
        again = master_import.apply(s, doc, {})
        assert again["archived"] == 0 and again["created"] == 0
        assert s.exec(select(ExperienceItem).where(ExperienceItem.kind == "skill_proof")).all()
