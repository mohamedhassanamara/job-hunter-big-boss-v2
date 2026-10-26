"""Mapper tests against real responses recorded by scripts/record_fixtures.py (offline)."""

import json
import re
from pathlib import Path

import pytest

from app.models.enums import RemoteType, Source
from app.providers.base import RawJob

FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def assert_common(jobs: list[RawJob], source: Source) -> None:
    assert jobs, "fixture produced no jobs"
    ids = [j.external_id for j in jobs]
    assert len(ids) == len(set(ids)), "external ids must be unique"
    for j in jobs:
        assert j.source == source
        assert j.title and j.company, j
        assert j.url.startswith("https://"), j.url
        assert j.remote_type in set(RemoteType)
        leftover = re.search(r"</?[a-z]+[^>]*>|&lt;|&gt;|&nbsp;", j.description)
        assert not leftover, j.description[:200]
        assert j.posted_at is None or j.posted_at.tzinfo is not None
        assert j.country is None or (len(j.country) == 2 and j.country.isupper())


def test_arbeitnow_mapper() -> None:
    from app.providers.sources.arbeitnow import parse_arbeitnow

    payload = load("arbeitnow")
    jobs = parse_arbeitnow(payload)
    assert_common(jobs, Source.arbeitnow)
    assert len(jobs) == len(payload["data"])
    by_id = {j.external_id: j for j in jobs}
    for item in payload["data"]:
        j = by_id[item["slug"]]
        assert j.title == item["title"].strip()
        if item["remote"] in (True, "true", "True"):
            assert j.remote_type == RemoteType.remote
    # Munich/Berlin/Hamburg… resolve to Germany through the city gazetteer.
    assert any(j.country == "DE" for j in jobs)
    # Paragraph/bullet structure survives the HTML cleanup.
    assert any("\n- " in j.description or j.description.startswith("- ") for j in jobs)


def test_remotive_mapper() -> None:
    from app.providers.sources.remotive import parse_remotive

    payload = load("remotive")
    jobs = parse_remotive(payload)
    assert_common(jobs, Source.remotive)
    assert all(j.remote_type == RemoteType.remote for j in jobs)
    assert all(j.url.startswith("https://remotive.com/") for j in jobs)  # link back (ToS)
    by_id = {j.external_id: j for j in jobs}
    for item in payload["jobs"]:
        j = by_id[str(item["id"])]
        assert j.location == (item["candidate_required_location"] or "Remote").strip()
        region = item["candidate_required_location"]
        if region == "USA":
            assert j.country == "US"
        if region in ("Worldwide", "Europe") or "," in region:
            assert j.country is None


def test_wttj_mapper() -> None:
    from app.providers.sources.wttj import parse_wttj

    payload = load("wttj")
    jobs = parse_wttj(payload, {"ES", "IT"})
    assert_common(jobs, Source.wttj)
    hits = {h["objectID"]: h for r in payload["results"] for h in r["hits"]}
    assert len(jobs) == len(hits)  # same job in several queries → stored once
    for j in jobs:
        hit = hits[j.external_id]
        assert j.url == (
            "https://www.welcometothejungle.com/en/companies/"
            f"{hit['organization']['slug']}/jobs/{hit['slug']}"
        )
        expected = {"fulltime": "remote", "partial": "hybrid", "punctual": "hybrid", "no": "onsite"}
        assert j.remote_type == expected.get(hit.get("remote"), "unknown")
        if hit.get("key_missions"):
            assert "## Key missions" in j.description
    assert any(j.country == "ES" for j in jobs) and any(j.country == "IT" for j in jobs)


def test_wttj_queries_cover_roles_countries_and_remote() -> None:
    from app.providers.base import ProfileSpec
    from app.providers.sources.wttj import build_queries

    queries = build_queries(ProfileSpec(roles=["Data Engineer", "ML Engineer"],
                                        locations=["ES", "PT", "FR", "IT"]))
    assert len(queries) == 2 * (4 + 1)
    assert all(q["indexName"] == "wttj_jobs_production_en" for q in queries)
    assert any("remote%3Afulltime" in q["params"] for q in queries)
    assert all("published_at_timestamp%3E%3D" in q["params"] for q in queries)


