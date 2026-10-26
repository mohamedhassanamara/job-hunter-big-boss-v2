"""HTTP client for job sources: timeouts, retries with backoff, per-source spacing, clear UA."""

import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import get_settings

RETRY_STATUS = {429, 500, 502, 503, 504}


class SourceError(RuntimeError):
    """A source request failed for good (after retries, or with a non-retryable status)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def user_agent() -> str:
    contact = get_settings().discovery_contact
    base = "JobHunter/0.1 (personal job search tool; non-commercial"
    return f"{base}; contact: {contact})" if contact else f"{base})"


class PoliteClient:
    def __init__(
        self,
        name: str,
        *,
        min_interval: float = 1.0,
        timeout: float = 20.0,
        retries: int = 3,
        backoff: float = 1.5,
        headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.name = name
        self.min_interval = min_interval
        self.retries = retries
        self.backoff = backoff
        self.requests = 0
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent(), "Accept": "application/json", **(headers or {})},
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _wait_turn(self) -> None:
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _delay(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None and (retry_after := response.headers.get("Retry-After")):
            try:
                return min(float(retry_after), 60.0)
            except ValueError:
                pass
        return self.backoff * (2**attempt) + random.uniform(0, 0.5)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error, last_status = "unknown error", None
        for attempt in range(self.retries + 1):
            self._wait_turn()
            self.requests += 1
            response: httpx.Response | None = None
            try:
                response = self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code < 400:
                    return response
                snippet = response.text[:200].strip()
                if response.status_code not in RETRY_STATUS:
                    raise SourceError(
                        f"{self.name}: HTTP {response.status_code} {snippet}", response.status_code
                    )
                last_error = f"HTTP {response.status_code} {snippet}"
                last_status = response.status_code
            if attempt < self.retries:
                self._sleep(self._delay(attempt, response))
        raise SourceError(f"{self.name}: gave up after {self.retries + 1} attempts ({last_error})",
                          last_status)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self._parse(self.request("GET", url, **kwargs))

    def post_json(self, url: str, **kwargs: Any) -> Any:
        return self._parse(self.request("POST", url, **kwargs))

    def _parse(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            snippet = response.text[:120]
            raise SourceError(f"{self.name}: response was not JSON ({snippet!r})") from exc


class Robots:
    """robots.txt per host, read once (honest User-Agent). A missing file (4xx) allows everything,
    an unreachable one (5xx, network) allows nothing: we don't crawl what we can't check."""

    AGENT = "JobHunter"

    def __init__(self, client: PoliteClient):
        self.client = client
        self._cache: dict[str, Any] = {}

    def _parser(self, url: str) -> Any:
        from urllib.parse import urlsplit
        from urllib.robotparser import RobotFileParser

        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._cache:
            parser = RobotFileParser()
            try:
                res = self.client._client.get(f"{host}/robots.txt")
                self.client.requests += 1
                if res.status_code >= 500:
                    parser.disallow_all = True
                elif res.status_code >= 400:
                    parser.allow_all = True
                else:
                    parser.parse(res.text.splitlines())
            except httpx.HTTPError:
                parser.disallow_all = True
            self._cache[host] = parser
        return self._cache[host]

    def allowed(self, url: str) -> bool:
        return bool(self._parser(url).can_fetch(self.AGENT, url))

    def sitemaps(self, url: str) -> list[str]:
        return list(self._parser(url).site_maps() or [])
