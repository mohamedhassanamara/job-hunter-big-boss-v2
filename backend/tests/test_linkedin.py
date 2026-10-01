"""LinkedIn: daily search links, capture validation, one-click import (dedupe, track, scoring
only that job), excluded from discovery, and never a request to linkedin.com. Offline."""

import re
from datetime import date
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Company, Contact, Job, LinkedInOutreach, ScoringTask
from app.models.enums import DISCOVERY_SOURCES, LinkedInGroup, RemoteType, Source
from app.services import linkedin

CAPTURE = {
    "url": "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=data",
    "title": "Data Engineer", "company": "Exemplo Labs Phase10",
    "company_url": "https://www.linkedin.com/company/exemplo-labs/life",
    "location": "Lisbon, Portugal", "workplace": "Hybrid",
    "description": "We build data pipelines with Spark and Airflow for logistics customers. " * 5,
    "poster": {"name": "Ana Exemplo", "title": "Head of Data",
               "url": "https://www.linkedin.com/in/ana-exemplo/?miniProfileUrn=x"},
    "sources": {"title": "page", "company": "page", "description": "json-ld"},
}


def test_search_url_uses_the_geo_id_never_a_text_location() -> None:
    url = linkedin.search_url("Data Engineer", "103710677", remote=True, easy=True)
    assert url.startswith("https://www.linkedin.com/jobs/search/?keywords=Data%20Engineer")
    for part in ("geoId=103710677", "f_TPR=r86400", "sortBy=DD", "f_WT=2", "f_AL=true"):
        assert part in url
    assert "location=" not in url and "f_WT" not in linkedin.search_url("Data Engineer", "1")


def test_links_need_a_geo_id_and_opened_today_resets(seeded: None, client) -> None:  # noqa: ANN001
    from app.models import AppSetting

    with Session(engine) as s:
        found = linkedin.search_links(s)
        assert found.groups and all(g.links for g in found.groups)
        assert all(not x.verified for g in found.groups for x in g.links)  # seeded unverified
        first = found.groups[0].links[0]
        linkedin.mark_opened(s, first.key, date(2026, 10, 1))
        s.flush()
        assert linkedin.search_links(s, today=date(2026, 10, 1)).groups[0].links[0].opened_today
        assert not linkedin.search_links(s, today=date(2026, 10, 2)).groups[0].links[0] \
            .opened_today
        row = s.exec(select(AppSetting).where(AppSetting.key == "linkedin")).first()
        geos = dict(linkedin.DEFAULT_LINKEDIN["geo_ids"])
        geos.pop(first.country)  # this country now has no geoId
        row.value = {**row.value, "geo_ids": geos}
        s.add(row)
        s.flush()
        after = linkedin.search_links(s)
        assert first.country in [c["code"] for c in after.missing_geo]
        assert all(x.country != first.country for g in after.groups for x in g.links)
        s.rollback()
    bad = client.put("/api/settings/linkedin",
                     json={"value": {"geo_ids": {"JO": {"id": "Jordan"}}}})
    assert bad.status_code == 422


def test_validate_reports_what_is_missing_and_never_hides_it() -> None:
    c = linkedin.validate({**CAPTURE, "description": ""})
    assert c.job_id == "4012345678" and c.url == "https://www.linkedin.com/jobs/view/4012345678/"
    assert c.missing == ["description"] and c.sources["description"] == "missing"
    assert c.poster["url"] == "https://www.linkedin.com/in/ana-exemplo/"
    assert c.company_url == "https://www.linkedin.com/company/exemplo-labs/"
    wall = linkedin.validate({**CAPTURE, "description": "Sign in to view more jobs like this"})
    assert any("sign-in wall" in w for w in wall.warnings)
    assert linkedin.remote_type("Hybrid", "") == RemoteType.hybrid


def test_import_scores_only_that_job_dedupes_and_saves_the_hiring_team(seeded: None,
                                                                    client) -> None:  # noqa: ANN001
    with Session(engine) as s:  # the same job from another source first
        company = Company(name="Exemplo Labs Phase10", normalized_name="exemplo labs phase10")
        s.add(company)
        s.flush()
        from app.services.dedupe import dedupe_key

        other = Job(source=Source.adzuna, external_id="adz-phase10", url="https://x.test",
                    title="Data Engineer", company_id=company.id, country="PT",
                    dedupe_key=dedupe_key(company.name, "Data Engineer", "PT"))
        s.add(other)
        s.flush()
        s.add(Application(job_id=other.id))
        s.commit()
        other_id = other.id
    preview = client.post("/api/linkedin/capture", json=CAPTURE).json()
    assert preview["existing"]["id"] == other_id and preview["missing"] == []
    r = client.post("/api/linkedin/import", json=CAPTURE)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] and out["duplicate_of"]["id"] == other_id
    with Session(engine) as s:
        job = s.get(Job, out["job_id"])
        assert (job.source, job.linkedin_job_id, job.remote_type) == ("linkedin", "4012345678",
                                                                      "hybrid")
        assert job.capture["description"] == "json-ld"
        assert s.get(Company, job.company_id).linkedin_url == \
            "https://www.linkedin.com/company/exemplo-labs/"
        person = s.exec(select(LinkedInOutreach).where(
            LinkedInOutreach.application_id == out["application_id"])).one()
        assert person.hiring_team and person.group == LinkedInGroup.lead  # Head of Data
        ana = s.get(Contact, person.contact_id)
        assert ana.source == "linkedin" and ana.email is None
        app = s.get(Application, out["application_id"])
        assert app.contact_id != ana.id  # a LinkedIn-only person is never the email's contact
        tasks = s.exec(select(ScoringTask).where(ScoringTask.job_id == job.id)).all()
        assert tasks or out["scoring"] != "queued"
    again = client.post("/api/linkedin/import", json={**CAPTURE, "title": "Data Engineer"}).json()
    assert again["job_id"] == out["job_id"] and not again["created"]  # idempotent


def test_import_refuses_missing_required_fields(client) -> None:  # noqa: ANN001
    r = client.post("/api/linkedin/import", json={**CAPTURE, "company": ""})
    assert r.status_code == 422 and "company" in r.json()["detail"]
    assert client.post("/api/linkedin/capture", json={"url": "x"}).status_code == 422


def test_paste_fallback_reads_title_and_company_from_the_first_lines(client) -> None:  # noqa: ANN001
    text = "Data Engineer\nExemplo Labs\nLisbon, Portugal\n" + "We build pipelines. " * 20
    r = client.post("/api/linkedin/paste", json={"url": "https://www.linkedin.com/jobs/view/4099999999/",
                                                 "text": text}).json()
    assert (r["title"], r["company"], r["job_id"]) == ("Data Engineer", "Exemplo Labs",
                                                       "4099999999")


def test_linkedin_is_never_a_discovery_source() -> None:
    assert Source.linkedin not in DISCOVERY_SOURCES


def test_the_backend_never_requests_linkedin() -> None:
    """Only links are built: no HTTP client call anywhere targets linkedin.com."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    calls = re.compile(r"(?:request|get|post|get_json|post_json|urlopen|fetch)\([^)]*linkedin\.com",
                       re.S)
    offenders = [str(p.relative_to(app_dir)) for p in app_dir.rglob("*.py")
                 if calls.search(p.read_text())]
    assert offenders == []