def test_adzuna_mapper() -> None:
    # NOTE: synthetic fixture (no API keys yet) — re-record once ADZUNA_APP_ID/KEY exist.
    from app.providers.sources.adzuna import parse_adzuna

    payload = load("adzuna")
    jobs = parse_adzuna(payload, payload.get("_country", "ES"))
    assert_common(jobs, Source.adzuna)
    assert len(jobs) == len(payload["results"])
    assert all("<strong>" not in j.title for j in jobs)  # search highlights stripped
    assert all(j.country for j in jobs)
    assert all(j.url.startswith("https://www.adzuna.") for j in jobs)


def test_adzuna_queries_every_supported_target_and_reports_the_rest() -> None:
    from app.providers.base import ProfileSpec
    from app.providers.sources.adzuna import AdzunaSource

    src = AdzunaSource()
    targets = ["FR", "ES", "IT", "PT", "DE", "BE", "AE", "QA", "BH", "KW", "JO"]
    assert src.targets(ProfileSpec(locations=targets)) == ["FR", "ES", "IT", "DE", "BE"]
    assert src.warnings == [
        "Not supported by Adzuna (no endpoint), skipped: PT, AE, QA, BH, KW, JO"
    ]
    assert AdzunaSource.unsupported_countries(["DE", "PT"]) == ["PT"]


# ------------------------------------------------------------- Adzuna: errors and skipped items


def _adzuna_with(monkeypatch: pytest.MonkeyPatch, handler):  # noqa: ANN001, ANN202
    """An AdzunaSource with keys whose HTTP goes to `handler` (no sleeping, no network)."""
    import httpx

    from app.providers.http import PoliteClient
    from app.providers.sources import adzuna

    def client(name: str, **kw):  # noqa: ANN003, ANN202
        return PoliteClient(name, min_interval=0, retries=1, backoff=0, sleep=lambda _s: None,
                            transport=httpx.MockTransport(handler))

    monkeypatch.setattr(adzuna, "PoliteClient", client)
    source = adzuna.AdzunaSource()
    source.app_id, source.app_key = "id", "key"
    return source


def _spec():  # noqa: ANN202
    from app.providers.base import ProfileSpec

    return ProfileSpec(locations=["DE", "FR"], roles=["Data Engineer"], max_age_days=14)


def test_adzuna_401_stops_at_once_with_a_clear_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(401, json={"error": "bad credentials"})

    source = _adzuna_with(monkeypatch, handler)
    assert source.fetch_payloads(_spec()) == []
    assert len(seen) == 1  # no second country, no retries
    assert any("401" in w and "ADZUNA_APP_ID" in w for w in source.warnings)


def test_adzuna_429_keeps_what_was_fetched_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "/de/" in str(request.url):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(429, json={"error": "slow down"})

    source = _adzuna_with(monkeypatch, handler)
    out = source.fetch_payloads(_spec())
    assert [country for country, _ in out] == ["DE"]  # FR hit the limit: stop with DE's batch
    assert any("429" in w and "rate limit" in w.lower() for w in source.warnings)


def test_adzuna_skips_items_without_an_id_or_a_url() -> None:
    from app.providers.sources.adzuna import parse_adzuna

    good = {"id": "1", "title": "Data Engineer", "redirect_url": "https://www.adzuna.de/x/1",
            "company": {"display_name": "Acme"}, "location": {"display_name": "Berlin"},
            "description": "d", "created": "2026-10-20T10:00:00Z"}
    payload = {"results": [good, {**good, "id": None}, {**good, "id": "2", "redirect_url": ""},
                           {k: v for k, v in good.items() if k != "id"}]}
    jobs = parse_adzuna(payload, "DE")
    assert [j.external_id for j in jobs] == ["1"]
