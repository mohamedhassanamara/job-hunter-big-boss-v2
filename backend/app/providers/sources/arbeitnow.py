"""Arbeitnow public job board API (https://www.arbeitnow.com/blog/job-board-api).

No server-side search: we page through the newest listings (250/page) and let the pre-filter
decide. The feed is mostly German/DACH jobs. Terms: link back to the listing (we store `url`).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.enums import RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.providers.http import PoliteClient
from app.services.geo import country_from_text, fold
from app.services.text import html_to_text

URL = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 4


def _remote_type(item: dict[str, Any]) -> RemoteType:
    if item.get("remote") in (True, "true", "True", 1):
        return RemoteType.remote
    words = fold(" ".join([item.get("title", ""), *map(str, item.get("tags") or [])]))
    if "hybrid" in words.split():
        return RemoteType.hybrid
    return RemoteType.onsite


def parse_arbeitnow(payload: dict[str, Any]) -> list[RawJob]:
    jobs = []
    for item in payload.get("data") or []:
        created = item.get("created_at")
        location = (item.get("location") or "").strip()
        jobs.append(
            RawJob(
                source=Source.arbeitnow,
                external_id=str(item["slug"]),
                url=item.get("url") or f"https://www.arbeitnow.com/view/{item['slug']}",
                title=(item.get("title") or "").strip(),
                company=(item.get("company_name") or "").strip(),
                location=location,
                country=country_from_text(location),
                remote_type=_remote_type(item),
                description=html_to_text(item.get("description")),
                posted_at=datetime.fromtimestamp(int(created), UTC) if created else None,
            )
        )
    return jobs


class ArbeitnowSource:
    source = Source.arbeitnow
    cooldown_hours = 1.0  # the feed refreshes hourly

    def __init__(self) -> None:
        self.requests = 0

    def configured(self) -> str | None:
        return None

    def fetch_payloads(self, profile: ProfileSpec) -> list[dict[str, Any]]:
        cutoff = datetime.now(UTC) - timedelta(days=profile.max_age_days)
        payloads = []
        with PoliteClient("Arbeitnow", min_interval=2.0) as client:
            for page in range(1, MAX_PAGES + 1):
                payload = client.get_json(URL, params={"page": page})
                payloads.append(payload)
                items = payload.get("data") or []
                oldest = min((int(i["created_at"]) for i in items if i.get("created_at")),
                             default=None)
                if not items or not (payload.get("links") or {}).get("next"):
                    break
                if oldest is not None and datetime.fromtimestamp(oldest, UTC) < cutoff:
                    break
            self.requests = client.requests
        return payloads

    def fetch(self, profile: ProfileSpec) -> list[RawJob]:
        return [job for p in self.fetch_payloads(profile) for job in parse_arbeitnow(p)]
