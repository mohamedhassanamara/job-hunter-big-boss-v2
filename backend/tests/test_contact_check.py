"""Is the contact still there? Signs they left, from researched pages and news. No model calls,
no network (fetchers are fakes)."""

from datetime import UTC, datetime

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Company, CompanyPage, Contact, ContactAlert, Job
from app.providers.mock import MockEmailDrafter
from app.services import contact_check, outreach, research
from tests.test_outreach import job_ready  # noqa: F401 (fixture)


def people(title: str = "CEO") -> tuple[Contact, Company]:
    return (Contact(id=1, company_id=1, full_name="Stephane Fontana", first_name="Stephane",
                    last_name="Fontana", title=title, normalized_name="stephane fontana"),
            Company(id=1, name="Zaion", normalized_name="zaion"))


def page(text: str, title: str = "") -> CompanyPage:
    return CompanyPage(company_id=1, url="https://news.example/a", title=title, text=text)


@pytest.mark.parametrize(("text", "kind"), [
    ("Zaion révoque son directeur général Stéphane Fontana, ad nutum.", "left"),
    ("Stéphane Fontana quitte Zaion après six ans.", "left"),
    ("Stephane Fontana, former CEO of Zaion, joins a new startup.", "left"),
    ("L'ancien PDG de Zaion, Stéphane Fontana, lance sa société.", "left"),
    ("Zaion nomme Marie Dupont directrice générale.", "new_holder"),
    ("Zaion appoints a new CEO to lead its growth in Europe.", "new_holder"),
    ("Stéphane Fontana, CEO de Zaion, présente la nouvelle plateforme.", None),
    ("Ancien ingénieur chez Google, Stéphane Fontana a fondé Zaion.", None),
    ("Zaion launches a new agent built for contact center CEOs.", None),
    ("Stéphane Fontana remercie les clients de Zaion.", None),
])
def test_what_counts_as_a_sign_they_left(text: str, kind: str | None) -> None:
    contact, company = people()
    found = contact_check.findings(contact, company, [page(text)])
    assert [f["kind"] for f in found] == ([kind] if kind else [])


def test_a_new_holder_only_matters_for_the_contacts_own_role() -> None:
    contact, company = people(title="Head of Data")
    assert contact_check.findings(contact, company, [
        page("Zaion nomme Marie Dupont directrice générale.")]) == []


def test_the_last_name_counts_on_a_page_that_names_them() -> None:
    contact, company = people()
    text = "Stéphane Fontana a dirigé Zaion. Le conseil a révoqué M. Fontana hier."
    assert [f["kind"] for f in contact_check.findings(contact, company, [page(text)])] == ["left"]


def add_page(company_id: int, text: str, url: str = "https://news.example/left") -> None:
    with Session(engine) as s:
        s.add(CompanyPage(company_id=company_id, url=url, kind="news", title="News", text=text,
                          page_date=datetime(2026, 2, 24, tzinfo=UTC)))
        s.commit()


def ids(job_ready: dict) -> tuple[int, int, int]:  # noqa: F811
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        return app.id, s.get(Job, app.job_id).company_id, app.contact_id


def test_an_active_alert_blocks_approval_until_dismissed(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    from app.services.hook_check import MockHookChecker

    app_id, company_id, contact_id = ids(job_ready)
    with Session(engine) as s:
        other = Contact(company_id=company_id, full_name="Bo Next", first_name="Bo",
                        title="Head of Data", email="bo@outco.test", normalized_name="bo next",
                        role_rank=1)
        s.add(other)
        s.commit()
        other_id = other.id
    d = outreach.generate(engine, app_id, MockEmailDrafter(), mode="speculative",
                          researcher=research.MockResearcher(),
                          fetcher=Fetcher("A mutual insurer automated 37% of its requests.",
                                          person="{name} has left the company after four "
                                                 "years."),
                          hook_checker=MockHookChecker())
    with Session(engine) as s:  # the draft step's research found the page and scanned it
        alerts = contact_check.active(s, contact_id)
        assert [a.kind for a in alerts] == ["left"]
    step = client.get(f"/api/applications/{app_id}/outreach").json()["draft"]
    assert step["contact_alerts"][0]["reason"].startswith("“has left”")
    assert step["next_contact"]["id"] == other_id  # the next by the ranking, not flagged
    r = client.post(f"/api/outreach/drafts/{d.id}/approve")
    assert r.status_code == 409 and "may have left" in r.json()["detail"]
    job = client.get(f"/api/jobs/{job_ready_job(app_id)}").json()
    assert job["contact_alerts"] and job["next_contact"]["full_name"] == "Bo Next"
    alert_id = alerts[0].id
    assert client.post(f"/api/contact-alerts/{alert_id}/dismiss",
                       json={"dismissed": True}).json()["dismissed_at"]
    with Session(engine) as s:  # found again (a later scan): it stays dismissed
        contact_check.scan(s, company_id)
        s.commit()
        assert contact_check.active(s, contact_id) == []
    assert client.post(f"/api/outreach/drafts/{d.id}/approve").status_code == 200


def job_ready_job(app_id: int) -> int:
    with Session(engine) as s:
        return s.get(Application, app_id).job_id


class Fetcher:
    """A company site with one page, and news for the contact's name."""

    def __init__(self, text: str, person: str = ""):
        self.text, self.person, self.searched = text, person, []

    def site(self, home, max_pages, progress):  # noqa: ANN001, ANN201
        return [research.Source(f"{home}/clients", "customers", "Clients", self.text)], []

    def news(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
        return [], []

    def person_news(self, full_name, company, language, settings):  # noqa: ANN001, ANN201
        self.searched.append((full_name, company))
        if not self.person:
            return [], []
        return [research.Source("https://news.example/person", "press", "Leadership",
                                self.person.format(name=full_name), None)], []


def test_research_searches_the_contacts_name_and_a_cached_reuse_only_rescans(
        job_ready: dict) -> None:  # noqa: F811
    app_id, company_id, contact_id = ids(job_ready)
    fetcher = Fetcher("A mutual insurer automated 37% of its requests.",
                      person="{name} stepped down as CTO last month.")
    research.ensure(engine, company_id, trigger="manual", researcher=research.MockResearcher(),
                    fetcher=fetcher)
    with Session(engine) as s:
        contact = s.get(Contact, contact_id)
        assert fetcher.searched == [(contact.full_name, s.get(Company, company_id).name)]
        assert [a.source_url for a in contact_check.active(s, contact_id)] == \
            ["https://news.example/person"]
        pages = s.exec(select(CompanyPage).where(CompanyPage.company_id == company_id,
                                                 CompanyPage.kind == "contact_news")).all()
        assert len(pages) == 1
    research.ensure(engine, company_id, trigger="draft", researcher=research.MockResearcher(),
                    fetcher=fetcher)  # fresh: no fetch at all
    assert len(fetcher.searched) == 1
    with Session(engine) as s:
        assert len(s.exec(select(ContactAlert).where(
            ContactAlert.contact_id == contact_id)).all()) == 1


def test_no_news_search_for_a_name_with_only_an_initial(job_ready: dict) -> None:  # noqa: F811
    _, company_id, contact_id = ids(job_ready)
    fetcher = Fetcher("", person="{name} left.")
    with Session(engine) as s:
        contact = s.get(Contact, contact_id)
        contact.full_name = "Gregoire G."
        warnings = contact_check.fetch_contact_news(s, company_id, fetcher, "fr", {}, [contact])
        s.rollback()
    assert fetcher.searched == [] and "only an initial" in warnings[0]
