"""Interprets what the browser extension read from a LinkedIn page the user is viewing
(docs/LINKEDIN_EXTENSION_DESIGN.md §2.8). The extension is a thin extractor: it slices the page into
regions of text lines and link shapes; EVERYTHING that reads those lines lives here, where it can be
tested against recorded text. Pure functions, no request to LinkedIn, no storage: the raw lines are
used for the parse and then dropped (only the parsed fields are saved).

English page text only (decided)."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.services import linkedin

# --------------------------------------------------------------------------------- shared

_DEGREE = re.compile(r"^(?:·\s*)?(1st|2nd|3rd\+?)$", re.I)
_DEGREE_IN = re.compile(r"(?:^|·\s*)(1st|2nd|3rd)\+?\s*$", re.I)  # alone, or ending the name line
_PRONOUN = re.compile(r"^\(.{1,20}/.{1,20}\)$")
_BADGE = {"hiring", "open to work", "premium", "verified", "pending", "following"}
_BUTTON = {"message", "connect", "follow", "more", "save", "apply", "easy apply", "show all",
           "show more", "see more", "show less", "contact info", "send profile in a message"}
_SKIP = {"·", "•"}


def _lines(region: dict[str, Any] | None) -> list[str]:
    return [" ".join(str(x).split()) for x in (region or {}).get("lines", []) if str(x).strip()]


def _links(payload: dict[str, Any], kind: str, region: str | None = None) -> list[dict[str, Any]]:
    return [x for x in payload.get("links", []) if x.get("kind") == kind
            and (region is None or x.get("region") == region)]


def _noise(line: str) -> bool:
    low = line.lower().strip()
    return (low in _SKIP or low in _BUTTON or low in _BADGE or bool(_DEGREE.match(line))
            or bool(_PRONOUN.match(line)))


# ------------------------------------------------------------------------------------- job

# Lines after the description that belong to the page, not to the listing.
_JOB_STOP = {"about the company", "set alert for similar jobs", "show premium insights",
             "company photos", "people you can reach out to", "meet the hiring team",
             "similar jobs", "people also viewed", "jobs you may be interested in",
             "job search faster with premium", "premium insights"}
_TIME_OR_UI = re.compile(
    r"\b(ago|applicants?|applied|reposted|promoted|easy apply|actively (?:reviewing|hiring)|"
    r"clicked apply|be an early applicant|over \d+|people)\b", re.I)
_WORKPLACE = re.compile(r"\b(remote|hybrid|on-?site)\b", re.I)
_CHIP = re.compile(r"^(?:remote|hybrid|on-?site)$", re.I)


def _description(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        if line.lower().strip(" :") in _JOB_STOP:
            break
        out.append(line)
    return "\n".join(out)


def _location_and_workplace(header: list[str], title: str, company: str) -> tuple[str, str]:
    """The top card's "Location · 2 weeks ago · 15 applicants" (one line, or split on a lone "·"),
    and a Remote/Hybrid/On-site chip or a "(Hybrid)" suffix."""
    workplace = ""
    location = ""
    rows = [h for h in header if h.lower() != title.lower() and h.lower() != company.lower()]
    for i, line in enumerate(rows):
        if _CHIP.match(line) and not workplace:
            workplace = line.strip().title().replace("Onsite", "On-site")
        if location:
            continue
        candidate = ""
        if " · " in line:
            candidate = line.split(" · ")[0]
        elif line == "·" and i > 0:
            candidate = rows[i - 1]
        if candidate and not _TIME_OR_UI.search(candidate) and not _noise(candidate) \
                and candidate.lower() not in (title.lower(), company.lower()):
            location = candidate
    if not location:  # a plain "City, Country" line right after the title / company lines
        for line in rows[:6]:
            plain = re.match(r"^[^\d·|]{2,60},\s*[^\d·|]{2,60}$", line)
            if plain and not _TIME_OR_UI.search(line) and not _noise(line) \
                    and "match" not in line.lower():
                location = line
                break
    if m := re.search(r"\((remote|hybrid|on-?site)\)\s*$", location, re.I):
        workplace = workplace or m.group(1).title()
        location = location[:m.start()].strip()
    if not workplace:
        for line in rows:
            m = _WORKPLACE.search(line)
            if m and len(line) < 40 and not line.lower().startswith(("job match", "your profile")):
                workplace = m.group(1).title()
                break
    return location.strip(), workplace.replace("Onsite", "On-site")


def _poster(payload: dict[str, Any]) -> dict[str, str] | None:
    team = _lines(payload.get("team"))
    people = [x for x in _links(payload, "person", "team") if x.get("href")]
    if not team or not people:
        return None
    name = next((line for line in team if not _noise(line) and line.lower() != "job poster"), "")
    if not name:
        return None
    at = team.index(name)
    title = next((line for line in team[at + 1:] if not _noise(line)
                  and line.lower() not in ("job poster", name.lower())), "")
    return {"name": name, "title": title, "url": str(people[0]["href"])}


def parse_job(payload: dict[str, Any]) -> dict[str, Any]:
    """The extension's job payload -> the fields `linkedin.validate` takes."""
    title = str(payload.get("title_parsed") or "").strip()
    company = str(payload.get("company_parsed") or "").strip()
    header = _lines(payload.get("header"))
    location, workplace = _location_and_workplace(header, title, company)
    company_href = next((x.get("href") for x in _links(payload, "company")
                         if x.get("href") and x.get("text", "").strip().lower() == company.lower()),
                        None) or next((x.get("href") for x in _links(payload, "company")
                                       if x.get("href")), None)
    sources = {"title": "title", "company": "title", "description": "page",
               "location": "page" if location else "missing",
               "workplace": "page" if workplace else "missing"}
    return {"url": payload.get("url") or "", "job_id": payload.get("job_id") or None,
            "title": title, "company": company, "company_url": company_href,
            "location": location, "workplace": workplace,
            "description": _description(_lines(payload.get("about"))),
            "poster": _poster(payload), "sources": sources}


