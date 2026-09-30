"""Company research, offline: a fake website behind httpx.MockTransport (robots.txt, sitemap,
links), news feed parsers, quote verification, the cache, and the model call policy."""

import json
from datetime import timedelta
from itertools import count

import httpx
import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Company, CompanySignal, Contact, ResearchRun
from app.models.base import utcnow
from app.providers.http import PoliteClient
from app.providers.news import parse_gdelt, parse_google_news
from app.services import research as rs

_n = count(1)

HOME = """<html><head><title>Voxa · Voice AI</title></head><body>
<a href="/a-propos">À propos</a> <a href="/solutions/voicebot">Nos solutions</a>
<a href="/clients">Clients</a> <a href="/private/admin">Admin</a>
<a href="https://twitter.com/voxa">Twitter</a>
<p>Voxa builds voice agents for customer service.</p></body></html>"""
PAGES = {
    "/a-propos": "<html><head><meta property='article:published_time' content='2026-05-02'>"
                 "</head><body><p>Voxa runs proprietary sovereign models for each channel.</p>"
                 "</body></html>",
    "/solutions/voicebot": "<html><body><p>Our voicebot answers calls in 12 languages.</p>"
                           "</body></html>",
    "/clients": "<html><body><p>A mutual insurer automated 37% of its incoming requests with "
                "Voxa.</p></body></html>",
    "/robots.txt": "User-agent: *\nDisallow: /private/\nSitemap: https://voxa.test/sitemap.xml",
    "/sitemap.xml": "<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/"
                    "sitemap/0.9'><url><loc>https://voxa.test/blog/launch-2026</loc>"
                    "<lastmod>2026-06-01</lastmod></url></urlset>",
    "/blog/launch-2026": "<html><body><p>We launched Voxa Agent Studio in June 2026.</p>"
                         "</body></html>",
}


