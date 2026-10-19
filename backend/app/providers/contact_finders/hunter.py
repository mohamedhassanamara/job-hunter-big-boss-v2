"""Hunter: domain search (people + positions + pattern, 1 credit) and the email verifier (0.5)."""

from typing import Any

import httpx

from app.providers.contact_finders import (
    Candidate,
    Cost,
    Search,
    classify,
)
from app.providers.http import PoliteClient, SourceError

API = "https://api.hunter.io/v2"
DEPARTMENTS = "executive,it,management,hr"
# Hunter's own deliverability words -> ours
STATUS = {"valid": "valid", "accept_all": "accept_all", "invalid": "invalid", "unknown": "unknown",
          "webmail": "unknown", "disposable": "invalid"}


def parse_domain_search(payload: dict[str, Any]) -> Search:
    d = payload.get("data") or {}
    people = []
    for e in d.get("emails") or []:
        if e.get("type") != "personal" or not e.get("value"):
            continue
        name = " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x)
        if not name:
            continue
        status = STATUS.get((e.get("verification") or {}).get("status") or "", "unknown")
        people.append(Candidate(full_name=name, title=e.get("position"), email=e["value"],
                                email_status=status, provider="hunter", has_email=True,
                                linkedin_url=e.get("linkedin")))
    org = {"industry": d.get("industry"), "linkedin_url": d.get("linkedin"),
           "name": d.get("organization")}
    return Search(people, Cost(credits=1.0), d.get("pattern"), None,
                  {k: v for k, v in org.items() if v})


def parse_verify(payload: dict[str, Any]) -> str:
    d = payload.get("data") or {}
    return STATUS.get(d.get("status") or "", "unknown")


class HunterFinder:
    provider = "hunter"
    unit = "credits"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def _get(self, key: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        client = PoliteClient("Hunter", retries=0, min_interval=0.5, timeout=40,
                              headers={"X-API-KEY": key}, transport=self._transport)
        try:
            return client.get_json(f"{API}/{path}", params=params)
        except SourceError as exc:
            raise classify(exc) from exc
        finally:
            client.close()

    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 10) -> Search:
        # Free plan: limit + offset can't exceed 10; one call is one credit whatever the limit.
        return parse_domain_search(self._get(key, "domain-search", {
            "domain": domain, "limit": min(limit, 10), "department": DEPARTMENTS}))

    def reveal(self, key: str, candidate: Candidate) -> tuple[Candidate, Cost]:
        return candidate, Cost()  # domain search already returns the emails

    def verify(self, key: str, email: str) -> tuple[str, Cost]:
        return parse_verify(self._get(key, "email-verifier", {"email": email})), Cost(0.5)
