"""Company resolution, local and free (Phase 12): a company name -> canonical domain, LinkedIn URL
and size, before any provider is called.

1. The company's own data: the domain you entered, a previous lookup, or the website captured from
   a listing (`company.website`: a fetched full listing's hiringOrganization.sameAs).
2. People Data Labs' free company dataset, read locally with DuckDB (CC BY 4.0, quarterly):
   `data/pdl/companies.parquet`, made once from the downloaded file with
   `scripts/pdl_to_parquet.py`. Missing file = this step is skipped.
3. The listing: the work-email domain of the company's contacts, the job's apply link
   (`job.apply_url`) or its own URL when that is the company's site (never a job board or ATS;
   the host must contain the company's name).
4. Only when nothing else worked and a `fetcher` is given: one polite request to the listing page
   for its JSON-LD company website (honest User-Agent; a site that blocks us gives nothing).

Steps 1-3 make no network request.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.config import DATA_DIR
from app.models import Company, Job
from app.services import geo, research
from app.services.dedupe import _LEGAL_SUFFIXES, normalize_company

PDL_PATH = DATA_DIR / "pdl" / "companies.parquet"
# Hosts that are job boards or applicant systems, never a company's own domain.
BOARD_HOSTS = (
    "ashbyhq.", "lever.co", "greenhouse.io", "workable.com", "smartrecruiters.", "recruitee.",
    "icims.", "jobvite.", "applytojob.", "pinpointhq.", "hire.", "teamtailor.", "workday",
    "oraclecloud.", "successfactors.", "taleo.", "careerpuck.", "rippling.", "dover.",
    "linkedin.", "indeed.", "glassdoor.", "welcometothejungle.", "wttj.", "adzuna.", "bayt.",
    "greenhouse.io", "lever.co", "ashbyhq.", "workable.", "smartrecruiters.", "recruitee.",
    "personio.", "teamtailor.", "join.com", "jobs.", "free-work.", "jobgether.", "remote",
    "monster.", "stepstone.", "apec.", "hellowork.", "myworkdayjobs.", "bamboohr.", "breezy.hr",
)
SIZE_MAX = {"1-10": 10, "11-50": 50, "51-200": 200, "201-500": 500, "501-1000": 1000,
            "1001-5000": 5000, "5001-10000": 10000, "10001+": None}


@dataclass
class Resolved:
    domain: str | None
    source: str | None  # manual | pdl | listing
    linkedin_url: str | None = None
    industry: str | None = None
    employees_max: int | None = None
    note: str = ""


def name_key_sql(column: str = "name") -> str:
    """normalize_company() as a DuckDB expression (for building the Parquet file without a Python
    callback; tests/test_contact_finders.py keeps it equal to the Python rule)."""
    suffixes = ", ".join(f"'{s}'" for s in sorted(_LEGAL_SUFFIXES))
    ascii_only = (f"regexp_replace(strip_accents(replace({column}, '.', '')), "
                  "'[^\\x00-\\x7F]', '', 'g')")
    words = (f"regexp_split_to_array(trim(regexp_replace(lower({ascii_only}), "
             "'[^a-z0-9]+', ' ', 'g')), ' ')")
    return (f"coalesce(nullif(array_to_string(list_filter({words}, "
            f"w -> w <> '' AND NOT list_contains([{suffixes}], w)), ' '), ''), "
            f"lower(trim({column})))")


def clean_domain(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    v = value.strip().lower()
    host = urlsplit(v if "//" in v else f"//{v}").netloc or v
    host = host.split("@")[-1].split(":")[0]
    host = re.sub(r"^www\.", "", host)
    return host if "." in host and " " not in host else None


def pdl_lookup(name: str, countries: list[str] | None = None,
               path: Path | None = None) -> Resolved | None:
    """Best match for the company name in the local PDL file (exact name, folded). Several
    companies with the same name: the one in a country the job is in, else the largest."""
    path = path or PDL_PATH
    if not path.exists():
        return None
    import duckdb

    key = normalize_company(name)
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT name, website, linkedin_url, size, industry, country FROM read_parquet(?) "
            "WHERE name_key = ? LIMIT 25", [str(path), key]).fetchall()
    finally:
        con.close()
    rows = [r for r in rows if clean_domain(r[1])]
    if not rows:
        return None
    order = list(SIZE_MAX)

    def score(r: tuple) -> tuple[int, int]:
        in_country = int(geo.country_from_text(r[5]) in (countries or []))
        return in_country, order.index(r[3]) if r[3] in order else -1

    best = max(rows, key=score)
    ambiguous = len(rows) > 1
    return Resolved(clean_domain(best[1]), "pdl", linkedin_url=best[2], industry=best[4],
                    employees_max=SIZE_MAX.get(best[3]),
                    note=f"{len(rows)} companies named like this in PDL: picked by country/size"
                    if ambiguous else "")


_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "ltd"}


def registered_domain(host: str) -> str:
    """careers.acme.co.uk -> acme.co.uk; jobs.acme.com -> acme.com (no public-suffix list: the
    usual two-part endings are enough for a company name check)."""
    labels = host.split(".")
    keep = 3 if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2 else 2
    return ".".join(labels[-keep:])


def company_host(url: str | None, company_name: str) -> str | None:
    """The registered domain of a listing/apply URL when it is the company's own site: not a job
    board or ATS, and the host carries the company's name."""
    host = clean_domain(url)
    token = normalize_company(company_name).split(" ")[0]
    if not host or not token or any(b in host for b in BOARD_HOSTS):
        return None
    return registered_domain(host) if token in host.replace("-", "") else None


