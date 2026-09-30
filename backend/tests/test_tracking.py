"""After the CV: mark applied (locks the CV sent), replies, interviews, closing, reminders,
ghosting suggestions, stats and the CSV export. No model calls."""

import csv
import hashlib
import io
from datetime import UTC, date, datetime, timedelta
from itertools import count
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    ApplicationEvent,
    AppSetting,
    Company,
    CVVersion,
    Job,
)
from app.models.enums import (
    ApplyMethod,
    CloseReason,
    CVStatus,
    EventKind,
    InterviewType,
    ResponseKind,
    Route,
    Stage,
)
from app.providers.mock import MockCVGenerator
from app.services import cv_build, cv_service, tracking

_ids = count(1)
NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)


def make_app(s: Session, *, stage: Stage = Stage.ready, route: Route = Route.web_apply,
             cv: CVStatus | None = CVStatus.approved, track: str = "T-test",
             country: str = "FR", source: str = "adzuna") -> Application:
    n = next(_ids)
    company = Company(name=f"Co {n}", normalized_name=f"tracking-co-{n}")
    s.add(company)
    s.flush()
    job = Job(source=source, external_id=f"trk-{n}", url=f"https://example.test/{n}",
              title=f"Data Engineer {n}", company_id=company.id, country=country,
              dedupe_key=f"trk-{n}", matched_track=track)
    s.add(job)
    s.flush()
    app = Application(job_id=job.id, stage=stage, route=route)
    s.add(app)
    s.flush()
    if cv:
        s.add(CVVersion(application_id=app.id, version=1, status=cv))
        s.flush()
    return app


def applied_app(s: Session, days_ago: float = 0, **kw) -> Application:  # noqa: ANN003
    app = make_app(s, **kw)
    tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.company_site)
    app.applied_at = NOW - timedelta(days=days_ago)
    s.add(app)
    s.flush()
    return app


def events(s: Session, app: Application) -> list[ApplicationEvent]:
    return list(s.exec(select(ApplicationEvent).where(
        ApplicationEvent.application_id == app.id).order_by(ApplicationEvent.id)).all())


# -------------------------------------------------------------------------------- stage moves


@pytest.mark.parametrize("start", [Stage.ready, Stage.cv_ready])
def test_mark_applied_locks_the_cv_and_records_details(seeded: None, start: Stage) -> None:
    with Session(engine) as s:
        app = make_app(s, stage=start)
        tracking.mark_applied(s, app, applied_on=date(2026, 9, 20), method=ApplyMethod.job_board,
                              notes=" via portal ")
        cv = s.get(CVVersion, app.applied_cv_version_id)
        assert app.stage == Stage.done and cv.locked_at is not None
        assert app.applied_at == datetime(2026, 9, 20, 12, tzinfo=UTC)
        assert app.applied_method == "job_board" and app.applied_notes == "via portal"
        moves = [(e.from_stage, e.to_stage) for e in events(s, app)
                 if e.kind == EventKind.stage_change]
        expected = [("ready", "done")] if start == Stage.ready else [
            ("cv_ready", "ready"), ("ready", "done")]
        assert moves == expected
        applied = [e for e in events(s, app) if e.kind == EventKind.applied][0]
        assert applied.payload["cv_version"] == 1 and applied.payload["method"] == "job_board"
        s.rollback()


@pytest.mark.parametrize("stage", [Stage.new, Stage.shortlisted])
def test_mark_applied_refused_before_an_approved_cv(seeded: None, stage: Stage) -> None:
    with Session(engine) as s:
        app = make_app(s, stage=stage)
        with pytest.raises(tracking.TrackingError):
            tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.other)
        s.rollback()


def test_mark_applied_after_an_email_keeps_the_stage_and_only_once(seeded: None) -> None:
    from datetime import date

    with Session(engine) as s:
        app = make_app(s, stage=Stage.done)  # the email went out first
        emailed = app.applied_at
        tracking.mark_applied(s, app, applied_on=date(2026, 9, 30), method=ApplyMethod.company_site)
        assert app.stage == Stage.done and app.web_applied_at is not None
        assert app.web_method == ApplyMethod.company_site
        if emailed is not None:
            assert app.applied_at == min(emailed, app.web_applied_at)
        with pytest.raises(tracking.TrackingError, match="already"):
            tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.other)
        s.rollback()


