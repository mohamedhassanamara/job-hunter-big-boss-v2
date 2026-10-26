from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.db import demo_engine, engine
from app.models import Application, AppSetting, UsageEvent
from app.services import usage

T0 = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


def ev(kind: str, name: str, minutes: float = 0, **kw) -> dict:
    return {"kind": kind, "name": name, "at": (T0 + timedelta(minutes=minutes)).isoformat(), **kw}


def wipe() -> None:
    with Session(engine) as s:
        usage.clear(s)
        row = s.exec(select(AppSetting).where(AppSetting.key == "usage_log")).first()
        if row:
            s.delete(row)
        s.commit()


def test_records_and_clears(client) -> None:
    wipe()
    r = client.post("/api/usage/events", json={"events": [
        ev("screen", "/jobs/:id/cv", duration_ms=30_000, wall_ms=40_000, ref_kind="job", ref_id=7),
        ev("action", "approve_cv", 1),
    ]})
    assert r.json() == {"enabled": True, "stored": 2}
    assert client.delete("/api/usage").json() == {"deleted": 2}
    with Session(engine) as s:
        assert s.exec(select(UsageEvent)).first() is None


def test_rejects_free_text_and_bad_values(client) -> None:
    wipe()
    bad = [
        ev("screen", "Dear Anna, I am writing about the Senior role"),  # page text, not a pattern
        ev("screen", "/jobs/:id?q=secret<script>"),
        ev("action", "approve_cv", duration_ms=-1),
        ev("action", "approve_cv", duration_ms=True),
        ev("nope", "x"),
        {"kind": "action", "name": "queue_add", "at": "not a date"},
        {"kind": "action", "name": "queue_add", "at": "2026-10-26T10:00:00"},  # no timezone
        ev("action", "queue_add", ref_kind="job; drop", ref_id=1),
    ]
    assert client.post("/api/usage/events", json={"events": bad}).json()["stored"] == 0


def test_job_id_resolved_from_application(client) -> None:
    wipe()
    with Session(engine) as s:
        app = s.exec(select(Application)).first()
        job_id, app_id = app.job_id, app.id
    client.post("/api/usage/events", json={"events": [
        ev("action", "mark_applied", ref_kind="app", ref_id=app_id)]})
    with Session(engine) as s:
        assert s.exec(select(UsageEvent)).one().job_id == job_id


def test_switch_off_stores_nothing(client) -> None:
    wipe()
    r = client.put("/api/settings/usage_log", json={"value": {"enabled": False}})
    assert r.json()["values"]["usage_log"] == {"enabled": False}
    assert client.post("/api/usage/events", json={"events": [ev("action", "queue_add")]}
                       ).json() == {"enabled": False, "stored": 0}
    client.put("/api/settings/usage_log", json={"value": {"enabled": True}})
    wipe()


def test_default_is_on_and_value_is_validated(client) -> None:
    wipe()
    assert client.get("/api/settings").json()["values"]["usage_log"] == {"enabled": True}
    bad = client.put("/api/settings/usage_log", json={"value": {"enabled": "yes"}})
    assert bad.status_code == 422


def test_sandbox_is_never_logged(client) -> None:
    assert client.post("/api/sandbox/reset").status_code == 204
    r = client.post("/api/usage/events", headers={"X-Workspace": "demo"},
                    json={"events": [ev("action", "queue_add")]})
    assert r.json()["stored"] == 0
    with Session(demo_engine) as s:
        assert s.exec(select(UsageEvent)).first() is None


def _row(kind, name, minutes, **kw) -> UsageEvent:
    return UsageEvent(at=T0 + timedelta(minutes=minutes), kind=kind, name=name, **kw)


def test_report_math() -> None:
    rows = [
        _row("screen", "/discover", 0, duration_ms=60_000, wall_ms=70_000),
        _row("screen", "/jobs/:id/cv", 2, duration_ms=120_000, wall_ms=150_000, job_id=5),
        _row("action", "approve_cv", 3, job_id=5),
        _row("screen", "/jobs/:id", 5, duration_ms=30_000, wall_ms=30_000, job_id=5),
        _row("screen", "/jobs/:id/cv", 6, duration_ms=60_000, wall_ms=60_000, job_id=5),
        _row("wait", "POST /applications/:id/cv/generate", 3, duration_ms=100_000,
             screen="/jobs/:id/cv", job_id=5),
        _row("wait", "POST /outreach/drafts/:id/approve", 4, duration_ms=25_000),
        _row("idle", "idle", 20, duration_ms=8 * 60_000),
        _row("action", "queue_add", 30, job_id=5),
    ]
    r = usage.build_report(rows)
    assert r["screen_visits"] == 4 and r["screen_switches"] == 3
    cv = next(d for d in r["per_screen"] if d["screen"] == "/jobs/:id/cv")
    assert (cv["visits"], cv["active_s"], cv["wall_s"]) == (2, 180.0, 210.0)
    assert r["per_screen"][0]["screen"] == "/jobs/:id/cv"  # most active time first
    assert r["per_job"] == [{"job_id": 5, "screens": 3, "distinct": 2, "active_s": 210.0}]
    assert r["longest_waits"][0]["seconds"] == 100.0 and r["waits_total_s"] == 125.0
    assert r["idle_gaps"] == [{"minutes": 8.0, "at": (T0 + timedelta(minutes=20)).isoformat()}]
    assert r["action_gaps_over_5_min"][0]["minutes"] == 27.0
    assert r["actions"] == {"approve_cv": 1, "queue_add": 1}
    assert "approve_cv" in usage.format_report(r)


def test_sessions_split_on_long_silence() -> None:
    rows = [_row("action", "a", 0), _row("action", "b", 60), _row("action", "c", 60 + 91)]
    groups = usage.split_sessions(rows)
    assert [len(g) for g in groups] == [2, 1]
