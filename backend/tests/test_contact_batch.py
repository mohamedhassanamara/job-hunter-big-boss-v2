"""Find contacts for this batch: which shortlisted jobs qualify, and the worst-case spend shown
before anything runs. The preview never calls a provider."""

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, CompanyProviderRun, Contact, Job
from app.models.enums import ContactSearch, Stage
from app.services import contact_waterfall as wf
from tests.test_contacts import make_company, make_job


def clean(s: Session) -> None:
    for row in s.exec(select(CompanyProviderRun)).all():
        s.delete(row)
    for app in s.exec(select(Application).where(Application.stage == Stage.shortlisted)).all():
        app.stage = Stage.new
        s.add(app)
    s.flush()


def shortlisted(s: Session, **company_kw) -> Application:
    company = make_company(s)
    for k, v in company_kw.items():
        setattr(company, k, v)
    app = make_job(s, company)
    app.stage = Stage.shortlisted
    s.add_all([company, app])
    s.flush()
    return app


def test_preview_lists_only_shortlisted_jobs_that_need_a_search(client) -> None:
    with Session(engine) as s:
        clean(s)
        wanted = shortlisted(s)
        never = shortlisted(s, contact_search=ContactSearch.never)
        nobody = shortlisted(s, contact_search=ContactSearch.not_found)
        has = shortlisted(s)
        person = Contact(company_id=s.get(Job, has.job_id).company_id, full_name="Ana Silva",
                         email="ana@x.test", source="manual")
        s.add(person)
        s.flush()
        has.contact_id = person.id
        s.add(has)
        new = make_job(s, make_company(s))  # a job that is not shortlisted
        s.commit()
        wanted_id = wanted.id
        others = {never.id, nobody.id, has.id, new.id}
    out = client.get("/api/contacts/batch-preview").json()
    ids = {j["application_id"] for j in out["jobs"]}
    assert wanted_id in ids and not (others & ids)
    assert out["companies"] == len({j["company_id"] for j in out["jobs"]})
    assert set(out["spend"]) == {"hunter", "prospeo", "apollo", "apify"}


def test_worst_case_counts_only_companies_not_looked_up_recently() -> None:
    with Session(engine) as s:
        clean(s)
        fresh, stale = make_company(s), make_company(s)
        for provider in wf.WATERFALL:  # every provider already looked this company up
            s.add(CompanyProviderRun(company_id=fresh.id, provider=provider, status="ok"))
        s.flush()
        spend = wf.estimate_batch(s, [fresh.id, stale.id, stale.id])  # a company counts once
        assert {p: v["companies"] for p, v in spend.items()} == {p: 1 for p in wf.WATERFALL}
        # one uncached company: Hunter search + 2 pattern checks, Prospeo search + 2 reveals,
        # Apollo 2 reveals (its search is free), Apify's start price
        assert spend["hunter"]["worst_case"] == 2.0
        assert spend["prospeo"]["worst_case"] == 3.0
        assert spend["apollo"]["worst_case"] == 2.0
        assert spend["apify"]["worst_case"] == 0.1
        only_fresh = wf.estimate_batch(s, [fresh.id])
        assert all(v["worst_case"] == 0 and v["companies"] == 0 for v in only_fresh.values())
        s.rollback()
