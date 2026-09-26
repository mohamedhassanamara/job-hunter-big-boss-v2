import httpx
import pytest

from app.providers.http import PoliteClient, SourceError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s

    def clock(self) -> float:
        return self.now


def client_with(responses: list, clock: FakeClock, **kw) -> PoliteClient:
    calls = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    return PoliteClient(
        "test", transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock.clock, **kw
    )


def test_retries_429_honouring_retry_after() -> None:
    clock = FakeClock()
    c = client_with(
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": 1})],
        clock,
        min_interval=0,
    )
    assert c.get_json("https://x.test/a") == {"ok": 1}
    assert 7.0 in clock.sleeps
    assert c.requests == 2


def test_backoff_on_5xx_then_gives_up() -> None:
    clock = FakeClock()
    c = client_with([httpx.Response(503)] * 3, clock, min_interval=0, retries=2, backoff=1)
    with pytest.raises(SourceError, match="gave up after 3 attempts"):
        c.get_json("https://x.test/a")
    assert len(clock.sleeps) == 2 and clock.sleeps[1] > clock.sleeps[0]


def test_timeout_is_retried() -> None:
    clock = FakeClock()
    c = client_with(
        [httpx.ConnectTimeout("slow"), httpx.Response(200, json=[1])], clock, min_interval=0
    )
    assert c.get_json("https://x.test/a") == [1]


def test_non_retryable_4xx_raises_immediately() -> None:
    clock = FakeClock()
    c = client_with([httpx.Response(403, text="nope")], clock, min_interval=0)
    with pytest.raises(SourceError) as err:
        c.get_json("https://x.test/a")
    assert err.value.status == 403 and c.requests == 1


def test_min_interval_spaces_requests() -> None:
    clock = FakeClock()
    c = client_with([httpx.Response(200, json={})] * 3, clock, min_interval=2.0)
    for _ in range(3):
        c.get_json("https://x.test/a")
    assert clock.sleeps == [2.0, 2.0]


def test_user_agent_header_is_set() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json={})

    PoliteClient("t", transport=httpx.MockTransport(handler)).get_json("https://x.test")
    assert seen["ua"].startswith("JobHunter/0.1")