def test_mark_applied_needs_an_approved_cv_of_this_job(seeded: None) -> None:
    with Session(engine) as s:
        draft_only = make_app(s, cv=CVStatus.draft)
        with pytest.raises(tracking.TrackingError, match="approved"):
            tracking.mark_applied(s, draft_only, applied_on=None, method=ApplyMethod.other)
        other = make_app(s)
        foreign = s.exec(select(CVVersion).where(CVVersion.application_id == other.id)).one()
        with pytest.raises(tracking.TrackingError):
            tracking.mark_applied(s, draft_only, applied_on=None, method=ApplyMethod.other,
                                  cv_version_id=foreign.id)
        s.rollback()


def test_first_interview_moves_to_interview_and_rounds_count(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        tracking.log_response(s, app, kind=ResponseKind.positive, received_on=None)
        assert app.stage == Stage.done  # a reply never moves the stage by itself
        first = tracking.log_interview(s, app, scheduled_at=NOW, type=InterviewType.hr)
        second = tracking.log_interview(s, app, scheduled_at=NOW, type=InterviewType.technical)
        assert app.stage == Stage.interview and (first.round, second.round) == (1, 2)
        kinds = [e.kind for e in events(s, app)]
        assert kinds.count(EventKind.interview) == 2 and EventKind.response in kinds
        s.rollback()


def test_replies_and_interviews_need_an_applied_job(seeded: None) -> None:
    with Session(engine) as s:
        app = make_app(s)
        with pytest.raises(tracking.TrackingError):
            tracking.log_response(s, app, kind=ResponseKind.other, received_on=None)
        with pytest.raises(tracking.TrackingError):
            tracking.log_interview(s, app, scheduled_at=NOW, type=InterviewType.hr)
        s.rollback()


@pytest.mark.parametrize("reason", sorted(tracking.AFTER_APPLY_REASONS))
def test_close_after_applying_with_each_outcome(seeded: None, reason: CloseReason) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        tracking.close(s, app, reason, "note")
        assert app.stage == Stage.closed and app.close_reason == reason
        assert events(s, app)[-1].to_stage == "closed"
        s.rollback()


def test_applied_jobs_cannot_be_merely_dismissed(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        with pytest.raises(tracking.TrackingError):
            tracking.close(s, app, CloseReason.dismissed)
        fresh = make_app(s, stage=Stage.new, cv=None)
        tracking.close(s, fresh, CloseReason.dismissed)
        assert fresh.close_reason == CloseReason.dismissed
        s.rollback()


def test_patch_stage_guards(client: TestClient) -> None:
    with Session(engine) as s:
        web = make_app(s)
        applied = applied_app(s)
        s.commit()
        web_id, applied_id = web.id, applied.id
    r = client.patch(f"/api/applications/{web_id}", json={"stage": "done"})
    assert r.status_code == 409 and "Mark applied" in r.json()["detail"]
    r = client.patch(f"/api/applications/{applied_id}", json={"stage": "interview"})
    assert r.status_code == 409
    r = client.patch(f"/api/applications/{applied_id}",
                     json={"stage": "closed", "close_reason": "dismissed"})
    assert r.status_code == 422


def test_approving_a_cv_without_contact_lands_in_ready_to_apply(client: TestClient) -> None:
    with Session(engine) as s:
        app = make_app(s, stage=Stage.shortlisted, route=Route.undecided, cv=CVStatus.draft)
        s.commit()
        cv_id = s.exec(select(CVVersion.id).where(CVVersion.application_id == app.id)).one()
        app_id = app.id
    r = client.post(f"/api/cv/{cv_id}/approve")
    assert r.status_code == 200
    body = r.json()
    assert (body["stage"], body["route"], body["next_step"]) == ("cv_ready", "web_apply", "apply")
    ready = client.get("/api/applications/ready").json()
    assert app_id in [x["application_id"] for x in ready]


# ---------------------------------------------------------------------------------- locked CV


def test_locked_cv_never_changes(seeded: None, monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    from tests.test_cv import fake_compiler

    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=60, calls=[]))
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
        row.value = {**row.value, "full_name": "Ada"}
        s.add(row)
        app = make_app(s, stage=Stage.cv_ready, cv=None)
        s.commit()
        app_id = app.id
    v1 = cv_service.generate(engine, app_id, MockCVGenerator())
    pdf = tmp_path / "sent.pdf"
    pdf.write_bytes(b"%PDF-1.4 sent version")
    with Session(engine) as s:
        v = s.get(CVVersion, v1.id)
        v.status, v.pdf_path = CVStatus.approved, str(pdf)
        s.add(v)
        app = s.get(Application, app_id)
        tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.company_site)
        s.commit()
        sent = s.get(CVVersion, v1.id)
        before = (sent.content, sent.status, sent.pdf_sha256, sent.locked_at)
    assert before[2] == hashlib.sha256(pdf.read_bytes()).hexdigest()

    edited = cv_service.rerender(engine, v1.id, overrides={"text": {"summary": "Changed."}})
    regenerated = cv_service.generate(engine, app_id, MockCVGenerator())
    assert edited.id != v1.id and regenerated.id != v1.id
    with Session(engine) as s:
        s.get(CVVersion, regenerated.id).page_count = 1
        s.commit()
    TestClient(__import__("app.main", fromlist=["app"]).app).post(
        f"/api/cv/{regenerated.id}/approve")
    with Session(engine) as s:
        sent = s.get(CVVersion, v1.id)
        assert (sent.content, sent.status, sent.pdf_sha256, sent.locked_at) == before
        assert s.get(Application, app_id).applied_cv_version_id == v1.id