# ------------------------------------------------------------------------------- profile

_DATES = re.compile(r"((?:[A-Z][a-z]{2,8} )?(?:19|20)\d{2})\s*[-–]\s*"
                    r"((?:[A-Z][a-z]{2,8} )?(?:(?:19|20)\d{2})|Present)", re.I)
_EMPLOYMENT = re.compile(r"^(.*?)\s·\s(?:Full-time|Part-time|Contract|Freelance|Internship|"
                         r"Self-employed|Apprenticeship|Seasonal|Temporary)\b", re.I)
_AT = re.compile(r"^(?P<title>.+?)\s+(?:at|@|chez)\s+(?P<company>.+?)(?:\s*[|·].*)?$", re.I)


@dataclass
class ProfileFields:
    name: str
    public_id: str
    url: str
    degree: int | None = None
    headline: str = ""
    location: str = ""
    current_title: str = ""
    current_company: str = ""
    company_url: str | None = None
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    about: str = ""
    badges: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)


def _region(payload: dict[str, Any], label: str) -> list[str]:
    for r in payload.get("regions", []):
        if r.get("label") == label:
            return _lines(r)
    return []


def _top(lines: list[str], name: str) -> tuple[int | None, str, str, list[str]]:
    """(degree, headline, location, badges) from the top card lines."""
    start = next((i for i, line in enumerate(lines) if line.lower().startswith(name.lower())), 0)
    rest = lines[start + 1:]
    degree = next((int(m.group(1)[0]) for line in [lines[start], *rest]
                   if (m := _DEGREE_IN.search(line))), None)
    badges = [line for line in rest if line.lower() in _BADGE]
    plain = [line for line in rest if not _noise(line)]
    headline = plain[0] if plain else ""
    location = ""
    contact = next((i for i, line in enumerate(rest) if line.lower() == "contact info"), None)
    if contact is not None:  # the line just before the "· Contact info" pair is the location
        before = [line for line in rest[:contact] if not _noise(line)]
        if len(before) >= 2:
            location = before[-1]
    return degree, headline, location, badges


