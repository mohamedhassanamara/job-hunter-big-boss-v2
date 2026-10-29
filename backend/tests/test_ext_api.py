"""The browser extension's API: the token (shown once, only its hash stored), CORS for the exact
extension id, `/api/ext/*` behind the bearer token on the real workspace only. Offline."""

import hashlib

from sqlmodel import Session, select

from app.db import engine
from app.models import AppSetting, Job
from app.services import ext_auth

EXT_ID = "chmdlkfgnkafhlghokcgggmddahnaoao"
OTHER_ID = "a" * 32
CAPTURE = {
    "url": "https://www.linkedin.com/jobs/view/4088888801/", "title": "Data Engineer",
    "company": "Exemplo Ext Labs", "location": "Lisbon, Portugal", "workplace": "Hybrid",
    "description": "We build data pipelines with Spark and Airflow for logistics customers. " * 5,
    "sources": {"title": "page", "company": "page", "description": "page"},
}


def _token(client) -> str:  # noqa: ANN001
    r = client.post("/api/linkedin/extension/token", json={})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_the_token_is_shown_once_and_only_its_hash_is_stored(client) -> None:  # noqa: ANN001
    token = _token(client)
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == ext_auth.KEY)).one()
        assert row.value["sha256"] == hashlib.sha256(token.encode()).hexdigest()
        assert token not in str(row.value)
    status = client.get("/api/linkedin/extension").json()
    assert status["exists"] and token not in str(status) and EXT_ID in status["extension_ids"]
    assert ext_auth.ID_PATTERN.match(EXT_ID)
    # the settings API never exposes it, and cannot write it
    assert "extension_auth" not in client.get("/api/settings").text
    assert client.put("/api/settings/extension_auth", json={"value": {"sha256": "x"}}).status_code \
        in (400, 404, 422)


def test_ext_routes_need_the_current_token(client) -> None:  # noqa: ANN001
    assert client.get("/api/ext/ping").status_code == 401
    assert client.get("/api/ext/ping", headers=_auth("nope")).status_code == 401
    first = _token(client)
    ok = client.get("/api/ext/ping", headers=_auth(first))
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert client.get("/api/linkedin/extension").json()["last_used_at"]
    second = _token(client)  # rotating revokes the old one
    assert client.get("/api/ext/ping", headers=_auth(first)).status_code == 401
    assert client.get("/api/ext/ping", headers=_auth(second)).status_code == 200
    client.delete("/api/linkedin/extension/token")
    assert client.get("/api/ext/ping", headers=_auth(second)).status_code == 401
    assert not client.get("/api/linkedin/extension").json()["exists"]


def test_the_token_opens_nothing_but_ext_and_the_sandbox_is_refused(client) -> None:  # noqa: ANN001
    token = _token(client)
    demo = {**_auth(token), "X-Workspace": "demo"}
    assert client.get("/api/ext/ping", headers=demo).status_code == 400
    assert client.post("/api/linkedin/extension/token", json={},
                       headers={"X-Workspace": "demo"}).status_code == 409
    tour = client.get("/api/linkedin/extension", headers={"X-Workspace": "demo"}).json()
    assert tour["available"] is False and tour["exists"] is False  # the tour can show the card
    # a plain (non-JSON) post cannot rotate the token: no body, no new token
    assert client.post("/api/linkedin/extension/token").status_code == 422
    assert client.get("/api/ext/ping", headers=_auth(token)).status_code == 200


def test_cors_accepts_only_the_exact_extension_origin(client) -> None:  # noqa: ANN001
    def preflight(origin: str):  # noqa: ANN202
        return client.options("/api/ext/ping", headers={
            "Origin": origin, "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-workspace"})

    ok = preflight(f"chrome-extension://{EXT_ID}")
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == f"chrome-extension://{EXT_ID}"
    for bad in (f"chrome-extension://{OTHER_ID}", f"chrome-extension://{EXT_ID}x",
                f"chrome-extension://x{EXT_ID}", "https://evil.example", "null"):
        assert "access-control-allow-origin" not in preflight(bad).headers, bad
    assert preflight("http://localhost:5173").headers["access-control-allow-origin"]
    assert ext_auth.origin_regex(["not-an-id", EXT_ID, EXT_ID]) == \
        rf"^chrome-extension://({EXT_ID})$"
    assert ext_auth.origin_regex(["bad"]) is None


def test_capture_a_job_through_ext_saves_nothing_when_a_field_is_missing(client) -> None:  # noqa: ANN001
    h = _auth(_token(client))
    miss = client.post("/api/ext/job", json={**CAPTURE, "description": ""}, headers=h).json()
    assert miss["saved"] is False and miss["missing"] == ["description"] and miss["job_id"] is None
    status = client.get("/api/ext/status", params={"linkedin_job_id": "4088888801"}, headers=h)
    assert status.json() == {"saved": False, "job_id": None, "title": None, "company": None,
                             "contact_id": None, "full_name": None}
    saved = client.post("/api/ext/job", json=CAPTURE, headers=h).json()
    assert saved["saved"] and saved["created"] and saved["job_id"]
    with Session(engine) as s:
        job = s.get(Job, saved["job_id"])
        assert job.source == "linkedin" and job.linkedin_job_id == "4088888801"
    found = client.get("/api/ext/status", params={"linkedin_job_id": "4088888801"}, headers=h)
    assert found.json()["saved"] and found.json()["job_id"] == saved["job_id"]
    again = client.post("/api/ext/job", json=CAPTURE, headers=h).json()
    assert again["job_id"] == saved["job_id"] and not again["created"]  # idempotent


def test_the_paste_fallback_returns_an_editable_preview(client) -> None:  # noqa: ANN001
    h = _auth(_token(client))
    text = "Data Engineer\nExemplo Ext Labs\nLisbon, Portugal\n" + "Build pipelines. " * 40
    r = client.post("/api/ext/paste", json={"url": CAPTURE["url"], "text": text}, headers=h)
    assert r.status_code == 200 and r.json()["title"] == "Data Engineer"
    assert client.post("/api/ext/paste", json={"text": text}).status_code == 401
