"""The Review CVs list: drafts of shortlisted jobs with the Approve gate evaluated."""

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, CVVersion
from app.models.enums import CVStatus, Stage
from app.providers.base import CVPlan, PlanBullet, PlanEntry, PlanExtra
from app.services import cv_build, cv_service, honesty
from app.services.cv_build import FitState
from tests.test_cv_rules import CURRENT, P1, RULES, make_pool
from tests.test_tracking import make_app


def clean(s: Session) -> None:
    for v in s.exec(select(CVVersion)).all():
        v.status = CVStatus.superseded
        s.add(v)
    for a in s.exec(select(Application).where(Application.stage == Stage.shortlisted)).all():
        a.stage = Stage.new
        s.add(a)
    s.commit()


def draft(s: Session, **kw) -> Application:
    violations = kw.pop("violations", [])
    app = make_app(s, stage=Stage.shortlisted, cv=None)
    s.add(CVVersion(application_id=app.id, version=1, status=CVStatus.draft,
                    page_count=kw.pop("page_count", 1), fill=0.97, violations=violations, **kw))
    s.flush()
    return app


def test_lists_shortlisted_drafts_with_the_approve_gate(client) -> None:
    with Session(engine) as s:
        clean(s)
        ok = draft(s)
        two_pages = draft(s, page_count=2)
        bullet = draft(s, violations=[
            {"type": "number", "severity": "error", "where": "bullet", "message": "x"}])
        summary_only = draft(s, violations=[
            {"type": "summary_style", "severity": "error", "where": "summary", "message": "y"},
            {"type": "summary_style", "severity": "warning", "where": "summary", "message": "z"}])
        failed = draft(s, error="generation failed")
        approved = make_app(s, stage=Stage.shortlisted, cv=CVStatus.approved)
        in_pipeline = make_app(s, stage=Stage.cv_ready, cv=CVStatus.draft)
        s.commit()
        ids = {n: a.id for n, a in dict(ok=ok, two=two_pages, bullet=bullet, summary=summary_only,
                                        failed=failed, approved=approved).items()}
        later = in_pipeline.id
    rows = {r["application_id"]: r for r in client.get("/api/cv/review").json()}
    assert later not in rows and ids["approved"] not in rows  # only shortlisted jobs with a draft
    assert rows[ids["ok"]]["approvable"] is True
    assert rows[ids["two"]]["approvable"] is False and rows[ids["two"]]["page_count"] == 2
    assert rows[ids["bullet"]]["approvable"] is False and rows[ids["bullet"]]["error_count"] == 1
    summary = rows[ids["summary"]]  # summary findings never block, as in approve_cv
    assert summary["approvable"] is True and summary["error_count"] == 0
    assert summary["summary_warnings"] == 1
    assert rows[ids["failed"]]["approvable"] is False
    assert client.get("/api/nav-counts").json()["cvs_to_review"] == len(rows)


def test_a_newer_approved_version_takes_the_job_off_the_list(client) -> None:
    with Session(engine) as s:
        clean(s)
        app = draft(s)
        s.add(CVVersion(application_id=app.id, version=2, status=CVStatus.approved))
        s.commit()
        app_id = app.id
    assert app_id not in {r["application_id"] for r in client.get("/api/cv/review").json()}


# ------------------------------------------------------------------------------ Left out

def left_out_version(force_in: list[str] | None = None) -> tuple[CVVersion, CVPlan]:
    pool = make_pool()
    plan = CVPlan(
        summary="Engineer.", summary_short="Engineer.",
        roles=[PlanEntry(item_id=CURRENT.id, relevance=8, bullets=[
            PlanBullet(source_index=n, text=CURRENT.bullets[n], priority=n + 1)
            for n in (0, 1, 2)])],
        fill_log=[{"kind": "role", "item_id": CURRENT.id, "source_index": 3, "relevance": 6,
                   "result": "skipped", "reason": "did not fit one page"},
                  {"kind": "project", "item_id": P1.id, "source_index": None, "relevance": 5,
                   "result": "skipped", "reason": "below_project_threshold"}],
        extras_rated=[PlanExtra(kind="role", item_id=CURRENT.id, source_index=4, relevance=4)])
    overrides = {"force_in": force_in or []}
    lay = cv_build.layout(plan, pool, RULES)
    state = FitState(counts={f"role:{CURRENT.id}": 2})
    doc = cv_build.build_document(plan, pool, state, overrides, 6, lay)
    v = CVVersion(application_id=1, version=1, status=CVStatus.draft, content=doc.model_dump(),
                  overrides=overrides, plan={"plan": plan.model_dump(), "fit": state.to_dict()})
    return v, plan


def test_left_out_lists_what_the_cv_does_not_show_with_relevance_and_reason() -> None:
    v, _ = left_out_version()
    items = {x["key"]: x for x in cv_service.left_out(v, make_pool())}
    assert f"role:{CURRENT.id}:0" not in items  # shown
    trimmed = items[f"role:{CURRENT.id}:2"]  # in the plan, cut to fit
    assert trimmed["why"] == "trimmed to fit this CV" and trimmed["relevance"] is None
    assert items[f"role:{CURRENT.id}:3"]["relevance"] == 6
    assert items[f"role:{CURRENT.id}:3"]["why"] == "did not fit one page"
    assert items[f"role:{CURRENT.id}:4"]["relevance"] == 4  # rated, never tried
    project = items[f"project:{P1.id}"]
    assert project["kind"] == "project" and project["why"] == "project below the minimum relevance"
    assert project["relevance"] == 5 and not project["included"]


def test_forcing_a_left_out_bullet_in_adds_the_pools_own_text_after_the_checks() -> None:
    pool = make_pool()
    _, plan = left_out_version()
    key = f"role:{CURRENT.id}:4"
    forced = cv_service.with_forced_bullets(plan, pool, {"force_in": [key]})
    added = forced.roles[0].bullets[-1]
    assert (added.source_index, added.text) == (4, CURRENT.bullets[4])
    assert len(plan.roles[0].bullets) == 3  # the stored plan is untouched
    pool.items[CURRENT.id].bullets[4] = "3 years building data pipelines for retail"
    rules = honesty.rules_from([{"name": "Data/AI", "experience": "projects",
                                 "roles": [{"title": "Data Engineer"}]}])
    try:
        with pytest.raises(cv_service.CVError, match="Can't include"):
            cv_service.with_forced_bullets(plan, pool, {"force_in": [key]}, rules)
    finally:
        pool.items[CURRENT.id].bullets[4] = "Software Engineer fact 4"
