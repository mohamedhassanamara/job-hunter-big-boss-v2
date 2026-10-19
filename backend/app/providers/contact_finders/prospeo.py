"""Prospeo: search-person at a domain (1 credit per page, emails masked), then enrich-person for
one chosen person (1 credit, verified emails only, free when nothing is found)."""

from typing import Any

import httpx

from app.providers.contact_finders import (
    Candidate,
    Cost,
    FinderError,
    Search,
    classify,
)
from app.providers.http import PoliteClient, SourceError

API = "https://api.prospeo.io"


def parse_search(payload: dict[str, Any]) -> Search:
    if payload.get("error"):
        raise FinderError(f"Prospeo: {payload.get('error_code') or 'error'}")
    people = []
    for r in payload.get("results") or []:
        p = r.get("person") or {}
        if not p.get("full_name") or not p.get("person_id"):
            continue
        e = p.get("email") or {}
        people.append(Candidate(
            full_name=p["full_name"], title=p.get("current_job_title"), provider="prospeo",
            provider_id=p["person_id"], linkedin_url=p.get("linkedin_url"),
            has_email=(e.get("status") or "").upper() == "VERIFIED"))
    company = (payload.get("results") or [{}])[0].get("company") or {} if people else {}
    org = {"industry": company.get("industry"), "linkedin_url": company.get("linkedin_url")}
    return Search(people, Cost(credits=0.0 if payload.get("free") or not people else 1.0),
                  organization={k: v for k, v in org.items() if v})


def parse_enrich(payload: dict[str, Any], candidate: Candidate) -> tuple[Candidate, Cost]:
    if payload.get("error"):
        code = payload.get("error_code") or "error"
        if code == "NO_MATCH":
            return candidate, Cost()  # not charged
        raise FinderError(f"Prospeo: {code}")
    email = (payload.get("person") or {}).get("email") or {}
    charged = Cost(0.0 if payload.get("free_enrichment") else 1.0)
    if email.get("email") and (email.get("status") or "").upper() == "VERIFIED":
        candidate.email, candidate.email_status = email["email"], "valid"
    return candidate, charged


class ProspeoFinder:
    provider = "prospeo"
    unit = "credits"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def _post(self, key: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        client = PoliteClient("Prospeo", retries=0, min_interval=0.5, timeout=40,
                              headers={"X-KEY": key}, transport=self._transport)
        try:
            return client.post_json(f"{API}/{path}", json=body)
        except SourceError as exc:
            raise classify(exc) from exc
        finally:
            client.close()

    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 10) -> Search:
        return parse_search(self._post(key, "search-person", {"page": 1, "filters": {
            "company": {"websites": {"include": [domain]}},
            "person_job_title": {"include": titles, "match_mode": "CONTAINS"}}}))

    def reveal(self, key: str, candidate: Candidate) -> tuple[Candidate, Cost]:
        return parse_enrich(self._post(key, "enrich-person", {
            "only_verified_email": True, "data": {"person_id": candidate.provider_id}}), candidate)
