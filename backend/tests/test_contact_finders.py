"""Provider mappers and clients over httpx.MockTransport (shapes recorded from the real APIs in
the Phase 12 probe), email patterns, company resolution, and per-key quotas. No network."""

import json
from pathlib import Path

import duckdb
import httpx
import pytest
from sqlmodel import Session

from app.db import engine
from app.models import Company
from app.providers.contact_finders import (
    Candidate,
    Cost,
    FinderError,
    KeyRefused,
    OutOfCredits,
    RateLimited,
)
from app.providers.contact_finders.apify import ApifyFinder
from app.providers.contact_finders.apollo import ApolloFinder
from app.providers.contact_finders.hunter import HunterFinder
from app.providers.contact_finders.prospeo import ProspeoFinder
from app.services import company_resolve, email_pattern
from app.services import provider_quota as quota

HUNTER_SEARCH = {"data": {"domain": "sekoia.io", "pattern": "{first}.{last}",
                          "organization": "Sekoia", "emails": [
    {"value": "david.bizeul@sekoia.io", "type": "personal", "first_name": "David",
     "last_name": "Bizeul", "position": "Co-Founder", "verification": {"status": "valid"}},
    {"value": "contact@sekoia.io", "type": "generic", "first_name": None, "last_name": None},
    {"value": "x.y@sekoia.io", "type": "personal", "first_name": "X", "last_name": "Y",
     "position": "IT Manager", "verification": {"status": "accept_all"}}]}}


def transport(handler) -> httpx.MockTransport:  # noqa: ANN001
    return httpx.MockTransport(handler)


def test_hunter_domain_search_keeps_status_and_pattern() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["key_in_header"] = req.headers["X-API-KEY"] == "k1"
        seen["key_in_url"] = "k1" in str(req.url)
        return httpx.Response(200, json=HUNTER_SEARCH)

    res = HunterFinder(transport(handler)).search("k1", "sekoia.io", ["cto"])
    assert seen == {"key_in_header": True, "key_in_url": False}
    assert [(c.full_name, c.email_status) for c in res.candidates] == [
        ("David Bizeul", "valid"), ("X Y", "accept_all")]  # generic addresses dropped
    assert res.pattern == "{first}.{last}" and res.cost.credits == 1.0
    assert [c.verified for c in res.candidates] == [True, False]  # catch-all is never verified


def test_hunter_verify_costs_half_a_credit() -> None:
    f = HunterFinder(transport(lambda r: httpx.Response(200, json={"data": {"status": "valid"}})))
    assert f.verify("k", "a@b.c") == ("valid", Cost(credits=0.5))


def test_prospeo_search_then_enrich() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["X-KEY"] == "k"
        if req.url.path == "/search-person":
            body = json.loads(req.content)
            assert body["filters"]["company"]["websites"]["include"] == ["elevenlabs.io"]
            return httpx.Response(200, json={"error": False, "free": False, "results": [
                {"person": {"person_id": "p1", "full_name": "Matthew Hills",
                            "current_job_title": "GTM Lead",
                            "email": {"status": "VERIFIED", "revealed": False}},
                 "company": {"industry": "Software"}}]})
        assert json.loads(req.content)["only_verified_email"] is True
        return httpx.Response(200, json={"error": False, "free_enrichment": False, "person": {
            "email": {"status": "VERIFIED", "revealed": True,
                      "email": "matthew.hills@elevenlabs.io"}}})

    f = ProspeoFinder(transport(handler))
    res = f.search("k", "elevenlabs.io", ["gtm"])
    cand = res.candidates[0]
    assert cand.provider_id == "p1" and cand.has_email and cand.email is None
    assert res.cost.credits == 1.0 and res.organization == {"industry": "Software"}
    got, cost = f.reveal("k", cand)
    assert got.verified and got.email == "matthew.hills@elevenlabs.io" and cost.credits == 1.0


