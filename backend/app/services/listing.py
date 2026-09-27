"""Fetch a job's full listing once (on demand, one job at a time) to raise scoring confidence.

We read the schema.org `JobPosting` JSON-LD that job pages publish for search engines. We send
our honest User-Agent: if a site refuses automated access (e.g. WTTJ's CloudFront answers 403),
we do NOT disguise ourselves — the UI offers "paste the full description" instead.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from app.providers.http import PoliteClient, SourceError
from app.services.text import html_to_text

_LD = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)


class ListingUnavailable(RuntimeError):
    """The page couldn't be fetched/parsed. `can_paste` tells the UI to offer manual paste."""

    def __init__(self, message: str, can_paste: bool = True):
        super().__init__(message)
        self.can_paste = can_paste


@dataclass
class FullListing:
    description: str
    location_requirements: str | None = None


def _postings(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, list):
        return [p for item in node for p in _postings(item)]
    if isinstance(node, dict):
        if node.get("@type") == "JobPosting" or (
            isinstance(node.get("@type"), list) and "JobPosting" in node["@type"]
        ):
            return [node]
        return _postings(node.get("@graph", []))
    return []


def _requirements(posting: dict[str, Any]) -> str | None:
    reqs = posting.get("applicantLocationRequirements")
    if not reqs:
        return None
    items = reqs if isinstance(reqs, list) else [reqs]
    names = [r.get("name") if isinstance(r, dict) else str(r) for r in items]
    names = [n for n in names if n]
    return ", ".join(names) or None


def extract_job_posting(html: str) -> FullListing | None:
    for raw in _LD.findall(html):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        for posting in _postings(data):
            text = html_to_text(posting.get("description") or "")
            if len(text) < 200:
                continue
            quals = posting.get("qualifications")
            if isinstance(quals, str) and quals.strip() and quals[:80] not in text:
                text += "\n\n## Qualifications\n\n" + html_to_text(quals)
            return FullListing(description=text, location_requirements=_requirements(posting))
    return None


def fetch_full_listing(url: str, client: PoliteClient | None = None) -> FullListing:
    own = client is None
    client = client or PoliteClient("Listing", min_interval=0, retries=1,
                                    headers={"Accept": "text/html,application/xhtml+xml"})
    try:
        response = client.request("GET", url)
    except SourceError as exc:
        if exc.status in (401, 403, 429):
            raise ListingUnavailable(
                "This site blocks automated fetching. Open the listing and paste the full "
                "description instead."
            ) from exc
        raise ListingUnavailable(f"Couldn't fetch the listing: {exc}") from exc
    finally:
        if own:
            client.close()
    listing = extract_job_posting(response.text)
    if listing is None:
        raise ListingUnavailable(
            "No structured job posting found on that page. Paste the full description instead."
        )
    return listing


def with_location_requirements(listing: FullListing) -> str:
    if listing.location_requirements:
        return (
            f"{listing.description}\n\n## Applicant location requirements\n\n"
            f"{listing.location_requirements}"
        )
    return listing.description
