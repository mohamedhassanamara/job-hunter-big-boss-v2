"""Company job boards: the public posting APIs of Greenhouse, Lever, Ashby, Workable and
SmartRecruiters. These APIs exist so companies can show their openings elsewhere; no key needed.

The company list is editable in Settings → Sources (`app_setting['company_boards']`), so users can
add employers later. Each board is fetched independently: one broken or renamed board becomes a
warning plus a per-board error in the run details, never a failed source (unless every board fails).

SmartRecruiters lists postings without descriptions; we fetch the detail only for postings that
could survive the pre-filter (role-matching title, target country or remote), to keep requests low.
"""

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.models.enums import DescriptionLevel, RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.providers.http import PoliteClient, SourceError
from app.services.geo import country_from_text
from app.services.roles import match_track, tracks_of
from app.services.text import html_to_text

ATS_KINDS = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters")
SR_PAGE = 100
SR_MAX_PAGES = 20
SR_MAX_DETAILS = 40


@dataclass(frozen=True)
class Board:
    ats: str
    token: str
    company: str = ""

    @property
    def label(self) -> str:
        return f"{self.company or self.token} ({self.ats})"


def parse_boards(value: dict[str, Any] | None) -> list[Board]:
    boards = []
    for row in (value or {}).get("boards") or []:
        ats, token = str(row.get("ats", "")).strip().lower(), str(row.get("token", "")).strip()
        if ats in ATS_KINDS and token and row.get("enabled", True):
            boards.append(Board(ats, token, str(row.get("company") or "").strip()))
    return boards


def list_url(board: Board) -> str:
    t = board.token
    return {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true",
        "lever": f"https://api.lever.co/v0/postings/{t}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{t}",
        "workable": f"https://apply.workable.com/api/v1/widget/accounts/{t}?details=true",
        "smartrecruiters": f"https://api.smartrecruiters.com/v1/companies/{t}/postings",
    }[board.ats]


