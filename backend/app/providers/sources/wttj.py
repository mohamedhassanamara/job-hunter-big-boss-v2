"""Welcome to the Jungle via the Algolia search index its own website uses.

WTTJ has no public API. The site's search runs on Algolia with a public, search-only key that
every browser receives; the key is referer-restricted, so we send the site's Referer.
Unofficial: if WTTJ rotates the key or renames the index, requests fail with a clear error and
the key can be updated in .env (WTTJ_ALGOLIA_KEY). All role×country queries go out in ONE
multi-query request per run. The index has no full description: we use summary + key missions.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from app.config import get_settings
from app.models.enums import DescriptionLevel, RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.providers.http import PoliteClient, SourceError
from app.services.text import html_to_text

SITE = "https://www.welcometothejungle.com"
INDEX = "wttj_jobs_production_en"
HITS_PER_QUERY = 50
ATTRIBUTES = [
    "objectID", "name", "slug", "organization.name", "organization.slug", "offices", "remote",
    "published_at", "published_at_timestamp", "summary", "key_missions", "profile", "language",
    "contract_type", "salary_minimum", "salary_maximum", "salary_currency", "salary_period",
]
_REMOTE = {
    "fulltime": RemoteType.remote,
    "partial": RemoteType.hybrid,
    "punctual": RemoteType.hybrid,
    "no": RemoteType.onsite,
}
_CURRENCY = {"EUR": "€", "GBP": "£", "USD": "$"}


def build_queries(profile: ProfileSpec, now: datetime | None = None) -> list[dict[str, str]]:
    # WTTJ search ranks by relevance, not date: filter by age server-side so every hit is fresh.
    cutoff = int(((now or datetime.now(UTC)) - timedelta(days=profile.max_age_days)).timestamp())
    queries = []
    for role in profile.roles:
        for country in profile.locations:
            filters = [[f"offices.country_code:{country.upper()}"]]
            queries.append((role, filters))
        # Fully-remote roles based anywhere; the pre-filter checks the region afterwards.
        queries.append((role, [["remote:fulltime"]]))
    return [
        {
            "indexName": INDEX,
            "params": urlencode(
                {
                    "query": role,
                    "hitsPerPage": HITS_PER_QUERY,
                    "facetFilters": json.dumps(filters),
                    "numericFilters": json.dumps([f"published_at_timestamp>={cutoff}"]),
                    "attributesToRetrieve": json.dumps(ATTRIBUTES),
                    "attributesToHighlight": "[]",
                }
            ),
        }
        for role, filters in queries
    ]


def _salary(hit: dict[str, Any]) -> str | None:
    lo, hi = hit.get("salary_minimum"), hit.get("salary_maximum")
    if not lo and not hi:
        return None
    sym = _CURRENCY.get(hit.get("salary_currency") or "", "")

    def k(v: float) -> str:
        return f"{sym}{round(v / 1000)}k" if v >= 1000 else f"{sym}{v:g}"

    amount = f"{k(lo)}–{k(hi)}" if lo and hi and lo != hi else k(lo or hi)
    period = {"yearly": "/year", "monthly": "/month", "daily": "/day"}.get(
        hit.get("salary_period") or "", ""
    )
    if period == "/year" and max(lo or 0, hi or 0) < 10_000:
        period = ""  # source data sometimes labels monthly stipends as yearly
    return f"{amount}{period}"


def _description(hit: dict[str, Any]) -> str:
    parts = []
    if summary := (hit.get("summary") or "").strip():
        parts.append(summary)
    missions = [m.strip() for m in hit.get("key_missions") or [] if m and m.strip()]
    if missions:
        parts.append("## Key missions\n\n" + "\n".join(f"- {m}" for m in missions))
    profile = html_to_text(hit.get("profile"))
    if profile and set(profile) - {".", " "}:  # skip placeholder profiles like "....."
        parts.append("## Profile\n\n" + profile)
    return "\n\n".join(parts)


def _office(hit: dict[str, Any], targets: set[str]) -> dict[str, Any]:
    offices = hit.get("offices") or []
    for office in offices:
        if (office.get("country_code") or "").upper() in targets:
            return office
    return offices[0] if offices else {}


def parse_wttj(payload: dict[str, Any], targets: set[str] | None = None) -> list[RawJob]:
    targets = targets or set()
    results = payload.get("results") or [payload]
    seen: dict[str, RawJob] = {}
    for result in results:
        for hit in result.get("hits") or []:
            if hit["objectID"] in seen:
                continue
            org = hit.get("organization") or {}
            office = _office(hit, targets)
            city, country_name = office.get("city"), office.get("country")
            location = ", ".join(p for p in (city, country_name) if p)
            published = hit.get("published_at")
            seen[hit["objectID"]] = RawJob(
                source=Source.wttj,
                external_id=hit["objectID"],
                url=f"{SITE}/en/companies/{org.get('slug')}/jobs/{hit.get('slug')}",
                title=(hit.get("name") or "").strip(),
                company=(org.get("name") or "").strip(),
                location=location,
                country=(office.get("country_code") or "").upper() or None,
                remote_type=_REMOTE.get(hit.get("remote") or "", RemoteType.unknown),
                description=_description(hit),
                salary_text=_salary(hit),
                description_level=DescriptionLevel.summary,
                posted_at=datetime.fromisoformat(published.replace("Z", "+00:00"))
                if published
                else None,
            )
    return list(seen.values())


class WTTJSource:
    source = Source.wttj
    cooldown_hours = 1.0

    def __init__(self) -> None:
        self.requests = 0
        settings = get_settings()
        self.app_id = settings.wttj_algolia_app_id
        self.key = settings.wttj_algolia_key

    def configured(self) -> str | None:
        if not (self.app_id and self.key):
            return "WTTJ_ALGOLIA_APP_ID / WTTJ_ALGOLIA_KEY are empty"
        return None

    def fetch_payload(self, profile: ProfileSpec) -> dict[str, Any]:
        headers = {
            "X-Algolia-Application-Id": self.app_id,
            "X-Algolia-API-Key": self.key,
            "Referer": f"{SITE}/",
            "Origin": SITE,
        }
        url = f"https://{self.app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
        with PoliteClient("Welcome to the Jungle", min_interval=2.0, headers=headers) as client:
            try:
                payload = client.post_json(url, json={"requests": build_queries(profile)})
            except SourceError as exc:
                if exc.status in (400, 401, 403, 404):
                    raise SourceError(
                        f"WTTJ search rejected the request (HTTP {exc.status}). The site may have "
                        "rotated its public Algolia key or renamed the index: update "
                        "WTTJ_ALGOLIA_KEY in .env (Settings → Sources explains how).",
                        exc.status,
                    ) from exc
                raise
            finally:
                self.requests = client.requests
        return payload

    def fetch(self, profile: ProfileSpec) -> list[RawJob]:
        return parse_wttj(self.fetch_payload(profile), {c.upper() for c in profile.locations})
