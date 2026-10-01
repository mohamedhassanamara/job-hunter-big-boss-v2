"""Checks for LinkedIn messages (connection notes and follow-ups). No model calls.

The same rules as the email where they apply: grounding of numbers and tools (your pool, the
listing, the signals), years wording, banned phrases and jargon, never your location /
nationality / visa. LinkedIn only: the school may be named, for alumni only. Plus: the length
limit (a free account's note is 200 characters), no links, and a question.
"""

import re
from dataclasses import dataclass, field

from app.services import outreach_check as oc
from app.services.cv_check import violation
from app.services.cv_claims import bad_years
from app.services.cv_pool import Pool

# Openers and clichés LinkedIn messages lean on (on top of the email's banned list).
LINKEDIN_BANNED = [
    "i would love to connect", "i'd love to connect", "love to connect", "i came across your "
    "profile", "i hope you're well", "i hope you are well", "pick your brain", "passionate",
    "let's connect", "expand my network", "grow my network", "je souhaiterais rejoindre votre "
    "réseau", "j'aimerais rejoindre votre réseau",
]
_URL = re.compile(r"https?://|www\.|linkedin\.com/", re.I)
_PLACE = re.compile(r"\b(?:visa|sponsor\w*|parrainage|work authori[sz]ation|work permit|permis de "
                    r"travail|titre de séjour|relocat\w*|based (?:in|out of)|bas[ée]e?s? (?:à|en)|"
                    r"nationalit\w*|citizen\w*)\b", re.I)


@dataclass
class Context:
    pool: Pool
    allowed_years: set[int]
    job_text: str  # title + listing (+ signals for a follow-up)
    company: str
    kind: str  # note | followup
    max_chars: int
    alumni: bool
    school: str | None  # the short school name ("INSAT")
    school_full: str | None
    first_name: str
    years_statement: str | None = None
    places: list[str] = field(default_factory=list)  # your city, country, nationality
    banned: list[str] = field(default_factory=list)


def check(text: str, ctx: Context) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    text = text.strip()
    n = len(text)
    if not text:
        return [violation("empty", "The message is empty", "body", "error")]
    if n > ctx.max_chars:
        out.append(violation("length", f"{n} characters: LinkedIn allows {ctx.max_chars}"
                             + (" in a connection note" if ctx.kind == "note" else ""),
                             "body", "error"))
    if _URL.search(text):
        out.append(violation("link", "No links in the message", "body", "error"))
    if "?" not in text:
        out.append(violation("ask", "Ask one real question", "body", "error"))
    if "!" in text:
        out.append(violation("tone", "Exclamation mark", "body"))
    folded = oc.fold(text)
    # The school: allowed only for alumni (and then it's not a location claim).
    mentions_school = any(s and re.search(rf"\b{re.escape(oc.fold(s))}\b", folded)
                          for s in (ctx.school, ctx.school_full))
    if mentions_school and not ctx.alumni:
        out.append(violation("school", "The school angle is for alumni only", "body", "error"))
    scrubbed = text
    for s in (ctx.school_full, ctx.school):
        if s:
            scrubbed = re.sub(re.escape(s), " ", scrubbed, flags=re.I)
    place = _PLACE.search(scrubbed)
    places = [p for p in ctx.places
              if p and re.search(rf"\b{re.escape(oc.fold(p))}\b", oc.fold(scrubbed))]
    if place or places:
        found = place.group(0) if place else places[0]
        out.append(violation("location", f"“{found}”: never mention where you are, your "
                             "nationality, visa or work authorization", "body", "error"))
    for phrase in [*ctx.banned, *LINKEDIN_BANNED]:
        key = oc.fold(phrase.replace("’", "'"))
        if key and re.search(rf"\b{re.escape(key)}\b", oc.fold(text.replace("’", "'"))):
            out.append(violation("banned", f"Banned phrase: “{phrase}”", "body", "error"))
            break
    if ctx.first_name and oc.fold(ctx.first_name) not in folded and ctx.kind == "note":
        out.append(violation("name", f"Address {ctx.first_name} by name", "body"))
    email_ctx = oc.Context(pool=ctx.pool, allowed_years=ctx.allowed_years,
                           job_text=ctx.job_text, company=ctx.company, first_name="")
    out += [violation("grounding", p, "body", "error")
            for p in oc._source_problems(scrubbed, email_ctx)]
    for claim in bad_years(text, ctx.allowed_years, ctx.years_statement):
        out.append(violation("years", f"Years claim “{claim}” isn't allowed", "body", "error"))
    return out


def school_short(org: str | None) -> str | None:
    """'National Institute of … (INSAT)' → 'INSAT'; otherwise the name itself."""
    if not org:
        return None
    m = re.search(r"\(([A-Za-zÀ-ÿ0-9&.\- ]{2,20})\)", org)
    return m.group(1).strip() if m else org.strip()
