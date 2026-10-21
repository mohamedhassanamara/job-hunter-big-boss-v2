"""Checks for LinkedIn messages (connection notes, follow-ups, InMails). No model calls.

Blocking (errors), as for the job-linked email: grounding of numbers and tools (your pool, the
listing, the signals), the years wording and the honesty rules, never a hint that you saw their
profile visit, no links, the school for alumni only, and LinkedIn's own length limits. Style is a
warning, never a block: banned phrases, jargon, the ask, an example's wording, and your location
or visa when the listing states no requirement about it (when it does, saying it once, plainly,
is the honest thing to do). The claim verifier is the other half of the guard.
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
# A message must never reveal that you know they looked at your profile (LinkedIn Premium shows
# you who viewed it). Any wording of it is an error, for every kind of message and every group.
_VIEWED = re.compile(
    r"\b(?:"
    r"(?:view(?:ed|ing)|visit(?:ed|ing)|look(?:ed|ing) (?:at|over)|check(?:ed|ing)(?: out)?|"
    r"saw|seen|noticed|spotted|came across|stopped by)\W+(?:\w+\W+){0,3}(?:your|my)\W+"
    r"(?:linkedin\W+)?profile"
    r"|(?:saw|noticed|spotted|appreciate|thanks for)\W+(?:\w+\W+){0,2}(?:your|their)\W+visit"
    r"|profile\W+(?:visit|view)s?"
    r"|(?:vu|vue?s?|consult[ée]e?s?|visit[ée]e?s?|regard[ée]e?s?)\W+(?:\w+\W+){0,3}"
    r"(?:mon|votre)\W+profil"
    r"|visite\W+de\W+(?:mon|votre)\W+profil)\b", re.I)
_GREETING = re.compile(r"^\W*(?:hi|hello|hey|dear|good (?:morning|afternoon|evening)|bonjour|"
                       r"bonsoir|salut|hola|hallo)\b", re.I)
SUBJECT_MAX_CHARS = 80
INMAIL_MIN_CHARS = 250
_EASY_ASK = re.compile(r"\b(?:cv|resume|résumé|send|share|envoyer|partager)\b", re.I)
_CHAT = re.compile(r"\b(?:chat|call|talk|coffee|minutes|échanger|échange|appel|discuter)\b", re.I)
_ADVICE = re.compile(r"\b(?:advice|tips|refer\w*|recommend\w*|conseil\w*|recommand\w*|"
                     r"cooptation|parrain\w*|point me|who should)\b", re.I)
_ASK_WORDS = re.compile(r"\b(?:would you|could you|can you|could i|can i|please|take a look|"
                        r"look at|have a look|vous pourriez|pourriez-vous|pourrais-je|"
                        r"jeter un œil|regarder)\b", re.I)
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
    warm: bool = False  # they found you first (viewed your profile): a warm opener, no mention


def check(text: str, ctx: Context) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    text = text.strip()
    n = len(text)
    if not text:
        return [violation("empty", "The message is empty", "body", "error")]
    if n > ctx.max_chars:
        out.append(violation("length", f"{n} characters: the limit is {ctx.max_chars}"
                             + (" in a connection note" if ctx.kind == "note" else
                                " for this InMail (Settings → LinkedIn)" if ctx.kind == "inmail"
                                else ""), "body", "error"))
    if ctx.kind == "inmail" and n < INMAIL_MIN_CHARS:
        out.append(violation("short", f"{n} characters is short for an InMail: give them a "
                             "reason to reply (why them, one proof, one ask)", "body"))
    if _VIEWED.search(text):
        out.append(violation("viewed", "Never mention that they looked at your profile, or that "
                             "you noticed their visit", "body", "error"))
    if ctx.warm and ctx.kind in ("note", "inmail") and not _GREETING.search(text):
        out.append(violation("warm", "Open warmly: start with a greeting and their name",
                             "body"))
    if _URL.search(text):
        out.append(violation("link", "No links in the message", "body", "error"))
    if "?" not in text and not _ASK_WORDS.search(text):
        out.append(violation("ask", "End with a simple ask (a question, or “I've attached my "
                             "CV, would you take a look?”)", "body"))
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
    out += _location(scrubbed, ctx, "body")
    for phrase in [*ctx.banned, *LINKEDIN_BANNED]:
        key = oc.fold(phrase.replace("’", "'"))
        if key and re.search(rf"\b{re.escape(key)}\b", oc.fold(text.replace("’", "'"))):
            out.append(violation("banned", f"Banned phrase: “{phrase}”", "body"))
            break
    if ctx.first_name and oc.fold(ctx.first_name) not in folded and ctx.kind in ("note", "inmail"):
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
                                 "write it fresh", "body"))
            break
    return out


def _location(text: str, ctx: Context, where: str) -> list[dict[str, str]]:
    """Where you are, a visa need or relocation: fine when the listing states a requirement about
    it (said once, plainly), a warning when nothing asked for it. Never a block."""
    from app.services.applied_check import listing_states_constraint

    place = _PLACE.search(text)
    places = [p for p in ctx.places
              if p and re.search(rf"\b{re.escape(oc.fold(p))}\b", oc.fold(text))]
    if (place or places) and not listing_states_constraint(ctx.job_text):
        found = place.group(0) if place else places[0]
        return [violation("location", f"“{found}”: the listing states no residency, work-permit "
                          "or language requirement, so leave your location and visa out", where)]
    return []


def inmail_text(message: dict[str, Any] | None) -> str:
    """What is verified and sent as one unit: the subject, then the body."""
    message = message or {}
    return f"Subject: {message.get('subject', '')}\n\n{message.get('text', '')}"


def check_subject(subject: str, ctx: Context) -> list[dict[str, str]]:
    """The InMail subject line: short and plain, never clickbait, never a claim the pool and the
    listing can't back, never your location, never a mention of a profile visit."""
    out: list[dict[str, str]] = []
    subject = " ".join(subject.split())
    if not subject:
        return [violation("subject_empty", "The InMail needs a subject line", "subject", "error")]
    if len(subject) > SUBJECT_MAX_CHARS:
        out.append(violation("subject_length", f"{len(subject)} characters: keep the subject "
                             f"under {SUBJECT_MAX_CHARS}", "subject", "error"))
    if "!" in subject:
        out.append(violation("subject_tone", "No exclamation mark in the subject", "subject"))
    if _URL.search(subject):
        out.append(violation("subject_link", "No links in the subject", "subject", "error"))
    if _VIEWED.search(subject):
        out.append(violation("viewed", "Never mention that they looked at your profile",
                             "subject", "error"))
    out += _location(subject, ctx, "subject")
    folded = oc.fold(subject.replace("’", "'"))
    for phrase in [*ctx.banned, *LINKEDIN_BANNED]:
        key = oc.fold(phrase.replace("’", "'"))
        if key and re.search(rf"\b{re.escape(key)}\b", folded):
            out.append(violation("banned", f"Banned phrase in the subject: “{phrase}”",
                                 "subject"))
            break
    if sum(1 for w in subject.split() if len(w) > 2 and w.isupper()) >= 2:
        out.append(violation("subject_caps", "Avoid shouting (ALL CAPS) in the subject", "subject"))
    email_ctx = oc.Context(pool=ctx.pool, allowed_years=ctx.allowed_years,
                           job_text=ctx.job_text, company=ctx.company, first_name="")
    out += [violation("grounding", p, "subject", "error")
            for p in oc._source_problems(subject, email_ctx)]
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
                                 "Say it plainly", "body"))
        from app.services.intro_check import _tools

        allowed = {t.lower() for t in ctx.matching_tools}
        extra = [x for x in _tools(text, ctx.pool) if x.lower() not in allowed]
        if len(extra) > 1:
            out.append(violation("tools", f"For a recruiter, name only tools from the listing "
                                 f"that you have ({', '.join(ctx.matching_tools) or 'none'}); "
                                 f"also named: {', '.join(extra[:3])}", "body"))
        if ctx.kind in ("note", "inmail") and not _EASY_ASK.search(text):
            out.append(violation("ask", "Give a recruiter an easy ask (“Could I send you my "
                                 "CV?”)", "body"))
    elif ctx.group == "alumni":
        if ctx.school and not re.search(rf"\b{re.escape(oc.fold(ctx.school))}\b", folded):
            out.append(violation("school", f"Open with the shared school ({ctx.school})",
                                 "body"))
        if ctx.kind in ("note", "inmail") and not _ADVICE.search(text):
            out.append(violation("ask", "Ask an alumnus for advice or a referral", "body"))
    elif ctx.kind in ("note", "inmail") and not _CHAT.search(text):
        out.append(violation("ask", "Ask a team lead for a short chat", "body"))
    return out


def school_short(org: str | None) -> str | None:
    """'National Institute of … (INSAT)' → 'INSAT'; otherwise the name itself."""
    if not org:
        return None
    m = re.search(r"\(([A-Za-zÀ-ÿ0-9&.\- ]{2,20})\)", org)
    return m.group(1).strip() if m else org.strip()