# ---------------------------------------------------------------------------------- reminders


def _due(s: Session, app: Application, now: datetime) -> list[str]:
    return [r.key for r in tracking.reminders(s, now) if r.application_id == app.id]


def test_followups_are_due_on_day_7_and_14_and_stop_after_a_reply(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        assert _due(s, app, NOW + timedelta(days=6)) == []
        assert _due(s, app, NOW + timedelta(days=7)) == ["followup:7"]
        assert _due(s, app, NOW + timedelta(days=15)) == ["followup:14"]  # latest only
        tracking.log_response(s, app, kind=ResponseKind.other, received_on=None)
        assert _due(s, app, NOW + timedelta(days=15)) == []
        s.rollback()


def test_an_interview_also_stops_reminders(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        tracking.log_interview(s, app, scheduled_at=NOW, type=InterviewType.hr)
        assert _due(s, app, NOW + timedelta(days=40)) == []
        s.rollback()


def test_snooze_hides_until_the_date_and_dismiss_for_good(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        day8 = NOW + timedelta(days=8)
        tracking.snooze(s, app, "followup:7", until=day8 + timedelta(days=2))
        assert _due(s, app, day8) == []
        assert _due(s, app, day8 + timedelta(days=3)) == ["followup:7"]
        tracking.dismiss(s, app, "followup:7")
        assert _due(s, app, day8 + timedelta(days=3)) == []
        assert _due(s, app, NOW + timedelta(days=14)) == ["followup:14"]
        s.rollback()


def test_a_changed_setting_applies_immediately(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        row = s.exec(select(AppSetting).where(AppSetting.key == "tracking")).one()
        row.value = {"followup_days": [3], "ghost_after_days": 10}
        s.add(row)
        s.flush()
        assert _due(s, app, NOW + timedelta(days=3)) == ["followup:3"]
        assert sorted(_due(s, app, NOW + timedelta(days=10))) == ["followup:3", "ghost"]
        s.rollback()


def test_ghosting_is_only_suggested_until_confirmed(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        assert "ghost" not in _due(s, app, NOW + timedelta(days=29))
        assert "ghost" in _due(s, app, NOW + timedelta(days=30))
        assert app.stage == Stage.done  # suggesting never closes anything
        tracking.confirm_ghosted(s, app)
        assert (app.stage, app.close_reason) == (Stage.closed, CloseReason.no_response)
        assert _due(s, app, NOW + timedelta(days=30)) == []
        s.rollback()


def test_reminder_api_round_trip(client: TestClient) -> None:
    with Session(engine) as s:
        app = applied_app(s, days_ago=31)
        app.applied_at = datetime.now(UTC) - timedelta(days=31)
        s.add(app)
        s.commit()
        app_id = app.id
    mine = [r for r in client.get("/api/reminders").json() if r["application_id"] == app_id]
    assert {r["kind"] for r in mine} == {"followup", "ghost"}
    assert client.post(f"/api/reminders/{app_id}/followup:14/dismiss").status_code == 204
    assert client.post(f"/api/reminders/{app_id}/ghost/snooze", json={"days": 5}).status_code == 204
    assert not [r for r in client.get("/api/reminders").json() if r["application_id"] == app_id]
    r = client.post(f"/api/reminders/{app_id}/ghost/confirm")
    assert r.status_code == 200 and r.json()["stage"] == "closed"


# ------------------------------------------------------------------------------------ stats


def rows_for(s: Session, track: str, **kw) -> list[tracking.TrackedRow]:  # noqa: ANN003
    return tracking.tracked(s, track=[track], **kw)


def test_stats_rates_weeks_and_median(seeded: None) -> None:
    with Session(engine) as s:
        a = applied_app(s, days_ago=10, track="T-stats", country="FR", source="adzuna")
        b = applied_app(s, days_ago=3, track="T-stats", country="AE", source="bayt")
        c = applied_app(s, days_ago=2, track="T-stats", country="FR", source="adzuna")
        applied_app(s, days_ago=1, track="T-other")
        tracking.log_response(s, a, kind=ResponseKind.rejection,
                              received_on=(NOW - timedelta(days=6)).date())  # 4 days after
        tracking.log_interview(s, b, scheduled_at=NOW - timedelta(days=1),
                               type=InterviewType.hr)  # 2 days after
        out = tracking.stats(rows_for(s, "T-stats"))
        assert out["applied"] == 3
        assert out["response"] == {"count": 2, "total": 3, "rate": 0.667}
        assert out["interview"] == {"count": 1, "total": 3, "rate": 0.333}
        assert out["median_days_to_first_response"] == 3.0  # even count: mean of 2 and 4
        assert sum(w["count"] for w in out["per_week"]) == 3
        assert out["per_week"][0]["week"] == "2026-W38"  # 18 Sep
        fr = next(g for g in out["by_country"] if g["group"] == "FR")
        assert fr["applied"] == 2 and fr["response"]["count"] == 1
        bayt = next(g for g in out["by_source"] if g["group"] == "bayt")
        assert bayt["interview"] == {"count": 1, "total": 1, "rate": 1.0}
        assert out["by_track"] == [{"group": "T-stats", "applied": 3, "response": out["response"],
                                    "interview": out["interview"]}]
        tracking.log_response(s, c, kind=ResponseKind.other,
                              received_on=(NOW - timedelta(days=1)).date())  # 1 day after
        assert tracking.stats(rows_for(s, "T-stats"))["median_days_to_first_response"] == 2.0
        s.rollback()


def test_stats_with_no_replies_and_no_rows(seeded: None) -> None:
    with Session(engine) as s:
        applied_app(s, track="T-quiet")
        out = tracking.stats(rows_for(s, "T-quiet"))
        assert out["median_days_to_first_response"] is None
        assert out["response"]["rate"] == 0
        empty = tracking.stats([])
        assert empty["applied"] == 0 and empty["response"]["rate"] is None
        s.rollback()


def test_filters_by_date_country_and_source(seeded: None) -> None:
    with Session(engine) as s:
        applied_app(s, days_ago=20, track="T-filter", country="FR", source="adzuna")
        applied_app(s, days_ago=2, track="T-filter", country="AE", source="bayt")
        recent = rows_for(s, "T-filter", start=(NOW - timedelta(days=5)).date())
        assert [r.job.country for r in recent] == ["AE"]
        old = rows_for(s, "T-filter", end=(NOW - timedelta(days=5)).date())
        assert [r.job.country for r in old] == ["FR"]
        assert len(rows_for(s, "T-filter", country=["FR", "AE"])) == 2
        assert [r.job.source for r in rows_for(s, "T-filter", source=["bayt"])] == ["bayt"]
        s.rollback()


def test_csv_export_columns(client: TestClient) -> None:
    with Session(engine) as s:
        app = applied_app(s, track="T-csv")
        tracking.log_response(s, app, kind=ResponseKind.positive, received_on=None)
        s.commit()
    r = client.get("/api/applications/export.csv", params={"track": "T-csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert list(rows[0].keys()) == tracking.CSV_COLUMNS
    assert rows[0]["method"] == "company_site" and rows[0]["cv_version"] == "1"
    assert rows[0]["positive_replies"] == "1" and rows[0]["track"] == "T-csv"


# ------------------------------------------------------------------------ the whole flow (API)


def test_ready_to_closed_through_the_api(client: TestClient) -> None:
    with Session(engine) as s:
        app = make_app(s, track="T-flow")
        s.commit()
        app_id = app.id
    r = client.post(f"/api/applications/{app_id}/applied",
                    json={"method": "company_site", "applied_on": "2026-09-01"})
    assert r.status_code == 200 and r.json()["stage"] == "done"
    assert client.post(f"/api/applications/{app_id}/responses",
                       json={"kind": "positive", "received_on": "2026-09-05"}).status_code == 201
    r = client.post(f"/api/applications/{app_id}/interviews",
                    json={"scheduled_at": "2026-09-10T09:00:00Z", "type": "technical"})
    assert r.status_code == 201 and r.json()["round"] == 1
    iid = r.json()["id"]
    r = client.patch(f"/api/interviews/{iid}", json={"outcome": "failed"})
    assert r.json()["outcome"] == "failed"
    r = client.post(f"/api/applications/{app_id}/close", json={"reason": "rejected"})
    assert r.status_code == 200 and r.json()["stage"] == "closed"
    tracked = client.get("/api/applications/tracked", params={"track": "T-flow"}).json()
    assert len(tracked) == 1 and tracked[0]["days_to_first_response"] == 4.0
    assert tracked[0]["applied_cv_version"] == 1 and len(tracked[0]["interviews"]) == 1
    stats = client.get("/api/stats", params={"track": "T-flow"}).json()
    assert stats["applied"] == 1 and stats["interview"]["count"] == 1
    assert client.post(f"/api/applications/{app_id}/responses",
                       json={"kind": "bogus"}).status_code == 422


# ------------------------------------------------------------------------------------ today


def test_upcoming_interviews_next_14_days_pending_only(seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s, track="T-upcoming")
        soon = tracking.log_interview(s, app, scheduled_at=NOW + timedelta(days=2),
                                      type=InterviewType.technical)
        tracking.log_interview(s, app, scheduled_at=NOW + timedelta(days=20),
                               type=InterviewType.final)
        done = tracking.log_interview(s, app, scheduled_at=NOW + timedelta(days=1),
                                      type=InterviewType.hr)
        tracking.update_interview(s, done, outcome="passed")
        s.flush()
        mine = [i.id for i, a, _, _ in tracking.upcoming_interviews(s, NOW) if a.id == app.id]
        assert mine == [soon.id]
        s.rollback()


def test_today_includes_reminders_interviews_and_stats(client: TestClient) -> None:
    body = client.get("/api/today").json()
    assert {"reminders", "upcoming_interviews", "stats_summary"} <= body.keys()
    summary = body["stats_summary"]
    assert summary["applied_total"] >= summary["responded"] >= 0
