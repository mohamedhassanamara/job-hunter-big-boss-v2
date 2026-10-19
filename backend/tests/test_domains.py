# ruff: noqa: F811
"""Domain accuracy before credits: PDL picked by evidence (LinkedIn page, country, size), a free MX
check before any provider is paid, other known domains tried first, a stop-and-ask when a provider
finds nobody, and the email domain stored beside the website's. Offline: DNS and providers are
scripted."""

import json
from pathlib import Path

import dns.exception
import dns.resolver
import duckdb
import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import CompanyProviderRun
from app.providers.contact_finders.mock import MockFinder
from app.services import company_resolve, dns_check, domains
from app.services import contact_waterfall as wf
from tests.test_contacts import make_job
from tests.test_waterfall import finders, setting  # noqa: F401
from tests.test_waterfall import world as _world  # noqa: F401

WEB, MAIL = "sekoia-web.test", "sekoia-mail.test"


class DomainHunter(MockFinder):
    """Knows people only at one domain (like Hunter at sekoia.io, nobody at sekoia.com)."""

    def __init__(self, only: str, calls: list[str]):
        super().__init__("hunter", finds=True, calls=calls)
        self.only = only

    def search(self, key, domain, titles, *, limit=10):  # noqa: ANN001, ANN201
        if domain != self.only:
            self.calls.append(f"hunter.search:{domain}")
            from app.providers.contact_finders import Cost, Search
            return Search([], Cost(credits=1.0))
        return super().search(key, domain, titles, limit=limit)


def mx_for(*with_mx: str):  # noqa: ANN201
    return lambda d: ["mx.example"] if d in with_mx else []


@pytest.fixture()
def world(_world):  # noqa: ANN001, ANN201
    s, company, app = _world
    company.domain = WEB
    s.flush()
    return s, company, app


# ------------------------------------------------------------------ PDL picks by evidence


@pytest.fixture()
def pdl(tmp_path: Path) -> Path:
    csv = tmp_path / "pdl.csv"
    csv.write_text(
        "name,website,linkedin_url,size,industry,country,name_key\n"
        "Sekoia,sekoia.com,linkedin.com/company/sekoia,201-500,security,germany,sekoia\n"
        "Sekoia,sekoia.io,linkedin.com/company/sekoia-io,11-50,security,france,sekoia\n"
        "Sekoia,sekoia.store,linkedin.com/company/sekoia-store,1-10,retail,france,sekoia\n"
        "Orbit,orbit.fr,linkedin.com/company/orbit-fr,11-50,software,france,orbit\n"
        "Orbit,orbit.de,linkedin.com/company/orbit-de,1001-5000,software,germany,orbit\n")
    out = tmp_path / "companies.parquet"
    duckdb.connect().execute(f"COPY (SELECT * FROM read_csv_auto('{csv}')) TO '{out}' "
                             "(FORMAT parquet)")
    return out


def test_the_linkedin_page_from_the_listing_beats_country_and_size(pdl: Path) -> None:
    hit = company_resolve.pdl_lookup("Sekoia", ["FR"], pdl, "https://www.linkedin.com/company/sekoia/")
    assert (hit.domain, hit.evidence) == ("sekoia.com", "linkedin")  # even in another country
    assert {a["domain"] for a in hit.alternatives} == {"sekoia.io", "sekoia.store"}


def test_then_the_jobs_country_then_size(pdl: Path) -> None:
    by_country = company_resolve.pdl_lookup("Sekoia", ["FR"], pdl)
    assert (by_country.domain, by_country.evidence) == ("sekoia.io", "country")  # FR: io (bigger)
    by_size = company_resolve.pdl_lookup("Orbit", [], pdl)
    assert (by_size.domain, by_size.evidence) == ("orbit.de", "size")
    assert "picked orbit.de" in by_size.note and "largest" in by_size.note
    assert company_resolve.pdl_lookup("Orbit", ["FR"], pdl).domain == "orbit.fr"
    only = company_resolve.pdl_lookup("Sekoia", [], pdl, "linkedin.com/company/sekoia-store")
    assert only.domain == "sekoia.store"


