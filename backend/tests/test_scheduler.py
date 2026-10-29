from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.services import scheduler


@pytest.fixture()
def sched():  # noqa: ANN201
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler._scheduler = BackgroundScheduler()
    scheduler._scheduler.start(paused=True)  # jobs are registered, nothing ever fires
    yield scheduler._scheduler
    scheduler._scheduler.shutdown(wait=False)
    scheduler._scheduler = None


def _cron(job) -> dict[str, str]:  # noqa: ANN001
    return {f.name: str(f) for f in job.trigger.fields}


def test_legacy_single_time_is_one_daily_run() -> None:
    assert scheduler.normalize({"enabled": True, "time": "07:30"}) == (["07:30"], False)
    assert scheduler.normalize(None) == (["07:00"], False)


def test_two_times_weekdays_only(sched) -> None:  # noqa: ANN001
    scheduler.configure({"enabled": True, "times": ["15:00", "07:00"], "weekdays_only": True})
    jobs = sorted(sched.get_jobs(), key=lambda j: j.id)
    assert [j.id for j in jobs] == ["daily-discovery-0", "daily-discovery-1"]
    assert [(_cron(j)["hour"], _cron(j)["day_of_week"]) for j in jobs] == [
        ("7", "mon-fri"), ("15", "mon-fri")]
    # Saturday 2026-10-31 14:00 → the next run is Monday 07:00
    nxt = jobs[0].trigger.get_next_fire_time(None, datetime(2026, 10, 31, 14).astimezone())
    assert nxt.weekday() == 0 and nxt.hour == 7


def test_reconfigure_replaces_and_disabled_removes(sched) -> None:  # noqa: ANN001
    scheduler.configure({"enabled": True, "times": ["07:00", "15:00"]})
    scheduler.configure({"enabled": True, "times": ["09:00"]})
    assert [j.id for j in sched.get_jobs()] == ["daily-discovery-0"]
    assert _cron(sched.get_jobs()[0])["day_of_week"] == "*"
    scheduler.configure({"enabled": False, "times": ["09:00"]})
    assert sched.get_jobs() == []


def test_schedule_setting_is_validated_and_normalized(client: TestClient) -> None:
    ok = client.put("/api/settings/schedule", json={"value": {
        "enabled": True, "times": ["15:00", "07:00", "07:00"], "weekdays_only": True}})
    assert ok.status_code == 200
    assert ok.json()["values"]["schedule"] == {
        "enabled": True, "times": ["07:00", "15:00"], "weekdays_only": True}
    too_many = [f"0{n}:00" for n in range(7)]
    for bad in (["25:00"], ["7:00"], too_many):
        r = client.put("/api/settings/schedule", json={"value": {"enabled": True, "times": bad}})
        assert r.status_code == 422
