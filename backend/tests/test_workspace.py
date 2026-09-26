"""Sample data lives only in the tour sandbox; the real workspace never sees it."""

from fastapi.testclient import TestClient

DEMO = {"X-Workspace": "demo"}


def total(client: TestClient, headers: dict | None = None) -> int:
    return client.get("/api/jobs?stage=all", headers=headers or {}).json()["total"]


def test_sandbox_is_isolated_from_real(client: TestClient) -> None:
    # Start from an empty real workspace.
    assert client.post("/api/workspace/erase", json={"confirm": "ERASE"}).status_code == 204
    assert total(client) == 0
    profile = client.get("/api/search-profile").json()
    assert profile["roles"]  # defaults survive the erase

    assert client.post("/api/sandbox/reset").status_code == 204
    demo_total = total(client, DEMO)
    assert demo_total > 0
    assert total(client) == 0  # real untouched by the sandbox reset

    # Mutations inside a tour only change the sandbox.
    job = client.get("/api/jobs", headers=DEMO).json()["items"][0]
    assert client.post(f"/api/jobs/{job['id']}/dismiss", headers=DEMO).status_code == 200
    assert total(client) == 0

    # A fresh sandbox reset restores the pristine sample data.
    client.post("/api/sandbox/reset")
    assert total(client, DEMO) == demo_total
    restored = client.get(f"/api/jobs/{job['id']}", headers=DEMO).json()
    assert restored["application"]["stage"] == "new"


def test_sandbox_discovery_uses_mock_sources(client: TestClient) -> None:
    client.post("/api/sandbox/reset")
    sources = client.get("/api/sources", headers=DEMO).json()
    assert all(s["configured"] for s in sources)  # mocks need no keys


def test_erase_requires_confirmation(client: TestClient) -> None:
    assert client.post("/api/workspace/erase", json={"confirm": "yes"}).status_code == 422
