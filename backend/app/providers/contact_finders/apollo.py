"""Apollo: people search is free but has no emails (only `has_email`); match reveals one work
email for about 1 credit. Free plans have no balance endpoint: credits are counted locally."""

from typing import Any

import httpx

from app.providers.contact_finders import Candidate, Cost, Search, classify
from app.providers.http import PoliteClient, SourceError

API = "https://api.apollo.io/api/v1"


def parse_search(payload: dict[str, Any]) -> Search:
    people = []
    for p in payload.get("people") or []:
        name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        # The search shows an obfuscated last name; the real one comes with the match.
        if not p.get("id") or not name:
            continue
        people.append(Candidate(full_name=name, title=p.get("title"), provider="apollo",
                                provider_id=p["id"], has_email=bool(p.get("has_email"))))
    return Search(people, Cost())


def parse_match(payload: dict[str, Any], candidate: Candidate) -> tuple[Candidate, Cost]:
    p = payload.get("person") or {}
    if p.get("email") and p.get("email_status") == "verified":
        candidate.email, candidate.email_status = p["email"], "valid"
    elif p.get("email"):
        candidate.email = p["email"]
        candidate.email_status = {"unavailable": "invalid", "extrapolated": "unknown",
                                  "likely to engage": "unknown"}.get(p.get("email_status"),
                                                                    "unknown")
    name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
    if name:
        candidate.full_name = name
    candidate.title = p.get("title") or candidate.title
    candidate.linkedin_url = p.get("linkedin_url") or candidate.linkedin_url
    return candidate, Cost(credits=1.0 if p.get("email") else 0.0)


class ApolloFinder:
    provider = "apollo"
    unit = "credits"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def _post(self, key: str, path: str, **kw: Any) -> dict[str, Any]:
        client = PoliteClient("Apollo", retries=0, min_interval=0.5, timeout=40,
                              headers={"x-api-key": key, "Content-Type": "application/json"},
                              transport=self._transport)
        try:
            return client.post_json(f"{API}/{path}", **kw)
        except SourceError as exc:
            raise classify(exc) from exc
        finally:
            client.close()

    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 10) -> Search:
        return parse_search(self._post(key, "mixed_people/api_search", json={
            "q_organization_domains_list": [domain], "person_titles": titles,
            "per_page": min(limit, 25)}))

    def reveal(self, key: str, candidate: Candidate) -> tuple[Candidate, Cost]:
        return parse_match(self._post(key, "people/match", params={"id": candidate.provider_id}),
                           candidate)
