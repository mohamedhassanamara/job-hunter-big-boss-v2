"""GET /api/ext/person/lookup: which saved person is this profile page? Keyed by the slug only,
read-only, no contact data in the answer. Offline, real workspace of the test DB."""

import pytest
from sqlmodel import Session, SQLModel, select

from app.db import engine
from app.models import Contact, Job, LinkedInOutreach, LinkedInProfile
from app.models.enums import LinkedInStatus
from app.services import linkedin
from tests.test_ext_people import _h, _profile
from tests.test_linkedin_page import job_payload

ALLOWED_TOP = {"matched", "name", "jobs"}
ALLOWED_JOB = {"job_id", "outreach_id", "title", "company", "status", "has_first_message"}


def _job(client, h, company: str, job_id: str, title: str = "Data Engineer") -> int:  # noqa: ANN001
    out = client.post("/api/ext/job", json={"payload": job_payload(
        url=f"https://www.linkedin.com/jobs/view/{job_id}/", job_id=job_id, title_parsed=title,
        company_parsed=company,
        about={"lines": ["We build data pipelines with Spark and Airflow. " * 6]})},
        headers=h).json()
    assert out["saved"], out
    return out["job_id"]


def _lookup(client, h, slug: str):  # noqa: ANN001, ANN202
    return client.get("/api/ext/person/lookup", params={"slug": slug}, headers=h)


def _snapshot() -> tuple[dict[str, int], list[tuple[int, str, bool]]]:
    with Session(engine) as s:
        counts = {t.name: len(s.exec(t.select()).all()) for t in SQLModel.metadata.sorted_tables}
        rows = [(r.id, str(r.status), bool(r.followup))
                for r in s.exec(select(LinkedInOutreach)).all()]
    return counts, rows


