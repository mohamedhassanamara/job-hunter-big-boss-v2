"""Adzuna official API (https://developer.adzuna.com). Needs free ADZUNA_APP_ID / ADZUNA_APP_KEY.

One request per role × country (title keyword search, newest first). Adzuna has no Portugal
endpoint, and descriptions are truncated snippets (~500 chars) — the full text is on the
listing page behind `redirect_url`.
"""

from datetime import datetime
from typing import Any

from app.config import get_settings
from app.models.enums import RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.providers.http import PoliteClient
from app.services.geo import country_from_text, fold
from app.services.text import html_to_text

BASE = "https://api.adzuna.com/v1/api/jobs"
SUPPORTED = {"ES": "es", "FR": "fr", "IT": "it"}  # no Portugal endpoint
RESULTS_PER_PAGE = 50

_REMOTE_WORDS = {"remote", "teletrabajo", "remoto", "remota", "teletravail", "full remote"}
_HYBRID_WORDS = {"hybrid", "hibrido", "hybride", "ibrido"}


def _remote_type(title: str, description: str) -> RemoteType:
    words = set(fold(f"{title} {description}").split())
    if words & _HYBRID_WORDS:
        return RemoteType.hybrid
    if words & _REMOTE_WORDS:
        return RemoteType.remote
    return RemoteType.unknown


def _salary(item: dict[str, Any]) -> str | None:
    if str(item.get("salary_is_predicted")) == "1":
        return None  # Adzuna's estimate, not the employer's figure
    lo, hi = item.get("salary_min"), item.get("salary_max")
    if not lo and not hi:
        return None

    def k(v: float) -> str:
        return f"€{round(v / 1000)}k"

    return f"{k(lo)}–{k(hi)}" if lo and hi and round(lo) != round(hi) else k(lo or hi)


def parse_adzuna(payload: dict[str, Any], country: str) -> list[RawJob]:
    jobs = []
    for item in payload.get("results") or []:
        title = html_to_text(item.get("title"))
        description = html_to_text(item.get("description"))
        location = item.get("location") or {}
        area = location.get("area") or []
        display = (location.get("display_name") or "").strip()
        created = item.get("created")
        jobs.append(
            RawJob(
                source=Source.adzuna,
                external_id=str(item["id"]),
                url=item["redirect_url"],
                title=title,
                company=((item.get("company") or {}).get("display_name") or "").strip(),
                location=display,
                country=country_from_text(area[0] if area else display) or country.upper(),
                remote_type=_remote_type(title, description),
                description=description,
                salary_text=_salary(item),
                posted_at=datetime.fromisoformat(created.replace("Z", "+00:00"))
                if created
                else None,
            )
        )
    return jobs


class AdzunaSource:
    source = Source.adzuna
    cooldown_hours = 1.0

    def __init__(self) -> None:
        settings = get_settings()
        self.app_id, self.app_key = settings.adzuna_app_id, settings.adzuna_app_key
        self.requests = 0
        self.warnings: list[str] = []

    def configured(self) -> str | None:
        if not (self.app_id and self.app_key):
            return "add ADZUNA_APP_ID and ADZUNA_APP_KEY to .env (free at developer.adzuna.com)"
        return None

    def targets(self, profile: ProfileSpec) -> list[str]:
        wanted = [c.upper() for c in profile.locations]
        self.warnings = [
            f"Adzuna has no {c} endpoint; skipped" for c in wanted if c not in SUPPORTED
        ]
        return [c for c in wanted if c in SUPPORTED]

    def fetch_payloads(self, profile: ProfileSpec) -> list[tuple[str, dict[str, Any]]]:
        out = []
        with PoliteClient("Adzuna", min_interval=1.5) as client:
            try:
                for country in self.targets(profile):
                    for role in profile.roles:
                        payload = client.get_json(
                            f"{BASE}/{SUPPORTED[country]}/search/1",
                            params={
                                "app_id": self.app_id,
                                "app_key": self.app_key,
                                "title_only": role,
                                "results_per_page": RESULTS_PER_PAGE,
                                "max_days_old": profile.max_age_days,
                                "sort_by": "date",
                                "content-type": "application/json",
                            },
                        )
                        out.append((country, payload))
            finally:
                self.requests = client.requests
        return out

    def fetch(self, profile: ProfileSpec) -> list[RawJob]:
        seen: dict[str, RawJob] = {}
        for country, payload in self.fetch_payloads(profile):
            for job in parse_adzuna(payload, country):
                seen.setdefault(job.external_id, job)
        return list(seen.values())