def site_transport(requested: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        requested.append(path)
        if path in ("", "/"):
            return httpx.Response(200, text=HOME)
        if path in PAGES:
            return httpx.Response(200, text=PAGES[path])
        return httpx.Response(404, text="nope")
    return httpx.MockTransport(handler)


def fetcher(requested: list[str]) -> rs.WebFetcher:
    client = PoliteClient("t", min_interval=0, retries=0, transport=site_transport(requested))
    f = rs.WebFetcher(client)
    f.news = lambda *a, **k: ([], [])  # type: ignore[method-assign]
    return f


def test_the_site_is_read_politely_and_by_kind() -> None:
    requested: list[str] = []
    sources, warnings = fetcher(requested).site("https://voxa.test", 8, lambda *a: None)
    kinds = {s.kind for s in sources}
    assert {"home", "about", "product", "customers", "news"} <= kinds
    assert "/private/admin" not in requested and requested.index("/robots.txt") < \
        requested.index("/a-propos")
    about = next(s for s in sources if s.kind == "about")
    assert about.page_date and about.page_date.date().isoformat() == "2026-05-02"
    blog = next(s for s in sources if s.kind == "news")
    assert blog.page_date and blog.page_date.month == 6  # the sitemap's lastmod
    assert warnings == []


def test_news_feeds_parse() -> None:
    gdelt = parse_gdelt(json.dumps({"articles": [
        {"url": "https://news.test/a", "title": "Voxa raises €12M",
         "seendate": "20260610T080000Z"}]}))
    assert gdelt[0].title == "Voxa raises €12M" and gdelt[0].published.year == 2026
    rss = parse_google_news("""<rss><channel><item>
      <title>Voxa opens Madrid office - Le Monde</title>
      <link>https://news.test/b</link><pubDate>Tue, 02 Jun 2026 08:00:00 GMT</pubDate>
      <description>&lt;a&gt;Voxa opens Madrid office&lt;/a&gt; Le Monde</description></item>
      </channel></rss>""")
    assert rss[0].url == "https://news.test/b" and rss[0].published.month == 6
    assert parse_google_news("not xml") == []


def test_quotes_are_verified_and_numbers_checked() -> None:
    src = [rs.Source("https://voxa.test/clients", "customers", "Clients",
                     "A mutual insurer automated 37% of its incoming requests with Voxa.")]
    ok = rs.RawSignal(kind="customer_result", fact="A mutual insurer automated 37% of requests",
                      quote="a mutual insurer automated 37% of its incoming requests",
                      source_url="https://voxa.test/clients")
    assert rs.verify(ok, src) is None
    assert rs.verify(ok.model_copy(update={"quote": "an insurer automated half its requests"}),
                     src) == "quote not found in the page"
    assert rs.verify(ok.model_copy(update={"fact": "An insurer automated 45% of requests"}),
                     src) == "a number in the fact isn't in the quote"
    assert rs.verify(ok.model_copy(update={"source_url": "https://elsewhere"}), src) == \
        "unknown source"


def make_company(s: Session, email: str | None = "ceo@voxa.test") -> Company:
    n = next(_n)
    company = Company(name=f"Voxa{n}", normalized_name=f"voxa research {n}")
    s.add(company)
    s.flush()
    if email:
        s.add(Contact(company_id=company.id, full_name=f"Ana V{n}", email=email,
                      normalized_name=f"ana v{n}"))
    s.commit()
    s.refresh(company)
    return company


def test_the_site_comes_from_the_contacts_work_email(seeded: None) -> None:
    with Session(engine) as s:
        assert rs.company_site(s, make_company(s)) == "https://voxa.test"
        assert rs.company_site(s, make_company(s, "ana@gmail.com")) is None
        c = make_company(s, None)
        c.website = "voxa.example"
        assert rs.company_site(s, c) == "https://voxa.example"


def test_research_stores_verified_signals_then_reuses_them(seeded: None) -> None:
    with Session(engine) as s:
        company_id = make_company(s).id
    requested: list[str] = []
    out = rs.ensure(engine, company_id, trigger="draft", researcher=rs.MockResearcher(),
                    fetcher=fetcher(requested))
    assert not out.cached and out.run.status == "done" and out.run.pages >= 4
    facts = {x.fact for x in out.signals}
    assert "A mutual insurer automated 37% of its incoming requests with Voxa." in facts
    assert all(x.verified and x.quote for x in out.signals)
    assert sum(x.selected for x in out.signals) <= 3
    assert out.run.calls and out.run.calls[0]["model"] == "mock-research"
    assert next(x for x in out.signals if "37%" in x.fact).selected  # customer results first

    class Boom:
        def site(self, *a):  # noqa: ANN002, ANN201
            raise AssertionError("fetched although the signals are fresh")

    again = rs.ensure(engine, company_id, trigger="draft", researcher=rs.MockResearcher(),
                      fetcher=Boom())  # type: ignore[arg-type]
    assert again.cached and again.run.status == "cached" and not again.run.calls
    with Session(engine) as s:
        company = s.get(Company, company_id)
        company.research_refreshed_at = utcnow() - timedelta(days=31)
        s.add(company)
        s.commit()
    stale = rs.ensure(engine, company_id, trigger="manual", researcher=rs.MockResearcher(),
                      fetcher=fetcher([]))
    assert not stale.cached


def test_no_website_fails_the_run_clearly(seeded: None) -> None:
    with Session(engine) as s:
        company_id = make_company(s, None).id
    with pytest.raises(rs.ResearchError, match="No website"):
        rs.ensure(engine, company_id, trigger="draft", researcher=rs.MockResearcher(),
                  fetcher=fetcher([]))
    with Session(engine) as s:
        run = s.exec(select(ResearchRun).where(ResearchRun.company_id == company_id)).one()
        assert run.status == "failed" and "No website" in run.error


def test_manual_signals_are_verified_selected_and_survive_refresh(seeded: None) -> None:
    with Session(engine) as s:
        company_id = make_company(s).id
        mine = rs.add_manual(s, company_id, "They just opened a team in Lyon", "https://x.test")
        assert mine.verified and mine.selected and mine.origin == "manual"
    rs.ensure(engine, company_id, trigger="manual", researcher=rs.MockResearcher(),
              fetcher=fetcher([]), force=True)
    with Session(engine) as s:
        kept = s.exec(select(CompanySignal).where(CompanySignal.company_id == company_id,
                                                  CompanySignal.origin == "manual")).all()
        assert [k.fact for k in kept] == ["They just opened a team in Lyon"]


def ollama(responses: list[tuple[int, str]], seen: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["model"])
        status, body = responses.pop(0)
        return httpx.Response(status, text=body)
    return httpx.MockTransport(handler)


ANSWER = json.dumps({"message": {"content": json.dumps({"signals": []})},
                     "prompt_eval_count": 900, "eval_count": 40})


def test_the_model_policy_retries_busy_and_falls_back_on_quota() -> None:
    seen: list[str] = []
    sleeps: list[float] = []
    busy = (429, '{"error":"too many concurrent requests"}')
    r = rs.OllamaResearcher(sleep=sleeps.append, transport=ollama([busy, (200, ANSWER)], seen))
    log: list[dict] = []
    assert r.extract("Voxa", [rs.Source("u", "home", "t", "x")], log.append) == []
    assert [c["outcome"] for c in log] == ["concurrency_limited", "ok"] and sleeps == [2.0]
    assert log[1]["prompt_tokens"] == 900

    quota = (429, '{"error":"you have reached your weekly usage limit"}')
    r = rs.OllamaResearcher(transport=ollama([quota, (200, ANSWER)], seen))
    log = []
    r.extract("Voxa", [rs.Source("u", "home", "t", "x")], log.append)
    assert seen[-2:] == ["gemma4:31b-cloud", "gemma4:12b"] and r.model == "gemma4:12b"
    assert [c["outcome"] for c in log] == ["quota", "ok"]


def test_a_schema_shaped_answer_is_unwrapped_not_read_as_empty() -> None:
    seen: list[str] = []
    wrapped = json.dumps({"message": {"content": json.dumps({"properties": {"signals": [
        {"kind": "product", "fact": "Voxa builds voice agents", "quote": "Voxa builds voice "
         "agents for customer service", "source_url": "u"}]}})}})
    r = rs.OllamaResearcher(transport=ollama([(200, wrapped)], seen))
    out = r.extract("Voxa", [rs.Source("u", "home", "t", "x")], lambda c: None)
    assert out and out[0].fact == "Voxa builds voice agents"
    empty_default = json.dumps({"message": {"content": json.dumps({"other": 1})}})
    r = rs.OllamaResearcher(transport=ollama([(200, empty_default), (200, empty_default),
                                              (200, empty_default), (200, empty_default)], seen))
    with pytest.raises(rs.ResearchError):
        r.extract("Voxa", [rs.Source("u", "home", "t", "x")], lambda c: None)


def test_a_run_without_verified_signals_is_not_fresh(seeded: None) -> None:
    with Session(engine) as s:
        company_id = make_company(s).id

    class Nothing:
        model = "none"

        def extract(self, company, sources, log):  # noqa: ANN001, ANN201
            return []

    rs.ensure(engine, company_id, trigger="draft", researcher=Nothing(), fetcher=fetcher([]))
    with Session(engine) as s:
        assert not rs.is_fresh(s, s.get(Company, company_id))


def test_auto_selection_mixes_kinds() -> None:
    rows = [CompanySignal(id=i, company_id=1, fact=f"f{i}", kind=k, verified=True)
            for i, k in enumerate(["customer_result", "customer_result", "customer_result",
                                   "technical", "launch"], 1)]
    rs._auto_select(rows, 3)
    assert [r.kind for r in rows if r.selected] == ["customer_result", "technical", "launch"]
