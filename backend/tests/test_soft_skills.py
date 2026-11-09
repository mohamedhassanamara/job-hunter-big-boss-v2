"""Soft skills on the job CV's skills list: named by the listing AND backed by your pool, as
ordinary entries at the end of the same line. No model calls."""
import shutil
from pathlib import Path

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import ExperienceItem, Job
from app.providers.base import CVPlan, PlanEntry
from app.services import cv_check, cv_service, experience_write, skill_fit, soft_skills
from app.services import skill_ledger as sl
from app.services.cv_build import FitState, build_document, fit_to_page
from app.services.cv_pool import Pool, cv_profile, load_pool, prompt_pool
from app.services.cv_render import load_template
from tests import test_skill_cooccurrence as co
from tests.test_cv import plan_for
from tests.test_skill_fit import HAS_SANS, sans_template

_ids = iter(range(50_000, 60_000))


def item(kind: str, title: str, soft: list[str], bullets: list[str] | None = None,
         tags: list[str] | None = None) -> ExperienceItem:
    return ExperienceItem(id=next(_ids), kind=kind, title=title, org="X", tags=tags or [],
                          tracks=[], soft_skills=soft, position=0,
                          bullets=["Did real work."] if bullets is None else bullets)


def with_items(*items: ExperienceItem) -> Pool:
    p = co.pool()
    for i in items:
        p.items[i.id] = i
        p.by_kind.setdefault(i.kind, []).append(i)
    return p


def names(pool: Pool, listing: str, title: str = "Developer") -> list[str]:
    return [e.display for e in soft_skills.select(pool, title, listing)]


# ------------------------------------------------------------------------- equivalence

LISTING_FORMS = ["collaboration", "Teamwork", "Teamfähigkeit", "travail d'équipe",
                 "esprit d’équipe", "Zusammenarbeit", "team player", "collaborative"]


@pytest.mark.parametrize("listing_word", LISTING_FORMS)
@pytest.mark.parametrize("mine", ["Teamwork", "Collaboration", "Teamfähigkeit", "Travail d'équipe"])
def test_collaboration_teamwork_teamfaehigkeit_and_travail_d_equipe_are_one_skill(
        mine: str, listing_word: str) -> None:
    pool = with_items(item("volunteering", "Club", [mine]))
    assert names(pool, f"We value {listing_word} in our team.") == [mine]  # your spelling prints


@pytest.mark.parametrize(("mine", "listing"), [
    ("Leadership", "You will be mentoring junior engineers."),
    ("Mentoring", "Strong leadership skills required."),
    ("Leadership", "You are a mentor to others."),
    ("Mentoring", "Führungsstärke ist wichtig."),
    ("Ownership", "You are adaptable and flexible."),
    ("Adaptability", "You take ownership of your work."),
    ("Communication", "A great team player."),
    ("Teamwork", "Excellent communication skills."),
    ("Problem-solving", "Strong communication."),
])
def test_no_group_implies_another(mine: str, listing: str) -> None:
    assert names(with_items(item("job", "Role", [mine])), listing) == []


@pytest.mark.parametrize(("mine", "listing"), [
    ("Leadership", "Leadership skills"), ("Mentoring", "mentorship of juniors"),
    ("Mentoring", "Mentorat des juniors"), ("Ownership", "Eigenverantwortung"),
    ("Problem solving", "Problemlösung"), ("Problem-solving", "résolution de problèmes"),
    ("Adaptability", "Anpassungsfähigkeit"), ("Adaptabilité", "You are adaptable"),
    ("Communication", "Kommunikationsstärke"), ("Leadership", "Führung"),
])
def test_english_french_and_german_forms(mine: str, listing: str) -> None:
    assert names(with_items(item("job", "Role", [mine])), f"Required: {listing}.") == [mine]


def test_a_skill_in_no_group_matches_only_its_own_words() -> None:
    pool = with_items(item("job", "Role", ["Public speaking"]))
    assert names(pool, "You enjoy public speaking.") == ["Public speaking"]
    assert names(pool, "Excellent communication skills.") == []


def test_words_inside_longer_words_do_not_match() -> None:
    pool = with_items(item("job", "Role", ["Leadership", "Mentoring"]))
    assert names(pool, "Our Führungskraft and the mentorless stand-ups.") == []


# ------------------------------------------------------------------------------ evidence


