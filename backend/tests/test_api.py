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
    assert stages == {"new", "shortlisted", "cv_ready", "ready", "done", "interview", "closed"}
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
    bad = client.patch(f"/api/applications/{app_id}", json={"stage": "interview"})
    assert bad.status_code == 409
    assert "Can't move" in bad.json()["detail"]


def test_cv_flow(client: TestClient) -> None:
    job = _job_by_title(client, "LLM Engineer")
    app_id = job["application"]["id"]
    studio = client.get(f"/api/applications/{app_id}/cv").json()
    draft = studio["versions"][0]
    assert draft["status"] == "draft"
    content = draft["content"] | {"headline": "Edited headline"}
    assert client.patch(f"/api/cv/{draft['id']}", json={"content": content}).status_code == 200
    new = client.post(f"/api/applications/{app_id}/cv/generate").json()
    assert new["version"] == draft["version"] + 1
    result = client.post(f"/api/cv/{new['id']}/approve").json()
    assert result["stage"] == "cv_ready"
    assert result["next_step"] == "draft_email"  # this job has a contact
    edit_approved = client.patch(f"/api/cv/{new['id']}", json={"content": content})
    assert edit_approved.status_code == 409


def test_outreach_flow(client: TestClient) -> None:
    drafts = client.get("/api/outreach/drafts").json()
    queue_before = client.get("/api/queue").json()["counts"]["pending"]
    first, second = drafts[0], drafts[1]
    edited = client.patch(f"/api/outreach/drafts/{first['id']}", json={"subject": "New subject"})
    assert edited.json()["edited"] is True
    approved = client.post(f"/api/outreach/drafts/{first['id']}/approve").json()
    assert approved["status"] == "queued"
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


def test_settings_and_profile(client: TestClient) -> None:
    r = client.put("/api/settings/sources", json={"value": {"adzuna": False, "wttj": True}})
    assert r.json()["values"]["sources"]["adzuna"] is False
    profile = client.get("/api/search-profile").json()
    profile["min_fit_score"] = 70
    assert client.put("/api/search-profile", json=profile).json()["min_fit_score"] == 70


def test_discovery_run_mock(client: TestClient) -> None:
    before = client.get("/api/jobs?stage=all").json()["total"]
    result = client.post("/api/discovery/run").json()
    assert result["new_jobs"] >= 1
    assert client.get("/api/jobs?stage=all").json()["total"] > before


def test_contacts_import_preview(client: TestClient) -> None:
    csv_data = "First Name,Last Name,Title,Email,Company\nAna,Ruiz,CTO,ana@x.example,X\n"
    r = client.post(
        "/api/contacts/import/preview", files={"file": ("apollo.csv", csv_data, "text/csv")}
    )
    body = r.json()
    assert body["total_rows"] == 1
    assert body["mapping"]["email"] == "Email"
    assert body["mapping"]["company"] == "Company"
