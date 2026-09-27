"""Bayt.com, the largest Gulf/MENA job board. No public API: we read its public per-country
search pages (`/en/<country>/jobs/<role>-jobs/`), which robots.txt allows (it disallows the
country-less `/en/jobs/…-jobs/` paths and `filters[` URLs, which we never request).

One request per role × target country Bayt covers, spaced 3s apart, at most every 6h. Each result
card carries the title, company, city/country, remote tag, experience band, a short summary and
the post date, so no job pages are fetched during discovery. The full listing (schema.org
JobPosting on the job page) can be fetched per job from the job panel. Honest User-Agent only:
if Bayt starts blocking us, the source fails visibly; we never disguise the client.
"""

import re
from datetime import UTC, datetime

from app.models.enums import DescriptionLevel, RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.providers.http import PoliteClient
from app.services.geo import country_from_text, fold
from app.services.text import html_to_text

SITE = "https://www.bayt.com"
# Bayt's country paths (what the site offers; targets come from the search profile).
COUNTRY_SLUGS = {
    "AE": "uae", "QA": "qatar", "BH": "bahrain", "KW": "kuwait", "JO": "jordan",
    "SA": "saudi-arabia", "OM": "oman", "EG": "egypt", "LB": "lebanon", "MA": "morocco",
    "DZ": "algeria", "TN": "tunisia", "IQ": "iraq",
}

_CARD = re.compile(r"<li[^>]*\bdata-js-job\b[^>]*>(.*?)</li>", re.S)
_ID = re.compile(r'data-job-id="(\d+)"')
_TITLE = re.compile(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_COMPANY = re.compile(r'href="/en/company/[^"]*"[^>]*>(.*?)</a>', re.S)
_LOCATION = re.compile(r'jb-label-location[^>]*>(.*?)</dt>', re.S)
_CAREER = re.compile(r'jb-label-careerlevel[^>]*>(.*?)</dt>', re.S)
_REMOTE = re.compile(r'jb-label-remote[^>]*>(.*?)</dt>', re.S)
_SUMMARY = re.compile(r'class="jb-descr[^"]*"[^>]*>(.*?)</div>', re.S)
_DATE = re.compile(r'data-automation-jobActiveDate="(\d+)"')


def role_slug(role: str) -> str:
    return "-".join(fold(role).split())


def search_url(country: str, role: str) -> str:
    return f"{SITE}/en/{COUNTRY_SLUGS[country]}/jobs/{role_slug(role)}-jobs/"


def _text(fragment: str | None) -> str:
    return " ".join(html_to_text(fragment or "").split())


def _remote(label: str) -> RemoteType:
    v = label.lower()
    if "hybrid" in v:
        return RemoteType.hybrid
    if "remote" in v or "home" in v:
        return RemoteType.remote
    return RemoteType.unknown  # Bayt only tags remote/hybrid; no tag doesn't prove on-site


def parse_bayt(page: str, country: str) -> list[RawJob]:
    jobs = []
    for card_match in _CARD.finditer(page):
        card = card_match.group(0)
        job_id, title = _ID.search(card), _TITLE.search(card)
        if not (job_id and title):
            continue
        location = _text(m.group(1)) if (m := _LOCATION.search(card)) else ""
        career = _text(m.group(1)) if (m := _CAREER.search(card)) else ""
        summary = _text(m.group(1)) if (m := _SUMMARY.search(card)) else ""
        summary = re.sub(r"^Summary:\s*", "", summary)
        stamp = _DATE.search(card)
        company = _text(m.group(1)) if (m := _COMPANY.search(card)) else ""
        parts = [summary, f"Experience: {career}" if career else ""]
        jobs.append(RawJob(
            source=Source.bayt,
            external_id=job_id.group(1),
            url=SITE + title.group(1) if title.group(1).startswith("/") else title.group(1),
            title=_text(title.group(2)),
            company=company or "Confidential company",
            location=location,
            country=country_from_text(location) or country,
            remote_type=_remote(_text(m.group(1)) if (m := _REMOTE.search(card)) else ""),
            description="\n\n".join(p for p in parts if p),
            description_level=DescriptionLevel.snippet,
            posted_at=datetime.fromtimestamp(int(stamp.group(1)), UTC) if stamp else None,
        ))
    return jobs


class BaytSource:
    source = Source.bayt
    cooldown_hours = 6.0

    def __init__(self) -> None:
        self.requests = 0
        self.warnings: list[str] = []

    def configured(self) -> str | None:
        return None

    @staticmethod
    def unsupported_countries(targets: list[str]) -> list[str]:
        return [c.upper() for c in targets if c.upper() not in COUNTRY_SLUGS]

    def targets(self, profile: ProfileSpec) -> list[str]:
        return [c.upper() for c in profile.locations if c.upper() in COUNTRY_SLUGS]

    def fetch_pages(self, profile: ProfileSpec) -> list[tuple[str, str]]:
        pages = []
        with PoliteClient("Bayt", min_interval=3.0) as client:
            try:
                for country in self.targets(profile):
                    for role in profile.roles:
                        response = client.request("GET", search_url(country, role))
                        pages.append((country, response.text))
            finally:
                self.requests = client.requests
        return pages

    def fetch(self, profile: ProfileSpec) -> list[RawJob]:
        self.warnings = []
        if not self.targets(profile):
            self.warnings.append("No target country is covered by Bayt (Gulf/MENA only)")
            return []
        seen: dict[str, RawJob] = {}
        for country, page in self.fetch_pages(profile):
            found = parse_bayt(page, country)
            if not found and "data-js-job" not in page:
                self.warnings.append(f"{country}: page had no job cards (layout change?)")
            for job in found:
                seen.setdefault(job.external_id, job)
        return list(seen.values())
