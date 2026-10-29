"""One-click capture safety net: review flags instead of a review screen, a guarded Undo, the
LinkedIn Jobs / Profiles lists, and hiding captures from Discover and the company contacts until you
act. Offline."""

from datetime import timedelta

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Job, LinkedInOutreach
from app.models.base import utcnow
from tests.test_ext_people import _h, _profile
from tests.test_linkedin_page import DESCRIPTION, job_payload

LONG = ["We build data pipelines on Spark and Airflow for logistics customers. " * 12]


def _job(client, h, jid: str, company: str, about: list[str] | None = None, **over):  # noqa: ANN001, ANN202
    links = [{"kind": "company", "shape": "/company/<id>/", "text": company, "region": "header",
              "href": "https://www.linkedin.com/company/x/"}]
    payload = job_payload(url=f"https://www.linkedin.com/jobs/view/{jid}/", job_id=jid,
                          title_parsed="Data Engineer", company_parsed=company,
                          about={"lines": about or LONG}, links=links)
    payload.update(over)
    return client.post("/api/ext/job", json={"payload": payload}, headers=h).json()


def test_a_clean_capture_has_no_flags_and_a_collapsed_one_is_flagged(client) -> None:  # noqa: ANN001
    h = _h(client)
    clean = _job(client, h, "4300000001", "Cleanco Phase4")
    assert clean["saved"] and clean["flags"] == [] and clean["undo"] is True
    assert clean["description_chars"] > 500 and clean["description_level"] == "full"
    cut = _job(client, h, "4300000002", "Cutco Phase4", about=DESCRIPTION)
    codes = {f["code"] for f in cut["flags"]}
    assert "collapsed" in codes and "short" not in codes  # collapsed explains the short text
    lst = client.get("/api/linkedin/captured/jobs").json()
    by_id = {i["job_id"]: i for i in lst["items"]}
    assert by_id[cut["job_id"]]["needs_review"] and not by_id[clean["job_id"]]["needs_review"]
    before = client.get("/api/nav-counts").json()["linkedin_review"]
    assert client.post(f"/api/linkedin/captured/jobs/{cut['job_id']}/reviewed").status_code == 204
    assert client.get("/api/nav-counts").json()["linkedin_review"] == before - 1
    again = _job(client, h, "4300000002", "Cutco Phase4", about=DESCRIPTION)  # same read again
    assert again["undo"] is False  # nothing was created this time
    after = {i["job_id"]: i for i in client.get("/api/linkedin/captured/jobs").json()["items"]}
    assert after[cut["job_id"]]["needs_review"] is False  # "Looks right" survives a same recapture


def test_a_company_link_that_was_only_guessed_is_flagged(client) -> None:  # noqa: ANN001
    h = _h(client)
    links = [{"kind": "company", "shape": "/company/<id>/", "text": "Someone Else",
              "region": "header", "href": "https://www.linkedin.com/company/else/"}]
    out = _job(client, h, "4300000003", "Guessco Phase4", links=links)
    assert "company_link" in {f["code"] for f in out["flags"]}


def test_captured_jobs_wait_in_their_own_section_until_you_act(client) -> None:  # noqa: ANN001
    h = _h(client)
    out = _job(client, h, "4300000004", "Hiddenco Phase4")
    jid = out["job_id"]

    def ids(**params) -> set[int]:  # noqa: ANN003
        r = client.get("/api/jobs", params={"stage": "new", **params}).json()
        return {j["id"] for j in r["items"]}

    assert jid not in ids()  # Discover's default list
    assert jid in ids(include_linkedin="true") and jid in ids(source="linkedin")
    with Session(engine) as s:  # shortlisted: now it is normal pipeline work
        app = s.exec(select(Application).where(Application.job_id == jid)).one()
        from app.models.enums import Stage
        from app.services import pipeline

        pipeline.transition(s, app, Stage.shortlisted)
        s.commit()
    opened = client.get("/api/jobs", params={"stage": "open"}).json()["items"]
    assert jid in {j["id"] for j in opened}


