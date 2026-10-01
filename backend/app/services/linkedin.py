"""LinkedIn as its own channel: daily job-search links, and importing the one job page you
capture with the bookmark (Phase 10).

The app never talks to LinkedIn: no request to linkedin.com is ever made from here
(tests/test_linkedin.py checks the source). Links are built in code; a capture comes from your
browser (the bookmarklet reads the page you're viewing and opens the local import window with
it). Every field says how it was found, and empty required fields are never saved silently.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import quote, urlsplit

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models import Application, Company, Contact, Job, LinkedInLinkOpen, LinkedInOutreach
from app.models.enums import ContactSource, LinkedInGroup, RemoteType, Source
from app.providers.base import RawJob
from app.services.contacts import local_midnight

DEFAULT_LINKEDIN: dict[str, Any] = {
    "note_max_chars": 200,  # a free account's connection note limit (Premium: 300)
    "daily_requests": 10,  # connection requests you send per day (a warning, never a block)
    "followup_days": 5,  # no answer after this many days: a reminder
    "gap_days": 3,  # never an email and a LinkedIn request to the same person within this
    # LinkedIn's location id per target country (a text location can resolve to the wrong place:
    # "Jordan" → Jordan, Pennsylvania). Seeded unverified; you confirm each in Settings → LinkedIn.
    "geo_ids": {code: {"id": gid, "verified": False} for code, gid in {
        "FR": "105015875", "DE": "101282230", "ES": "105646813", "IT": "103350119",
        "PT": "100364837", "BE": "100565514", "AE": "104305776", "QA": "104170880",
        "JO": "103710677", "BH": "100425729", "KW": "103239229"}.items()},
}
JOBS_SEARCH = "https://www.linkedin.com/jobs/search/"
PAST_24H = "r86400"
REQUIRED = ("title", "company", "description")
MIN_DESCRIPTION = 200
# A login or bot wall instead of the listing (adapted from jobhunt-posting's wall check).
_WALL = re.compile(r"\b(?:sign in to (?:view|continue|see)|join (?:now )?to see|verify you are "
                   r"(?:a )?human|unusual activity|captcha|s'identifier pour|connectez-vous)\b",
                   re.I)


def linkedin_settings(s: Session) -> dict[str, Any]:
    from app.models import AppSetting

    row = s.exec(select(AppSetting).where(AppSetting.key == "linkedin")).first()
    return {**DEFAULT_LINKEDIN, **(row.value if row else {})}


# ------------------------------------------------------------------------------- search links


@dataclass
class SearchLink:
    key: str
    role: str
    country: str  # ISO code
    country_name: str
    geo_id: str
    verified: bool  # you confirmed this country's geoId (Settings → LinkedIn)
    url: str
    opened_today: bool = False


@dataclass
class LinkGroup:
    track: str
    role: str
    links: list[SearchLink] = field(default_factory=list)


@dataclass
class Links:
    groups: list[LinkGroup]
    # Target countries without a geoId: no link at all (never a text-location fallback).
    missing_geo: list[dict[str, str]]


def link_key(role: str, country: str, remote: bool, easy: bool) -> str:
    return f"{role.strip().lower()}|{country.lower()}|{'r' if remote else ''}{'e' if easy else ''}"


def search_url(role: str, geo_id: str, *, remote: bool = False, easy: bool = False) -> str:
    """One LinkedIn job search: this role in this country (LinkedIn's geoId, never a text
    location), posted in the past 24 hours, newest first; optionally remote only (f_WT=2) and
    Easy Apply only (f_AL=true)."""
    params = [("keywords", role), ("geoId", geo_id), ("f_TPR", PAST_24H), ("sortBy", "DD")]
    if remote:
        params.append(("f_WT", "2"))
    if easy:
        params.append(("f_AL", "true"))
    return JOBS_SEARCH + "?" + "&".join(f"{k}={quote(v, safe='')}" for k, v in params)


def geo_ids(s: Session) -> dict[str, dict[str, Any]]:
    """{ISO code: {id, verified}} (Settings → LinkedIn); a code without an id has no links."""
    return {code.upper(): v for code, v in (linkedin_settings(s).get("geo_ids") or {}).items()
            if isinstance(v, dict) and str(v.get("id") or "").strip()}


def search_links(s: Session, *, remote: bool = False, easy: bool = False,
                 today: date | None = None) -> Links:
    """One link per role × target country (Settings → Search profile) that has a geoId,
    grouped by role. Countries without one are listed apart, with no link."""
    from app.services.discovery import active_profile
    from app.services.geo import country_catalog

    _, profile = active_profile(s)
    names = {c["code"]: c["name"] for c in country_catalog()}
    geos = geo_ids(s)
    day = today or local_midnight().date()
    opened = set(s.exec(select(LinkedInLinkOpen.key).where(LinkedInLinkOpen.day == day)).all())
    missing = [{"code": c.upper(), "name": names.get(c.upper(), c)} for c in profile.locations
               if c.upper() not in geos]
    groups = []
    for track in profile.tracks:
        for role in track.get("roles") or []:
            title = (role.get("title") or "").strip()
            if not title:
                continue
            group = LinkGroup(track=track.get("name") or "", role=title)
            for code in profile.locations:
                geo = geos.get(code.upper())
                if geo is None:
                    continue
                key = link_key(title, code, remote, easy)
                gid = str(geo["id"]).strip()
                group.links.append(SearchLink(
                    key, title, code.upper(), names.get(code.upper(), code), gid,
                    bool(geo.get("verified")),
                    search_url(title, gid, remote=remote, easy=easy), key in opened))
            groups.append(group)
    return Links(groups, missing)


def mark_opened(s: Session, key: str, today: date | None = None) -> None:
    day = today or local_midnight().date()
    if s.exec(select(LinkedInLinkOpen).where(LinkedInLinkOpen.key == key,
                                             LinkedInLinkOpen.day == day)).first() is None:
        s.add(LinkedInLinkOpen(key=key, day=day))


# ------------------------------------------------------------------------------------ capture


class CaptureError(ValueError):
    pass


def job_id_from(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"/jobs/view/(?:[^/?#]*?-)?(\d{6,})", url) or \
        re.search(r"[?&](?:currentJobId|jobId)=(\d{6,})", url)
    return m.group(1) if m else None


def job_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def company_url(url: str | None) -> str | None:
    """https://www.linkedin.com/company/<slug>/ (the people search needs the slug)."""
    m = re.search(r"linkedin\.com/company/([^/?#]+)", url or "")
    return f"https://www.linkedin.com/company/{m.group(1)}/" if m else None


