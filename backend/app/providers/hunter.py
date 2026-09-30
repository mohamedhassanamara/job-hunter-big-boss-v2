"""Hunter.io, an optional helper in the Get contact step: only when you click Try Hunter (never
automatic). The key is HUNTER_API_KEY in .env, sent in a header (never in a URL or the database).

- account(): the remaining monthly searches and verifications. Free: it uses no credit.
- find(domain, first_name, last_name): the email-finder, 1 search.
- verify(email): the email-verifier, 1 verification.

Paid calls are never retried (a retry could spend a second credit). Tests and the sandbox use
MockHunter.
"""

from dataclasses import asdict, dataclass
from typing import Any

import httpx

from app.providers.http import PoliteClient, SourceError

API = "https://api.hunter.io/v2"


class HunterError(RuntimeError):
    pass


@dataclass
class Credits:
    plan: str
    searches_used: int
    searches_available: int
    verifications_used: int
    verifications_available: int
    reset_date: str | None

    @property
    def searches_left(self) -> int:
        return max(0, self.searches_available - self.searches_used)

    @property
    def verifications_left(self) -> int:
        return max(0, self.verifications_available - self.verifications_used)

    def dict(self) -> dict[str, Any]:
        return {**asdict(self), "searches_left": self.searches_left,
                "verifications_left": self.verifications_left}


@dataclass
class Found:
    email: str | None
    score: int | None  # Hunter's confidence, 0-100
    first_name: str | None
    last_name: str | None
    position: str | None
    linkedin_url: str | None
    status: str | None  # Hunter's verification of it: valid | accept_all | unknown …
    sources: int


@dataclass
class Verified:
    email: str
    result: str  # deliverable | risky | undeliverable
    status: str  # valid | invalid | accept_all | webmail | disposable | unknown
    score: int | None


def parse_account(payload: dict[str, Any]) -> Credits:
    data = payload.get("data") or {}
    req = data.get("requests") or {}
    # Newer plans count one pool of "credits"; older ones separate searches and verifications.
    searches = req.get("searches") or req.get("credits") or {}
    verifs = req.get("verifications") or req.get("credits") or {}
    return Credits(plan=data.get("plan_name") or "", reset_date=data.get("reset_date"),
                   searches_used=int(searches.get("used") or 0),
                   searches_available=int(searches.get("available") or 0),
                   verifications_used=int(verifs.get("used") or 0),
                   verifications_available=int(verifs.get("available") or 0))


def parse_find(payload: dict[str, Any]) -> Found:
    d = payload.get("data") or {}
    return Found(email=d.get("email"), score=d.get("score"), first_name=d.get("first_name"),
                 last_name=d.get("last_name"), position=d.get("position"),
                 linkedin_url=d.get("linkedin_url"),
                 status=(d.get("verification") or {}).get("status"),
                 sources=len(d.get("sources") or []))


def parse_verify(payload: dict[str, Any]) -> Verified:
    d = payload.get("data") or {}
    return Verified(email=d.get("email") or "", result=d.get("result") or "unknown",
                    status=d.get("status") or "unknown", score=d.get("score"))


class HunterClient:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise HunterError("Add HUNTER_API_KEY to .env to use Hunter")
        self._key, self._transport = api_key, transport

    def _get(self, path: str, params: dict[str, str], *, retries: int) -> dict[str, Any]:
        client = PoliteClient("Hunter", retries=retries, min_interval=0.5,
                              headers={"X-API-KEY": self._key}, transport=self._transport)
        try:
            return client.get_json(f"{API}/{path}", params=params)
        except SourceError as exc:
            if exc.status == 401:
                raise HunterError("Hunter rejected the API key (check HUNTER_API_KEY)") from exc
            if exc.status in (402, 403) or "usage" in str(exc).lower():
                raise HunterError("No Hunter credits left this month") from exc
            raise HunterError(str(exc)) from exc
        finally:
            client.close()

    def account(self) -> Credits:
        return parse_account(self._get("account", {}, retries=1))

    def find(self, domain: str, first_name: str, last_name: str) -> Found:
        return parse_find(self._get("email-finder", {"domain": domain, "first_name": first_name,
                                                     "last_name": last_name}, retries=0))

    def verify(self, email: str) -> Verified:
        return parse_verify(self._get("email-verifier", {"email": email}, retries=0))


class MockHunter:
    """The sandbox and tests: made-up answers, no network, credits that go down."""

    def __init__(self) -> None:
        self.searches, self.verifications = 3, 2

    def account(self) -> Credits:
        return Credits(plan="Free (sample)", searches_used=self.searches, searches_available=25,
                       verifications_used=self.verifications, verifications_available=50,
                       reset_date=None)

    def find(self, domain: str, first_name: str, last_name: str) -> Found:
        self.searches += 1
        email = f"{first_name}.{last_name}@{domain}".lower()
        return Found(email=email, score=91, first_name=first_name, last_name=last_name,
                     position=None, linkedin_url=None, status="valid", sources=2)

    def verify(self, email: str) -> Verified:
        self.verifications += 1
        return Verified(email=email, result="deliverable", status="valid", score=94)