def from_listing(s: Session, company: Company) -> tuple[str | None, str]:
    """(domain, where it came from): the contacts' work-email domain, the apply link, or the
    listing's own host."""
    domains = research.company_site(s, company)  # website, domain, or the contacts' email domain
    if domains:
        return clean_domain(domains), "listing"
    for url, apply in s.exec(select(Job.url, Job.apply_url).where(Job.company_id == company.id)):
        for candidate, how in ((apply, "apply link"), (url, "listing")):
            if host := company_host(candidate, company.name):
                return host, how
    return None, ""


def resolve(s: Session, company: Company, *, domain: str | None = None,
            path: Path | None = None,
            fetcher: Callable[[str], str | None] | None = None) -> Resolved:
    """Fill the company's domain / LinkedIn / size from the cheapest source. Writes the company
    only for fields that were empty; an explicit `domain` (you typed it) always wins.
    `fetcher(listing_url)` reads the company website from the listing page (last resort)."""
    if domain and clean_domain(domain):
        company.domain, company.domain_source = clean_domain(domain), "manual"
        s.add(company)
        return Resolved(company.domain, "manual")
    if company.domain:
        return Resolved(company.domain, company.domain_source or "manual")
    if captured := clean_domain(company.website):  # the listing's own company website
        company.domain, company.domain_source = registered_domain(captured), "listing"
        s.add(company)
        return Resolved(company.domain, "listing", note="the company website from its listing")
    countries = [c for c in s.exec(select(Job.country).where(
        Job.company_id == company.id).distinct()).all() if c]
    hit = pdl_lookup(company.name, countries, path)
    if hit is None:
        site, how = from_listing(s, company)
        if site is None and fetcher is not None:
            for url in s.exec(select(Job.url).where(Job.company_id == company.id).limit(2)):
                if page_site := clean_domain(fetcher(url)):
                    site, how = registered_domain(page_site), "the listing page"
                    break
        hit = Resolved(site, "listing", note=f"from {how}") if site \
            else Resolved(None, None, note="no domain found")
    if hit.domain:
        company.domain, company.domain_source = hit.domain, hit.source
        if hit.linkedin_url and not company.linkedin_url:
            company.linkedin_url = hit.linkedin_url
        if hit.industry and not company.industry:
            company.industry = hit.industry
        if hit.employees_max and company.employees is None and company.employees_max is None:
            company.employees_max, company.size_source = hit.employees_max, "pdl"
        s.add(company)
    return hit
