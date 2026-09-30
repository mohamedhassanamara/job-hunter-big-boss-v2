"""Recent news about a company, from two free sources without keys: the GDELT DOC 2.0 API and
the Google News RSS search feed. Pure parsers (tested on fixtures) plus a small fetcher. Only
titles, links, dates and the feed's own snippet are kept; articles are never scraped here."""

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree

from app.providers.http import PoliteClient, SourceError

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"


@dataclass
class NewsItem:
    title: str
    url: str
    source: str  # gdelt | google_news
    published: datetime | None = None
    snippet: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}. {self.snippet}".strip(" .")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def parse_gdelt(payload: str | dict) -> list[NewsItem]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    out = []
    for a in (data or {}).get("articles") or []:
        seen = a.get("seendate") or ""
        try:
            published = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            published = None
        if a.get("url") and a.get("title"):
            out.append(NewsItem(title=_clean(a["title"]), url=a["url"], source="gdelt",
                                published=published))
    return out


def parse_google_news(xml_text: str) -> list[NewsItem]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = _clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            published = None
        snippet = _clean(item.findtext("description") or "")
        if snippet.startswith(title):
            snippet = snippet[len(title):].strip(" -–")
        if title and link:
            out.append(NewsItem(title=title, url=link, source="google_news",
                                published=published, snippet=snippet))
    return out


def fetch_news(name: str, domain: str | None, *, language: str = "en", gdelt: bool = True,
               google_news: bool = True, limit: int = 10, context: str = "",
               client: PoliteClient | None = None) -> tuple[list[NewsItem], list[str]]:
    """(items from the last 12 months, warnings). A failing source is a warning, not an error.
    `context` narrows the search (e.g. the company name next to a person's quoted name)."""
    own = client is None
    client = client or PoliteClient("News", min_interval=1.0, retries=1,
                                    headers={"Accept": "*/*"})
    since = datetime.now(UTC) - timedelta(days=365)
    items, warnings = [], []
    query = f'"{name}" {context}'.strip()
    try:
        if gdelt:
            # GDELT asks for at most one request every 5 seconds: its own spaced client.
            spaced = PoliteClient("GDELT", min_interval=6.0, retries=1, backoff=6.0,
                                  headers={"Accept": "application/json"})
            try:
                res = spaced.request("GET", GDELT_URL, params={
                    "query": query, "mode": "ArtList", "format": "json", "maxrecords": limit,
                    "startdatetime": since.strftime("%Y%m%d%H%M%S"), "sort": "DateDesc"})
                items += parse_gdelt(res.text or "{}")[:limit]
            except (SourceError, ValueError) as exc:
                warnings.append(f"GDELT: {exc}")
            finally:
                spaced.close()
        if google_news:
            hl = "fr" if language == "fr" else "en"
            gl = "FR" if language == "fr" else "US"
            url = (f"{GOOGLE_NEWS_URL}?q={quote_plus(query + ' when:365d')}&hl={hl}&gl={gl}"
                   f"&ceid={gl}:{hl}")
            try:
                items += parse_google_news(client.request("GET", url).text)[:limit]
            except SourceError as exc:
                warnings.append(f"Google News: {exc}")
    finally:
        if own:
            client.close()
    from app.services.fit import _norm

    key = _norm(name)  # accents folded: "Stephane Fontana" finds "Stéphane Fontana"
    fresh = [i for i in items if key in _norm(i.text)
             and (i.published is None or i.published >= since)]
    seen, unique = set(), []
    for i in fresh:
        k = re.sub(r"\W+", " ", i.title.lower()).strip()
        if k not in seen:
            seen.add(k)
            unique.append(i)
    return unique, warnings
