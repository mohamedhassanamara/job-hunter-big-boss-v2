"""Motivation (Phase 11): the streak (weekends, resets, today in progress, timezone), what counts
(click day, undo, emails, LinkedIn), chests (carry-over, goal changes, never taken back), the
token ledger and shop, uploads, and undoing "Mark applied". Offline."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.db import engine
from app.models import (
    ApplicationEvent,
    ApplicationResponse,
    ChestOpen,
    CVVersion,
    OutreachDraft,
    ShopItem,
    TokenEntry,
)
from app.models.enums import ApplyMethod, DraftStatus, EventKind, LinkedInStatus, Stage
from app.services import linkedin_track as lt
from app.services import motivation as mv
from app.services import tracking
from app.services.motivation import activity, files, rewards
from app.services.motivation.streak import compute
from tests.test_linkedin_track import job_with_people
from tests.test_tracking import make_app

CFG = {**mv.DEFAULT_MOTIVATION, "chests_since": "2020-01-01"}
WED = date(2026, 9, 30)  # a Wednesday


def days(*pairs: tuple[int, int]) -> dict[date, int]:
    """{WED + offset: count}"""
    return {WED + timedelta(days=o): n for o, n in pairs}


# --------------------------------------------------------------------------------- streak


def test_the_example_wednesday_to_monday_is_six() -> None:
    counts = days((0, 5), (1, 5), (2, 5), (5, 5))  # Wed Thu Fri, (Sat Sun), Mon
    expected = [1, 2, 3, 4, 5, 6]
    for offset, want in enumerate(expected):
        assert compute(counts, WED + timedelta(days=offset), 5).current == want


def test_a_missed_friday_resets_and_the_weekend_never_revives_it() -> None:
    counts = days((0, 5), (1, 5), (2, 3), (5, 5))  # Friday: 3/5
    sat, sun, mon = (WED + timedelta(days=o) for o in (3, 4, 5))
    assert compute(counts, sat, 5).current == 0
    assert compute(counts, sun, 5).current == 0
    st = compute(counts, mon, 5)
    assert st.current == 1 and st.longest == 2


def test_today_is_in_progress_never_broken() -> None:
    counts = days((0, 5), (1, 2))  # Thursday so far: 2/5
    st = compute(counts, WED + timedelta(days=1), 5)
    assert (st.current, st.today_state, st.today_count, st.goal) == (1, "in_progress", 2, 5)
    tomorrow = compute(counts, WED + timedelta(days=2), 5)
    assert tomorrow.current == 0  # Thursday ended below the goal


def test_starting_on_a_weekend_counts_nothing_until_a_workday() -> None:
    sat = WED + timedelta(days=3)
    assert compute({sat: 9}, sat, 5).current == 0
    assert compute({sat: 9}, sat, 5).today_state == "weekend_idle"


def test_the_calendar_covers_eight_weeks_from_monday() -> None:
    st = compute(days((0, 5)), WED, 5)
    assert len(st.calendar) == 56 and st.calendar[0].day.weekday() == 0
    states = {d.day: d.state for d in st.calendar}
    assert states[WED] == "met" and states[WED + timedelta(days=1)] == "future"
    assert states[WED - timedelta(days=1)] == "idle"  # before your first day


def test_local_day_uses_your_timezone() -> None:
    late_friday = datetime(2026, 10, 2, 23, 30, tzinfo=UTC)  # 00:30 Saturday in Tunis
    assert mv.local_day(late_friday, CFG) == date(2026, 10, 3)
    assert mv.local_day(datetime(2026, 10, 2, 22, 59, tzinfo=UTC), CFG) == date(2026, 10, 2)
    assert mv.local_day(datetime(2026, 10, 2, 23, 30), CFG) == date(2026, 10, 3)  # naive = UTC
    assert mv.local_day(late_friday, {**CFG, "timezone": "UTC"}) == date(2026, 10, 2)


# --------------------------------------------------------------------------- what counts


def _click(s: Session, app_id: int, at: datetime) -> None:
    ev = s.exec(select(ApplicationEvent).where(ApplicationEvent.application_id == app_id,
                                               ApplicationEvent.kind == EventKind.applied)).one()
    ev.at = at
    s.add(ev)
    s.flush()


def test_applications_count_on_the_click_day_and_drop_out_when_undone(seeded: None) -> None:
    day = date(2020, 1, 6)
    with Session(engine) as s:
        app = make_app(s)
        tracking.mark_applied(s, app, applied_on=date(2019, 12, 1), method=ApplyMethod.other)
        _click(s, app.id, datetime(2020, 1, 6, 10, tzinfo=UTC))
        counts = activity.per_day(s, CFG)
        assert counts[day] == 1 and counts[date(2019, 12, 1)] == 0  # not the date you picked
        tracking.undo_applied(s, app)
        assert activity.per_day(s, CFG)[day] == 0
        s.rollback()


def test_emails_and_linkedin_requests_count_only_when_enabled(seeded: None) -> None:
    email_day, li_day = date(2020, 2, 3), date(2020, 2, 4)
    with Session(engine) as s:
        app = make_app(s)
        s.add(OutreachDraft(application_id=app.id, subject="s", body="b",
                            status=DraftStatus.sent, sent_at=datetime(2020, 2, 3, 9, tzinfo=UTC)))
        li_app, _ = job_with_people(s)
        row = lt.add(s, li_app, full_name="Lin Kedin", title="Recruiter", linkedin_url=None)
        lt.set_status(s, row, LinkedInStatus.sent)
        row.sent_at = datetime(2020, 2, 4, 9, tzinfo=UTC)
        s.flush()
        off = activity.per_day(s, CFG)
        assert off[email_day] == 0 and off[li_day] == 0
        on = activity.per_day(s, {**CFG, "count_emails": True, "count_linkedin": True})
        assert on[email_day] == 1 and on[li_day] == 1
        lt.set_status(s, row, LinkedInStatus.to_contact)  # undo the request
        assert activity.per_day(s, {**CFG, "count_linkedin": True})[li_day] == 0
        s.rollback()


def test_a_sent_email_alone_does_not_move_the_streak_by_default(seeded: None) -> None:
    """The reported case: an email goes out (the job reaches Done), nothing is marked Applied.
    By default only "Mark applied" counts; with `count_emails` the email counts as one. Compared
    against the counts before this email is added, so the sandbox's own sent drafts (dated
    relative to the clock) never matter."""
    # 23:30 UTC on the 20th is already the 21st in Tunis: the day boundary must not hide it
    sent = datetime(2026, 10, 20, 23, 30, tzinfo=UTC)
    today, utc_day = date(2026, 10, 21), date(2026, 10, 20)
    emails = {**CFG, "count_emails": True}
    with Session(engine) as s:
        app = make_app(s)
        off_before, on_before = activity.per_day(s, CFG), activity.per_day(s, emails)
        s.add(OutreachDraft(application_id=app.id, subject="s", body="b",
                            status=DraftStatus.sent, sent_at=sent))
        s.flush()
        off, on = activity.per_day(s, CFG), activity.per_day(s, emails)
        assert off == off_before  # by default the sent email moves nothing
        assert on[today] == on_before[today] + 1  # counted on the Tunis day...
        assert on[utc_day] == on_before[utc_day]  # ...not on the UTC day
        st = compute(on, today, CFG["daily_goal"])
        assert st.today_count == on[today] and st.today_state == "in_progress"
        s.rollback()


# ------------------------------------------------------------------------- undo applied


def test_undo_applied_puts_everything_back(seeded: None, client: TestClient) -> None:
    with Session(engine) as s:
        app = make_app(s, stage=Stage.cv_ready)
        s.commit()
        app_id = app.id
    assert client.post(f"/api/applications/{app_id}/applied",
                       json={"method": "company_site"}).status_code == 200
    with Session(engine) as s:
        cv = s.exec(select(CVVersion).where(CVVersion.application_id == app_id)).one()
        assert cv.locked_at is not None
    card = client.delete(f"/api/applications/{app_id}/applied")
    assert card.status_code == 200 and card.json()["stage"] == "cv_ready"
    with Session(engine) as s:
        app = s.get(tracking.Application, app_id)
        cv = s.exec(select(CVVersion).where(CVVersion.application_id == app_id)).one()
        assert app.web_applied_at is None and app.applied_at is None and cv.locked_at is None
        kinds = [e.kind for e in s.exec(select(ApplicationEvent).where(
            ApplicationEvent.application_id == app_id)).all()]
        assert kinds[-1] == EventKind.applied_undone
    assert client.delete(f"/api/applications/{app_id}/applied").status_code == 422  # not applied


def test_undo_applied_is_refused_after_a_reply(seeded: None) -> None:
    with Session(engine) as s:
        app = make_app(s)
        tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.other)
        s.add(ApplicationResponse(application_id=app.id, kind="rejection"))
        s.flush()
        with pytest.raises(tracking.TrackingError, match="reply or interview"):
            tracking.undo_applied(s, app)
        s.rollback()


# ------------------------------------------------------------------------------- chests


def _used(s: Session) -> int:
    return int(s.exec(select(func.coalesce(func.sum(ChestOpen.cost), 0))).one())


def test_chests_unlock_carry_over_and_are_never_taken_back(seeded: None, monkeypatch) -> None:  # noqa: ANN001
    with Session(engine) as s:
        base = _used(s)
        monkeypatch.setattr(activity, "total_since", lambda *a: base + 65)
        state = rewards.chests(s, {**CFG, "chest_goal": 30})
        assert (state.available, state.progress) == (2, 5)  # two waiting, 5 carried over
        before = rewards.balance(s)
        first = rewards.open_chest(s, {**CFG, "chest_goal": 30})
        assert 1 <= first.tokens <= 10 and first.cost == 30
        rewards.open_chest(s, {**CFG, "chest_goal": 30})
        with pytest.raises(rewards.RewardError, match="No chest"):
            rewards.open_chest(s, {**CFG, "chest_goal": 30})
        won = rewards.balance(s) - before
        # A smaller goal later never re-awards the 60 applications already used.
        assert rewards.chests(s, {**CFG, "chest_goal": 10}).available == 0
        # Undoing applications never takes chests or tokens back.
        monkeypatch.setattr(activity, "total_since", lambda *a: base + 10)
        state = rewards.chests(s, {**CFG, "chest_goal": 30})
        assert (state.available, state.progress) == (0, 0)
        assert rewards.balance(s) - before == won


def test_chest_draws_are_one_to_ten(seeded: None, monkeypatch) -> None:  # noqa: ANN001
    with Session(engine) as s:
        base = _used(s)
        monkeypatch.setattr(activity, "total_since", lambda *a: base + 40)
        draws = [rewards.open_chest(s, {**CFG, "chest_goal": 1}).tokens for _ in range(40)]
        assert set(draws) <= set(range(1, 11)) and len(set(draws)) > 3


# ------------------------------------------------------------------------- tokens, shop


def test_the_shop_never_takes_the_balance_below_zero(seeded: None) -> None:
    with Session(engine) as s:
        start = rewards.balance(s)
        if start:
            s.add(TokenEntry(amount=-start, kind="adjust", note="test reset"))
            s.commit()
        item = rewards.save_item(s, None, name="Coffee out", price=5, emoji="☕", image_name=None)
        with pytest.raises(rewards.RewardError, match="Not enough tokens: 0 of 5"):
            rewards.buy(s, item)
        s.add(TokenEntry(amount=7, kind="adjust", note="test"))
        s.commit()
        bought = rewards.buy(s, item)
        assert rewards.balance(s) == 2 and bought.name == "Coffee out" and bought.price == 5
        with pytest.raises(rewards.RewardError, match="Not enough"):
            rewards.buy(s, item)
        assert rewards.set_redeemed(s, bought, True).redeemed_at is not None
        assert rewards.set_redeemed(s, bought, False).redeemed_at is None
        item.archived = True
        with pytest.raises(rewards.RewardError, match="archived"):
            rewards.buy(s, item)
        with pytest.raises(rewards.RewardError, match="price"):
            rewards.save_item(s, None, name="Free", price=0, emoji=None, image_name=None)


def test_shop_api_round_trip(client: TestClient) -> None:
    shop = client.post("/api/motivation/shop", json={"name": "Movie night", "price": 3}).json()
    item = next(i for i in shop["items"] if i["name"] == "Movie night")
    poor = client.post(f"/api/motivation/shop/{item['id']}/buy")
    if shop["balance"] < 3:
        assert poor.status_code == 409
    archived = client.patch(f"/api/motivation/shop/{item['id']}", json={"archived": True}).json()
    assert next(i for i in archived["items"] if i["id"] == item["id"])["archived"]


# ------------------------------------------------------------------------------ uploads

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def media(tmp_path: Path, monkeypatch) -> Path:  # noqa: ANN001
    monkeypatch.setattr(files, "ROOT", tmp_path)
    return tmp_path


def test_goal_uploads_are_checked_stored_and_removed(client: TestClient, media: Path) -> None:
    up = client.post("/api/motivation/goals", files={"file": ("me.png", PNG, "image/png")},
                     data={"caption": "Senior data engineer by 2028"})
    assert up.status_code == 201, up.text
    tile = up.json()
    stored = media / "real" / tile["file_name"]
    assert stored.read_bytes() == PNG and tile["kind"] == "image"
    assert client.get(f"/api/motivation/files/{tile['file_name']}").content == PNG
    fake = client.post("/api/motivation/goals", files={"file": ("x.png", b"not an image", "x")})
    assert fake.status_code == 415
    assert client.post("/api/motivation/goals",
                       files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 415
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
    video = client.post("/api/motivation/goals", files={"file": ("v.mp4", mp4, "video/mp4")})
    assert video.status_code == 201 and video.json()["kind"] == "video"
    ids = [t["id"] for t in client.get("/api/motivation/goals").json()]
    order = client.put("/api/motivation/goals/order", json={"ids": list(reversed(ids))}).json()
    assert [t["id"] for t in order] == list(reversed(ids))
    assert client.patch(f"/api/motivation/goals/{tile['id']}",
                        json={"caption": "  Lead  "}).json()["caption"] == "Lead"
    assert client.delete(f"/api/motivation/goals/{tile['id']}").status_code == 204
    assert not stored.exists()
    assert client.get("/api/motivation/files/../../jobhunter.db").status_code == 404


def test_the_upload_limit_is_a_setting(client: TestClient, media: Path) -> None:
    cfg = client.get("/api/settings").json()["values"]["motivation"]
    client.put("/api/settings/motivation", json={"value": {**cfg, "max_upload_mb": 1}})
    big = PNG + b"\x00" * (1024 * 1024)
    assert client.post("/api/motivation/goals",
                       files={"file": ("big.png", big, "image/png")}).status_code == 413
    client.put("/api/settings/motivation", json={"value": cfg})
    assert client.post("/api/sandbox/reset").status_code == 204
    demo = client.post("/api/motivation/images", files={"file": ("i.png", PNG, "image/png")},
                       headers={"X-Workspace": "demo"})
    assert demo.status_code == 201 and (media / "demo" / demo.json()["name"]).exists()


# ---------------------------------------------------------------------- settings, summary


def test_the_toggle_hides_it_and_keeps_when_chests_started(client: TestClient) -> None:
    cfg = client.get("/api/settings").json()["values"]["motivation"]
    since = cfg["chests_since"]
    off = client.put("/api/settings/motivation",
                     json={"value": {**cfg, "enabled": False, "chests_since": "1999-01-01"}})
    assert off.status_code == 200
    summary = client.get("/api/motivation/summary").json()
    assert summary["enabled"] is False and summary["chests"]["since"] == since
    bad = client.put("/api/settings/motivation", json={"value": {**cfg, "timezone": "Mars/Base"}})
    assert bad.status_code == 422
    client.put("/api/settings/motivation", json={"value": cfg})


def test_woop_wins_and_suggestion(client: TestClient) -> None:
    w = client.post("/api/motivation/woops", json={"wish": "Land a data role", "outcome": "Visa",
                                                   "obstacle": "Fear", "plan": "If… then…"})
    assert w.status_code == 201 and client.get("/api/motivation/woops").json()[0]["wish"]
    assert client.post("/api/motivation/woops", json={"wish": " "}).status_code == 422
    win = client.post("/api/motivation/journal", json={"text": "Sent 5 applications"}).json()
    wins = client.get("/api/motivation/wins").json()
    assert wins["journal"][0]["id"] == win["id"] and "longest_streak" in wins
    assert client.get("/api/motivation/suggestion").json()["href"].startswith("/")


def test_items_listed_in_shop_order(seeded: None) -> None:
    with Session(engine) as s:
        a = rewards.save_item(s, None, name="A", price=1, emoji=None, image_name=None)
        b = rewards.save_item(s, None, name="B", price=1, emoji=None, image_name=None)
        names = [i.name for i in rewards.items(s) if i.id in (a.id, b.id)]
        assert names == ["A", "B"] and s.get(ShopItem, a.id).position < b.position