def test_prospeo_no_match_is_free_and_repeat_enrichment_is_free() -> None:
    nm = ProspeoFinder(transport(lambda r: httpx.Response(
        400, json={"error": True, "error_code": "NO_MATCH"})))
    # 400 -> SourceError -> classified as a plain FinderError (not a refused key)
    with pytest.raises(FinderError):
        nm.reveal("k", Candidate("A B", provider_id="p"))
    repeat = ProspeoFinder(transport(lambda r: httpx.Response(200, json={
        "error": False, "free_enrichment": True,
        "person": {"email": {"status": "VERIFIED", "email": "a@b.c"}}})))
    assert repeat.reveal("k", Candidate("A B", provider_id="p"))[1].credits == 0


def test_apollo_search_is_free_and_match_reveals() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["x-api-key"] == "k"
        if req.url.path.endswith("api_search"):
            return httpx.Response(200, json={"people": [
                {"id": "a1", "first_name": "Mariano", "title": "Chief Technology Officer",
                 "has_email": True},
                {"id": "a2", "first_name": "Jing", "title": "Head of Engineering",
                 "has_email": False}]})
        assert req.url.params["id"] == "a1"
        return httpx.Response(200, json={"person": {
            "first_name": "Mariano", "last_name": "Albera", "email": "m@checkout.com",
            "email_status": "verified", "title": "Chief Technology Officer"}})

    f = ApolloFinder(transport(handler))
    res = f.search("k", "checkout.com", ["cto"])
    assert res.cost.credits == 0 and [c.has_email for c in res.candidates] == [True, False]
    got, cost = f.reveal("k", res.candidates[0])
    assert got.verified and got.full_name == "Mariano Albera" and cost.credits == 1.0


def test_apollo_unverified_email_is_not_accepted() -> None:
    f = ApolloFinder(transport(lambda r: httpx.Response(200, json={"person": {
        "email": "a@b.c", "email_status": "extrapolated"}})))
    got, cost = f.reveal("k", Candidate("A", provider_id="x"))
    assert not got.verified and got.email_status == "unknown" and cost.credits == 1.0


def test_apify_caps_the_run_and_takes_verified_leads_only() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["Authorization"] == "Bearer tok"
        seen["cap"] = req.url.params["maxTotalChargeUsd"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(201, json=[
            {"first_name": "David", "last_name": "K", "email": "david@grafana.com",
             "title": "VP of Engineering"}, {}])

    res = ApifyFinder(transport(handler)).search("tok", "grafana.com", ["vp engineering"])
    assert seen["auth"] and float(seen["cap"]) <= 0.10
    assert seen["body"]["email_status"] == ["verified"] and seen["body"]["max_result"] <= 5
    assert [c.email for c in res.candidates] == ["david@grafana.com"]
    assert res.cost.usd == pytest.approx(0.007) and res.candidates[0].actor == \
        "microworlds/leads-finder"


@pytest.mark.parametrize(("status", "body", "error"), [
    (401, "bad key", KeyRefused), (403, "forbidden", KeyRefused),
    (402, "payment", OutOfCredits), (429, "slow down", RateLimited),
    (500, "boom", FinderError)])
def test_errors_are_typed_and_never_retried(status: int, body: str, error: type) -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, text=body)

    with pytest.raises(error):
        HunterFinder(transport(handler)).search("k", "a.b", ["cto"])
    assert len(calls) == 1  # paid calls are never retried


# ------------------------------------------------------------------------------- patterns


def test_email_pattern_inference_and_build() -> None:
    pattern, conf, evidence = email_pattern.infer([
        ("David Bizeul", "david.bizeul@sekoia.io"), ("Dylan Braët", "dylan.braet@sekoia.io"),
        ("Odd One", "oo@sekoia.io")])
    assert pattern == "{first}.{last}" and conf >= 65 and len(evidence) == 2
    assert email_pattern.build("{f}{last}", "Jean-Luc Dupont", "x.fr") == "jdupont@x.fr"
    assert email_pattern.build("{first}.{last}", "Mono", "x.fr") is None
    assert email_pattern.infer([("A B", "zzz@x.y")])[0] is None


# ------------------------------------------------------------------- company resolution