def company_slug(url: str | None) -> str | None:
    m = re.search(r"linkedin\.com/company/([^/?#]+)", url or "")
    return m.group(1) if m else None


def profile_url(url: str | None) -> str | None:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    return f"https://www.linkedin.com/in/{m.group(1)}/" if m else None


def remote_type(workplace: str | None, location: str | None) -> RemoteType:
    text = f"{workplace or ''} {location or ''}".lower()
    if re.search(r"\bremote\b|télétravail|à distance|remoto", text):
        return RemoteType.remote
    if re.search(r"\bhybrid|hybride|híbrido|ibrido", text):
        return RemoteType.hybrid
    if re.search(r"on-?site|sur site|presencial|présentiel", text):
        return RemoteType.onsite
    return RemoteType.unknown


def _clean(text: Any) -> str:
    return re.sub(r"[ \t ]+", " ", str(text or "")).strip()


def clean_description(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text or "")
    text = re.sub(r"[ \t ]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # LinkedIn's own controls that come along with innerText.
    text = re.sub(r"\n?(?:…\s*)?(?:show more|show less|voir plus|voir moins)\s*$", "", text,
                  flags=re.I)
    return text.strip()


@dataclass
class Capture:
    url: str
    job_id: str | None
    title: str
    company: str
    company_url: str | None
    location: str
    workplace: str
    description: str
    poster: dict[str, str] | None
    sources: dict[str, str]  # field → how found: json-ld, page, meta, url, you or missing
    missing: list[str]
    warnings: list[str]


def validate(payload: dict[str, Any]) -> Capture:
    """The bookmarklet's (or the paste box's) data, checked: what's missing, what looks wrong.
    Raises CaptureError only when nothing usable came."""
    sources = dict(payload.get("sources") or {})
    url = _clean(payload.get("url"))
    jid = _clean(payload.get("job_id")) or job_id_from(url)
    if jid and not sources.get("job_id"):
        sources["job_id"] = "url"
    title, company = _clean(payload.get("title")), _clean(payload.get("company"))
    description = clean_description(str(payload.get("description") or ""))
    location, workplace = _clean(payload.get("location")), _clean(payload.get("workplace"))
    poster = payload.get("poster") or None
    if poster:
        poster = {"name": _clean(poster.get("name")), "title": _clean(poster.get("title")),
                  "url": profile_url(poster.get("url")) or ""}
        if not poster["name"]:
            poster = None
    values = {"title": title, "company": company, "description": description,
              "location": location, "workplace": workplace, "job_id": jid or ""}
    for k, v in values.items():
        if not v:
            sources[k] = "missing"
    missing = [k for k in REQUIRED if not values[k]]
    warnings = []
    if description and len(description) < MIN_DESCRIPTION:
        warnings.append(f"The description is short ({len(description)} characters): open the full "
                        "listing (\"See more\") and capture again, or paste it")
    if _WALL.search(description[:2000]) and len(description) < 1600:
        warnings.append("This looks like a sign-in wall, not the listing: sign in to LinkedIn, "
                        "open the job, then capture again")
    if not jid:
        warnings.append("No LinkedIn job id found in the URL: the job is saved with its URL only")
    if not (title or company or description):
        raise CaptureError("Nothing was captured: open a LinkedIn job page and click the "
                           "bookmark there, or paste the listing below")
    return Capture(url=job_url(jid) if jid else url, job_id=jid, title=title, company=company,
                   company_url=company_url(payload.get("company_url")), location=location,
                   workplace=workplace, description=description, poster=poster, sources=sources,
                   missing=missing, warnings=warnings)


def from_paste(url: str, text: str) -> dict[str, Any]:
    """The fallback: a pasted URL and listing text. The first lines usually hold the title and
    the company; you check them in the import window."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    title = lines[0] if lines else ""
    company = lines[1] if len(lines) > 1 and len(lines[1]) < 80 else ""
    location = lines[2] if len(lines) > 2 and len(lines[2]) < 80 and "," in lines[2] else ""
    return {"url": url, "title": title, "company": company, "location": location,
            "description": text, "sources": {"title": "you", "company": "you",
                                             "location": "you", "description": "you"}}


# ------------------------------------------------------------------------------------- import


@dataclass
class ImportResult:
    job_id: int
    application_id: int
    created: bool
    duplicate_of: dict[str, Any] | None
    matched_track: str | None
    warnings: list[str]
    scoring: str  # queued | already scored | blocked: …


def _external_id(c: Capture) -> str:
    return c.job_id or "url-" + hashlib.sha1(c.url.encode()).hexdigest()[:16]


def import_job(engine: Engine, c: Capture, *, workspace: str = "real") -> ImportResult:
    """Save one captured LinkedIn job: deduped against every source, its track matched, its
    contacts resolved, and only this job queued for scoring (same scorer and rules)."""
    from app.services import contacts as contacts_svc
    from app.services.discovery import active_profile
    from app.services.geo import country_from_text
    from app.services.ingest import ingest
    from app.services.roles import match_track
    from app.services.scoring import workspace_queue

    if c.missing:
        raise CaptureError("Fill in " + ", ".join(c.missing) + " before saving")
    warnings = list(c.warnings)
    with Session(engine) as s:
        profile_id, profile = active_profile(s)
        matched = match_track(c.title, profile.tracks)
        if matched is None:
            warnings.append("The title matches none of your roles (Settings → Search profile): "
                            "it's saved without a track")
        country = country_from_text(c.location)
        if c.location and country and profile.locations and \
                country.upper() not in {x.upper() for x in profile.locations}:
            warnings.append(f"{c.location} is outside your target countries")
        raw = RawJob(source=Source.linkedin, external_id=_external_id(c), url=c.url,
                     title=c.title, company=c.company, location=c.location, country=country,
                     remote_type=remote_type(c.workplace, c.location), description=c.description,
                     matched_track=matched[0] if matched else None,
                     matched_role=matched[1] if matched else None)
        stats = ingest(s, [raw], source_run_id=None, profile_id=profile_id)
        job = s.exec(select(Job).where(Job.source == Source.linkedin,
                                       Job.external_id == raw.external_id)).one()
        created = stats.new + stats.duplicates > 0
        if not created:  # captured again: refresh what the page now shows
            job.title, job.location, job.description = c.title, c.location, c.description
            job.remote_type = raw.remote_type
            if matched:
                job.matched_track, job.matched_role = matched
        job.linkedin_job_id, job.capture = c.job_id, {**c.sources, "warnings": warnings}
        s.add(job)
        company = s.get(Company, job.company_id)
        if c.company_url and not company.linkedin_url:
            company.linkedin_url = c.company_url
            s.add(company)
        app = s.exec(select(Application).where(Application.job_id == job.id)).one()
        if c.poster:
            add_person(s, app, full_name=c.poster["name"], title=c.poster.get("title"),
                       linkedin_url=c.poster.get("url"), group=LinkedInGroup.hiring_team)
        duplicate = None
        if job.duplicate_of_id:
            orig = s.get(Job, job.duplicate_of_id)
            duplicate = {"id": orig.id, "title": orig.title, "source": orig.source}
        s.commit()
        job_id, app_id, track = job.id, app.id, job.matched_track
        contacts_svc.resolve_after_discovery(engine, [job_id])
    queue = workspace_queue(workspace)
    if queue.blocked:
        scoring = f"blocked: {queue.blocked}"
    else:
        scoring = "queued" if queue.enqueue([job_id], front=True, trigger="linkedin") else \
            "already scored or queued"
    return ImportResult(job_id, app_id, created, duplicate, track, warnings, scoring)


def add_person(s: Session, app: Application, *, full_name: str, title: str | None,
               linkedin_url: str | None, group: LinkedInGroup,
               alumni: bool = False) -> LinkedInOutreach:
    """Someone to message on LinkedIn about this job: one person table across tracks (a
    contact at the company), one LinkedIn row per job. Known by their profile URL or name."""
    from app.services.contacts import normalize_person, rank, role_ranking

    job = s.get(Job, app.job_id)
    url = profile_url(linkedin_url)
    name = " ".join(full_name.split())
    if not name:
        raise CaptureError("A name is needed")
    people = s.exec(select(Contact).where(Contact.company_id == job.company_id)).all()
    contact = next((p for p in people if url and profile_url(p.linkedin_url) == url), None) or \
        next((p for p in people if p.normalized_name == normalize_person(name)), None)
    if contact is None:
        parts = name.split(" ", 1)
        contact = Contact(company_id=job.company_id, full_name=name, first_name=parts[0],
                          last_name=parts[1] if len(parts) > 1 else None,
                          normalized_name=normalize_person(name),
                          title=(title or "").strip() or None, linkedin_url=url,
                          source=ContactSource.linkedin,
                          role_rank=rank(title, role_ranking(s))[0])
        s.add(contact)
        s.flush()
    elif url and not contact.linkedin_url:
        contact.linkedin_url = url
        s.add(contact)
    row = s.exec(select(LinkedInOutreach).where(LinkedInOutreach.application_id == app.id,
                                                LinkedInOutreach.contact_id == contact.id)).first()
    if row is None:
        row = LinkedInOutreach(application_id=app.id, contact_id=contact.id, group=group,
                               alumni=alumni or group == LinkedInGroup.alumni)
        s.add(row)
        s.flush()
    return row


def host(url: str) -> str:
    return urlsplit(url).netloc


def existing(s: Session, c: Capture) -> dict[str, Any] | None:
    """Is this job already in your list? Same LinkedIn job, or the same company + title +
    country from another source (the cross-source dedupe key)."""
    from app.services.company_merge import resolve_alias
    from app.services.dedupe import dedupe_key, normalize_company
    from app.services.geo import country_from_text

    job = s.exec(select(Job).where(Job.source == Source.linkedin,
                                   Job.external_id == _external_id(c))).first()
    how = "already imported"
    if job is None and c.company and c.title:
        norm = normalize_company(c.company)
        company = s.exec(select(Company).where(Company.normalized_name == norm)).first() \
            or resolve_alias(s, norm)
        key = dedupe_key(company.name if company else c.company, c.title,
                         country_from_text(c.location))
        job = s.exec(select(Job).where(Job.dedupe_key == key)).first()
        how = "the same job from another source"
    if job is None:
        return None
    return {"id": job.id, "title": job.title, "source": job.source, "how": how}
