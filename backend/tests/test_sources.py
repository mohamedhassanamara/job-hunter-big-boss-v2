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
