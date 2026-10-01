"""Honesty about years of experience, per track (professional vs project-based), and the
LinkedIn notes written for their reader (groups, agency jobs). Offline, no model."""

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import Job
from app.models.enums import LinkedInGroup
from app.services import agency, honesty
from app.services import linkedin as li
from app.services import linkedin_check as lc
from app.services import linkedin_track as lt
from tests.test_contacts import make_company, make_job
from tests.test_linkedin_track import ctx

TRACKS = [
    {"name": "Mobile", "experience": "professional", "roles": [{"title": "Mobile Developer"}]},
    {"name": "Backend", "experience": "professional", "roles": [{"title": "Backend Engineer"}]},
    {"name": "Data/AI", "experience": "projects",
     "experience_note": "personal projects, a graduation project, an internship and certifications",
     "roles": [{"title": "Data Engineer"}, {"title": "AI Engineer"}]},
]
RULES = honesty.rules_from(TRACKS)
APPROVED = ("Hi Alex, I saw your Data Engineer role. I'm a software engineer (3 years, mobile and "
            "backend) moving into data, with dbt and Airflow projects. Could I send you my CV?")


@pytest.mark.parametrize("text", [
    "I have 3 years of experience building data pipelines.",
    "Software engineer with 3 years in data.",
    "Software and AI Engineer with over 2 years of experience developing robust data pipelines.",
    "I'm an experienced data engineer.",
    "Data Engineer with a lakehouse on S3.",
    "As a Data Engineer at Acme, I built pipelines.",
    "Ingénieur logiciel avec 3 ans d'expérience en data et IA.",
    "I bring 3 years of software engineering experience across data pipelines and backend.",
    "Professional data engineering experience with dbt.",
])
def test_years_or_titles_attached_to_a_projects_track_fail(text: str) -> None:
    assert honesty.problems(text, RULES), text


@pytest.mark.parametrize("text", [
    APPROVED,
    "I'm a software engineer with 3 years in mobile and backend.",
    "In personal projects I built a dbt and Airflow lakehouse.",
    "J'ai 3 ans d'expérience en ingénierie logicielle.",  # "J'ai" isn't AI
    "J'ai 3 ans d'expérience, avec des bases de données relationnelles.",  # databases: backend
    "I'm moving into data engineering, with a graduation project on LLMs.",
    "Software engineer with 3 years of experience in backend and mobile, now building data "
    "pipelines and LLM systems in personal projects.",
])
def test_honest_wording_passes(text: str) -> None:
    assert not honesty.problems(text, RULES), honesty.problems(text, RULES)


def test_no_projects_track_means_no_rule() -> None:
    assert not honesty.problems("3 years of data pipelines.", honesty.rules_from(TRACKS[:2]))
    facts = honesty.prompt_facts(RULES)
    assert {f["track"]: f["experience"] for f in facts["experience_by_track"]} == \
        {"Data/AI": "projects", "Mobile": "professional", "Backend": "professional"}


@pytest.mark.parametrize(("title", "group"), [
    ("Specialist Recruiter for startups & scaleups", LinkedInGroup.recruiter),
    ("Talent Acquisition Partner", LinkedInGroup.recruiter),
    ("Chargée de recrutement", LinkedInGroup.recruiter),
    ("Head of Data", LinkedInGroup.lead),
    ("Engineering Manager", LinkedInGroup.lead),
    ("Software Engineer", LinkedInGroup.other),
    (None, LinkedInGroup.other),
])
def test_the_group_comes_from_the_title(title: str | None, group: LinkedInGroup) -> None:
    assert li.detect_group(title) == group


def test_an_agency_job_skips_alumni_and_leads_and_puts_the_recruiter_first(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s)
        company.name = "Mentor Talent Acquisition"
        app = make_job(s, company)
        job = s.get(Job, app.job_id)
        assert agency.signals(company, job) == ["the name says “Talent Acquisition”"]
        assert [g["group"] for g in lt.suggestions(s, app)] == ["hiring_team",
                                                                LinkedInGroup.recruiter]
        company.name = "Acme"
        job.description = "We are recruiting for our client, a fintech in Paris."
        assert agency.is_agency(company, job)
        job.description = "We build data pipelines."
        assert not agency.is_agency(company, job)
        assert LinkedInGroup.alumni in [g["group"] for g in lt.suggestions(s, app)]
        s.rollback()


def test_a_captured_poster_keeps_the_hiring_flag_and_gets_a_detected_angle(seeded: None) -> None:
    with Session(engine) as s:
        app = make_job(s, make_company(s))
        row = lt.add(s, app, full_name="Pat Poster", title="Talent Acquisition Lead",
                     linkedin_url=None, hiring_team=True)
        assert row.hiring_team and row.group == LinkedInGroup.recruiter
        s.rollback()