def test_a_soft_skill_needs_a_bullet_on_its_item() -> None:
    bare = with_items(item("volunteering", "Club", ["Teamwork"], bullets=[]))
    assert names(bare, "Teamwork matters.") == []
    blank = with_items(item("volunteering", "Club", ["Teamwork"], bullets=["  ", ""]))
    assert names(blank, "Teamwork matters.") == []
    backed = with_items(item("volunteering", "Club", ["Teamwork"], bullets=["Led 5 volunteers."]))
    assert names(backed, "Teamwork matters.") == ["Teamwork"]


def test_the_listing_must_name_it() -> None:
    assert names(with_items(item("job", "Role", ["Teamwork", "Mentoring"])),
                 "You write Python services.") == []


def test_only_the_soft_skills_field_counts() -> None:
    tagged = with_items(item("job", "Role", [], tags=["teamwork", "leadership"]))
    assert names(tagged, "Teamwork and leadership are key.") == []
    project = with_items(item("project", "Side", ["Teamwork"]))
    assert names(project, "Teamwork is key.") == []  # only jobs and volunteering back one
    proof = co.pool(proofs=[["Teamwork"]], study=[["Leadership"]])
    assert names(proof, "Teamwork and leadership are key.") == []


def test_two_spellings_of_one_skill_are_shown_once_and_the_cap_is_four() -> None:
    items = [item("job", "A", ["Teamwork"]), item("volunteering", "B", ["Collaboration"]),
             item("job", "C", ["Leadership", "Mentoring", "Ownership", "Communication",
                               "Problem-solving"])]
    listing = ("Teamwork, leadership, mentoring, ownership, communication, problem-solving "
               "and collaboration are all required.")
    out = soft_skills.select(with_items(*items), "Dev", listing)
    assert len(out) == soft_skills.MAX_SOFT == 4
    assert [e.display for e in out].count("Teamwork") == 1
    assert "Collaboration" not in [e.display for e in out]  # the first spelling wins


def test_the_most_relevant_come_first() -> None:
    pool = with_items(item("job", "A", ["Mentoring", "Leadership", "Ownership"]))
    listing = ("Fluent in Python. Nice to have: mentoring. Required: strong leadership. "
               "Leadership is a must. We like ownership.")
    # leadership is in the title and on a requirement line, mentoring on a "nice to have" line
    assert names(pool, listing, title="Engineering Leadership role") == [
        "Leadership", "Mentoring", "Ownership"]


# ------------------------------------------------------------ in the skills list: placement


LISTING = co.BACKEND_LISTING + "You show teamwork and mentoring, and you take ownership."


def selection(**kw):  # noqa: ANN003, ANN201
    pool = with_items(item("volunteering", "Club", ["Teamwork", "Mentoring"]),
                      item("job", "Platform engineer 2", ["Ownership", "Leadership"]))
    return sl.select_skills(pool, title="Developer", description=LISTING, min_items=1,
                            emphasis=co.BACKEND_EMPHASIS, **kw)


def test_soft_skills_are_ordinary_entries_at_the_end_of_the_list() -> None:
    out = selection()
    assert out.display[-3:] == ["Teamwork", "Mentoring", "Ownership"]
    softs = [s for s in out.skills if s.kind == "soft"]
    assert [s.reason for s in out.skills[-len(softs):]] == ["soft"] * len(softs)
    assert all(s.reason != "soft" for s in out.skills[:-len(softs)])  # nothing after them
    assert "Leadership" not in out.display  # the listing doesn't name it
    assert all(s.to_dict()["kind"] == "soft" for s in softs)


def test_the_cut_order_is_filler_then_soft_skills_then_matches() -> None:
    out = selection()
    kinds = [(out.skills[i].reason if out.skills[i].kind != "soft" else "soft")
             for i in out.cut_order]
    first_soft, first_match = kinds.index("soft"), kinds.index("jd")
    assert set(kinds[:first_soft]) <= {"cooc", "pin", "fill"} and first_soft > 0
    assert first_soft < first_match
    assert kinds[first_soft:first_match] == ["soft"] * (first_match - first_soft)
    assert kinds[first_match:] == ["jd"] * (len(kinds) - first_match)
    assert sorted(out.cut_order) == list(range(len(out.skills)))  # every entry exactly once


def test_soft_skills_count_in_the_ceiling() -> None:
    out = selection(max_items=10)
    assert len(out.skills) == 10 and sum(s.kind == "soft" for s in out.skills) == 3


