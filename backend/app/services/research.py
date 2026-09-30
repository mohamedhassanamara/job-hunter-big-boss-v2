"""Company research for cold emails: the company's own site (home, about, product, customers,
news, careers) and recent news (GDELT, Google News RSS), turned into signals by a model. Every
signal keeps its exact supporting quote, verified in code against the fetched text; a signal
without a verified quote is dropped.

It runs ONLY at the email draft step (services/outreach.draft_with_research) or from the
"Research now" button (api/research.py): never on discovery, scoring, shortlisting, matching,
CV generation or in bulk (tests/test_research_guard.py). Fresh signals (within
`research.refresh_days`) are reused: no fetch, no model call.
"""

import re
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import AppSetting, Company, CompanyPage, CompanySignal, Contact, ResearchRun
from app.models.base import utcnow
from app.services.fit import _norm
from app.services.text import html_to_text

DEFAULT_RESEARCH: dict[str, Any] = {
    "refresh_days": 30,
    "max_pages": 8,
    "news": {"gdelt": True, "google_news": True},
    "max_selected": 3,
}
PAGE_CHARS = 6000  # per page, after conversion to text
CHUNK_CHARS = 14000  # per model call
FREEMAIL = {"gmail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr", "outlook.com",
            "outlook.fr", "live.com", "icloud.com", "orange.fr", "free.fr", "laposte.net",
            "protonmail.com", "gmx.com", "gmx.fr"}
# Which site pages are worth reading, by words in their URL path or link text (EN/FR).
PAGE_KINDS: dict[str, list[str]] = {
    "about": ["about", "a-propos", "apropos", "qui-sommes-nous", "company", "entreprise",
              "notre-histoire", "about-us"],
    "product": ["product", "products", "produit", "produits", "solution", "solutions",
                "platform", "plateforme", "technology", "technologie", "features"],
    "customers": ["customers", "clients", "case-studies", "case-study", "cas-clients",
                  "temoignages", "references", "success-stories", "etudes-de-cas"],
    "news": ["news", "blog", "actualites", "actualite", "presse", "press", "newsroom",
             "insights", "articles"],
    "careers": ["careers", "career", "carrieres", "recrutement", "jobs", "join-us",
                "nous-rejoindre", "rejoignez-nous"],
}
KIND_PRIORITY = ["customer_result", "technical", "launch", "product", "funding", "expansion",
                 "other"]
Progress = Callable[[str, int, int], None]  # (phase, done, total)
_one_at_a_time = threading.Lock()


class ResearchError(RuntimeError):
    """Shown to the user (no website known, the site can't be read…)."""


def research_settings(s: Session) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == "research")).first()
    saved = dict(row.value) if row else {}
    return {**DEFAULT_RESEARCH, **saved,
            "news": {**DEFAULT_RESEARCH["news"], **(saved.get("news") or {})}}


# ----------------------------------------------------------------------------- the website


def company_site(s: Session, company: Company) -> str | None:
    """https://domain for the company: its website/domain if set, otherwise the domain most of
    its contacts' work emails use (Apollo imports), freemail excluded."""
    for value in (company.website, company.domain):
        if value and value.strip():
            v = value.strip()
            return v if v.startswith("http") else f"https://{v.strip('/')}"
    domains = Counter()
    for email in s.exec(select(Contact.email).where(Contact.company_id == company.id,
                                                       col(Contact.email).is_not(None))).all():
        domain = email.rsplit("@", 1)[-1].lower().strip() if email and "@" in email else ""
        if domain and domain not in FREEMAIL:
            domains[domain] += 1
    if not domains:
        return None
    return f"https://{domains.most_common(1)[0][0]}"


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.dates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._href, self._text = a["href"], []
        if tag == "meta" and (a.get("property") or a.get("name") or "") in (
                "article:published_time", "og:updated_time", "date", "dc.date"):
            self.dates.append(a.get("content") or "")
        if tag == "time" and a.get("datetime"):
            self.dates.append(a["datetime"] or "")

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _kind_of(url: str, text: str) -> str | None:
    hay = f"{urlsplit(url).path.lower()} {re.sub(r'[^a-z]+', '-', text.lower())}"
    for kind, words in PAGE_KINDS.items():
        if any(re.search(rf"(^|[/\-_ ]){re.escape(w)}($|[/\-_ .])", hay) for w in words):
            return kind
    return None