def test_resolve_keeps_the_alternatives_for_the_picker(seeded: None, pdl: Path) -> None:
    from app.models import Company

    with Session(engine) as s:
        c = Company(name="Sekoia", normalized_name="sekoia-dom",
                    linkedin_url="https://fr.linkedin.com/company/sekoia-io")
        s.add(c)
        s.flush()
        r = company_resolve.resolve(s, c, path=pdl)
        assert (r.domain, r.evidence) == ("sekoia.io", "linkedin")
        assert set(domains.known(c)) == {"sekoia.io", "sekoia.com", "sekoia.store"}
        assert c.domains["sekoia.com"]["source"] == "pdl"
        assert "another company named Sekoia" in c.domains["sekoia.com"]["note"]
        s.rollback()


def test_a_linkedin_page_in_the_listing_is_evidence_not_the_website() -> None:
    from app.services.listing import extract_job_posting

    html = ('<script type="application/ld+json">' + json.dumps({
        "@type": "JobPosting", "title": "x", "description": "d " * 200,
        "hiringOrganization": {"name": "Sekoia", "sameAs": [
            "https://www.linkedin.com/company/sekoia-io", "https://www.sekoia.io"]}})
        + "</script>")
    got = extract_job_posting(html)
    assert got.company_url == "https://www.sekoia.io"
    assert got.linkedin_url == "https://www.linkedin.com/company/sekoia-io"


# ------------------------------------------------------------------------- the DNS check


class _Answer:
    def __init__(self, pref: int, host: str):
        self.preference, self.exchange = pref, host


def test_lookup_mx_maps_dns_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolver(result):  # noqa: ANN001, ANN202
        def resolve(self, domain, rdtype):  # noqa: ANN001, ANN202
            if isinstance(result, Exception):
                raise result
            return result
        return resolve

    cases = [([_Answer(20, "b.mx."), _Answer(10, "a.mx.")], ["a.mx", "b.mx"]),
             ([_Answer(0, ".")], []),  # a null MX: no mail
             (dns.resolver.NXDOMAIN(), []), (dns.resolver.NoAnswer(), []),
             (dns.exception.Timeout(), None), (dns.resolver.NoNameservers(), None)]
    for result, expected in cases:
        monkeypatch.setattr(dns.resolver.Resolver, "resolve", resolver(result))
        assert dns_check.lookup_mx("x.test") == expected
    assert dns_check.has_mx("x", lambda d: ["m"]) is True
    assert dns_check.has_mx("x", lambda d: []) is False
    assert dns_check.has_mx("x", lambda d: None) is None  # unknown is not "no"


def test_known_domains_alternatives_and_cached_mx(seeded: None) -> None:
    from app.models import Company

    calls: list[str] = []

    def lookup(d: str) -> list[str]:
        calls.append(d)
        return ["m"] if d in {"acme.io", "acme.fr"} else []

    c = Company(name="Acme", normalized_name="acme-d", domain="acme.com")
    domains.register(c, "https://www.Acme.io/", "listing")
    domains.register(c, "acme.net", "pdl")
    got = domains.alternatives(c, "acme.com", lookup)
    assert [(a["domain"], a["source"]) for a in got] == [("acme.io", "listing")]
    guesses = domains.alternatives(c, "acme.com", lookup, guess=True)
    assert [a["domain"] for a in guesses] == ["acme.io", "acme.fr"]  # variants have MX only
    assert guesses[1]["source"] == "guess" and c.domains["acme.fr"]["mx"] is True
    before = len(calls)
    assert domains.mx(c, "acme.io", lookup) is True and len(calls) == before  # cached 30 days
    assert domains.mx(c, "acme.io", lookup, force=True) is True and len(calls) == before + 1


def test_site_domains_read_the_websites_own_addresses() -> None:
    pages = {"https://acme.com": "<a href='mailto:hello@acme.io'>x</a> me@gmail.com",
             "https://acme.com/contact": "jobs@acme.io  press@acme-group.fr  logo@2x.png"}
    got = domains.site_domains("https://www.acme.com/", lambda u: pages.get(u))
    assert got == ["acme.io", "acme-group.fr"]
    assert domains.site_domains("acme.com", None) == []
    assert domains.site_domains(None, lambda u: "") == []