def test_a_token_is_required(client) -> None:  # noqa: ANN001
    assert client.get("/api/ext/person/lookup", params={"slug": "x"}).status_code == 401
    bad = client.get("/api/ext/person/lookup", params={"slug": "x"},
                     headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


def test_an_unknown_slug_is_an_empty_answer(client) -> None:  # noqa: ANN001
    h = _h(client)
    for slug in ("nobody-at-all", ""):
        r = _lookup(client, h, slug)
        assert r.status_code == 200
        assert r.json() == {"matched": False, "name": None, "jobs": []}


def test_one_job_several_jobs_and_no_job(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Lookupco Phase4"
    job_a = _job(client, h, company, "4100000001", "Data Engineer")
    prof = _profile(company, slug="lia-lookup", name="Lia Lookup")
    client.post("/api/ext/person", json={"payload": prof}, headers=h)
    one = _lookup(client, h, "lia-lookup").json()
    assert one["matched"] and one["name"] == "Lia Lookup" and len(one["jobs"]) == 1
    assert one["jobs"][0]["job_id"] == job_a and one["jobs"][0]["company"] == company
    assert one["jobs"][0]["status"] == "to_contact" and one["jobs"][0]["has_first_message"] is False

    job_b = _job(client, h, company, "4100000002", "Analytics Engineer")
    client.post("/api/ext/person", json={"payload": prof, "job_id": job_b}, headers=h)
    many = _lookup(client, h, "lia-lookup").json()
    assert {j["job_id"] for j in many["jobs"]} == {job_a, job_b}
    assert many["jobs"][0]["job_id"] == job_b  # newest first

    alone = _profile("Nojobco Phase4", slug="nico-nojob", name="Nico Nojob")
    client.post("/api/ext/person", json={"payload": alone}, headers=h)
    nojob = _lookup(client, h, "nico-nojob").json()
    assert nojob == {"matched": True, "name": "Nico Nojob", "jobs": []}


@pytest.mark.parametrize("variant", [
    "mia-variant", "MIA-Variant", "mia-variant/", "/in/mia-variant/", "/in/mia-variant",
    "/fr/in/mia-variant/", "/in/mia-variant/?miniProfileUrn=x", "mia-variant?x=1",
    "https://www.linkedin.com/in/mia-variant/fr/", "/in/mia-variant/#top"])
def test_slug_variants_find_the_same_person(client, variant: str) -> None:  # noqa: ANN001
    h = _h(client)
    client.post("/api/ext/person", json={"payload": _profile(
        "Variantco Phase4", slug="mia-variant", name="Mia Variant")}, headers=h)
    assert _lookup(client, h, variant).json()["name"] == "Mia Variant"


def test_lookup_key_unit() -> None:
    key = linkedin.lookup_key
    assert key("/fr/in/Jo%C3%A3o-Silva/") == "joão-silva"
    assert key("  ") == "" and key(None) == ""
    assert key("https://www.linkedin.com/in/abc/?x=1") == "abc"


def test_a_contact_stored_with_an_opaque_url_matches_by_that_url(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Opaqueco Phase4"
    _job(client, h, company, "4100000003")
    client.post("/api/ext/person", json={"payload": _profile(
        company, slug="ACoAAB1x2y3", name="Opa Que")}, headers=h)
    assert _lookup(client, h, "acoaab1x2y3").json()["name"] == "Opa Que"


def test_the_answer_has_no_contact_data(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Privateco Phase4"
    _job(client, h, company, "4100000004")
    client.post("/api/ext/person", json={"payload": _profile(
        company, slug="pat-private", name="Pat Private")}, headers=h)
    with Session(engine) as s:
        c = s.exec(select(Contact).where(Contact.full_name == "Pat Private")).one()
        c.email, c.notes = "pat@private.test", "private contact notes"
        row = s.exec(select(LinkedInOutreach).where(LinkedInOutreach.contact_id == c.id)).one()
        row.notes = "secret note about Pat"
        row.followup = {"text": "Thanks for connecting, Pat. Draft text here?"}
        row.status = LinkedInStatus.accepted
        s.commit()
    r = _lookup(client, h, "pat-private")
    out = r.json()
    assert set(out) == ALLOWED_TOP and set(out["jobs"][0]) == ALLOWED_JOB
    assert out["jobs"][0]["has_first_message"] is True and out["jobs"][0]["status"] == "accepted"
    for secret in ("pat@private.test", "private contact notes", "secret note", "Draft text",
                   "linkedin.com"):
        assert secret not in r.text


def test_the_lookup_changes_nothing(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Readonlyco Phase4"
    _job(client, h, company, "4100000005")
    client.post("/api/ext/person", json={"payload": _profile(
        company, slug="rex-readonly", name="Rex Readonly")}, headers=h)
    with Session(engine) as s:  # an accepted invite with no draft: the lookup must not draft
        row = s.exec(select(LinkedInOutreach).join(
            Contact, Contact.id == LinkedInOutreach.contact_id).where(
            Contact.full_name == "Rex Readonly")).one()
        row.status = LinkedInStatus.accepted
        s.commit()
    before = _snapshot()
    for slug in ("rex-readonly", "/in/rex-readonly/", "unknown-person"):
        assert _lookup(client, h, slug).status_code == 200
    assert _snapshot() == before


def test_saving_returns_the_linked_jobs(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Savedco Phase4"
    job_id = _job(client, h, company, "4100000006")
    saved = client.post("/api/ext/person", json={"payload": _profile(
        company, slug="sue-saved", name="Sue Saved")}, headers=h).json()
    linked = saved["linked"]
    assert linked["matched"] and linked["name"] == "Sue Saved"
    assert [j["job_id"] for j in linked["jobs"]] == [job_id]
    assert set(linked["jobs"][0]) == ALLOWED_JOB
    assert linked == _lookup(client, h, "sue-saved").json()  # one answer, two routes
    nojob = client.post("/api/ext/person", json={"payload": _profile(
        "Lonelyco Phase4", slug="lon-lonely", name="Lon Lonely")}, headers=h).json()
    assert nojob["linked"] == {"matched": True, "name": "Lon Lonely", "jobs": []}


def test_a_name_and_company_match_stores_the_vanity_slug(client) -> None:  # noqa: ANN001
    h = _h(client)
    company = "Namematchco Phase4"
    job_id = _job(client, h, company, "4100000007")
    with Session(engine) as s:  # a hiring-team style contact: an opaque id, no vanity slug
        company_id = s.get(Job, job_id).company_id
        opaque = "https://www.linkedin.com/in/ACoAAnora123/"
        contact = linkedin.ensure_contact(s, company_id, full_name="Nora Match",
                                          title="Engineering Manager", linkedin_url=opaque)
        s.commit()
        contact_id = contact.id
    assert _lookup(client, h, "nora-match").json()["matched"] is False  # not yet known by slug
    saved = client.post("/api/ext/person", json={"payload": _profile(
        company, slug="nora-match", name="Nora Match")}, headers=h).json()
    assert saved["contact_id"] == contact_id and saved["linked"]["jobs"]
    with Session(engine) as s:
        prof = s.exec(select(LinkedInProfile).where(
            LinkedInProfile.contact_id == contact_id)).one()
        assert prof.public_id == "nora-match"
        assert s.get(Contact, contact_id).linkedin_url == opaque  # untouched
    found = _lookup(client, h, "nora-match").json()
    assert found["matched"] and found["name"] == "Nora Match" and found["jobs"]
    assert _lookup(client, h, "ACoAAnora123").json()["name"] == "Nora Match"  # the old id too
