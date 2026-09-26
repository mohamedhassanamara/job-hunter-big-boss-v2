"""Mapper tests against real responses recorded by scripts/record_fixtures.py (offline)."""

import json
import re
from pathlib import Path

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


def test_adzuna_skips_portugal_with_warning() -> None:
    from app.providers.base import ProfileSpec
    from app.providers.sources.adzuna import AdzunaSource

    src = AdzunaSource()
    assert src.targets(ProfileSpec(locations=["ES", "PT", "FR", "IT"])) == ["ES", "FR", "IT"]
    assert src.warnings == ["Adzuna has no PT endpoint; skipped"]
