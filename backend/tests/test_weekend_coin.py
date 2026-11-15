"""Weekend coin: +1 token for a job marked Applied on a Saturday or Sunday (Tunis time)."""

from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, func, select

from app.db import engine
from app.models import TokenEntry, WeekendCoin
from app.models.enums import ApplyMethod
from app.services import motivation as mv
from app.services import tracking
from app.services.motivation import activity, rewards, weekend
from app.services.motivation.streak import compute
from tests.test_tracking import make_app

# Africa/Tunis is UTC+1 all year. 2026-10-02 is a Friday.
FRI_NOON = datetime(2026, 10, 2, 12, tzinfo=UTC)
SAT_NOON = datetime(2026, 10, 3, 12, tzinfo=UTC)
SUN_NOON = datetime(2026, 10, 4, 12, tzinfo=UTC)


def _apply(s: Session, at: datetime, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN202
    monkeypatch.setattr(weekend, "utcnow", lambda: at)
    app = make_app(s)
    tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.company_site)
    return app


def _coins(s: Session) -> int:
    return int(s.exec(select(func.count()).select_from(WeekendCoin)).one())


def _weekend_tokens(s: Session) -> int:
    return int(s.exec(select(func.coalesce(func.sum(TokenEntry.amount), 0))
                      .where(TokenEntry.kind == "weekend")).one())


@pytest.mark.parametrize("at", [SAT_NOON, SUN_NOON])
def test_saturday_and_sunday_earn_one_token(seeded: None, monkeypatch, at) -> None:  # noqa: ANN001
    with Session(engine) as s:
        before = rewards.balance(s)
        app = _apply(s, at, monkeypatch)
        assert rewards.balance(s) == before + 1
        coin = s.exec(select(WeekendCoin).where(WeekendCoin.application_id == app.id)).one()
        assert coin.day == mv.local_day(at, mv.settings(s))
        s.rollback()


def test_a_weekday_earns_nothing(seeded: None, monkeypatch) -> None:  # noqa: ANN001
    with Session(engine) as s:
        before = rewards.balance(s)
        _apply(s, FRI_NOON, monkeypatch)
        assert rewards.balance(s) == before and _coins(s) == 0
        s.rollback()


def test_one_coin_per_job_even_after_undo_and_mark_again(seeded: None, monkeypatch) -> None:  # noqa: ANN001
    with Session(engine) as s:
        before = rewards.balance(s)
        app = _apply(s, SAT_NOON, monkeypatch)
        tracking.undo_applied(s, app)
        tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.company_site)
        assert rewards.balance(s) == before + 1 and _coins(s) == 1
        assert weekend.award(s, app, SUN_NOON) is False  # directly, too
        assert _weekend_tokens(s) == 1
        s.rollback()


def test_no_contact_or_email_needed(seeded: None, monkeypatch) -> None:  # noqa: ANN001
    """make_app has no contact, no draft and no verification: the coin is still paid, and the
    sent-only setting (count_emails on) changes nothing."""
    with Session(engine) as s:
        before = rewards.balance(s)
        monkeypatch.setattr(mv, "settings", lambda _s: {**mv.DEFAULT_MOTIVATION,
                                                         "chests_since": "2020-01-01",
                                                         "count_emails": True})
        _apply(s, SAT_NOON, monkeypatch)
        assert rewards.balance(s) == before + 1
        s.rollback()


def test_the_streak_is_unchanged_by_the_coin(seeded: None, monkeypatch) -> None:  # noqa: ANN001
    with Session(engine) as s:
        cfg = {**mv.DEFAULT_MOTIVATION, "chests_since": "2020-01-01"}
        today = date(2026, 10, 3)
        without = compute(activity.per_day(s, cfg), today, cfg["daily_goal"])
        _apply(s, SAT_NOON, monkeypatch)
        counts = activity.per_day(s, cfg)
        with_coin = compute(counts, today, cfg["daily_goal"])
        # the application is counted for the day (as before this feature), the streak is not
        assert with_coin.current == without.current == 0
        assert with_coin.today_state == without.today_state == "weekend_idle"
        s.rollback()


def test_a_failing_award_logs_a_warning_and_never_breaks_mark_applied(
        seeded: None, monkeypatch, caplog) -> None:  # noqa: ANN001
    def boom(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("ledger exploded")

    with Session(engine) as s:
        monkeypatch.setattr(weekend, "utcnow", lambda: SAT_NOON)
        monkeypatch.setattr(weekend, "TokenEntry", boom)
        # the migration fixture's alembic logging config disables loggers created before it ran
        monkeypatch.setattr(weekend.log, "disabled", False)
        app = make_app(s)
        with caplog.at_level("WARNING", logger=weekend.log.name):
            done = tracking.mark_applied(s, app, applied_on=None,
                                         method=ApplyMethod.company_site)
        assert done.web_applied_at is not None  # the application went through
        records = [r for r in caplog.records if r.name == weekend.log.name]
        assert len(records) == 1 and records[0].levelname == "WARNING"
        assert f"application {app.id}" in records[0].getMessage()
        assert _coins(s) == 0
        s.rollback()


@pytest.mark.parametrize(("at", "expected"), [
    (datetime(2026, 10, 2, 22, 59, tzinfo=UTC), False),  # Fri 23:59 Tunis
    (datetime(2026, 10, 2, 23, 1, tzinfo=UTC), True),    # Sat 00:01 Tunis
    (datetime(2026, 10, 4, 22, 59, tzinfo=UTC), True),   # Sun 23:59 Tunis
    (datetime(2026, 10, 4, 23, 1, tzinfo=UTC), False),   # Mon 00:01 Tunis
])
def test_day_boundaries_use_your_timezone(at: datetime, expected: bool) -> None:
    cfg = {**mv.DEFAULT_MOTIVATION}
    assert weekend.is_weekend(at, cfg) is expected
