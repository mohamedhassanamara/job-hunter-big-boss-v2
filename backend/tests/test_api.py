import shutil

import pytest
from fastapi.testclient import TestClient

GET_ENDPOINTS = [
    "/api/health",
    "/api/today",
    "/api/nav-counts",
    "/api/jobs",
    "/api/jobs?stage=all&sort=newest",
    "/api/applications",
    "/api/outreach/drafts?status=all",
    "/api/queue",
    "/api/experience",
    "/api/companies",
    "/api/contacts/lookups",
    "/api/settings",
    "/api/search-profile",
    "/api/search?q=engineer",
    "/api/discovery/status",
    "/api/sources",
]


@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_get_endpoints_ok(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200


def _job_by_title(client: TestClient, title: str, stage: str = "all") -> dict:
    items = client.get(f"/api/jobs?stage={stage}").json()["items"]
    return next(i for i in items if i["title"] == title)


def test_seed_shape(client: TestClient) -> None:
    jobs = client.get("/api/jobs?stage=all").json()
    assert 15 <= jobs["total"] <= 20
    assert {i["source"] for i in jobs["items"]} == {"adzuna", "remotive", "arbeitnow", "wttj"}
    stages = {c["stage"] for c in client.get("/api/applications").json()}
    assert stages == {"new", "shortlisted", "cv_ready", "drafted", "ready", "done", "interview",
                      "closed"}
    assert sum(1 for i in jobs["items"] if i["duplicate_of_id"]) == 2


def test_job_filters_and_sort(client: TestClient) -> None:
    items = client.get("/api/jobs?stage=all&min_score=80").json()["items"]
    assert items and all(i["fit"]["score"] >= 80 for i in items)
    scores = [i["fit"]["score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    remote = client.get("/api/jobs?stage=all&remote=remote").json()["items"]
    assert remote and all(i["remote_type"] == "remote" for i in remote)
    no_dups = client.get("/api/jobs?stage=all&hide_duplicates=true").json()["items"]
    assert all(i["duplicate_of_id"] is None for i in no_dups)


def test_job_detail(client: TestClient) -> None:
    job = _job_by_title(client, "Applied AI Engineer")
    detail = client.get(f"/api/jobs/{job['id']}").json()
    assert detail["fit_detail"]["strengths"]
    assert detail["contact"]["full_name"]
    assert detail["events"][0]["at"] >= detail["events"][-1]["at"]
    assert client.get("/api/jobs/99999").status_code == 404


def test_shortlist_then_undo(client: TestClient) -> None:
    job = _job_by_title(client, "Senior Data Engineer", stage="new")
    r = client.post(f"/api/jobs/{job['id']}/shortlist")
    assert r.status_code == 200 and r.json()["application"]["stage"] == "shortlisted"
    app_id = r.json()["application"]["id"]
    undo = client.patch(f"/api/applications/{app_id}", json={"stage": "new"})
    assert undo.json()["stage"] == "new"


def test_dismiss_and_invalid_transition(client: TestClient) -> None:
    job = _job_by_title(client, "Junior BI Developer", stage="new")
    r = client.post(f"/api/jobs/{job['id']}/dismiss")
    assert r.json()["application"]["close_reason"] == "dismissed"
    app_id = r.json()["application"]["id"]
    bad = client.patch(f"/api/applications/{app_id}", json={"stage": "cv_ready"})
    assert bad.status_code == 409
    assert "Can't move" in bad.json()["detail"]


@pytest.mark.skipif(shutil.which("latexmk") is None, reason="needs TeX Live")
def test_cv_flow(client: TestClient) -> None:
    job = _job_by_title(client, "LLM Engineer")
    app_id = job["application"]["id"]
    profile = client.get("/api/settings").json()["values"]["profile"]
    blocked = client.put("/api/settings/profile", json={"value": {**profile, "full_name": ""}})
    assert blocked.status_code == 200
    no_name = client.post(f"/api/applications/{app_id}/cv/generate", json={})
    assert no_name.status_code == 422 and "full name" in no_name.json()["detail"]
    client.put("/api/settings/profile", json={"value": {**profile, "full_name": "Test Person"}})

    new = client.post(f"/api/applications/{app_id}/cv/generate", json={}).json()
    assert new["status"] == "draft" and new["page_count"] == 1 and new["has_pdf"]
    studio = client.get(f"/api/applications/{app_id}/cv").json()
    assert studio["versions"][0]["id"] == new["id"] and studio["usage"]["roles"]
    pdf = client.get(f"/api/cv/{new['id']}/pdf?download=true")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "Test_Person_CV_" in pdf.headers["content-disposition"]

    # Edit a bullet and force a project out: re-rendered in place, no generator call.
    bullet = studio["usage"]["roles"][0]["bullets"][0]
    edited = client.patch(f"/api/cv/{new['id']}", json={
        "text": {bullet["key"]: bullet["text"] + " Quickly."}}).json()
    assert edited["id"] == new["id"] and edited["page_count"] == 1
    assert any(bullet["text"] + " Quickly." in b for r in edited["content"]["roles"]
               for b in r["bullets"])

    result = client.post(f"/api/cv/{new['id']}/approve").json()
    assert result["stage"] == "cv_ready"
    assert result["next_step"] == "draft_email"  # this job has a contact
    # Changing an approved CV creates a new draft instead of editing it.
    again = client.patch(f"/api/cv/{new['id']}", json={"force_out": []}).json()
    assert again["id"] != new["id"] and again["status"] == "draft"
    client.put("/api/settings/profile", json={"value": profile})


def test_outreach_flow(client: TestClient) -> None:
    drafts = client.get("/api/outreach/drafts").json()
    queue_before = client.get("/api/queue").json()["counts"]["pending"]
    first, second = drafts[0], drafts[1]
    edited = client.patch(f"/api/outreach/drafts/{first['id']}", json={"subject": "New subject"})
    assert edited.json()["edited"] is True
    approved = client.post(f"/api/outreach/drafts/{first['id']}/approve").json()
    assert approved["status"] == "approved"  # approving doesn't queue
    assert client.get("/api/queue").json()["counts"]["pending"] == queue_before
    queued = client.post(f"/api/outreach/drafts/{first['id']}/queue").json()
    assert queued["status"] == "queued"
    assert client.get("/api/queue").json()["counts"]["pending"] == queue_before + 1
    rejected = client.post(f"/api/outreach/drafts/{second['id']}/reject").json()
    assert rejected["status"] == "rejected"
    restored = client.post(f"/api/outreach/drafts/{second['id']}/restore").json()
    assert restored["status"] == "draft"


def test_queue_pause_resume_remove(client: TestClient) -> None:
    running = client.post("/api/queue/resume").json()
    assert running["status"] == "running" and running["next_send_at"]
    pending = [i for i in running["items"] if i["status"] == "pending"]
    assert pending[0]["scheduled_at"] < pending[1]["scheduled_at"]
    assert client.post("/api/queue/pause").json()["status"] == "paused"
    after = client.delete(f"/api/queue/items/{pending[0]['id']}").json()
    assert after["counts"]["pending"] == len(pending) - 1


def test_experience_crud_and_reorder(client: TestClient) -> None:
    created = client.post(
        "/api/experience",
        json={"kind": "project", "title": "Test project", "bullets": ["a"], "tags": ["x"]},
    )
    assert created.status_code == 201
    item = created.json()
    patched = client.patch(f"/api/experience/{item['id']}", json={"title": "Renamed"}).json()
    assert patched["title"] == "Renamed"
    projects = [i for i in client.get("/api/experience").json() if i["kind"] == "project"]
    ids = [p["id"] for p in reversed(projects)]
    reordered = client.post("/api/experience/reorder", json={"kind": "project", "ids": ids}).json()
    assert [i["id"] for i in reordered if i["kind"] == "project"] == ids
    assert client.delete(f"/api/experience/{item['id']}").status_code == 204


def test_experience_volunteering_kind(client: TestClient) -> None:
    body = {"kind": "volunteering", "title": "Flutter Instructor", "org": "Android Club"}
    item = client.post("/api/experience", json=body).json()
    assert item["kind"] == "volunteering"
    assert client.post("/api/experience", json={**body, "kind": "hobby"}).status_code == 422
    assert client.delete(f"/api/experience/{item['id']}").status_code == 204


def test_settings_and_profile(client: TestClient) -> None:
    r = client.put("/api/settings/sources", json={"value": {"adzuna": False, "wttj": True}})
    assert r.json()["values"]["sources"]["adzuna"] is False
    profile = client.get("/api/search-profile").json()
    profile["min_fit_score"] = 70
    profile["max_age_days"] = 14
    saved = client.put("/api/search-profile", json=profile).json()
    assert saved["min_fit_score"] == 70 and saved["max_age_days"] == 14


def test_discovery_run_mock(client: TestClient) -> None:
    import time

    before = client.get("/api/jobs?stage=all").json()["total"]
    started = client.post("/api/discovery/run")
    assert started.status_code == 202
    for _ in range(100):
        status = client.get("/api/discovery/status").json()
        if not status["running"]:
            break
        time.sleep(0.05)
    run = status["run"]
    assert run["id"] == started.json()["run_id"] and run["status"] == "success"
    assert {s["source"] for s in run["sources"]} == {
        "adzuna", "remotive", "arbeitnow", "wttj", "boards", "bayt",
    }
    assert client.get("/api/jobs?stage=all").json()["total"] > before


def test_sources_list_and_dry_run(client: TestClient) -> None:
    sources = {s["source"]: s for s in client.get("/api/sources").json()}
    assert set(sources) == {"adzuna", "remotive", "arbeitnow", "wttj", "boards", "bayt"}
    locations = client.get("/api/search-profile").json()["locations"]
    assert "PT" in sources["adzuna"]["unsupported_countries"] or "PT" not in locations
    assert sources["remotive"]["unsupported_countries"] == []
    assert "FR" in sources["bayt"]["unsupported_countries"] or "FR" not in locations
    assert sources["boards"]["configured"]  # default company list is seeded


def test_company_boards_setting_is_validated(client: TestClient) -> None:
    good = {"boards": [{"ats": "greenhouse", "token": "tamara", "company": "Tamara"}]}
    assert client.put("/api/settings/company_boards", json={"value": good}).status_code == 200
    bad = {"boards": [{"ats": "taleo", "token": "x"}]}
    assert client.put("/api/settings/company_boards", json={"value": bad}).status_code == 422
    empty = {"boards": [{"ats": "lever", "token": " "}]}
    assert client.put("/api/settings/company_boards", json={"value": empty}).status_code == 422
    before = client.get("/api/jobs?stage=all").json()["total"]
    result = client.post("/api/sources/arbeitnow/test").json()
    assert result["fetched"] == result["kept"] + result["filtered"]
    assert client.get("/api/jobs?stage=all").json()["total"] == before  # dry run writes nothing


def test_countries_and_remote_scope(client: TestClient) -> None:
    codes = {c["code"]: c for c in client.get("/api/countries").json()}
    assert codes["AE"]["region"] == "Middle East & North Africa"
    assert codes["BE"]["region"] == "Europe"
    profile = client.get("/api/search-profile").json()
    saved = client.put(
        "/api/search-profile", json={**profile, "locations": ["BE", "JO"], "remote_scope": "europe"}
    ).json()
    assert saved["locations"] == ["BE", "JO"] and saved["remote_scope"] == "europe"
    bad = client.put("/api/search-profile", json={**profile, "locations": ["XX"]})
    assert bad.status_code == 422
    bad = client.put("/api/search-profile", json={**profile, "remote_scope": "mars"})
    assert bad.status_code == 422
    client.put("/api/search-profile", json=profile)


def test_contacts_import_preview(client: TestClient) -> None:
    csv_data = "First Name,Last Name,Title,Email,Company\nAna,Ruiz,CTO,ana@x.example,X\n"
    r = client.post(
        "/api/contacts/import/preview", files=[("files", ("apollo.csv", csv_data, "text/csv"))]
    )
    [body] = r.json()
    assert body["total_rows"] == 1
    assert body["mapping"]["email"] == "Email"
    assert body["mapping"]["company"] == "Company"


def test_manual_run_can_ignore_a_source_cooldown(client: TestClient) -> None:
    import time

    r = client.post("/api/discovery/run?ignore_cooldown=adzuna")
    assert r.status_code == 202
    for _ in range(100):
        if not client.get("/api/discovery/status").json()["running"]:
            break
        time.sleep(0.05)
