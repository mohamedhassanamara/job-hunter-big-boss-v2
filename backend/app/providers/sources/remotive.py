"""Remotive public API (https://remotive.com/api-documentation).

Usage terms we honour: at most a few requests per day (6h cooldown ⇒ ≤ 4/day), always link
back to the Remotive listing URL, and show "Remotive" as the source in the UI.
All Remotive jobs are remote; `candidate_required_location` says who may apply.
"""

from datetime import UTC, datetime
from typing import Any

from app.models.enums import RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.providers.http import PoliteClient
from app.services.geo import COUNTRY_ALIASES, fold
from app.services.text import html_to_text

URL = "https://remotive.com/api/remote-jobs"
# The public feed is a small, 24h-delayed sample (~20 jobs) and category/search params barely
# change it, so by default we make ONE unfiltered request per run and let the pre-filter select.
CATEGORIES: list[str | None] = [None]


def _single_country(region: str) -> str | None:
    """'Spain' → ES; 'Europe' / 'USA, Canada' → None (region, or several countries)."""
    folded = f" {fold(region)} "
    found = {code for code, aliases in COUNTRY_ALIASES.items()
             if any(f" {a} " in folded for a in aliases)}
    return found.pop() if len(found) == 1 else None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_remotive(payload: dict[str, Any]) -> list[RawJob]:
    jobs = []
    for item in payload.get("jobs") or []:
        region = (item.get("candidate_required_location") or "").strip()
        jobs.append(
            RawJob(
                source=Source.remotive,
                external_id=str(item["id"]),
                url=item["url"],
                title=(item.get("title") or "").strip(),
                company=(item.get("company_name") or "").strip(),
                location=region or "Remote",
                country=_single_country(region) if region else None,
                remote_type=RemoteType.remote,
                description=html_to_text(item.get("description")),
                salary_text=(item.get("salary") or "").strip() or None,
                posted_at=_parse_date(item.get("publication_date")),
            )
        )
    return jobs


class RemotiveSource:
    source = Source.remotive
    cooldown_hours = 6.0  # Remotive asks for max ~4 requests per day

    def __init__(
        self, categories: list[str | None] | None = None, limit: int | None = None
    ) -> None:
        self.categories = categories or CATEGORIES
        self.limit = limit
        self.requests = 0

    def configured(self) -> str | None:
        return None

    def fetch_payloads(self, profile: ProfileSpec) -> list[dict[str, Any]]:
        payloads = []
        with PoliteClient("Remotive", min_interval=5.0) as client:
            for category in self.categories:
                params: dict[str, Any] = {"category": category} if category else {}
                if self.limit:
                    params["limit"] = self.limit
                payloads.append(client.get_json(URL, params=params))
            self.requests = client.requests
        return payloads

    def fetch(self, profile: ProfileSpec) -> list[RawJob]:
        seen: dict[str, RawJob] = {}
        for payload in self.fetch_payloads(profile):
            for job in parse_remotive(payload):
                seen.setdefault(job.external_id, job)  # a job can sit in several categories
        return list(seen.values())
