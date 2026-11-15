"""Streak freezes: purchase, the cap of 2, the price rules, the unique frozen day, and how a frozen
day counts in the streak. No model calls; the real workspace is never touched (temp DB)."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.db import engine
from app.models import StreakFreeze, TokenEntry
from app.services import motivation as mv
from app.services.motivation import freezes, rewards
from app.services.motivation.rewards import RewardError
from app.services.motivation.streak import compute

CFG = {**mv.DEFAULT_MOTIVATION, "chests_since": "2020-01-01"}  # freeze_price 10
WED = date(2026, 9, 30)  # a Wednesday


def _fund(s: Session, tokens: int) -> None:
    """Make the balance exactly `tokens` (the sandbox seed leaves a few)."""
    s.add(TokenEntry(amount=tokens - rewards.balance(s), kind="adjust", note="test"))
    s.commit()


def _rows(s: Session) -> tuple[int, int]:
    return (int(s.exec(select(func.count()).select_from(StreakFreeze)).one()),
            int(s.exec(select(func.count()).select_from(TokenEntry)).one()))


def test_the_default_price_is_ten() -> None:
    assert mv.DEFAULT_MOTIVATION["freeze_price"] == 10 and freezes.CAP == 2


def test_buying_deducts_the_price_once_and_records_it(seeded: None) -> None:
    with Session(engine) as s:
        _fund(s, 25)
        row = freezes.buy(s, CFG)
        assert rewards.balance(s) == 15 and row.price == 10 and row.used_on is None
        entry = s.get(TokenEntry, row.purchase_entry_id)
        assert entry.amount == -10 and entry.kind == "freeze"
        assert freezes.owned(s) == 1


def test_a_later_price_change_never_touches_an_existing_freeze(seeded: None) -> None:
    with Session(engine) as s:
        _fund(s, 40)
        first = freezes.buy(s, CFG)
        second = freezes.buy(s, {**CFG, "freeze_price": 4})
        assert (first.price, second.price) == (10, 4)
        s.refresh(first)
        assert first.price == 10 and rewards.balance(s) == 40 - 10 - 4


def test_the_cap_of_two_refuses_a_third_and_writes_nothing(seeded: None) -> None:
    with Session(engine) as s:
        _fund(s, 100)
        freezes.buy(s, CFG)
        freezes.buy(s, CFG)
        before = _rows(s)
        with pytest.raises(RewardError, match="2 freezes"):
            freezes.buy(s, CFG)
        assert _rows(s) == before and rewards.balance(s) == 80 and freezes.owned(s) == 2
        assert freezes.state(s, CFG).can_buy is False


def test_an_insufficient_balance_leaves_no_ledger_entry_and_no_freeze(seeded: None) -> None:
    with Session(engine) as s:
        _fund(s, 9)
        before = _rows(s)
        with pytest.raises(RewardError, match="Not enough tokens"):
            freezes.buy(s, CFG)
        assert _rows(s) == before and rewards.balance(s) == 9
        st = freezes.state(s, CFG)
        assert st.can_buy is False and "1 more token" in (st.reason or "")


@pytest.mark.parametrize("bad", [0, -3, "10", 2.5, True, None])
def test_a_price_must_be_a_positive_whole_number(seeded: None, bad) -> None:  # noqa: ANN001
    with Session(engine) as s:
        _fund(s, 50)
        before = _rows(s)
        with pytest.raises(RewardError, match="positive whole number"):
            freezes.buy(s, {**CFG, "freeze_price": bad})
        assert _rows(s) == before


def test_unused_freezes_coexist_and_a_day_can_be_frozen_once(seeded: None) -> None:
    """SQLite treats NULLs as distinct in a unique index: any number of unused rows, but two
    freezes on the same day are rejected."""
    with Session(engine) as s:
        s.add_all([StreakFreeze(price=10), StreakFreeze(price=10), StreakFreeze(price=10)])
        s.commit()  # three unused rows (used_on NULL) are fine
        assert freezes.owned(s) >= 3
        s.add(StreakFreeze(price=10, used_on=WED))
        s.commit()
        s.add(StreakFreeze(price=10, used_on=WED))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        s.add(StreakFreeze(price=10, used_on=WED + timedelta(days=1)))
        s.commit()  # another day is fine
        assert freezes.used_days(s) >= {WED, WED + timedelta(days=1)}
        s.rollback()


# ------------------------------------------------------------------ the streak with a freeze


def test_a_frozen_workday_counts_one_and_shows_as_a_freeze() -> None:
    counts = {WED - timedelta(days=1): 5, WED: 0}
    plain = compute(counts, WED + timedelta(days=1), 5)  # Thursday: Wed missed -> reset
    assert plain.current == 0
    st = compute(counts, WED + timedelta(days=1), 5, frozen={WED})
    day = {d.day: d for d in st.calendar}[WED]
    assert day.state == "freeze" and day.count == 0 and day.streak == 2
    assert st.current == 2  # Tue met + Wed frozen; Thursday is in progress


def test_a_frozen_day_that_later_meets_the_goal_counts_once() -> None:
    counts = {WED - timedelta(days=1): 5, WED: 5}
    st = compute(counts, WED, 5, frozen={WED})
    assert st.current == 2 and st.today_state == "met"
    assert {d.day: d for d in st.calendar}[WED].state == "met"


def test_a_freeze_on_a_weekend_changes_nothing() -> None:
    sat = WED + timedelta(days=3)
    counts = {WED: 5, WED + timedelta(days=1): 5, WED + timedelta(days=2): 5}
    assert compute(counts, sat, 5, frozen={sat}).current == compute(counts, sat, 5).current


def test_today_frozen_is_a_completed_day() -> None:
    st = compute({WED - timedelta(days=1): 5}, WED, 5, frozen={WED})
    assert st.today_state == "freeze" and st.current == 2


# ------------------------------------------------------------------------------- the API


def test_the_shop_lists_the_freeze_even_with_no_shop_items(client: TestClient) -> None:
    with Session(engine) as s:
        _fund(s, 3)
    shop = client.get("/api/motivation/shop").json()
    assert shop["freeze"] == {"price": 10, "owned": 0, "cap": 2, "can_buy": False,
                              "reason": "7 more tokens needed"}


def test_buying_a_freeze_through_the_api(client: TestClient) -> None:
    with Session(engine) as s:
        _fund(s, 25)
    r = client.post("/api/motivation/freeze/buy")
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 15 and body["freeze"]["owned"] == 1 and body["freeze"]["can_buy"]
    assert client.post("/api/motivation/freeze/buy").json()["freeze"]["owned"] == 2
    again = client.post("/api/motivation/freeze/buy")  # cap (and the balance is 5)
    assert again.status_code == 409


def test_the_price_is_a_validated_setting(client: TestClient) -> None:
    current = client.get("/api/settings").json()["values"]["motivation"]
    assert current["freeze_price"] == 10
    for bad in (0, -1, "10", 1.5, True):
        r = client.put("/api/settings/motivation", json={"value": {**current, "freeze_price": bad}})
        assert r.status_code == 422, bad
    ok = client.put("/api/settings/motivation", json={"value": {**current, "freeze_price": 12}})
    assert ok.status_code == 200
    with Session(engine) as s:
        _fund(s, 50)
    assert client.get("/api/motivation/shop").json()["freeze"]["price"] == 12
    client.put("/api/settings/motivation", json={"value": current})  # put it back
