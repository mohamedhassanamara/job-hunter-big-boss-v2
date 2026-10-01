"""Checks for LinkedIn messages (connection notes and follow-ups). No model calls.

The same rules as the email where they apply: grounding of numbers and tools (your pool, the
listing, the signals), years wording, banned phrases and jargon, never your location /
nationality / visa. LinkedIn only: the school may be named, for alumni only. Plus: the length
limit (a free account's note is 200 characters), no links, and a question.
"""

import re
from dataclasses import dataclass, field
from typing import Any

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
# What a recruiter shouldn't have to decode (plain language; 2-3 tools from the listing are fine).
JARGON = ["idempotent", "schema drift", "lakehouse", "orchestration", "orchestrated",
          "microservices", "event-driven", "data lineage", "medallion", "ci/cd", "observability",
          "throughput", "latency", "scalable architecture", "end-to-end", "stack", "backfill",
          "upsert", "partitioning", "containerized", "containerised", "kubernetes", "terraform",
          "infrastructure as code", "deduplication", "entity resolution"]
_EASY_ASK = re.compile(r"\b(?:cv|resume|résumé|send|share|envoyer|partager)\b", re.I)
_CHAT = re.compile(r"\b(?:chat|call|talk|coffee|minutes|échanger|échange|appel|discuter)\b", re.I)
_ADVICE = re.compile(r"\b(?:advice|tips|refer\w*|recommend\w*|conseil\w*|recommand\w*|"
                     r"cooptation|parrain\w*|point me|who should)\b", re.I)
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
    honesty: Any = None  # services/honesty.Rules: years never attached to a projects track
    examples: list[str] = field(default_factory=list)  # reference notes (never copied)
    group: str = "lead"  # the note's angle: recruiter | lead | alumni
    matching_tools: list[str] = field(default_factory=list)  # listing tools you have


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
    from app.services import honesty

    out += honesty.violations(text, ctx.honesty)
    out += _group_rules(text, ctx)
    from app.services.intro_check import _longest_run

    for example in ctx.examples:  # structure and honesty references, never wording to copy
        run = _longest_run(text, example)
        if run >= 8:
            out.append(violation("example_copy", f"{run} words in a row from a reference note: "
                                 "write it fresh", "body", "error"))
            break
    return out


def _group_rules(text: str, ctx: Context) -> list[dict[str, str]]:
    """Written for its reader: plain words for recruiters, a proof for team leads, the school
    for alumni. (A follow-up keeps the person's angle but isn't held to the note's ask.)"""
    out: list[dict[str, str]] = []
    folded = oc.fold(text)
    if ctx.group == "recruiter":
        jargon = [j for j in JARGON if re.search(rf"\b{re.escape(oc.fold(j))}\b", folded)]
        if jargon:
            out.append(violation("jargon", f"Jargon for a recruiter: {', '.join(jargon[:3])}. "
                                 "Say it plainly", "body", "error"))
        from app.services.intro_check import _tools

        allowed = {t.lower() for t in ctx.matching_tools}
        extra = [x for x in _tools(text, ctx.pool) if x.lower() not in allowed]
        if len(extra) > 1:
            out.append(violation("tools", f"For a recruiter, name only tools from the listing "
                                 f"that you have ({', '.join(ctx.matching_tools) or 'none'}); "
                                 f"also named: {', '.join(extra[:3])}", "body"))
        if ctx.kind == "note" and not _EASY_ASK.search(text):
            out.append(violation("ask", "Give a recruiter an easy ask (“Could I send you my "
                                 "CV?”)", "body"))
    elif ctx.group == "alumni":
        if ctx.school and not re.search(rf"\b{re.escape(oc.fold(ctx.school))}\b", folded):
            out.append(violation("school", f"Open with the shared school ({ctx.school})",
                                 "body"))
        if ctx.kind == "note" and not _ADVICE.search(text):
            out.append(violation("ask", "Ask an alumnus for advice or a referral", "body"))
    elif ctx.kind == "note" and not _CHAT.search(text):
        out.append(violation("ask", "Ask a team lead for a short chat", "body"))
    return out


def school_short(org: str | None) -> str | None:
    """'National Institute of … (INSAT)' → 'INSAT'; otherwise the name itself."""
    if not org:
        return None
    m = re.search(r"\(([A-Za-zÀ-ÿ0-9&.\- ]{2,20})\)", org)
    return m.group(1).strip() if m else org.strip()