def test_undo_a_new_job_dismisses_it_and_is_refused_when_it_is_old_or_moved(client) -> None:  # noqa: ANN001
    h = _h(client)
    new = _job(client, h, "4300000005", "Undoco Phase4")
    assert client.delete(f"/api/ext/job/{new['job_id']}", headers=h).json() == {"undone": True}
    with Session(engine) as s:
        assert s.exec(select(Application).where(
            Application.job_id == new["job_id"])).one().stage == "closed"
    assert client.delete(f"/api/ext/job/{new['job_id']}", headers=h).status_code == 409
    old = _job(client, h, "4300000006", "Oldco Phase4")
    with Session(engine) as s:
        job = s.get(Job, old["job_id"])
        job.discovered_at = utcnow() - timedelta(hours=2)
        s.add(job)
        s.commit()
    refused = client.delete(f"/api/ext/job/{old['job_id']}", headers=h)
    assert refused.status_code == 409 and "too long ago" in refused.json()["detail"]
    assert client.delete("/api/ext/job/999999", headers=h).status_code == 409
    assert client.delete(f"/api/ext/job/{new['job_id']}").status_code == 401  # needs the token


def test_person_flags_review_and_undo_only_for_a_new_person(client) -> None:  # noqa: ANN001
    h = _h(client)
    p = _profile("Flagco Phase4", slug="fay-flag", name="Fay Flag")
    p["regions"][2]["lines"] = ["Notes only"]  # no dated experience
    p["links"] = []
    first = client.post("/api/ext/person", json={"payload": p, "company": "Flagco Phase4"},
                        headers=h).json()
    codes = {f["code"] for f in first["flags"]}
    assert {"company_headline", "no_experience"} <= codes and first["undo"] is True
    typed = client.post("/api/ext/person", json={"payload": p, "company": "Typed Elsewhere"},
                        headers=h).json()
    assert "company_typed" in {f["code"] for f in typed["flags"]}
    cid = first["contact_id"]
    listed = {i["contact_id"]: i for i in client.get("/api/linkedin/profiles").json()["items"]}
    assert {f["code"] for f in listed[cid]["flags"]} >= {"no_experience"}
    assert client.post(f"/api/linkedin/profiles/{cid}/reviewed").status_code == 204
    assert client.get("/api/linkedin/profiles").json()["items"][0]["reviewed_at"] \
        or any(i["contact_id"] == cid and i["reviewed_at"]
               for i in client.get("/api/linkedin/profiles").json()["items"])
    second = client.post("/api/ext/person", json={"payload": p, "company": "Flagco Phase4"},
                         headers=h).json()
    assert second["undo"] is False  # already in your list
    assert client.delete(f"/api/ext/person/{cid}", headers=h).json() == {"undone": True}
    assert client.get("/api/linkedin/profiles").json()["total"] >= 0
    assert client.delete(f"/api/ext/person/{cid}", headers=h).status_code == 409


def test_undo_person_is_refused_once_you_worked_on_them(client) -> None:  # noqa: ANN001
    h = _h(client)
    _job(client, h, "4300000007", "Workco Phase4")
    body = {"payload": _profile("Workco Phase4", slug="wes-work", name="Wes Work")}
    out = client.post("/api/ext/person", json=body, headers=h).json()
    assert out["job"] and out["undo"] is True
    with Session(engine) as s:
        row = s.exec(select(LinkedInOutreach).where(
            LinkedInOutreach.contact_id == out["contact_id"])).one()
        row.note = {"text": "Hello"}
        s.add(row)
        s.commit()
    refused = client.delete(f"/api/ext/person/{out['contact_id']}", headers=h)
    assert refused.status_code == 409 and "already worked" in refused.json()["detail"]


def test_captured_people_are_hidden_from_the_company_contacts_until_asked(client) -> None:  # noqa: ANN001
    h = _h(client)
    out = client.post("/api/ext/person", headers=h,
                      json={"payload": _profile("Hideco Phase4", slug="hal-hide", name="Hal Hide")}
                      ).json()
    from app.models import Contact

    with Session(engine) as s:
        company_id = s.get(Contact, out["contact_id"]).company_id
    plain = client.get(f"/api/companies/{company_id}").json()
    assert plain["hidden_linkedin"] == 1 and plain["contacts"] == []
    shown = client.get(f"/api/companies/{company_id}",
                       params={"include_linkedin": "true"}).json()
    assert shown["hidden_linkedin"] == 0 and [c["full_name"] for c in shown["contacts"]] == \
        ["Hal Hide"]
