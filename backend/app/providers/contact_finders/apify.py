"""Apify, last paid step: microworlds/leads-finder (the one that returned verified emails and
titles in the Phase 12 tests: about $0.001 per run + $0.003 per lead on the free tier). Validated
emails only, a few leads per run, a hard per-run charge ceiling. Cost is read from the run."""

from typing import Any

import httpx

from app.providers.contact_finders import Candidate, Cost, Search, classify
from app.providers.http import PoliteClient, SourceError

API = "https://api.apify.com/v2"
ACTOR = "microworlds/leads-finder"
MAX_RUN_USD = 0.10  # a run can never charge more than this


def parse_items(items: list[dict[str, Any]], actor: str = ACTOR) -> list[Candidate]:
    people = []
    for it in items:
        email = it.get("email")
        name = " ".join(x for x in (it.get("first_name"), it.get("last_name")) if x) \
            or it.get("full_name")
        if not email or not name:
            continue
        people.append(Candidate(full_name=name, title=it.get("title") or it.get("job_title"),
                                email=email, email_status="valid", provider="apify",
                                has_email=True, actor=actor, linkedin_url=it.get("linkedin")))
    return people


class ApifyFinder:
    provider = "apify"
    unit = "usd"

    def __init__(self, transport: httpx.BaseTransport | None = None, actor: str = ACTOR):
        self._transport, self._actor = transport, actor

    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 5) -> Search:
        client = PoliteClient("Apify", retries=0, min_interval=0.5, timeout=300,
                              headers={"Authorization": f"Bearer {key}"},
                              transport=self._transport)
        try:
            run = client.post_json(
                f"{API}/acts/{self._actor.replace('/', '~')}/run-sync-get-dataset-items",
                params={"maxTotalChargeUsd": MAX_RUN_USD, "timeout": 240},
                json={"max_result": min(limit, 5), "company_domains": [domain],
                      "contact_job_titles": titles, "email_status": ["verified"]})
            items = run if isinstance(run, list) else []
            # Documented price per lead + the start fee: the run object's usage lags, so the
            # estimate is what the quota counts (the Settings screen re-reads the real month).
            people = parse_items([i for i in items if isinstance(i, dict)], self._actor)
            return Search(people, Cost(usd=round(0.001 + 0.003 * len(items), 4)))
        except SourceError as exc:
            raise classify(exc) from exc
        finally:
            client.close()

    def reveal(self, key: str, candidate: Candidate) -> tuple[Candidate, Cost]:
        return candidate, Cost()