@pytest.fixture()
def pdl(tmp_path: Path) -> Path:
    csv = tmp_path / "pdl.csv"
    csv.write_text(
        "name,website,linkedin_url,size,industry,country,name_key\n"
        "Sekoia,https://www.sekoia.io/,linkedin.com/company/sekoia,51-200,Software,france,sekoia\n"
        "Acme,acme-us.com,linkedin.com/company/acme-us,1001-5000,Retail,united states,acme\n"
        "Acme,acme.fr,linkedin.com/company/acme-fr,11-50,Retail,france,acme\n"
        "NoSite,,,1-10,x,france,nosite\n")
    out = tmp_path / "companies.parquet"
    duckdb.connect().execute(f"COPY (SELECT * FROM read_csv_auto('{csv}')) TO '{out}' "
                             "(FORMAT parquet)")
    return out


def test_pdl_lookup_domain_linkedin_size(pdl: Path) -> None:
    hit = company_resolve.pdl_lookup("Sekoia SAS", path=pdl)
    assert (hit.domain, hit.source, hit.employees_max) == ("sekoia.io", "pdl", 200)
    assert hit.linkedin_url == "linkedin.com/company/sekoia"
    assert company_resolve.pdl_lookup("NoSite", path=pdl) is None  # no website, no domain
    assert company_resolve.pdl_lookup("Unknown Co", path=tmp_missing(pdl)) is None


def tmp_missing(p: Path) -> Path:
    return p.parent / "missing.parquet"


def test_pdl_prefers_the_jobs_country_then_size(pdl: Path) -> None:
    assert company_resolve.pdl_lookup("Acme", ["FR"], pdl).domain == "acme.fr"
    assert company_resolve.pdl_lookup("Acme", [], pdl).domain == "acme-us.com"  # largest


def test_resolve_fills_only_empty_fields_and_never_a_job_board(seeded: None, pdl: Path) -> None:
    with Session(engine) as s:
        c = Company(name="Sekoia", normalized_name="sekoia-res")
        s.add(c)
        s.flush()
        r = company_resolve.resolve(s, c, path=pdl)
        assert r.source == "pdl" and c.domain == "sekoia.io" and c.domain_source == "pdl"
        assert c.industry == "Software" and c.employees_max == 200
        typed = company_resolve.resolve(s, c, domain="https://Sekoia.io/jobs")
        assert typed.source == "manual" and c.domain == "sekoia.io"
        assert company_resolve.clean_domain("www.greenhouse.io/x") == "greenhouse.io"
        s.rollback()


# ------------------------------------------------------------------------------- quotas