def test_a_soft_skill_alone_does_not_make_a_flat_list() -> None:
    pool = with_items(item("job", "Role", ["Teamwork"]))
    out = sl.select_skills(pool, title="Mover", min_items=1,
                           description="Packing boxes with teamwork. " * 10)
    assert not any(s.reason == "jd" for s in out.skills)  # the caller keeps the grouped list


def test_soft_skills_never_count_as_things_you_did() -> None:
    plan = CVPlan(summary="S", summary_short="S", skills_mode="flat", skill_list=[
        {"skill": "Python", "tier": 1, "item_ids": [], "reason": "jd", "kind": "technical"},
        {"skill": "Teamwork", "tier": 1, "item_ids": [], "reason": "soft", "kind": "soft"}])
    assert cv_check.shown_skills(plan) == ["Python"]


# ------------------------------------------------------------------- grouped fallback


def test_the_grouped_list_never_shows_soft_skills(seeded: None) -> None:
    with Session(engine) as s:
        pool = load_pool(s)
        volunteering = pool.of("volunteering")[0]
        experience_write.update(s, s.get(ExperienceItem, volunteering.id),
                                {"soft_skills": ["Teamwork"],
                                 "bullets": [*volunteering.bullets, "Coordinated a team."]})
        s.commit()
        pool = load_pool(s)
        plan = plan_for(pool)
        listing = Job(title="Developer", company_id=1, location="Berlin",
                      description="Nobody here knows Teamwork. " * 12)
        out = cv_service.with_job_skills(s, plan, pool, listing, "Acme")
    assert out.skills_mode == "grouped" and out.skill_list == []  # no match: the groups stay
    doc = build_document(out, pool, FitState())
    assert doc.skills_flat == [] and "Teamwork" not in str(doc.skills)


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
def test_when_no_length_fits_the_grouped_list_has_no_soft_skills(
        seeded: None, tmp_path: Path) -> None:
    with Session(engine) as s:
        pool = load_pool(s)
    plan = plan_for(pool).model_copy(update={
        "skills_mode": "flat", "skills_target": 3, "skill_cut_order": [2, 1, 0],
        "skill_list": [
            {"skill": "Python", "tier": 1, "item_ids": [], "reason": "jd", "kind": "technical"},
            {"skill": "SQL", "tier": 1, "item_ids": [], "reason": "jd", "kind": "technical"},
            {"skill": "Teamwork", "tier": 1, "item_ids": [], "reason": "soft", "kind": "soft"}]})
    result = fit_to_page(plan, pool, cv_profile(pool), load_template("default"),
                         tmp_path / "out", state=FitState())
    assert result.document.skills_flat == [] and "Teamwork" not in result.tex