def _experience(lines: list[str]) -> list[dict[str, Any]]:
    """One entry per dated line: the line above it is the role (or "Company · Full-time", then the
    line above that is the role). A grouped company keeps the role lines it lists."""
    out: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        m = _DATES.search(line)
        if not m or i == 0 or len(line) > 90:
            continue
        above, above2 = lines[i - 1], (lines[i - 2] if i >= 2 else "")
        title, company = above, ""
        if e := _EMPLOYMENT.match(above):
            company, title = e.group(1).strip(), above2
        elif above2 and not re.search(r"\d", above2) and len(above) <= 70:
            company, title = above, above2  # "Title / Company / dates"
        out.append({"title": title, "company": company, "start": m.group(1),
                    "end": m.group(2), "current": m.group(2).lower() == "present"})
    return out[:8]


def _education(lines: list[str], schools: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for school in dict.fromkeys(s for s in schools if s):
        at = next((i for i, line in enumerate(lines) if line == school), None)
        if at is None:
            out.append({"school": school, "detail": "", "dates": ""})
            continue
        nxt = [x for x in lines[at + 1:at + 4] if not _noise(x)]
        dates = next((x for x in nxt if _DATES.search(x) or re.fullmatch(r"(?:19|20)\d{2}", x)),
                     "")
        detail = next((x for x in nxt if x != dates and x not in schools), "")
        out.append({"school": school, "detail": detail[:140], "dates": dates})
    return out[:5]


def parse_profile(payload: dict[str, Any]) -> ProfileFields:
    name = str(payload.get("name_parsed") or "").strip()
    slug = str(payload.get("slug") or "")
    url = linkedin.profile_url(str(payload.get("url") or "")) or ""
    top = _region(payload, "top")
    degree, headline, location, badges = _top(top, name)
    exp_lines = _region(payload, "experience")
    experience = _experience(exp_lines)
    first = next((e for e in experience if e["current"]), experience[0] if experience else None)
    title = (first or {}).get("title", "")
    company = (first or {}).get("company", "")
    company_url = None
    exp_links = [x for x in _links(payload, "company", "experience") if x.get("text", "").strip()]
    if exp_links:
        company = company or str(exp_links[0]["text"]).strip()
        company_url = linkedin.company_url(str(exp_links[0].get("href") or "")) or None
    sources = {"name": "title", "headline": "page" if headline else "missing"}
    if not company and headline and (m := _AT.match(headline)):
        title, company = title or m.group("title"), m.group("company")
        sources["company"] = "headline"
    elif company:
        sources["company"] = "experience"
    else:
        sources["company"] = "missing"
    schools = [str(x.get("text", "")).strip() for x in _links(payload, "school", "education")
               if str(x.get("text", "")).strip()]
    about = " ".join(_region(payload, "about"))[:1500]
    return ProfileFields(
        name=name, public_id=slug, url=url, degree=degree, headline=headline, location=location,
        current_title=title or headline, current_company=company, company_url=company_url,
        experience=experience, education=_education(_region(payload, "education"), schools),
        about=about, badges=badges, sources=sources)


def is_alum(education: list[dict[str, Any]], school_short: str | None,
            school_full: str | None) -> bool:
    """Did they study where you did (your pool's school, by its short or full name)?"""
    wanted = {w.lower() for w in (school_short, school_full) if w}
    if not wanted:
        return False
    for e in education:
        text = f"{e.get('school', '')} {e.get('detail', '')}".lower()
        if any(w in text or (len(e.get("school", "")) > 4 and e["school"].lower() in w)
               for w in wanted):
            return True
    return False