# -------------------------------------------------------------- the waterfall: MX first


def test_no_mx_tries_the_other_known_domains_before_any_credit(world) -> None:  # noqa: ANN001
    s, company, app = world
    domains.register(company, "acme-mail.test", "pdl", "another company named Sekoia")
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, prospeo=True),
                 mx_lookup=mx_for("acme-mail.test"))
    assert out.lookup_domain == "acme-mail.test" and out.found_by == "prospeo"
    assert calls[0] == "hunter.search:acme-mail.test"  # never the dead domain
    assert any("receives no email" in st.detail and "acme-mail.test" in st.detail
               for st in out.steps)


def test_the_websites_contact_page_gives_another_mail_domain(world) -> None:  # noqa: ANN001
    s, company, app = world
    out = wf.run(s, app, mock=False, finders=finders([], prospeo=True), mx_lookup=mx_for(MAIL),
                 site_fetcher=lambda u: "write to jobs@" + MAIL if u.endswith("/contact") else "")
    assert out.lookup_domain == MAIL and out.choice is None
    assert company.domains[MAIL]["source"] == "website contact page"


def test_nothing_with_mx_stops_before_spending_and_offers_guesses(world) -> None:  # noqa: ANN001
    s, company, app = world
    calls: list[str] = []
    guess = WEB.rsplit(".", 1)[0] + ".io"
    out = wf.run(s, app, mock=True, finders=finders(calls, hunter=True),
                 mx_lookup=mx_for(guess))
    assert calls == [] and out.credits == 0 and out.usd == 0 and out.found_by is None
    assert out.choice["domain"] == WEB
    assert [a["domain"] for a in out.choice["alternatives"]] == [guess]
    assert out.steps[-1].status == "no_mx"
    assert s.exec(select(CompanyProviderRun)).all() == []


def test_unknown_mx_does_not_block_a_search(world) -> None:  # noqa: ANN001
    s, _, app = world
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, hunter=True), mx_lookup=lambda d: None)
    assert out.found_by == "hunter" and calls[0].startswith("hunter.search")


# ------------------------------------------------- the waterfall: nobody found -> ask


def test_zero_people_stops_and_asks_instead_of_paying_the_next_provider(world) -> None:  # noqa: ANN001
    s, company, app = world
    domains.register(company, MAIL, "pdl")
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, prospeo=True),
                 mx_lookup=mx_for(WEB, MAIL))
    assert calls == [f"hunter.search:{WEB}"]  # Prospeo was not asked about the same domain
    assert out.choice["reason"] == f"Hunter found nobody at {WEB}"
    assert out.choice["alternatives"] == [{"domain": MAIL, "source": "pdl", "mx": True}]
    assert out.found_by is None and company.email_domain is None
    run = s.exec(select(CompanyProviderRun)).one()
    assert (run.provider, run.domain, run.status) == ("hunter", WEB, "empty")


def test_choosing_the_offered_domain_finds_people_and_stores_both_domains(world) -> None:  # noqa: ANN001
    s, company, app = world
    domains.register(company, MAIL, "pdl")
    calls: list[str] = []
    fs = finders(calls, prospeo=True)
    fs["hunter"] = DomainHunter(MAIL, calls)
    first = wf.run(s, app, mock=True, finders=fs, mx_lookup=mx_for(WEB, MAIL))
    assert first.choice and first.found_by is None and calls == [f"hunter.search:{WEB}"]
    out = wf.run(s, app, mock=True, finders=fs, mx_lookup=mx_for(WEB, MAIL), email_domain=MAIL)
    assert out.lookup_domain == MAIL and out.found_by == "hunter"
    assert calls[1] == f"hunter.search:{MAIL}" and not any(c.startswith("prospeo") for c in calls)
    # website domain and email domain are both on the company; the email domain is used next time
    assert (company.domain, company.email_domain) == (WEB, MAIL)
    assert out.email_domain == MAIL and any("both are stored" in st.detail for st in out.steps)
    assert all(c["email"].endswith("@" + MAIL) for c in out.candidates if c["verified"])
    other = make_job(s, company)
    again = wf.run(s, other, mock=True, finders=fs, mx_lookup=mx_for(WEB, MAIL))
    assert again.from_cache and again.credits == 0 and again.lookup_domain == MAIL
    n = len(calls)
    wf.run(s, other, mock=True, finders=fs, mx_lookup=mx_for(WEB, MAIL), requery=True)
    assert calls[n] == f"hunter.search:{MAIL}"  # a re-query asks about the email domain


