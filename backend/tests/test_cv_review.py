"""The Review CVs list: drafts of shortlisted jobs with the Approve gate evaluated."""

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, CVVersion
from app.models.enums import CVStatus, Stage
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
