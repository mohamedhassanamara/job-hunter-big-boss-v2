"""Every domain known for a company, and whether each one receives email (Phase 12c).

`company.domain` is the website's; `company.email_domain` is the one mail and provider lookups
use when it differs (sekoia.com vs sekoia.io). `company.domains` is the registry:
{domain: {source, mx, checked_at, note}}, filled from PDL duplicates, the listing, the apply
link, the website's contact page, verified emails and you. MX answers are cached for 30 days.

No credit is ever spent here: DNS lookups and, when a fetcher is given, one polite request to the
company's own website. Guessed variants (the same name under another ending) are only ever
OFFERED to you, never used on their own.
"""

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from app.models import Company
from app.models.base import utcnow
from app.services import dns_check

MX_TTL_DAYS = 30
VARIANT_TLDS = ("com", "io", "co", "fr", "de", "eu", "net", "ai", "org", "app", "tech", "dev",
                "group")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


def clean_domain(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    v = value.strip().lower()
    host = urlsplit(v if "//" in v else f"//{v}").netloc or v
    host = host.split("@")[-1].split(":")[0]
    host = re.sub(r"^www\.", "", host)
    return host if "." in host and " " not in host else None


def _entry(company: Company, domain: str) -> dict[str, Any] | None:
    return (company.domains or {}).get(domain)


def register(company: Company, domain: str | None, source: str, note: str = "") -> str | None:
    """Remember a domain (first source wins; a note can be added later)."""
    d = clean_domain(domain)
    if not d:
        return None
    known = dict(company.domains or {})
    if d not in known:
        known[d] = {"source": source, "mx": None, "checked_at": None, "note": note}
        company.domains = known
    return d


def mx(company: Company, domain: str, lookup: dns_check.Lookup | None = None,
       now: datetime | None = None, force: bool = False) -> bool | None:
    """True / False / None (unknown), from the cache when it is under 30 days old."""
    now = now or utcnow()
    entry = _entry(company, domain) or {}
    at = entry.get("checked_at")
    if not force and entry.get("mx") is not None and at and \
            datetime.fromisoformat(at) > now - timedelta(days=MX_TTL_DAYS):
        return bool(entry["mx"])
    found = dns_check.has_mx(domain, lookup)
    register(company, domain, "lookup")
    known = dict(company.domains or {})
    known[domain] = {**known[domain], "mx": found, "checked_at": now.isoformat()
                     if found is not None else None}
    company.domains = known
    return found


def lookup_domain(company: Company) -> str | None:
    """The domain mail and provider lookups use: the email domain when known."""
    return company.email_domain or company.domain


def variants(domain: str) -> list[str]:
    """The same name under other common endings (sekoia.com -> sekoia.io…): guesses to offer."""
    labels = domain.split(".")
    if len(labels) < 2:
        return []
    name = labels[-2] if labels[-2] not in {"co", "com", "org", "net"} or len(labels) < 3 \
        else labels[-3]
    return [f"{name}.{tld}" for tld in VARIANT_TLDS if f"{name}.{tld}" != domain]


def known(company: Company) -> list[str]:
    """Registered domains, the email domain and the website's first."""
    order = [company.email_domain, company.domain, *(company.domains or {})]
    seen: list[str] = []
    for d in order:
        if d and d not in seen:
            seen.append(d)
    return seen


def alternatives(company: Company, current: str, lookup: dns_check.Lookup | None = None, *,
                 guess: bool = False, skip: set[str] | None = None) -> list[dict[str, Any]]:
    """Other domains that RECEIVE EMAIL (MX confirmed), registered ones first; with `guess`,
    the name's other endings too. Each: {domain, source, mx}."""
    skip = {current, *(skip or set())}
    out: list[dict[str, Any]] = []
    for d in known(company):
        if d not in skip and mx(company, d, lookup) is True:
            out.append({"domain": d, "source": (_entry(company, d) or {}).get("source", "known"),
                        "mx": True})
    if guess:
        guesses = [d for d in variants(current) if d not in skip
                   and d not in {o["domain"] for o in out}]
        with ThreadPoolExecutor(max_workers=8) as pool:
            found = list(pool.map(lambda d: dns_check.has_mx(d, lookup), guesses))
        for d, ok in zip(guesses, found, strict=True):
            if ok:
                register(company, d, "guess", "same name, another ending")
                known_entry = dict(company.domains)
                known_entry[d] = {**known_entry[d], "mx": True, "checked_at": utcnow().isoformat()}
                company.domains = known_entry
                out.append({"domain": d, "source": "guess", "mx": True})
    return out


def site_domains(website: str | None, fetch: Callable[[str], str | None] | None) -> list[str]:
    """Domains of the email addresses the company's own site shows (home and contact page):
    the usual place a different mail domain gives itself away. Free email providers dropped."""
    host = clean_domain(website)
    if not host or fetch is None:
        return []
    from app.services.research import FREEMAIL

    found: list[str] = []
    for path in ("", "/contact", "/contact-us", "/contactez-nous"):
        text = fetch(f"https://{host}{path}")
        for m in _EMAIL.finditer(text or ""):
            d = m.group(1).lower().rstrip(".")
            if d not in FREEMAIL and not d.endswith((".png", ".jpg", ".svg", ".webp")) \
                    and d not in found:
                found.append(d)
    return found
