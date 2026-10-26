"""Filling the page by relevance (cv_build.fill_by_relevance): the rated leftovers of the 2-pass
generator go on one at a time, best first, each checked, only while the page is under target."""

from pathlib import Path

from app.providers.base import CVPlan, PlanBullet, PlanEntry, PlanExtra, PlanProject
from app.services import cv_build, cv_check, honesty
from app.services.cv_build import fit_to_page, layout
from app.services.cv_render import CVProfile, load_template
from tests.test_cv import fake_compiler
from tests.test_cv_rules import CURRENT, MOBILE, P1, P4, RULES, TODAY, make_pool


def bullets(it, indices):  # noqa: ANN001, ANN201
    return [PlanBullet(source_index=n, text=it.bullets[n], priority=k + 1)
            for k, n in enumerate(indices)]


def essentials(**kw) -> CVPlan:  # noqa: ANN003
    return CVPlan(summary="Engineer.", summary_short="Engineer.",
                  roles=[PlanEntry(item_id=CURRENT.id, relevance=8, bullets=bullets(CURRENT, [0, 1, 2])),
                         PlanEntry(item_id=MOBILE.id, relevance=5, bullets=bullets(MOBILE, [0, 1]))],
                  **kw)


def run(plan: CVPlan, capacity: int, monkeypatch, tmp_path: Path, honesty_rules=None):  # noqa: ANN001, ANN201
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=capacity, calls=[]))
    lay = layout(plan, make_pool(), RULES, today=TODAY)
    lay.honesty = honesty_rules
    return fit_to_page(plan, make_pool(), CVProfile(full_name="Ada"), load_template("default"),
                       tmp_path, lay=lay), lay


def added(plan: CVPlan) -> list[tuple[int, int | None]]:
    return [(e["item_id"], e["source_index"]) for e in plan.fill_log if e["result"] == "added"]


def test_extras_are_added_best_first_and_stop_when_the_page_is_full(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    extras = [PlanExtra(kind="role", item_id=CURRENT.id, source_index=3, relevance=3),
              PlanExtra(kind="role", item_id=CURRENT.id, source_index=4, relevance=9),
              PlanExtra(kind="role", item_id=MOBILE.id, source_index=2, relevance=6),
              PlanExtra(kind="role", item_id=MOBILE.id, source_index=3, relevance=1)]
    # a page with room for exactly one more bullet pair than the essentials need
    base = run(essentials(), 400, monkeypatch, tmp_path)[0].compiled.fill
    plan = essentials(extras=extras)
    result, _lay = run(plan, 400, monkeypatch, tmp_path)
    assert base < result.compiled.fill  # the extras filled the page
    order = [(e["item_id"], e["source_index"]) for e in plan.fill_log]
    assert order[0] == (CURRENT.id, 4)  # rated 9: first
    assert added(plan)[0] == (CURRENT.id, 4)
    assert plan.extras == []  # consumed: on the page or in the log


def test_nothing_is_added_when_the_page_is_already_full(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    calls: list[int] = []
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=400, calls=calls))
    plain = essentials()
    lay = layout(plain, make_pool(), RULES, today=TODAY)
    fit_to_page(plain, make_pool(), CVProfile(full_name="Ada"), load_template("default"),
                tmp_path, lay=lay)
    full = calls[-1]  # the size of the essentials CV once the plan's own bullets are used
    extras = [PlanExtra(kind="role", item_id=CURRENT.id, source_index=n, relevance=9 - n)
              for n in (3, 4)]
    plan = essentials(extras=extras)
    result, _ = run(plan, full, monkeypatch, tmp_path)  # a page exactly that big
    assert result.compiled.fill >= 0.98
    assert plan.fill_log == [] and len(plan.extras) == 2  # untouched: a later re-fit may use them


def test_an_item_that_fails_the_checks_is_skipped_and_the_next_one_used(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    rules = honesty.rules_from([{"name": "Data/AI", "experience": "projects",
                                 "roles": [{"title": "Data Engineer"}]}])
    pool = make_pool()
    pool.items[CURRENT.id].bullets[4] = "3 years building data pipelines for retail"
    try:
        extras = [PlanExtra(kind="role", item_id=CURRENT.id, source_index=4, relevance=10),
                  PlanExtra(kind="role", item_id=CURRENT.id, source_index=3, relevance=5)]
        plan = essentials(extras=extras)
        monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=400, calls=[]))
        lay = layout(plan, pool, RULES, today=TODAY)
        lay.honesty = rules
        fit_to_page(plan, pool, CVProfile(full_name="Ada"), load_template("default"), tmp_path,
                    lay=lay)
    finally:
        pool.items[CURRENT.id].bullets[4] = "Software Engineer fact 4"
    skipped = [e for e in plan.fill_log if e["result"] == "skipped"]
    assert skipped and skipped[0]["source_index"] == 4 and skipped[0]["relevance"] == 10
    assert (CURRENT.id, 3) in added(plan)


def test_an_unknown_fact_is_skipped(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    plan = essentials(extras=[PlanExtra(kind="role", item_id=CURRENT.id, source_index=99,
                                        relevance=10)])
    run(plan, 400, monkeypatch, tmp_path)
    assert plan.fill_log[0]["result"] == "skipped"


def test_extras_never_go_past_the_entry_allowance(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    extras = [PlanExtra(kind="role", item_id=MOBILE.id, source_index=n, relevance=9)
              for n in (2, 3)]  # a 2.5-year role: at most 4 bullets, 2 already there
    plan = essentials(extras=extras)
    result, lay = run(plan, 4000, monkeypatch, tmp_path)
    assert result.state.counts[f"role:{MOBILE.id}"] <= lay.bounds[f"role:{MOBILE.id}"][1] <= 4


def test_a_whole_project_comes_in_only_under_projects_max_and_with_two_bullets(
        monkeypatch, tmp_path) -> None:  # noqa: ANN001
    plan = essentials(extras=[PlanExtra(kind="project", item_id=P1.id, relevance=8),
                              PlanExtra(kind="project", item_id=P4.id, relevance=7)])
    result, _ = run(plan, 4000, monkeypatch, tmp_path)
    assert {p.item_id for p in plan.projects} <= {P1.id, P4.id}
    assert all(len(p.bullets) >= 2 for p in result.document.projects)
    assert len(result.document.projects) <= RULES["projects_max"]


def test_no_project_is_injected_when_nothing_was_rated(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    plan = essentials()
    result, _ = run(plan, 4000, monkeypatch, tmp_path)
    assert plan.projects == [] and result.document.projects == []


def test_check_extra_uses_the_pools_own_text() -> None:
    pool = make_pool()
    text, why = cv_check.check_extra(pool, "role", CURRENT.id, 2)
    assert text == CURRENT.bullets[2] and why is None
    assert cv_check.check_extra(pool, "role", CURRENT.id, 40)[1] == "not a fact of that item"
    assert cv_check.check_extra(pool, "project", CURRENT.id, 0)[1] == "unknown item"