def test_with_no_other_domain_to_offer_it_goes_on_to_the_next_provider(world) -> None:  # noqa: ANN001
    s, _, app = world
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, prospeo=True), mx_lookup=mx_for(WEB))
    assert out.choice is None and out.found_by == "prospeo"
    assert [c.split(":")[0] for c in calls][:2] == ["hunter.search", "prospeo.search"]


def test_a_run_for_another_domain_is_not_a_cache_hit(world) -> None:  # noqa: ANN001
    s, company, app = world
    s.add(CompanyProviderRun(company_id=company.id, provider="hunter", domain="old.test",
                             status="empty", candidates=[]))
    s.add(CompanyProviderRun(company_id=company.id, provider="prospeo", domain=None,
                             status="empty", candidates=[]))  # recorded before domains were
    s.flush()
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls), mx_lookup=mx_for(WEB))
    statuses = {st.provider: st.status for st in out.steps if st.provider in wf.WATERFALL}
    assert statuses["hunter"] != "cached" and statuses["prospeo"] == "cached"


def test_a_typed_domain_replaces_what_was_learned(world) -> None:  # noqa: ANN001
    s, company, app = world
    company.email_domain = MAIL
    s.flush()
    out = wf.run(s, app, mock=True, finders=finders([], hunter=True), domain="fresh.test",
                 mx_lookup=mx_for("fresh.test"))
    assert (company.domain, company.email_domain, out.lookup_domain) == (
        "fresh.test", None if out.found_by is None else "fresh.test", "fresh.test")


# ------------------------------------------------------------------------------ endpoints


def test_domain_picker_endpoints(client, world, monkeypatch) -> None:  # noqa: ANN001
    s, company, app = world
    domains.register(company, MAIL, "pdl", "another company named Sekoia")
    s.commit()
    monkeypatch.setattr(dns_check, "lookup_mx", lambda d: ["m"] if d != "dead.test" else [])
    r = client.get(f"/api/companies/{company.id}/domains")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["website"] == WEB and body["in_use"] == WEB
    assert {(d["domain"], d["mx"], d["is_website"]) for d in body["domains"]} == {
        (WEB, True, True), (MAIL, True, False)}
    put = client.put(f"/api/companies/{company.id}/domains", json={"email_domain": MAIL}).json()
    assert put["email"] == MAIL and put["in_use"] == MAIL
    assert client.put(f"/api/companies/{company.id}/domains", json={"email_domain": "no spaces"}
                      ).status_code == 422
    back = client.put(f"/api/companies/{company.id}/domains", json={"email_domain": None}).json()
    assert back["email"] is None and back["in_use"] == WEB


def test_find_endpoint_returns_the_choice(client, world) -> None:  # noqa: ANN001
    s, company, app = world
    domains.register(company, MAIL, "pdl")
    s.commit()
    r = client.post(f"/api/applications/{app.id}/contact/find", json={})
    # the test workspace uses the mock: MX only for the company's own domain, so no choice here
    assert r.status_code == 200 and r.json()["lookup_domain"] == WEB
    assert r.json()["choice"] is None
    again = client.post(f"/api/applications/{app.id}/contact/find",
                        json={"email_domain": MAIL, "requery": True}).json()
    assert again["lookup_domain"] == MAIL  # the chosen domain was asked about, not the website's
    assert again["choice"]["reason"] == f"Hunter found nobody at {MAIL}"
    assert [c["domain"] for c in again["choice"]["alternatives"]] == [WEB]  # nothing was stored
    assert again["email_domain"] is None