# ----------------------------------------------------------- the real page, both templates


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
@pytest.mark.parametrize("which", ["default", "sans"])
def test_soft_skills_print_in_the_same_line_and_meet_the_line_rule(
        which: str, seeded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if which == "sans" and not HAS_SANS:
        pytest.skip("Source Sans Pro is not installed")
    template = load_template("default") if which == "default" else sans_template(tmp_path)
    monkeypatch.setitem(cv_service.cv_rules.DEFAULT_STRUCTURE, "skills_max", 30)
    skills_pool = with_items(item("volunteering", "Club", ["Teamwork", "Mentoring"]))
    with Session(engine) as s:
        pool = load_pool(s)
        job = Job(title="Developer", company_id=1, location="Berlin", description=LISTING * 2)
        plan = cv_service.with_job_skills(s, plan_for(pool), skills_pool, job, "Acme")
    assert [x["skill"] for x in plan.skill_list if x["kind"] == "soft"] == [
        "Teamwork", "Mentoring"]
    result = fit_to_page(plan, pool, cv_profile(pool), template, tmp_path / "out",
                         state=FitState())
    printed = result.document.skills_flat
    assert printed[-2:] == ["Teamwork", "Mentoring"]  # last, in the same flat list
    block = result.tex.split("\\section{Skills}")[1].split("\\end{itemize}")[0]
    assert "\\mbox{Teamwork}, \\mbox{Mentoring}" in block  # the same \mbox wrapping
    assert "Soft" not in result.tex and "soft" not in block.lower()  # no label, no prefix
    metrics = skill_fit.metrics_for(template, ["Python"])
    lines, last = skill_fit.measure_block(result.compiled.pdf_path, template, metrics.linewidth)
    assert 2 <= lines <= 3 and last >= 0.74  # counted in the same rule


def test_soft_skills_are_cut_after_the_filler_and_before_the_matches() -> None:
    skills = [f"S{i}" for i in range(16)]  # S0-S1 matches, S2-S12 filler, S13-S15 soft
    cut = [*range(12, 1, -1), 15, 14, 13, 1, 0]
    m = skill_fit.Metrics(540.0, 4.0, 2.0, 1.0, 3.0, {s: 100.0 for s in skills}, 0.0, True)
    pick = skill_fit.choose(skills, cut, 16, m)
    assert pick is not None and {"S0", "S1", "S13", "S14", "S15"} <= set(pick.skills)
    small = skill_fit.choose(skills, cut, 6, skill_fit.Metrics(
        540.0, 4.0, 2.0, 1.0, 3.0, {s: 100.0 for s in skills}, 0.0, True), floor=1)
    assert small is not None and {"S0", "S1"} <= set(small.skills)


# ------------------------------------------- volunteering and fit decisions are untouched


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="LaTeX not installed")
def test_soft_skills_on_a_volunteering_item_change_neither_entries_nor_fit_decisions(
        seeded: None, tmp_path: Path) -> None:
    def fitted(label: str) -> tuple:
        with Session(engine) as s:
            pool = load_pool(s)
        plan = plan_for(pool)
        plan.volunteering = [PlanEntry(item_id=v.id, relevance=5, bullets=[
            {"source_index": n, "text": text, "priority": n + 1}
            for n, text in enumerate(pool.facts(v))]) for v in pool.of("volunteering")]
        assert plan.volunteering
        res = fit_to_page(plan, pool, cv_profile(pool), load_template("default"),
                          tmp_path / label, state=FitState())
        return (res.document.model_dump(), res.state.to_dict(), res.compiled.pages,
                round(res.compiled.fill, 3),
                [(h.get("pass"), h.get("pages"), h.get("fill")) for h in res.history
                 if "pass" in h],
                prompt_pool(pool), [v.title for v in pool.of("volunteering")],
                plan.model_dump())

    before = fitted("before")
    with Session(engine) as s:
        for v in load_pool(s).of("volunteering"):
            experience_write.update(s, s.get(ExperienceItem, v.id), {
                "soft_skills": ["Teamwork", "Mentoring", "Leadership"]})
        s.commit()
        assert all(v.soft_skills for v in load_pool(s).of("volunteering"))
    after = fitted("after")
    assert before == after  # entries, bullets, fit state, page counts and the model's pool


# ------------------------------------------------------------------------ the field itself


def test_the_field_is_guarded_like_the_rest_of_the_pool(seeded: None) -> None:
    from app.services.experience_write import PoolWriteError

    with Session(engine) as s:
        row = s.query(ExperienceItem).filter(ExperienceItem.kind == "volunteering").first()
        row.soft_skills = ["Teamwork"]
        s.add(row)
        with pytest.raises(PoolWriteError):
            s.commit()


def test_the_api_saves_it_with_history_and_the_master_import_keeps_it(
        client, seeded: None) -> None:
    items = client.get("/api/experience").json()
    vol = next(i for i in items if i["kind"] == "volunteering")
    assert vol["soft_skills"] == ["Mentoring"]  # the sandbox sample for the tour
    done = client.patch(f"/api/experience/{vol['id']}", json={"soft_skills": ["Teamwork"]})
    assert done.status_code == 200 and done.json()["soft_skills"] == ["Teamwork"]
    history = client.get(f"/api/experience/{vol['id']}/history").json()
    assert history[0]["after"]["soft_skills"] == ["Teamwork"] and history[0]["before"][
        "soft_skills"] == ["Mentoring"]
    from app.services import master_import

    doc = master_import.parse("## Volunteering & Leadership Experience\n"
                              f"- **{vol['org']} — {vol['title']} (2022 – Present):** Did it.\n")
    with Session(engine) as s:
        mapping = {"match": {f"volunteering|{doc[0]['key']}": vol["id"]}}
        counts = master_import.apply(s, doc, mapping)
        s.commit()
        row = s.get(ExperienceItem, vol["id"])
        assert counts["updated"] == 1 and row.is_active  # the import really rewrote this item
        assert row.bullets == ["Did it."]
        assert row.soft_skills == ["Teamwork"]  # and left the hand-added soft skills alone