def test_recruiter_notes_are_plain_with_an_easy_ask(seeded: None) -> None:
    def errors(text: str, **kw) -> set[str]:  # noqa: ANN003
        return {v["type"] for v in lc.check(text, ctx(group="recruiter", **kw))
                if v["severity"] == "error"}

    assert not errors(APPROVED.replace("Alex", "Lea"), honesty=RULES)
    assert "jargon" in errors("Hi Lea, I built an idempotent lakehouse with schema drift "
                              "handling. Could I send you my CV?")
    found = lc.check("Hi Lea, I build data pipelines. Open to a quick chat?",
                     ctx(group="recruiter"))
    assert "ask" in {v["type"] for v in found}
    assert "years_domain" in errors("Hi Lea, I have 3 years of experience in data pipelines. "
                                    "Could I send you my CV?", honesty=RULES)


def test_a_reference_note_is_never_copied(seeded: None) -> None:
    note = APPROVED.replace("Alex", "Lea")
    found = lc.check(note, ctx(group="recruiter", examples=[note]))
    assert "example_copy" in {v["type"] for v in found if v["severity"] == "error"}


def test_the_transition_line_names_project_tools_not_concepts(seeded: None) -> None:
    with Session(engine) as s:
        from app.services.cv_pool import load_pool

        tools = lt.project_tools(load_pool(s), RULES.projects[0].terms, "Python, SQL and AWS")
        assert tools and not {t.lower() for t in tools} & honesty.CONCEPTS


def test_who_to_contact_at_an_agency_is_the_recruiter_only(seeded: None) -> None:
    from app.services.contacts import who_to_contact

    with Session(engine) as s:
        company = make_company(s)
        app = make_job(s, company)
        job = s.get(Job, app.job_id)
        job.matched_track = "Data/AI"
        assert any("Head of" in r["label"] for r in who_to_contact(s, job, company)["roles"])
        company.name = "Mentor Talent Acquisition"
        who = who_to_contact(s, job, company)
        assert [r["label"] for r in who["roles"]] == ["Recruiter / Talent acquisition"]
        assert who["agency"] and "Head of" not in who["linkedin_query"]
        assert "recruiting agency" in who["reason"]
        s.rollback()


def test_at_an_agency_the_recruiter_is_the_automatic_contact(seeded: None) -> None:
    from app.services import contacts

    with Session(engine) as s:
        company = make_company(s, ("Cora Tech", "CTO", "apollo_dump"),
                               ("Rita Recruit", "Talent Acquisition Partner", "apollo_dump"))
        company.employees = 40  # small: the CTO first, unless it's an agency
        app = make_job(s, company)
        contacts.resolve(s, app)
        assert s.get(contacts.Contact, app.contact_id).full_name == "Cora Tech"
        company.name = "Northwind Recruitment"
        app.contact_id = None
        contacts.resolve(s, app)
        assert s.get(contacts.Contact, app.contact_id).full_name == "Rita Recruit"
        s.rollback()


@pytest.mark.parametrize(("name", "listing", "expected"), [
    ("Acme", "Unser Kunde ist eine Genossenschaftsbank in München.", True),
    ("Acme", "For one of our clients active in defense, we are looking for a Data Engineer.", True),
    ("Northwind Recruitment", "", True),
    ("Recruitee", "We build recruiting software.", False),  # a product name, not an agency
    ("Acme Conseil", "Pour notre client TF1, nous recherchons un Tech Lead.", False),
    ("Acme Conseil", "Vous êtes en mission chez l'un de nos clients du secteur du luxe.", False),
    ("Acme Conseil", "Mission longue chez l'un de nos clients grands comptes.", False),
])
def test_agencies_vs_consultancies(name: str, listing: str, expected: bool) -> None:
    from app.models import Company

    assert agency.is_agency(Company(name=name, normalized_name=name.lower()),
                            Job(title="Data Engineer", description=listing)) is expected


def test_your_agency_answer_wins_and_drives_the_ranking(seeded: None, client) -> None:  # noqa: ANN001
    from app.services import contacts

    with Session(engine) as s:
        company = make_company(s, ("Cora Tech", "CTO", "apollo_dump"),
                               ("Rita Recruit", "Talent Acquisition Partner", "apollo_dump"))
        company.name, company.employees = "Northwind Workforce Staffing", 40
        app = make_job(s, company)
        contacts.resolve(s, app)
        assert s.get(contacts.Contact, app.contact_id).full_name == "Rita Recruit"
        s.commit()
        company_id, app_id = company.id, app.id

    r = client.put(f"/api/companies/{company_id}/agency", json={"value": "employer"}).json()
    assert r["agency_override"] == "employer" and r["previous"] is None and r["detected"]
    with Session(engine) as s:
        app, company = s.get(contacts.Application, app_id), s.get(contacts.Company, company_id)
        assert not agency.is_agency(company) and \
            s.get(contacts.Contact, app.contact_id).full_name == "Cora Tech"  # matched again
        assert len(lt.suggestions(s, app)) > 2  # team leads (and alumni) are back
    undo = client.put(f"/api/companies/{company_id}/agency", json={"value": r["previous"]}).json()
    assert undo["agency_override"] is None and undo["previous"] == "employer"
    marked = client.put(f"/api/companies/{company_id}/agency", json={"value": "agency"}).json()
    assert marked["agency_override"] == "agency"
    with Session(engine) as s:
        assert agency.signals(s.get(contacts.Company, company_id)) == ["you marked it as an agency"]
    assert client.put(f"/api/companies/{company_id}/agency",
                      json={"value": "maybe"}).status_code == 422