def parse_sitemap(xml_text: str) -> list[tuple[str, datetime | None]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    out = []
    for node in root.iter():
        if node.tag.endswith("url") or node.tag.endswith("sitemap"):
            loc = next((c.text for c in node if c.tag.endswith("loc")), None)
            mod = next((c.text for c in node if c.tag.endswith("lastmod")), None)
            if loc:
                out.append((loc.strip(), _date(mod)))
    return out


@dataclass
class Source:
    url: str
    kind: str  # home | about | product | customers | news | careers | press (a news item)
    title: str
    text: str
    page_date: datetime | None = None


class Fetcher(Protocol):
    def site(self, home: str, max_pages: int, progress: Progress) -> tuple[list[Source],
                                                                           list[str]]: ...

    def news(self, name: str, domain: str | None, language: str,
             settings: dict[str, Any]) -> tuple[list[Source], list[str]]: ...


class WebFetcher:
    """Real fetching: PoliteClient (honest User-Agent, 1 request/second) and robots.txt."""

    def __init__(self, client: Any = None):
        from app.providers.http import PoliteClient, Robots

        self.client = client or PoliteClient("Research", min_interval=1.0, retries=1,
                                             headers={"Accept": "text/html,application/xml,*/*"})
        self.robots = Robots(self.client)

    def _get(self, url: str) -> str | None:
        from app.providers.http import SourceError

        if not self.robots.allowed(url):
            return None
        try:
            return self.client.request("GET", url).text
        except SourceError:
            return None

    def site(self, home: str, max_pages: int, progress: Progress) -> tuple[list[Source],
                                                                           list[str]]:
        warnings: list[str] = []
        html = self._get(home)
        if html is None:
            raise ResearchError(f"Couldn't read {home} (blocked by robots.txt or unreachable)")
        host = urlsplit(home).netloc.removeprefix("www.")
        links = _Links()
        links.feed(html)
        candidates: dict[str, tuple[str, datetime | None]] = {}  # url → (kind, date)
        sitemap_urls = self.robots.sitemaps(home) or [urljoin(home, "/sitemap.xml")]
        for sm in sitemap_urls[:2]:
            xml = self._get(sm)
            for url, mod in parse_sitemap(xml or "")[:500]:
                if (kind := _kind_of(url, "")) and url not in candidates:
                    candidates[url] = (kind, mod)
        for href, text in links.links:
            url = urljoin(home, href).split("#")[0]
            if urlsplit(url).netloc.removeprefix("www.") != host:
                continue
            if (kind := _kind_of(url, text)) and url not in candidates:
                candidates[url] = (kind, None)
        # One page per kind first (shortest URL = the section page), then fill up.
        chosen: list[tuple[str, str, datetime | None]] = []
        for kind in PAGE_KINDS:
            urls = sorted((u for u, (k, _d) in candidates.items() if k == kind), key=len)
            if urls:
                chosen.append((urls[0], kind, candidates[urls[0]][1]))
        rest = sorted((u for u in candidates if u not in {c[0] for c in chosen}),
                      key=lambda u: (candidates[u][0] != "customers", len(u)))
        chosen += [(u, candidates[u][0], candidates[u][1]) for u in rest]
        chosen = chosen[:max(0, max_pages - 1)]
        sources = [Source(home, "home", _title(html), html_to_text(html)[:PAGE_CHARS],
                          _date(links.dates[0]) if links.dates else None)]
        for i, (url, kind, mod) in enumerate(chosen, 1):
            progress("fetching", i, len(chosen) + 1)
            page = self._get(url)
            if page is None:
                warnings.append(f"Skipped {url} (robots.txt or error)")
                continue
            dates = _Links()
            dates.feed(page)
            sources.append(Source(url, kind, _title(page), html_to_text(page)[:PAGE_CHARS],
                                  _date(dates.dates[0]) if dates.dates else mod))
        return sources, warnings

    def news(self, name: str, domain: str | None, language: str,
             settings: dict[str, Any]) -> tuple[list[Source], list[str]]:
        from app.providers.news import fetch_news

        items, warnings = fetch_news(name, domain, language=language,
                                     gdelt=bool(settings.get("gdelt")),
                                     google_news=bool(settings.get("google_news")),
                                     client=self.client)
        return [Source(i.url, "press", i.title, i.text, i.published) for i in items], warnings


class SampleFetcher:
    """The tour sandbox: made-up pages for its made-up companies. Never touches the web."""

    def site(self, home: str, max_pages: int, progress: Progress) -> tuple[list[Source],
                                                                           list[str]]:
        host = urlsplit(home).netloc or home
        name = host.split(".")[0].replace("-", " ").title()
        return [
            Source(home, "home", name, f"{name} builds a data platform for logistics teams."),
            Source(f"{home}/clients", "customers", "Clients",
                   f"A regional carrier cut its planning time by 30% with {name}."),
            Source(f"{home}/blog/launch", "news", "Launch",
                   f"In 2026 {name} launched a real-time routing engine."),
        ], []

    def news(self, name: str, domain: str | None, language: str,
             settings: dict[str, Any]) -> tuple[list[Source], list[str]]:
        return [], []


def _title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else ""


# -------------------------------------------------------------------------------- extraction


class RawSignal(BaseModel):
    kind: str = Field(description="product | technical | customer_result | launch | funding | "
                                  "expansion | other")
    fact: str = Field(description="One short sentence stating only what the quote says")
    quote: str = Field(description="Exact excerpt from the source text (at most 300 characters)")
    source_url: str = Field(description="The URL of the source the quote comes from")


class Extraction(BaseModel):
    signals: list[RawSignal]  # required: a malformed answer is retried, never read as "none"


class Researcher(Protocol):
    model: str

    def extract(self, company: str, sources: list[Source],
                log: Callable[[dict[str, Any]], None]) -> list[RawSignal]: ...


def prompt() -> tuple[str, str]:
    from app.services.prompt import PROMPTS_DIR

    text = (PROMPTS_DIR / "research.md").read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    return f"research/v{version.group(1) if version else '0'}", \
        text.split("## system", 1)[1].strip()


def chunks(sources: list[Source]) -> list[list[Source]]:
    out, cur, size = [], [], 0
    for src in sources:
        if cur and size + len(src.text) > CHUNK_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(src)
        size += len(src.text)
    return out + ([cur] if cur else [])


def user_message(company: str, sources: list[Source]) -> str:
    parts = [f"COMPANY: {company}"]
    for src in sources:
        date = f" (dated {src.page_date.date().isoformat()})" if src.page_date else ""
        parts.append(f"SOURCE {src.url} [{src.kind}]{date}\nTITLE: {src.title}\n{src.text}")
    return "\n\n".join(parts)


class OllamaResearcher:
    """gemma4:31b-cloud, local gemma4:12b as the fallback, with scoring's error handling: a
    429 concurrency limit backs off and retries (3 attempts), a quota error switches to the
    fallback for the rest of the run, other errors get one retry."""

    def __init__(self, model: str = "gemma4:31b-cloud", fallback: str | None = "gemma4:12b",
                 sleep: Callable[[float], None] = time.sleep, transport: Any = None):
        self.model, self.fallback, self._sleep, self._transport = model, fallback, sleep, transport

    def extract(self, company: str, sources: list[Source],
                log: Callable[[dict[str, Any]], None]) -> list[RawSignal]:
        from app.providers.base import ConcurrencyLimited, QuotaExceeded, ScoringFailed
        from app.providers.ollama import structured

        version, system = prompt()
        message = user_message(company, sources)
        failures, limited = 0, 0
        while True:
            started = time.monotonic()
            try:
                out, meta = structured(self.model, system, message, Extraction,
                                       transport=self._transport)
                log({"model": self.model, "prompt_version": version, "outcome": "ok",
                     "duration_ms": meta.get("duration_ms"), "calls": meta.get("calls"),
                     "prompt_tokens": meta.get("prompt_tokens"),
                     "output_tokens": meta.get("output_tokens"), "sources": len(sources)})
                return out.signals
            except ConcurrencyLimited as exc:
                limited += 1
                log(self._failed(version, "concurrency_limited", exc, started))
                if limited >= 3:
                    raise ResearchError(f"The model is busy: {exc}") from exc
                self._sleep(2.0 * 2 ** (limited - 1))
            except QuotaExceeded as exc:
                log(self._failed(version, "quota", exc, started))
                if not self.fallback or self.model == self.fallback:
                    raise ResearchError(str(exc)) from exc
                self.model = self.fallback  # the rest of this run uses the local model
            except ScoringFailed as exc:  # transient errors, invalid answers
                failures += 1
                log(self._failed(version, "error", exc, started))
                if failures >= 2:
                    raise ResearchError(f"Signal extraction failed: {exc}") from exc

    def _failed(self, version: str, outcome: str, exc: Exception, started: float) -> dict:
        return {"model": self.model, "prompt_version": version, "outcome": outcome,
                "error": str(exc)[:200], "duration_ms": int((time.monotonic() - started) * 1000)}


class MockResearcher:
    """Tests and the sandbox: sentences with a number or a product word become signals, with the
    sentence itself as the quote. No model."""

    model = "mock-research"

    def extract(self, company: str, sources: list[Source],
                log: Callable[[dict[str, Any]], None]) -> list[RawSignal]:
        log({"model": self.model, "prompt_version": "research/mock", "outcome": "ok",
             "duration_ms": 0, "sources": len(sources)})
        out = []
        for src in sources:
            for sentence in re.split(r"(?<=[.!?])\s+", src.text):
                s = sentence.strip()
                if 20 <= len(s) <= 300 and (re.search(r"\d", s) or re.search(
                        r"\b(platform|plateforme|model|modèle|launch|lance|customers?|clients?)\b",
                        s, re.I)):
                    kind = "customer_result" if re.search(r"\d+\s?%", s) else "product"
                    out.append(RawSignal(kind=kind, fact=s, quote=s, source_url=src.url))
        return out[:8]


# ------------------------------------------------------------------------------ verification


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[^\d]", "", n) for n in re.findall(r"\d[\d\s.,]*", text)} - {""}


def verify(raw: RawSignal, sources: list[Source]) -> str | None:
    """Why a signal is dropped (None = keep): its quote must be in the fetched text of its
    source (normalised: case, accents, punctuation), and the fact's numbers in the quote."""
    src = next((x for x in sources if x.url == raw.source_url), None)
    if src is None:
        return "unknown source"
    quote = _norm(raw.quote)
    if len(quote.split()) < 4:
        return "quote too short"
    if quote not in _norm(f"{src.title} {src.text}"):
        return "quote not found in the page"
    if not _numbers(raw.fact) <= _numbers(raw.quote):
        return "a number in the fact isn't in the quote"
    return None


# -------------------------------------------------------------------------------- the runs


def is_fresh(s: Session, company: Company) -> bool:
    days = int(research_settings(s).get("refresh_days") or 30)
    when = company.research_refreshed_at
    if when is None:
        return False
    when = when if when.tzinfo else when.replace(tzinfo=UTC)
    return utcnow() - when < timedelta(days=days)


def signals(s: Session, company_id: int, *, selected_only: bool = False) -> list[CompanySignal]:
    rows = s.exec(select(CompanySignal).where(CompanySignal.company_id == company_id,
                                              col(CompanySignal.dismissed).is_(False))
                  .order_by(col(CompanySignal.id))).all()
    rows = [r for r in rows if r.verified]
    return [r for r in rows if r.selected] if selected_only else rows


def last_run(s: Session, company_id: int) -> ResearchRun | None:
    return s.exec(select(ResearchRun).where(ResearchRun.company_id == company_id)
                  .order_by(col(ResearchRun.id).desc())).first()


def _auto_select(rows: list[CompanySignal], limit: int) -> None:
    """Up to `limit` signals, one per kind first (customer results, technical choices,
    launches…), so the email has a mix to choose from."""
    if any(r.selected for r in rows):
        return
    rank = {k: i for i, k in enumerate(KIND_PRIORITY)}
    ranked = sorted(rows, key=lambda r: (rank.get(r.kind, len(rank)), r.id or 0))
    picked: list[CompanySignal] = []
    for r in ranked:  # the first of each kind
        if len(picked) < limit and r.kind not in {p.kind for p in picked}:
            picked.append(r)
    for r in ranked:  # then fill up
        if len(picked) < limit and r not in picked:
            picked.append(r)
    for r in picked:
        r.selected = True


@dataclass
class Outcome:
    run: ResearchRun
    cached: bool
    signals: list[CompanySignal] = field(default_factory=list)


def ensure(engine: Engine, company_id: int, *, trigger: str, researcher: Researcher,
           fetcher: Fetcher | None = None, language: str = "en", force: bool = False,
           progress: Progress | None = None) -> Outcome:
    """Research the company unless its signals are fresh (then: no fetch, no model call).
    Called only by the email draft step and the Research now button."""
    progress = progress or (lambda *_: None)
    with Session(engine) as s:
        company = s.get(Company, company_id)
        if company is None:
            raise ResearchError("Company not found")
        if not force and is_fresh(s, company):
            run = ResearchRun(company_id=company_id, trigger=trigger, status="cached",
                              finished_at=utcnow(),
                              signals_kept=len(signals(s, company_id)))
            s.add(run)
            s.commit()
            s.refresh(run)
            return Outcome(run, True, signals(s, company_id))
    if not _one_at_a_time.acquire(blocking=False):
        raise ResearchError("Another company is being researched; one at a time")
    try:
        return _run(engine, company_id, trigger, researcher, fetcher or WebFetcher(), language,
                    progress)
    finally:
        _one_at_a_time.release()


def _run(engine: Engine, company_id: int, trigger: str, researcher: Researcher,
         fetcher: Fetcher, language: str, progress: Progress) -> Outcome:
    with Session(engine) as s:
        company = s.get(Company, company_id)
        home = company_site(s, company)
        name = company.name
        cfg = research_settings(s)
        run = ResearchRun(company_id=company_id, trigger=trigger)
        s.add(run)
        s.commit()
        s.refresh(run)
        run_id = run.id
    calls: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        if home is None:
            raise ResearchError(f"No website known for {name}: add it on the company (or a "
                                "contact with a work email)")
        progress("fetching", 0, int(cfg["max_pages"]))
        sources, w = fetcher.site(home, int(cfg["max_pages"]), progress)
        warnings += w
        news, w = fetcher.news(name, urlsplit(home).netloc.removeprefix("www."), language,
                               cfg["news"])
        sources += news
        warnings += w
        parts = chunks(sources)
        raw: list[RawSignal] = []
        for i, part in enumerate(parts, 1):
            progress("extracting", i, len(parts))
            raw += researcher.extract(name, part, calls.append)
        kept, dropped = [], []
        seen = set()
        for r in raw:
            reason = verify(r, sources)
            key = _norm(r.fact)
            if reason is None and key in seen:
                reason = "duplicate"
            (dropped if reason else kept).append((r, reason))
            seen.add(key)
        with Session(engine) as s:
            for old in s.exec(select(CompanyPage).where(CompanyPage.company_id == company_id)):
                s.delete(old)
            for old in s.exec(select(CompanySignal).where(
                    CompanySignal.company_id == company_id,
                    CompanySignal.origin == "research")).all():
                s.delete(old)
            for src in sources:
                s.add(CompanyPage(company_id=company_id, research_run_id=run_id, url=src.url,
                                  kind="news" if src.kind == "press" else "page",
                                  title=src.title, text=src.text, page_date=src.page_date))
            dated = {src.url: src.page_date for src in sources}
            rows = [CompanySignal(company_id=company_id, research_run_id=run_id,
                                  kind=r.kind if r.kind in KIND_PRIORITY else "other",
                                  fact=r.fact.strip(), quote=r.quote.strip(),
                                  source_url=r.source_url, page_date=dated.get(r.source_url),
                                  verified=True) for r, _ in kept]
            s.add_all(rows)
            s.flush()
            manual = [x for x in signals(s, company_id) if x.origin == "manual"]
            _auto_select([*rows, *manual], int(cfg.get("max_selected") or 3))
            run = s.get(ResearchRun, run_id)
            run.status, run.finished_at = "done", utcnow()
            run.pages, run.signals_kept, run.signals_dropped = len(sources), len(rows), \
                len(dropped)
            run.calls, run.warnings = calls, warnings + [
                f"Dropped “{r.fact[:80]}”: {why}" for r, why in dropped]
            company = s.get(Company, company_id)
            if rows:  # nothing verified: the next draft step researches again
                company.research_refreshed_at = utcnow()
            s.add_all([run, company, *rows])
            s.commit()
            s.refresh(run)
            return Outcome(run, False, signals(s, company_id))
    except Exception as exc:
        with Session(engine) as s:
            run = s.get(ResearchRun, run_id)
            run.status, run.finished_at, run.error = "failed", utcnow(), str(exc)[:500]
            run.calls, run.warnings = calls, warnings
            s.add(run)
            s.commit()
        raise


def add_manual(s: Session, company_id: int, fact: str, source_url: str = "",
               kind: str = "other") -> CompanySignal:
    """Your own signal: treated as verified (you're the source) and selected."""
    fact = fact.strip()
    if len(fact) < 8:
        raise ResearchError("Write the fact in a sentence")
    row = CompanySignal(company_id=company_id, kind=kind if kind in KIND_PRIORITY else "other",
                        fact=fact, quote=fact, source_url=source_url.strip(), origin="manual",
                        verified=True, selected=True)
    s.add(row)
    s.commit()
    s.refresh(row)
    return row
