"""Company job boards + Bayt: mappers against recorded real responses, and fetch behaviour with a
mocked transport (per-board failure isolation, detail budget, robots-friendly Bayt URLs)."""

import json
from functools import partial
from pathlib import Path

import httpx
import pytest

from app.models.enums import DescriptionLevel, RemoteType, Source
from app.providers import http
from app.providers.base import ProfileSpec
from app.providers.sources import bayt, boards
from app.providers.sources.bayt import BaytSource, parse_bayt, search_url
from app.providers.sources.boards import Board, CompanyBoardsSource, parse_boards

from .test_sources import assert_common

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
PROFILE = ProfileSpec(roles=["Data Engineer", "AI Engineer"], locations=["FR", "AE", "QA"])


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("ats", ["greenhouse", "lever", "ashby", "workable"])
def test_board_mappers(ats: str) -> None:
    board = Board(ats, "acme", "Acme")
    jobs = getattr(boards, f"parse_{ats}")(fixture(f"boards_{ats}.json"), board)
    assert_common(jobs, Source.boards)
    assert all(j.company == "Acme" for j in jobs)  # the configured display name wins
    assert all(j.external_id.startswith(f"{ats}:acme:") for j in jobs)
    assert all(j.description_level == DescriptionLevel.full for j in jobs)
    assert sum(bool(j.description) for j in jobs) >= len(jobs) - 1  # demo boards have blanks


def test_greenhouse_unescapes_content_and_detects_gulf_country() -> None:
    jobs = boards.parse_greenhouse(fixture("boards_greenhouse.json"), Board("greenhouse", "tamara"))
    assert {j.country for j in jobs} & {"AE", "SA"}
    assert all("&lt;" not in j.description for j in jobs)


def test_smartrecruiters_uses_detail_when_fetched() -> None:
    payload = fixture("boards_smartrecruiters.json")
    first = str(payload["content"][0]["id"])
    jobs = boards.parse_smartrecruiters(
        payload["content"], Board("smartrecruiters", "DeliveryHero"), {first: payload["_detail"]}
    )
    assert_common(jobs, Source.boards)
    assert jobs[0].description and jobs[0].description_level == DescriptionLevel.full
    assert all(j.description_level == DescriptionLevel.snippet for j in jobs[1:])
    assert all(", ," not in j.location for j in jobs)


def test_parse_boards_skips_invalid_rows() -> None:
    value = {"boards": [
        {"ats": "Greenhouse", "token": " tamara ", "company": "Tamara"},
        {"ats": "taleo", "token": "x"},
        {"ats": "lever", "token": ""},
        {"ats": "ashby", "token": "ziina", "enabled": False},
    ]}
    assert parse_boards(value) == [Board("greenhouse", "tamara", "Tamara")]
    assert CompanyBoardsSource().configured()  # empty list → not configured
    src = CompanyBoardsSource()
    src.apply_settings(value)
    assert src.configured() is None


def _patch_client(monkeypatch: pytest.MonkeyPatch, module, handler) -> list[str]:  # noqa: ANN001
    seen: list[str] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    factory = partial(http.PoliteClient, transport=httpx.MockTransport(wrapped),
                      sleep=lambda _: None)
    monkeypatch.setattr(module, "PoliteClient", factory)
    return seen


def test_one_broken_board_does_not_fail_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "greenhouse" in request.url.host:
            return httpx.Response(200, json=fixture("boards_greenhouse.json"))
        if "workable" in request.url.host:
            return httpx.Response(200, json={"name": "Ghost", "jobs": []})
        return httpx.Response(404, json={"error": "not found"})

    _patch_client(monkeypatch, boards, handler)
    src = CompanyBoardsSource([Board("greenhouse", "tamara", "Tamara"),
                               Board("lever", "gone", "Gone"), Board("workable", "ghost")])
    jobs = src.fetch(PROFILE)
    assert jobs and all(j.company == "Tamara" for j in jobs)
    assert src.board_results["Tamara (greenhouse)"] == len(jobs)
    assert str(src.board_results["Gone (lever)"]).startswith("error:")
    assert src.board_results["ghost (workable)"] == 0
    assert any("0 jobs (check the token)" in w for w in src.warnings)
    assert any("Gone (lever) failed" in w for w in src.warnings)


def test_all_boards_failing_fails_the_source(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, boards, lambda r: httpx.Response(404, json={}))
    src = CompanyBoardsSource([Board("lever", "a"), Board("ashby", "b")])
    with pytest.raises(http.SourceError, match="All 2 company boards failed"):
        src.fetch(PROFILE)


def test_smartrecruiters_details_only_for_plausible_postings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        {"id": "1", "name": "Senior Data Engineer", "location": {"country": "ae", "city": "Dubai"}},
        {"id": "2", "name": "Accountant", "location": {"country": "ae"}},  # not a role
        {"id": "3", "name": "Data Engineer", "location": {"country": "de"}},  # not a target
        {"id": "4", "name": "AI Engineer", "location": {"country": "us", "remote": True}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/postings"):
            return httpx.Response(200, json={"totalFound": 4, "content": items})
        return httpx.Response(200, json=fixture("boards_smartrecruiters.json")["_detail"])

    seen = _patch_client(monkeypatch, boards, handler)
    jobs = CompanyBoardsSource([Board("smartrecruiters", "DeliveryHero")]).fetch(PROFILE)
    details = [u for u in seen if not u.split("?")[0].endswith("postings")]
    detail_ids = sorted(u.rsplit("/", 1)[1] for u in details)
    assert detail_ids == ["1", "4"]
    assert len(jobs) == 4


# ------------------------------------------------------------------------------------ Bayt


def test_bayt_mapper() -> None:
    jobs = parse_bayt((FIXTURES / "bayt_uae_data_engineer.html").read_text(), "AE")
    assert_common(jobs, Source.bayt)
    assert len(jobs) >= 20
    assert all(j.country == "AE" for j in jobs)
    assert all(j.url.startswith("https://www.bayt.com/en/uae/jobs/") for j in jobs)
    assert all(j.posted_at for j in jobs)
    assert all(j.description_level == DescriptionLevel.snippet for j in jobs)
    assert any(j.remote_type == RemoteType.hybrid for j in jobs)
    assert any("Experience:" in j.description for j in jobs)


def test_bayt_urls_stay_on_robots_allowed_country_paths() -> None:
    url = search_url("AE", "Data Engineer")
    assert url == "https://www.bayt.com/en/uae/jobs/data-engineer-jobs/"
    assert "/en/jobs/" not in url and "filters" not in url
    assert search_url("SA", "Analytics Engineer").endswith(
        "/en/saudi-arabia/jobs/analytics-engineer-jobs/"
    )


def test_bayt_queries_only_covered_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    page = (FIXTURES / "bayt_uae_data_engineer.html").read_text()
    seen = _patch_client(monkeypatch, bayt, lambda r: httpx.Response(200, text=page))
    src = BaytSource()
    jobs = src.fetch(PROFILE)
    assert len(seen) == 4  # 2 roles × {AE, QA}; France isn't on Bayt
    assert len(jobs) == len({j.external_id for j in jobs})  # deduped across queries
    assert BaytSource.unsupported_countries(["FR", "AE", "BE"]) == ["FR", "BE"]


def test_bayt_without_gulf_targets_makes_no_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_client(monkeypatch, bayt, lambda r: httpx.Response(500))
    src = BaytSource()
    assert src.fetch(PROFILE.model_copy(update={"locations": ["FR"]})) == []
    assert seen == [] and src.warnings
