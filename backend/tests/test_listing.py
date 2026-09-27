from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.providers.http import PoliteClient
from app.services.listing import ListingUnavailable, extract_job_posting, fetch_full_listing

PAGE = (Path(__file__).parent / "fixtures" / "sources" / "wttj_job_page.html").read_text()


def client_returning(response: httpx.Response) -> PoliteClient:
    return PoliteClient("t", min_interval=0, retries=0,
                        transport=httpx.MockTransport(lambda r: response))


def test_extracts_full_description_from_json_ld() -> None:
    listing = extract_job_posting(PAGE)
    assert listing is not None
    assert len(listing.description) > 3000  # vs ~1.8k chars in the WTTJ search index
    assert "<" not in listing.description


def test_blocked_site_offers_paste_not_disguise() -> None:
    with pytest.raises(ListingUnavailable) as err:
        fetch_full_listing("https://example.test/job", client_returning(httpx.Response(403)))
    assert err.value.can_paste and "paste" in str(err.value).lower()


def test_page_without_posting() -> None:
    page = httpx.Response(200, text="<html><body>No structured data</body></html>")
    with pytest.raises(ListingUnavailable, match="No structured job posting"):
        fetch_full_listing("https://example.test/job", client_returning(page))


def test_paste_description_raises_level_and_rescores(client: TestClient) -> None:
    job = client.get("/api/jobs?stage=all").json()["items"][0]
    assert client.put(f"/api/jobs/{job['id']}/description",
                      json={"description": "too short"}).status_code == 422
    text = "<h2>About</h2><p>" + ("We build data platforms with Spark. " * 30) + "</p>"
    res = client.put(f"/api/jobs/{job['id']}/description", json={"description": text}).json()
    assert res["ok"] and res["characters"] > 200
    from app.services import scoring

    scoring.workspace_queue("real").wait()
    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert detail["description_level"] == "full" and detail["fit_detail"]["confidence"] == "high"
