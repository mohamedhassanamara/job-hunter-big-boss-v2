"""People captured through the extension API: preview (writes nothing), save, the job they join, the
waiting list that links itself when a job at their company is captured, role / alum overrides, and
deleting the snapshot. Offline, real workspace of the test DB."""

from sqlmodel import Session, select

from app.db import engine
from app.models import Contact, LinkedInOutreach, LinkedInProfile
from app.services.cv_pool import load_pool
from app.services.linkedin_track import school
from tests.test_linkedin_page import job_payload, profile_payload


def _h(client) -> dict[str, str]:  # noqa: ANN001
    token = client.post("/api/linkedin/extension/token", json={}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _profile(company: str, slug: str = "maria-exemplo", name: str = "Maria Exemplo",
             headline: str = "Senior Data Engineer", school_name: str | None = None) -> dict:
    p = profile_payload()
    p["slug"], p["name_parsed"] = slug, name
    p["url"] = f"https://www.linkedin.com/in/{slug}/"
    p["regions"][0]["lines"][0] = name
    p["regions"][0]["lines"][2] = f"{headline} at {company}"
    p["regions"][2]["lines"][1] = f"{company} · Full-time"
    p["links"][0]["text"] = company
    if school_name:
        p["regions"][3]["lines"][0] = school_name
        p["links"][1]["text"] = school_name
    return p


def test_preview_writes_nothing_and_explains_the_role(client) -> None:  # noqa: ANN001
    h = _h(client)
    out = client.post("/api/ext/person/preview", json={"payload": _profile("Previewco Phase3")},
                      headers=h).json()
    assert out["saved"] is False and out["persona"] == "peer" and out["job"] is None
    assert out["current_company"] == "Previewco Phase3" and out["missing"] == []
    with Session(engine) as s:
        assert s.exec(select(LinkedInProfile)).all() == [] or all(
            p.public_id != "maria-exemplo" for p in s.exec(select(LinkedInProfile)).all())


def test_a_person_without_a_job_waits_and_joins_the_job_captured_later(client) -> None:  # noqa: ANN001
    h = _h(client)
    saved = client.post("/api/ext/person", json={"payload": _profile("Waitco Phase3")},
                        headers=h).json()
    assert saved["saved"] and saved["job"] is None and saved["contact_id"]
    people = client.get("/api/linkedin/profiles").json()
    assert any(p["contact_id"] == saved["contact_id"] and p["jobs"] == [] for p in people["items"])
    # the job at that company is captured afterwards: the person joins it by themselves
    cap = client.post("/api/ext/job", json={"payload": job_payload(
        url="https://www.linkedin.com/jobs/view/4099999977/", job_id="4099999977",
        title_parsed="Data Engineer", company_parsed="Waitco Phase3",
        about={"lines": ["We build data pipelines with Spark and Airflow. " * 6]})},
        headers=h).json()
    assert cap["saved"] and any("joined this job" in w for w in cap["warnings"])
    with Session(engine) as s:
        row = s.exec(select(LinkedInOutreach).where(
            LinkedInOutreach.contact_id == saved["contact_id"])).one()
        assert row.source == "extension" and row.group == "peer"
    again = client.post("/api/ext/person", json={"payload": _profile("Waitco Phase3")},
                        headers=h).json()
    assert again["existing"] and again["job"]["title"] == "Data Engineer"


def test_roles_alum_and_overrides_stick(client) -> None:  # noqa: ANN001
    h = _h(client)
    with Session(engine) as s:
        short, _full = school(load_pool(s))
    assert short  # the seeded pool has a school
    body = {"payload": _profile("Rolesco Phase3", slug="lee-lead", name="Lee Lead",
                                headline="Head of Data", school_name=short)}
    first = client.post("/api/ext/person", json=body, headers=h).json()
    assert first["persona"] == "lead" and first["alumni"] is True and first["school"] == short
    cid = first["contact_id"]
    # you pick a role: it is kept on the next capture of the same person
    patched = client.patch(f"/api/ext/person/{cid}", json={"persona": "recruiter"}, headers=h)
    assert patched.status_code == 200 and patched.json()["persona"] == "recruiter"
    second = client.post("/api/ext/person", json=body, headers=h).json()
    assert second["persona"] == "recruiter" and second["persona_source"] == "manual"
    bad = client.patch(f"/api/ext/person/{cid}", json={"persona": "boss"}, headers=h)
    assert bad.status_code == 422
    # alum is a flag, never a role
    off = client.patch(f"/api/ext/person/{cid}", json={"alumni": False}, headers=h).json()
    assert off["alumni"] is False and off["persona"] == "recruiter"


def test_missing_company_asks_for_it_and_paste_is_a_fallback(client) -> None:  # noqa: ANN001
    h = _h(client)
    p = profile_payload()
    p["regions"][0]["lines"][2] = "Freelance data person"
    p["regions"][2]["lines"] = ["Notes only"]
    p["links"] = []
    r = client.post("/api/ext/person", json={"payload": p}, headers=h).json()
    assert r["saved"] is False and r["missing"] == ["company"]
    typed = client.post("/api/ext/person", json={"payload": p, "company": "Typedco Phase3"},
                        headers=h).json()
    assert typed["saved"] and typed["current_company"] == "Typedco Phase3"
    pasted = client.post("/api/ext/person", headers=h, json={
        "paste": "Pia Pasted\nData Engineer at Pastedco Phase3\nhttps://www.linkedin.com/in/pia-pasted"
    }).json()
    assert pasted["saved"] and pasted["name"] == "Pia Pasted"
    assert pasted["current_company"] == "Pastedco Phase3"


def test_delete_snapshot_keeps_the_contact(client) -> None:  # noqa: ANN001
    h = _h(client)
    cid = client.post("/api/ext/person", json={"payload": _profile("Snapco Phase3", slug="sam-snap",
                                                                    name="Sam Snap")},
                      headers=h).json()["contact_id"]
    assert client.delete(f"/api/linkedin/profiles/{cid}").status_code == 204
    assert client.delete(f"/api/linkedin/profiles/{cid}").status_code == 404
    with Session(engine) as s:
        assert s.get(Contact, cid) is not None
        left = select(LinkedInProfile).where(LinkedInProfile.contact_id == cid)
        assert s.exec(left).first() is None