def test_quota_counts_per_key_and_resets_each_month(seeded: None) -> None:
    from datetime import UTC, datetime

    with Session(engine) as s:
        keys = [("prospeo#1", "a"), ("prospeo#2", "b")]
        oct_, nov = datetime(2026, 10, 3, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
        quota.apply_remote(s, "prospeo", "prospeo#1", limit=100, used=99.5, now=oct_)
        assert quota.next_key(s, "prospeo", 1, keys=keys, now=oct_) == ("prospeo#2", "b")
        quota.record(s, "prospeo", "prospeo#2", "search", Cost(credits=1), now=oct_)
        assert quota.remaining(s, "prospeo", "prospeo#2", oct_) == 99
        assert quota.next_key(s, "prospeo", 1, keys=keys, now=nov) == ("prospeo#1", "a")
        quota.disable(s, "prospeo", "prospeo#1", "refused")
        assert quota.next_key(s, "prospeo", 1, keys=keys, now=nov) == ("prospeo#2", "b")
        quota.exhaust(s, "prospeo", "prospeo#2", nov)
        assert quota.next_key(s, "prospeo", 1, keys=keys, now=nov) is None
        quota.enable(s, "prospeo", "prospeo#1")
        assert quota.next_key(s, "prospeo", 1, keys=keys, now=nov) == ("prospeo#1", "a")
        s.rollback()


def test_apify_is_counted_in_dollars(seeded: None) -> None:
    with Session(engine) as s:
        keys = [("apify#1", "t")]
        assert quota.UNITS["apify"] == "usd"
        quota.apply_remote(s, "apify", "apify#1", limit=5.0, used=4.95)
        assert quota.next_key(s, "apify", 0.10, keys=keys) is None  # a run could exceed the limit
        assert quota.next_key(s, "apify", 0.04, keys=keys) == ("apify#1", "t")
        s.rollback()


def test_sql_name_key_equals_the_python_rule() -> None:
    names = ["Sekoia SAS", "In The Pocket", "Évelyne & Fils S.A.", "Børn og Unge",
             "ABOUT YOU SE & Co. KG", "Café Müller GmbH", "Reply Deutschland SE",
             "Acme Group Inc.", "株式会社", "  "]
    con = duckdb.connect()
    con.execute("CREATE TABLE t(name VARCHAR)")
    con.executemany("INSERT INTO t VALUES (?)", [(n,) for n in names])
    rows = con.execute(f"SELECT name, {company_resolve.name_key_sql('name')} FROM t").fetchall()
    for name, key in rows:
        assert key == company_resolve.normalize_company(name), name


# ------------------------------------------------- domains from the listing (Phase 12b)


def test_company_host_accepts_only_the_companys_own_site() -> None:
    host = company_resolve.company_host
    assert host("https://careers.acme.co.uk/jobs/42", "Acme Ltd") == "acme.co.uk"
    assert host("https://www.acme.com/careers", "ACME SAS") == "acme.com"
    assert host("https://jobs.lever.co/acme/123", "Acme") is None  # an ATS
    assert host("https://boards.greenhouse.io/acme/jobs/1", "Acme") is None
    assert host("https://www.welcometothejungle.com/en/companies/acme", "Acme") is None
    assert host("https://other.example.org/x", "Acme") is None  # the name isn't in the host
    assert host(None, "Acme") is None


def test_listing_json_ld_gives_the_company_website_and_apply_link() -> None:
    from app.services.listing import extract_job_posting

    html = (Path(__file__).parent / "fixtures/sources/wttj_job_page.html").read_text()
    listing = extract_job_posting(html)
    assert listing.company_url == "https://www.yubo.live"


def test_ats_mappers_keep_the_apply_link() -> None:
    from app.providers.sources import boards

    root = Path(__file__).parent / "fixtures/sources"
    board = boards.Board("lever", "acme")
    jobs = boards.parse_lever(json.loads((root / "boards_lever.json").read_text()), board)
    assert jobs and all(j.apply_url and j.apply_url.startswith("http") for j in jobs)


def test_resolve_order_stored_website_then_pdl_then_listing(seeded: None, pdl: Path) -> None:
    from app.models import Job

    with Session(engine) as s:
        sek = Company(name="Sekoia", normalized_name="sekoia-ord")
        site = Company(name="Yubo", normalized_name="yubo-ord", website="https://www.yubo.live/")
        apply_co = Company(name="Zorro", normalized_name="zorro-ord")
        none_co = Company(name="Nobody Known", normalized_name="nobody-ord")
        s.add_all([sek, site, apply_co, none_co])
        s.flush()
        s.add(Job(source="adzuna", external_id="ord-1", url="https://job-board.test/1", title="x",
                  company_id=apply_co.id, dedupe_key="ord-1",
                  apply_url="https://careers.zorro.io/apply/1"))
        s.add(Job(source="adzuna", external_id="ord-2", url="https://job-board.test/2", title="x",
                  company_id=none_co.id, dedupe_key="ord-2"))
        s.flush()
        assert company_resolve.resolve(s, site, path=pdl).source == "listing"
        assert site.domain == "yubo.live"  # the captured website beats a name lookup
        assert company_resolve.resolve(s, sek, path=pdl).source == "pdl"
        r = company_resolve.resolve(s, apply_co, path=tmp_missing(pdl))
        assert (r.domain, r.note) == ("zorro.io", "from apply link")
        calls: list[str] = []

        def fetcher(url: str) -> str | None:
            calls.append(url)
            return "https://www.nobody-known.fr/about"

        r = company_resolve.resolve(s, none_co, path=tmp_missing(pdl), fetcher=fetcher)
        assert r.domain == "nobody-known.fr" and calls == ["https://job-board.test/2"]
        blocked = Company(name="Blocked Co", normalized_name="blocked-ord")
        s.add(blocked)
        s.flush()
        assert company_resolve.resolve(s, blocked, path=tmp_missing(pdl),
                                       fetcher=lambda u: None).domain is None
        s.rollback()