def _dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):  # epoch milliseconds (Lever)
        return datetime.fromtimestamp(value / 1000, UTC)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _remote(value: Any) -> RemoteType:
    v = str(value or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    if v in {"remote", "fullyremote", "true"}:
        return RemoteType.remote
    if v == "hybrid":
        return RemoteType.hybrid
    if v in {"onsite", "inoffice", "office"}:
        return RemoteType.onsite
    return RemoteType.unknown


def _job(board: Board, company: str, **kw: Any) -> RawJob:
    location = re.sub(r"\s*(,\s*)+", ", ", kw.pop("location", "") or "").strip(" ,")
    return RawJob(
        source=Source.boards,
        company=board.company or company or board.token,
        location=location,
        country=kw.pop("country", None) or country_from_text(location),
        description_level=DescriptionLevel.full,
        **kw,
    )


def parse_greenhouse(payload: dict[str, Any], board: Board) -> list[RawJob]:
    jobs = []
    for item in payload.get("jobs") or []:
        location = (item.get("location") or {}).get("name") or ""
        # `content` is HTML with its entities escaped once more.
        text = html_to_text(html.unescape(item.get("content") or ""))
        jobs.append(_job(
            board, item.get("company_name") or "",
            external_id=f"greenhouse:{board.token}:{item['id']}",
            url=item.get("absolute_url") or "",
            title=(item.get("title") or "").strip(),
            location=location,
            remote_type=RemoteType.remote if "remote" in location.lower() else RemoteType.unknown,
            description=text,
            posted_at=_dt(item.get("first_published") or item.get("updated_at")),
        ))
    return jobs


def parse_lever(payload: list[dict[str, Any]], board: Board) -> list[RawJob]:
    jobs = []
    for item in payload or []:
        cats = item.get("categories") or {}
        parts = [item.get("descriptionPlain") or ""]
        for block in item.get("lists") or []:
            parts.append(f"{block.get('text', '')}\n{html_to_text(block.get('content') or '')}")
        parts.append(item.get("additionalPlain") or "")
        jobs.append(_job(
            board, "",
            external_id=f"lever:{board.token}:{item['id']}",
            url=item.get("hostedUrl") or "",
            apply_url=item.get("applyUrl") or None,
            title=(item.get("text") or "").strip(),
            location=cats.get("location") or ", ".join(cats.get("allLocations") or []),
            country=(item.get("country") or "").upper() or None,
            remote_type=_remote(item.get("workplaceType")),
            description="\n\n".join(p.strip() for p in parts if p and p.strip()),
            posted_at=_dt(item.get("createdAt")),
        ))
    return jobs


def parse_ashby(payload: dict[str, Any], board: Board) -> list[RawJob]:
    jobs = []
    for item in payload.get("jobs") or []:
        if item.get("isListed") is False:
            continue
        address = ((item.get("address") or {}).get("postalAddress") or {})
        location = item.get("location") or address.get("addressLocality") or ""
        remote = _remote(item.get("workplaceType"))
        if remote == RemoteType.unknown and item.get("isRemote"):
            remote = RemoteType.remote
        jobs.append(_job(
            board, "",
            external_id=f"ashby:{board.token}:{item['id']}",
            url=item.get("jobUrl") or "",
            apply_url=item.get("applyUrl") or None,
            title=(item.get("title") or "").strip(),
            location=location,
            country=country_from_text(address.get("addressCountry")) or country_from_text(location),
            remote_type=remote,
            description=item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml")),
            posted_at=_dt(item.get("publishedAt")),
        ))
    return jobs


def parse_workable(payload: dict[str, Any], board: Board) -> list[RawJob]:
    jobs = []
    seen: set[str] = set()
    for item in payload.get("jobs") or []:
        if item.get("shortcode") in seen:  # Workable repeats a posting once per location
            continue
        seen.add(item.get("shortcode"))
        loc = (item.get("locations") or [{}])[0]
        city = item.get("city") or loc.get("city") or ""
        country_name = item.get("country") or loc.get("country") or ""
        code = (loc.get("countryCode") or "").upper() or None
        remote = RemoteType.remote if item.get("telecommuting") else RemoteType.unknown
        if str(item.get("workplace") or "").lower() in {"hybrid", "on_site", "remote"}:
            remote = _remote(item.get("workplace"))
        jobs.append(_job(
            board, payload.get("name") or "",
            external_id=f"workable:{board.token}:{item.get('shortcode')}",
            url=item.get("url") or item.get("shortlink") or "",
            apply_url=item.get("application_url") or None,
            title=(item.get("title") or "").strip(),
            location=", ".join(p for p in (city, country_name) if p),
            country=code,
            remote_type=remote,
            description=html_to_text(item.get("description")),
            posted_at=_dt(item.get("published_on") or item.get("created_at")),
        ))
    return jobs


def _sr_text(detail: dict[str, Any]) -> str:
    sections = ((detail.get("jobAd") or {}).get("sections") or {})
    parts = []
    for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        sec = sections.get(key) or {}
        if sec.get("text"):
            parts.append(f"## {sec.get('title') or key}\n\n{html_to_text(sec['text'])}")
    return "\n\n".join(parts)


def parse_smartrecruiters(
    items: list[dict[str, Any]], board: Board, details: dict[str, dict[str, Any]] | None = None
) -> list[RawJob]:
    details = details or {}
    jobs = []
    for item in items:
        loc = item.get("location") or {}
        location = loc.get("fullLocation") or ", ".join(
            p for p in (loc.get("city"), loc.get("country", "").upper()) if p
        )
        remote = RemoteType.remote if loc.get("remote") else (
            RemoteType.hybrid if loc.get("hybrid") else RemoteType.unknown
        )
        detail = details.get(str(item["id"]))
        jobs.append(_job(
            board, (item.get("company") or {}).get("name") or "",
            external_id=f"smartrecruiters:{board.token}:{item['id']}",
            url=f"https://jobs.smartrecruiters.com/{board.token}/{item['id']}",
            apply_url=(detail or {}).get("applyUrl") or None,
            title=(item.get("name") or "").strip(),
            location=location,
            country=(loc.get("country") or "").upper() or None,
            remote_type=remote,
            description=_sr_text(detail) if detail else "",
            posted_at=_dt(item.get("releasedDate")),
        ))
        if not detail:
            jobs[-1].description_level = DescriptionLevel.snippet
    return jobs


def _sr_worth_detail(item: dict[str, Any], profile: ProfileSpec) -> bool:
    """Would this posting plausibly survive the pre-filter? Only then is the detail worth a call."""
    tracks = tracks_of(profile)
    if tracks and not match_track(item.get("name") or "", tracks):
        return False
    loc = item.get("location") or {}
    targets = {c.upper() for c in profile.locations}
    return bool(loc.get("remote")) or not targets or (loc.get("country") or "").upper() in targets


class CompanyBoardsSource:
    source = Source.boards
    cooldown_hours = 6.0
    settings_key = "company_boards"

    def __init__(self, boards: list[Board] | None = None) -> None:
        self.boards = boards or []
        self.requests = 0
        self.warnings: list[str] = []
        self.board_results: dict[str, str | int] = {}  # label → job count, or an error

    def apply_settings(self, value: dict[str, Any] | None) -> None:
        self.boards = parse_boards(value)

    def configured(self) -> str | None:
        return None if self.boards else "add company boards below (Greenhouse, Lever, Ashby…)"

    def _fetch_board(
        self, client: PoliteClient, board: Board, profile: ProfileSpec
    ) -> list[RawJob]:
        if board.ats != "smartrecruiters":
            payload = client.get_json(list_url(board))
            parser = {"greenhouse": parse_greenhouse, "lever": parse_lever,
                      "ashby": parse_ashby, "workable": parse_workable}[board.ats]
            return parser(payload, board)
        items: list[dict[str, Any]] = []
        for page in range(SR_MAX_PAGES):
            payload = client.get_json(
                list_url(board), params={"limit": SR_PAGE, "offset": page * SR_PAGE}
            )
            items += payload.get("content") or []
            if len(items) >= int(payload.get("totalFound") or 0) or not payload.get("content"):
                break
        details = {}
        for item in [i for i in items if _sr_worth_detail(i, profile)][:SR_MAX_DETAILS]:
            details[str(item["id"])] = client.get_json(f"{list_url(board)}/{item['id']}")
        return parse_smartrecruiters(items, board, details)

    def fetch(self, profile: ProfileSpec) -> list[RawJob]:
        self.warnings, self.board_results, self.requests = [], {}, 0
        jobs: list[RawJob] = []
        failures = 0
        with PoliteClient("Company boards", min_interval=1.0, retries=2) as client:
            try:
                for board in self.boards:
                    try:
                        found = self._fetch_board(client, board, profile)
                    except SourceError as exc:
                        failures += 1
                        self.board_results[board.label] = f"error: {exc}"[:300]
                        self.warnings.append(f"{board.label} failed: {exc}"[:300])
                        continue
                    self.board_results[board.label] = len(found)
                    if not found:
                        # Workable/SmartRecruiters answer 200 + nothing for unknown companies.
                        self.warnings.append(f"{board.label}: 0 jobs (check the token)")
                    jobs += found
            finally:
                self.requests = client.requests
        if self.boards and failures == len(self.boards):
            raise SourceError(f"All {failures} company boards failed; see warnings")
        return jobs
