"""Checks for the job-linked email, an honest application follow-up (prompt v11, mode "applied").
No model calls.

Blocking (errors): only what protects the facts. Facts about you come from your pool and the
profile (cited sentences, numbers and tools, the years wording and the honesty rules), facts about
the company only from the listing and the selected signals, and names are spelled right. The
Claude verifier (`services/verifier.py`) is the other half of that guard.

Everything about style is a warning, never a block: length (about 90-170 words), tool lists,
banned phrases, jargon, restating the listing, a location or visa mention the listing doesn't ask
for, a constraint said twice. The listing, the role, your location and a visa need are all
allowed to be mentioned here: the old introduction rules live in `intro_check` (mode
"speculative").
"""

import re
from datetime import date, timedelta
from typing import Any

from app.providers.base import AppliedEmailPlan, SummarySentence
from app.services import intro_check as ic
from app.services import outreach_check as oc
from app.services.cv_check import numbers, sentence_problems, violation
from app.services.cv_claims import bad_years

MIN_WORDS, MAX_WORDS = 0, 110  # v17: a warning above 110 words (greeting to ask, no signature)
SNIPPET_CHARS = 1500  # a shorter stored listing is a snippet: requirements may be missing
MIN_SENTENCES, MAX_SENTENCES = 1, 2  # at most two proofs, one sentence each
MAX_PROOF_WORDS = 55  # a summary sentence may merge two facts
MAX_OPENING_WORDS = 35
MAX_TOOLS = 3  # in the whole email (a warning)
MAX_NUMBERS = 2  # in the whole email, years wording aside (a warning)
COPY_RUN = 8  # consecutive words shared with a pool bullet or a style reference = a copy
_FIRST_PERSON = {"en": re.compile(r"\b(?:I|I'm|I've|I'd|I'll|my|me)\b", re.I),
                 "fr": re.compile(r"\b(?:je|j['’]|mon|ma|mes|moi)", re.I)}
_URL = re.compile(r"\s*\(\s*(?:https?://)?[\w.-]+\.[a-z]{2,12}(?:/[^)\s]*)?\s*\)|"
                  r"\s*https?://[^\s)]+", re.I)
# What a listing says when it states a requirement tied to where you live, your right to work or
# a language (English, German and French): the only reason to mention your situation.
_LISTING_CONSTRAINT = re.compile(
    r"\b(?:residen\w+|right to work|work (?:permit|authori[sz]ation)|visa|sponsor\w*|"
    r"eligible to work|applicant location|location requirements?|citizen\w*|"
    r"must (?:be|live|reside)\b[^.]{0,30}\b(?:in|within|near)|"
    r"based in|on-?site|in[- ]office|relocat\w*|(?:fluent|native|proficient|business[- ]level|"
    r"working knowledge)\b[^.]{0,25}\b(?:english|german|french|dutch|arabic|spanish)|"
    r"(?:english|german|french|dutch|arabic|spanish)\W+(?:language|speaker|speaking|fluency)|"
    r"(?:english|german|french|dutch|arabic|spanish)\s+(?:and|und|et)\s+(?:english|german|"
    r"french|dutch|arabic|spanish|englisch|deutsch)|written and spoken|deutsch(?:kenntnisse)?|"
    r"englischkenntnisse|"
    r"wohnsitz|arbeitserlaubnis|arbeitsgenehmigung|aufenthalt\w*|deutschkenntnisse|"
    r"sprachkenntnisse|vor ort vor|r[ée]sidence|permis de travail|titre de s[ée]jour|"
    r"autorisation de travail|fran[cç]ais courant|bilingue)\b", re.I)
# What a listing says when it states a requirement tied to WHERE you live or may work: the only
# reason to mention your location, visa or relocation. A language requirement is not one.
_LISTING_LOCATION = re.compile(
    r"\b(?:residen\w+|right to work|work (?:permit|authori[sz]ation)|visa|sponsor\w*|"
    r"eligible to work|applicant location|location requirements?|citizen\w*|"
    r"must (?:be|live|reside)\b[^.]{0,30}\b(?:in|within|near)|"
    r"based in|on-?site|in[- ]office|relocat\w*|"
    r"wohnsitz|arbeitserlaubnis|arbeitsgenehmigung|aufenthalt\w*|vor ort vor|"
    r"r[ée]sidence|permis de travail|titre de s[ée]jour|autorisation de travail)\b", re.I)
_SIGNAL_RUN = 7
# The ban applies to what the model writes (opening, experience, ask), in the languages the
# emails are written in. A signal or a company fact may say "sponsor" about anything else.
_VISA_DISCLAIMER_WORDS = re.compile(
    r"\b(?:visas?|visum|sponsorship|sponsor\w*|work authori[sz]ation|work permit|"
    r"right to work|rules me out|relocat\w*|"
    r"arbeitserlaubnis|arbeitsgenehmigung|aufenthalt\w*|umzug|relokation|umsiedlung|"
    r"titre de s[ée]jour|permis de travail|autorisation de travail|parrainage|"
    r"d[ée]m[ée]nagement|relocalisation)\b", re.I)
# A signal says what it says: never what it "shows about" the company (the verifier blocks that
# kind of embroidery; this warns earlier).
_INFERENCE = re.compile(
    r"\b(?:(?:says|shows|tells|speaks|reflects)\b[^.]{0,25}\babout|which (?:shows|means|says|"
    r"tells)|(?:shows|demonstrates|proves|signals) (?:that|how)|this means)\b", re.I)


def listing_states_constraint(job_text: str) -> bool:
    return bool(_LISTING_CONSTRAINT.search(job_text or ""))


def listing_states_location(job_text: str) -> bool:
    return bool(_LISTING_LOCATION.search(job_text or ""))


def clean(text: str) -> str:
    """No markdown backticks and no URLs or domains in an email (a project's own address
    belongs on the CV, not in the sentence)."""
    text = _URL.sub("", (text or "").replace("`", ""))
    return re.sub(r"[ \t]+([,.;])", r"\1", text)


def plain_role(role: str) -> str:
    """The role as a subject says it: no gender tag, no "– Flutter, Enterprise-App" tail."""
    role = re.sub(r"\s*\((?:[mwfdxi]\s*/\s*){1,3}[mwfdxi]\)", "", role or "", flags=re.I)
    role = re.split(r",\s*\(", role.strip())[0]  # "Engineer, (New Grad) Milan" → "Engineer"
    return " ".join(re.split(r"\s+[–—|]\s+|\s+-\s+", role)[0].split())


def display_company(name: str | None) -> str:
    """The company as people say it: trailing legal forms ("GmbH", "S.r.l.", "Inc.") dropped,
    the rest exactly as written (never lowercased)."""
    from app.services.dedupe import _LEGAL_SUFFIXES

    words = " ".join((name or "").replace(",", " ").split()).split(" ")
    while len(words) > 1 and re.sub(r"[^a-z]", "", words[-1].lower()) in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words).strip()


def subject_line(role: str, name: str, language: str, company: str = "") -> str:
    """"<Role> at <Company> - <your name>" (without a company: "<Role> application - <name>";
    French: "Candidature <role> chez <company> - <name>"); editable."""
    role, name = plain_role(role), " ".join((name or "").split())
    if company := display_company(company):
        if language == "fr":
            head = f"Candidature {role} chez {company}" if role else f"Candidature chez {company}"
        else:
            head = f"{role} at {company}" if role else f"Application at {company}"
        return f"{head} - {name}" if name else head
    if language == "fr":
        head = f"Candidature {role}" if role else "Candidature"
    else:
        head = f"{role} application" if role else "Application"
    return f"{head} - {name}" if name else head


def speculative_subject(role: str, company: str, language: str) -> str:
    """"Quick intro | <Role> at <Company>" (French: "Présentation rapide | <Role> chez <X>")."""
    role, company = plain_role(role), " ".join((company or "").split())
    head = "Présentation rapide" if language == "fr" else "Quick intro"
    at = "chez" if language == "fr" else "at"
    if role and company:
        return f"{head} | {role} {at} {company}"
    return f"{head} | {role or company}" if role or company else head


# ---------------------------------------------------------------- the opening and the ask (code)

_RECRUITER = re.compile(
    r"recruit|talent|\bhr\b|human resources|\bpeople\b|ressources humaines|\brh\b|"
    r"acquisition|sourc(?:er|ing)|personal|rekrut", re.I)
_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"]}
VARIANTS = 4
_WEEKDAYS = {"en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
             "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]}


def method_phrase(method: str | None, language: str) -> str:
    """Where the application went in, in the words that fit: never "careers page" for a board
    or LinkedIn. A board is never named: the record says "job board", not which one (the
    listing's source is where it was found, not where you applied)."""
    if method == "linkedin":
        return "LinkedIn"
    if method == "job_board":
        return "une plateforme d'emploi" if language == "fr" else "a job board"
    return "votre site carrières" if language == "fr" else "your careers page"


def when_phrase(applied: date | None, today: date, language: str) -> str:
    """"today", "yesterday", "on Monday" (within the last week), else "on 12 October"."""
    fr = language == "fr"
    if applied is None:
        return ""
    if applied == today:
        return "aujourd'hui" if fr else "today"
    if applied == today - timedelta(days=1):
        return "hier" if fr else "yesterday"
    if today - timedelta(days=6) <= applied < today:
        day = _WEEKDAYS["fr" if fr else "en"][applied.weekday()]
        return f"{day} dernier" if fr else f"on {day}"
    month = _MONTHS["fr" if fr else "en"][applied.month - 1]
    year = f" {applied.year}" if applied.year != today.year else ""
    return f"le {applied.day} {month}{year}" if fr else f"on {applied.day} {month}{year}"


def opening_line(role: str, method: str | None, applied: date | None, today: date,
                 language: str, variant: int = 0, company: str = "") -> str:
    """"I applied for the <Role> role at <Company> through <where> <when>." Everything comes
    from the application record; four equivalent wordings rotate. Nothing else is said."""
    role, via = plain_role(role), method_phrase(method, language)
    company = display_company(company)
    when = when_phrase(applied, today, language)
    v = variant % VARIANTS
    lead = when[:1].upper() + when[1:]
    if language == "fr":
        chez = f" chez {company}" if company else ""
        post = (f"au poste de {role}" if role else "à ce poste") + chez
        pour = (f"pour le poste de {role}" if role else "pour ce poste") + chez
        lines = [f"J'ai postulé {post} via {via} {when}.",
                 f"J'ai déposé ma candidature {pour} via {via} {when}.",
                 f"{lead + ', ' if when else ''}j'ai postulé {post} via {via}.",
                 f"Ma candidature {pour} a été envoyée via {via} {when}."]
        return lines[v].replace(" .", ".").replace("  ", " ")
    at = f" at {company}" if company else ""
    role_ = (f"the {role} role" if role else "the role") + at
    position = (f"the {role} position" if role else "the position") + at
    lines = [f"I applied for {role_} through {via} {when}.",
             f"I submitted my application for {position} via {via} {when}.",
             f"{lead + ', ' if when else ''}I applied for {role_} on {via}.",
             f"My application for {role_} went in through {via} {when}."]
    return lines[v].replace(" .", ".").replace("  ", " ")


def is_recruiter(title: str | None, group: str | None = None) -> bool:
    return bool(_RECRUITER.search(f"{title or ''} {group or ''}"))


# ------------------------------------------------------------- persona and scenario (v19, code)

PERSONAS = ("engineering_manager", "founder_cto", "tech_lead", "recruiter", "other")
SCENARIOS = ("direct", "years_gap", "stack_pivot")
# Guidance on tone and on which pool-backed facts to lead with. Never a source of claims.
PERSONA_FOCUS = {
    "engineering_manager": "architecture reliability, refactoring legacy code, codebase health "
                           "and delivering with little supervision",
    "founder_cto": "end-to-end execution, shipping to the stores or production, practical delivery",
    "tech_lead": "technical craft: state management, architecture boundaries, release pipelines",
    "recruiter": "a skimmable match to the role's checklist: the honest years of production "
                 "software engineering, the platforms shipped, the backend or API work and "
                 "features owned from endpoint to release; no library names, no refactoring "
                 "or metric detail",
    "other": "a neutral technical tone"}
_FOUNDER = re.compile(r"founder|fondateur|\bceo\b|\bcto\b|chief|owner|managing director|"
                      r"geschäftsführer", re.I)
_MANAGER = re.compile(r"manager|head of|director|\bvp\b|vice president|\bdirektor|responsable|"
                      r"directeur", re.I)
_TECHLEAD = re.compile(r"lead|staff|principal|architect|senior|engineer|developer|"
                       r"ingénieur|entwickler|développeu", re.I)


def persona_for(title: str | None, group: str | None = None) -> str:
    """Who the recipient is: their own title decides; the contact ranking's group label only
    settles a title that says nothing (an empty one, or "Partner")."""
    if is_recruiter(title, None if title else group):
        return "recruiter"
    for text in (title or "", group or ""):
        if _FOUNDER.search(text):
            return "founder_cto"
        if _MANAGER.search(text):
            return "engineering_manager"
        if _TECHLEAD.search(text):
            return "tech_lead"
        if text == (title or "") and is_recruiter(None, group):
            return "recruiter"
    return "other"


_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?|ans|jahre?n?)\b", re.I)
_EXPERIENCE = re.compile(r"experience|expérience|erfahrung|berufserfahrung", re.I)
YEARS_GAP_MARGIN = 2  # the posting asks for at least this many years more than you have
# Neutral technology names (not personal data): what a listing's primary stack can be, grouped
# by family. A pivot is a primary stack your pool lacks while it shows another of the same family.
STACK_FAMILIES: dict[str, tuple[str, ...]] = {
    "mobile": ("flutter", "react native", "kotlin", "swift", "swiftui", "jetpack compose",
               "xamarin", "ionic", "nativescript"),
    "frontend": ("react", "vue", "angular", "svelte", "next.js"),
    "backend": ("java", "spring", "python", "django", "fastapi", "flask", "node.js", "nestjs",
                "golang", "ruby", "rails", "rust", "php", "laravel", "c#", ".net", "kotlin"),
}


def required_years(listing: str) -> int | None:
    """The most years of experience the listing asks for (a number near "experience"), or None."""
    found = []
    for m in _YEARS.finditer(listing or ""):
        window = (listing or "")[max(0, m.start() - 60): m.end() + 60]
        if _EXPERIENCE.search(window) and 1 <= int(m.group(1)) <= 15:
            found.append(int(m.group(1)))
    return max(found) if found else None


def _has_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![\w.+#]){re.escape(term)}(?![\w+#])", text, re.I))


def stack_pivot(title: str, listing: str, pool_text: str) -> tuple[str, list[str]] | None:
    """(target, what the pool shows in that family) when the listing's primary stack is one your
    pool never names while it names another of the same family; else None. The title decides;
    without a stack in the title, a stack the listing names at least four times and twice as
    often as any other of its family does (a stray mention is not the primary stack)."""
    for terms in STACK_FAMILIES.values():
        named = [t for t in terms if _has_term(title or "", t)]
        if not named:
            counts = sorted(((len(re.findall(rf"(?<![\w.+#]){re.escape(t)}(?![\w+#])",
                                              listing or "", re.I)), t) for t in terms),
                            reverse=True)
            top, runner_up = counts[0], counts[1][0]
            named = [top[1]] if top[0] >= 4 and top[0] >= 2 * runner_up else []
        if not named or any(_has_term(pool_text, t) for t in named):
            continue
        have = [t for t in terms if _has_term(pool_text, t)]
        if have:
            return named[0], have
    return None


def scenario_for(title: str, listing: str, pool_text: str, have_years: int | None) -> dict:
    """direct | years_gap | stack_pivot, from the listing and your pool (no model). A pivot
    outranks a years gap (one acknowledgement per email); both are reported."""
    out: dict = {"scenario": "direct"}
    asked = required_years(listing)
    if asked and have_years and asked >= have_years + YEARS_GAP_MARGIN:
        out.update(scenario="years_gap", required_years=asked, have_years=have_years)
    if pivot := stack_pivot(title, listing, pool_text):
        out.update(scenario="stack_pivot", target_stack=pivot[0], pool_stack=pivot[1])
    return out


SCENARIO_PATTERN = {
    "direct": "Lead with the single strongest pool proof for the job's primary requirement.",
    "years_gap": "Acknowledge the posting's years once, plainly, then go straight to concrete "
                 "work: \"While the posting calls for {required_years} years, my {have_years} "
                 "years of software engineering have centered on {what the pool shows}: at "
                 "{employer} ...\". No defensiveness, no spin.",
    "stack_pivot": "Say once, up front and without defensiveness, that your production work is "
                   "in {pool_stack} rather than {target_stack}, then connect fundamentals the "
                   "pool backs: \"While my production background is in {pool_stack} rather than "
                   "{target_stack}, the core engineering overlaps directly: {pool-backed "
                   "fundamentals} ...\"."}

# What no applied email may say (a blocking error): filler, clichés and the disclaimer patterns
# that sound defensive or robotic. Matched on folded text with word boundaries.
V19_BANNED = (
    "wanted to introduce myself directly", "i hope this email finds you well",
    "fits your team's roadmap", "align with your roadmap", "aligns with your roadmap",
    "building screens and integrating backend services", "spearheaded", "delve", "testament",
    "passionate", "thrilled", "esteemed", "humbled", "moves fast", "without hand-holding",
    "without supervision", "rock-solid", "zero-regression", "engineering discipline",
    "ui assembly", "i'd love to grab", "so here is the part that matters",
    "i'd rather say that up front", "i also", "additionally i", "furthermore", "moreover",
    "seamlessly", "successfully")
SCENARIO_BANNED = {
    "years_gap": ("despite my lack of", "even though i only have", "rather than ticket-taking",
                  "high-velocity"),
    "stack_pivot": ("what carries over is work i've done", "productive from day one",
                    "transfer immediately")}


def banlist_violations(text: str, scenario: str = "direct") -> list[dict[str, str]]:
    folded = oc.fold(text)  # punctuation-free, so "rock-solid" and "I'd" match their folded form
    banned = V19_BANNED + SCENARIO_BANNED.get(scenario, ())
    return [violation("banlist", f"Banned wording: “{p}”", "body", "error")
            for p in banned if re.search(rf"\b{re.escape(oc.fold(p))}\b", folded)]


CTA_VARIANTS = 3
_NEXT_WEEK = re.compile(r"\b(?:next week|la semaine prochaine|nächste woche)\b", re.I)


def cta_variant(previous: int | None, seed: int) -> int:
    """Which closing to use: rotated by `seed`, never the one the previous email to the same
    company used (`previous`)."""
    options = [v for v in range(CTA_VARIANTS) if v != previous]
    return options[seed % len(options)]


def cta_line(language: str, recruiter: bool = False, variant: int = 0, weekday: int = 0) -> str:
    """The closing, built by code: the attached-CV call-out, then a 10-minute call question
    (for HR and recruiters always the same introductory-call line). Never "next week" and
    never a date. The wordings say "this week" only on Monday to Wednesday (`weekday` 0-2, in
    your timezone), else "in the next few days"."""
    callout = ("Je joins mon CV pour un aperçu rapide. " if language == "fr"
               else "I have attached my CV for quick review. ")
    return callout + _call_question(language, recruiter, variant, weekday)


def _call_question(language: str, recruiter: bool, variant: int, weekday: int) -> str:
    fr, v = language == "fr", variant % CTA_VARIANTS
    early = weekday <= 2
    if fr:
        when = "cette semaine" if early else "dans les prochains jours"
        if recruiter:
            return ("Si mon profil correspond à ce que vous recherchez, je serais ravi d'avoir "
                    f"un bref appel de présentation de 10 minutes {when}.")
        if v == 0:
            return ("Seriez-vous disponible pour un court échange technique de 10 minutes "
                    "dans les prochains jours ?")
        if v == 1:
            return f"Auriez-vous 10 minutes pour un bref appel technique {when} ?"
        return f"Je serais ravi d'échanger 10 minutes par téléphone {when}, si cela vous convient."
    when = "this week" if early else "in the next few days"
    if recruiter:
        return ("If my background aligns with what you're screening for, I'd welcome a brief "
                f"10-minute introductory call {when}.")
    if v == 0:
        return f"Would you be open to a brief 10-minute introductory call {when}?"
    if v == 1:
        return f"Do you have 10 minutes for a brief technical call {when}?"
    return f"Happy to hop on a 10-minute call {when} if you'd like to connect."


_ISO_DATE = re.compile(r"\s*\b(?:on\s+)?\d{4}-\d{2}-\d{2}\b", re.I)
_OPENING_LIKE = re.compile(
    r"\b(?:applied|application|candidature|postul\w+)\b.*\b(?:role|position|poste|portal|"
    r"careers?|linkedin|job board|via|through)\b", re.I)


def strip_model_opening(sentences: list[Any]) -> list[Any]:
    """The program writes the one opening; a model sentence that opens again ("I applied for
    the … role through …") is dropped, and a raw ISO date is never printed."""
    kept = []
    for sentence in sentences:
        text = sentence.text
        short = len(re.findall(r"\w+", text)) <= 40
        if (_OPENING_LIKE.search(text) and _FIRST_PERSON["en"].search(text) and short
                and not re.search(r"\bbuilt|shipped|led\b", text)):
            continue
        sentence.text = _ISO_DATE.sub("", text).strip()
        kept.append(sentence)
    return kept


# Recruiters skim for a checklist; library, pattern and counted-metric detail is noise.
RECRUITER_MAX_WORDS, RECRUITER_MAX_SENTENCE = 85, 25
_RECRUITER_JARGON = re.compile(
    r"\bBFF\b|\bendpoints?\b|\bRESTful\b|\bclean architecture\b|\bstate management\b|"
    r"\bRiverpod\b|\bGoRouter\b|\bBLoC\b|\bRetrofit\b|\bDio\b|\bbinary size\b|"
    r"\d+\s?%|\b\d+\s?\+\s*\w+|\b\d+\s+(?!years?\b|months?\b|ans\b)[a-z]+\s+"
    r"(?:screens|services|apis|modules|features|endpoints)\b", re.I)


def recruiter_problems(plan: "AppliedEmailPlan") -> list[dict[str, str]]:
    """Recruiter persona: lead with years, no counted metrics or library names, short sentences,
    under 85 words in all. Errors, so the one retry gets them as feedback."""
    out: list[dict[str, str]] = []
    proof = " ".join(s.text for s in plan.experience)
    if not re.search(r"\b\d+\+?\s*(?:years?|ans)\b", proof, re.I):
        out.append(violation("recruiter_years", "Lead with the years of production software "
                             "engineering: a recruiter looks for them first",
                             "experience", "error"))
    if m := _RECRUITER_JARGON.search(proof):
        out.append(violation("recruiter_jargon", f"“{m.group(0)}” is detail a recruiter doesn't "
                             "screen for: say the platforms and the stack, no counts or library "
                             "names", "experience", "error"))
    for sentence in plan.experience:
        if len(oc.words(sentence.text)) > RECRUITER_MAX_SENTENCE:
            out.append(violation("recruiter_long", f"A recruiter reads short sentences: split "
                                 f"“{sentence.text[:50]}…” (max {RECRUITER_MAX_SENTENCE} words)",
                                 "experience", "error"))
    if len(oc.words(body(plan))) > RECRUITER_MAX_WORDS:
        out.append(violation("recruiter_words", f"{len(oc.words(body(plan)))} words: a recruiter "
                             f"email stays under {RECRUITER_MAX_WORDS}", "body", "error"))
    return out


def body(plan: AppliedEmailPlan) -> str:
    """greeting · opening · proof (the model's only part) · ask. No signature, no opt-out."""
    experience = " ".join(s.text.strip() for s in plan.experience)
    parts = [plan.greeting.strip(), plan.opening.strip(), experience, plan.ask.strip()]
    return clean("\n\n".join(p for p in parts if p))


def proof_of(text: str) -> str:
    """The proof paragraph of a v17 body (between the opening and the ask)."""
    parts = [p for p in (text or "").split("\n\n") if p.strip()]
    return "\n\n".join(parts[2:-1]) if len(parts) >= 4 else ""


def _acknowledgement_free(text: str, ctx: ic.Context) -> str:
    """The scenario's one acknowledgement is allowed to name the posting's years and the target
    stack ("the posting calls for 5 years", "rather than React Native"): they come from the
    listing, not from your pool, so they are not claims about you."""
    for n in ctx.required_years:
        text = re.sub(rf"\b(?:posting|listing|role|job|position|description)\s+"
                      rf"(?:calls for|asks for|requires|wants|lists|specifies)\s+{n}\+?\s+"
                      r"years?", "the posting asks", text, flags=re.I)
    if ctx.target_stack:
        text = re.sub(rf"(?<![\w.+#]){re.escape(ctx.target_stack)}(?![\w+#])", "the target stack",
                      text, flags=re.I)
    return text


def _facts_without_statement(text: str, ctx: ic.Context) -> str:
    return _acknowledgement_free(ic._without_statement(text, ctx), ctx)


def _source_text(ctx: ic.Context) -> oc.Context:
    """The sources a sentence without citations may rely on: pool, listing, signals."""
    source = f"{ctx.job_text}\n" + " ".join(ctx.signals.values())
    return oc.Context(pool=ctx.pool, allowed_years=ctx.allowed_years, job_text=source,
                      company=ctx.company, first_name="")


def _paragraph_hits(text: str, pattern: re.Pattern[str]) -> int:
    return sum(1 for p in text.split("\n\n") if pattern.search(p))


_LEGAL = {"gmbh", "ag", "inc", "ltd", "llc", "sas", "sarl", "sa", "bv", "plc", "co", "corp", "ug"}


def _is_company_word(word: str, company: str) -> bool:
    """A "tool" that is really a word of the company's name ("GmbH", "SaltRock", "ElevenLabs")."""
    w = oc.fold(word).replace(" ", "")
    parts = {oc.fold(c) for c in re.split(r"[\s,.]+", company or "") if c}
    return w in _LEGAL or w in parts or w == oc.fold(company or "").replace(" ", "")


_DOMAIN = re.compile(
    r"\b(?:https?://|www\.)\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|dev|io|net|org|app|ai|fr|de|"
    r"eu|co|me|tech|xyz|info|tn|ly|so|page|site|online|cloud)\b(?:/\S*)?", re.I)
_APOLOGY = re.compile(
    r"\b(?:sorry|apolog\w*|forgive|excuse me|even though|although i(?:'m| am| was)|"
    r"i know (?:that )?you(?:'re| are| probably| must| likely)?|you (?:probably |must |likely )?"
    r"(?:receive|get|are sent) (?:many|a lot|so many|countless|plenty)|hope you don'?t mind|"
    r"(?:don'?t|do not) mean to (?:bother|disturb|intrude)|bother you|take up your time|"
    r"d[ée]sol[ée]\w*|je sais que vous (?:recevez|avez)|pardon\w*|excusez)\b", re.I)
_BYPASS = re.compile(
    r"\b(?:are you (?:currently )?hiring|do you (?:currently )?have (?:any )?(?:open(?:ing)?s?|"
    r"positions?|vacanc\w+)|is there (?:an? )?(?:open(?:ing)?|position|vacancy)|(?:any )?open "
    r"(?:positions?|roles?) (?:at|on your)|instead of (?:the |your )?(?:portal|careers|"
    r"application|website|site)|rather than (?:going )?(?:through )?(?:the |your )?(?:portal|"
    r"careers|application)|bypass\w*|skip(?:ping)? (?:the )?(?:portal|queue|application)|"
    r"without going through|outside (?:of )?(?:the |your )?(?:portal|application|process)|"
    r"avoid(?:ing)? (?:the )?(?:portal|queue)|recrutez-vous|avez-vous des postes|"
    r"au lieu (?:du|de votre) (?:portail|site))\b", re.I)


def v17_violations(text: str) -> list[dict[str, str]]:
    """Blocking rules of the portal-first follow-up: no link or domain in the body (links live
    in the signature), no apology or defensive wording, no asking whether they hire and no
    wording about going around the portal."""
    out: list[dict[str, str]] = []
    if m := _DOMAIN.search(text):
        out.append(violation("url", f"“{m.group(0)}”: no link or domain in the body (your links "
                             "are in the signature)", "body", "error"))
    if m := _APOLOGY.search(text):
        out.append(violation("apology", f"“{m.group(0)}”: no apology or defensive wording: say "
                             "what you did, plainly", "body", "error"))
    if m := _BYPASS.search(text):
        out.append(violation("bypass", f"“{m.group(0)}”: you already applied: don't ask whether "
                             "they hire or hint at going around the portal", "body", "error"))
    return out


def _visa_banned(text: str, where: str) -> list[dict[str, str]]:
    if match := _VISA_DISCLAIMER_WORDS.search(text):
        return [violation(
            "visa_disclaimer_banned",
            "Cold outreach must never mention visa, sponsorship or relocation caveats "
            f"(found “{match.group(0)}”)", where, "error")]
    return []


def _visa_in_edited_text(text: str, ctx: ic.Context) -> list[dict[str, str]]:
    """An edited email has no plan: check every paragraph but the greeting and the company
    fact (the paragraph that shares a run of words with a selected signal)."""
    signals = list(ctx.signals.values())
    out: list[dict[str, str]] = []
    for paragraph in text.split("\n\n")[1:]:
        if any(ic._longest_run(paragraph, sig) >= 4 for sig in signals):
            continue
        out += _visa_banned(paragraph, "body")
    return out[:1]


def text_rules(subject: str, text: str, ctx: ic.Context, *,
               visa_in_whole_text: bool = True, v17: bool = False) -> list[dict[str, str]]:
    """What any version of the email must satisfy (generated or edited by you).
    `visa_in_whole_text=False`: the caller scopes the visa ban itself (job-linked emails).
    `v17`: the portal-first follow-up (no company-name rule, 110 words in all, duplicates and
    copies judged on the proof only, the v17 errors)."""
    out: list[dict[str, str]] = []
    folded = oc.fold(text)
    everything = f"{subject}\n{text}"
    if v17:
        out += v17_violations(text)
        out += banlist_violations(text, ctx.scenario)
        closing = (text.strip().split("\n\n") or [""])[-1]
        if _NEXT_WEEK.search(closing):
            out.append(violation("closing", "The closing says “next week”: ask for a few minutes "
                                 "“in the next few days” or “this week” instead, never a date",
                                 "body"))
    # --- blocking: names, years, honesty, facts without a citation
    if not subject.strip():
        out.append(violation("subject", "The subject is empty", "subject", "error"))
    elif len(oc.words(subject)) > 12:
        out.append(violation("subject", "The subject is long (about 8 words is easier to "
                             "scan)", "subject"))
    greeting = text.split("\n", 1)[0]
    if ctx.first_name and oc.fold(ctx.first_name) not in oc.fold(greeting):
        out.append(violation("name", f"The greeting doesn't use {ctx.first_name}'s first name",
                             "greeting", "error"))
    elif ctx.first_name and ctx.first_name not in greeting:
        out.append(violation("name", f"Spell it “{ctx.first_name}”, as the company's pages do",
                             "greeting"))
    for other in ctx.other_companies:
        if other and oc.fold(other) != oc.fold(ctx.company) and re.search(
                rf"\b{re.escape(oc.fold(other))}\b", folded):
            out.append(violation("company", f"Mentions “{other}”, the company of another draft",
                                 "body", "error"))
    from app.services.dedupe import normalize_company
    norm_comp = normalize_company(ctx.company) if ctx.company else ""
    named = oc.fold(ctx.company) in oc.fold(everything) or (
        norm_comp and oc.fold(norm_comp) in oc.fold(everything))
    if ctx.company and not named and not v17:
        out.append(violation("company", f"The company name “{ctx.company}” isn't mentioned",
                             "body"))
    for claim in bad_years(_facts_without_statement(text, ctx), ctx.allowed_years,
                           ctx.years_statement):
        out.append(violation("years", f"Years claim “{claim}” isn't allowed", "body", "error"))
    from app.services import honesty

    out += honesty.violations(text, ctx.honesty)
    if visa_in_whole_text:
        out += _visa_banned(text, "body")
    # --- warnings: style
    if len(ctx.job_text or "") < SNIPPET_CHARS:
        out.append(violation("snippet", "Listing is a short snippet: constraints like residency or "
                             "a language requirement can't be detected. Paste the full description "
                             "or fetch it, then regenerate", "body"))
    n = len(oc.words(text)) - (0 if v17 else len(oc.words(greeting)))
    if v17 and n > ctx.max_words:
        out.append(violation("length", f"{n} words: the follow-up is {ctx.max_words} words or "
                             "fewer", "body", "error"))
    elif not v17 and (n < ctx.min_words or n > ctx.max_words):
        out.append(violation("length", f"{n} words (about {ctx.min_words}-{ctx.max_words} reads "
                             "best)", "body"))
    tools = [x for x in ic._tools(_facts_without_statement(text, ctx), ctx.pool)
             if not _is_company_word(x, ctx.company)]
    if len(tools) > MAX_TOOLS:
        out.append(violation("tools", f"Names {len(tools)} tools ({', '.join(tools)}): "
                             f"{MAX_TOOLS} at most reads better", "body"))
    figures = [n for n in numbers(_facts_without_statement(text, ctx).split("\n", 1)[-1])]
    if len(figures) > MAX_NUMBERS:
        out.append(violation("numbers", f"{len(figures)} numbers ({', '.join(figures)}): keep "
                             f"at most {MAX_NUMBERS}, only if they make the point", "body"))
    for phrase in ctx.banned:
        key = oc.fold(phrase.replace("’", "'"))
        if key and re.search(rf"\b{re.escape(key)}\b", oc.fold(everything.replace("’", "'"))):
            out.append(violation("banned", f"Banned phrase: “{phrase}”", "body"))
    for j in ctx.jargon:
        if (key := oc.fold(j)) and re.search(rf"\b{re.escape(key)}\b", folded):
            out.append(violation("jargon", f"CV jargon “{j}”", "body"))
    if "!" in everything:
        out.append(violation("tone", "Exclamation mark", "body"))
    mentions = _paragraph_hits(text, ic._PLACE)
    places = [p for p in ctx.places if p and re.search(
        rf"\b{re.escape(oc.fold(p))}\b", folded)]
    if (mentions or places) and not listing_states_location(ctx.job_text):
        out.append(violation("constraint", "The listing states no residency, work-permit, "
                             "on-site or relocation requirement: leave your location, visa and "
                             "relocation out", "body"))
    elif mentions > 1:
        out.append(violation("constraint", "Say where you are and what you'd need once, in one "
                             "place", "body"))
    for draft_id, to, other in ctx.others:
        score = oc.similarity(proof_of(text), proof_of(other)) if v17 and proof_of(
            text) and proof_of(other) else (0.0 if v17 else oc.similarity(text, other))
        if score >= oc.DUPLICATE_THRESHOLD:
            out.append(violation("duplicate", f"{round(score * 100)}% the same as your draft to "
                                 f"{to} (#{draft_id})", "body"))
    return out


def copy_run(text: str, facts: list[str], references: list[str]) -> tuple[int, str]:
    """The longest run of words shared with one pool bullet or style reference, and which."""
    best, where = 0, ""
    for label, group in (("a CV bullet", facts), ("the style reference", references)):
        for source in group:
            run = ic._longest_run(text, source)
            if run > best:
                best, where = run, label
    return best, where


def copies(found: list[dict[str, str]]) -> bool:
    return any(v["type"] == "cv_copy" for v in found)


_INTERNSHIP = re.compile(r"intern|stage|stagiaire|praktik|trainee|apprenti|alternan|thesis|pfe",
                         re.I)


def projects_track_problems(plan: AppliedEmailPlan, ctx: ic.Context) -> list[dict[str, str]]:
    """On a projects track (Settings → Profile: experience "projects") the proof describes
    projects, the graduation project or an internship: never a job, which would read as
    professional experience."""
    if not ctx.honesty or ctx.track not in {t.name for t in ctx.honesty.projects}:
        return []
    out = []
    for i, sentence in enumerate(plan.experience, 1):
        for item_id in sentence.citations:
            item = ctx.pool.items.get(item_id)
            if item is not None and str(item.kind) == "job" and not _INTERNSHIP.search(
                    f"{item.title} {item.org or ''}"):
                out.append(violation(
                    "projects_track", f"{ctx.track} is a projects track: “{sentence.text}” cites "
                    f"“{item.title}”, a job. Describe the work as a project, the graduation "
                    "project or the internship", f"experience {i}", "error"))
                break
    return out


def check_plan(plan: AppliedEmailPlan, ctx: ic.Context,
               recruiter: bool = False) -> list[dict[str, str]]:
    """The proof is the only model-written part: grounded, in plain first person, in pool
    wording. The greeting, opening and ask are code; the whole body gets the v17 rules."""
    from app.services.letter_check import RESTATE_THRESHOLD, _item_terms, _overlap

    out: list[dict[str, str]] = []
    if not plan.experience:
        out.append(violation("experience", "Add one or two sentences of proof from your "
                             "experience", "experience", "error"))
    elif not MIN_SENTENCES <= len(plan.experience) <= MAX_SENTENCES:  # warning: style
        out.append(violation("experience", f"{len(plan.experience)} proof sentences: at "
                             f"most {MAX_SENTENCES}, one sentence each", "experience"))
    facts = [f for item in ctx.pool.items.values() for f in ctx.pool.facts(item)]
    for i, sentence in enumerate(plan.experience, 1):
        where = f"experience {i}"
        out += _visa_banned(sentence.text, where)
        text = _facts_without_statement(sentence.text, ctx)
        if text != sentence.text and len(re.findall(r"\w+", text)) <= 3:
            continue  # only "I have <the years statement>": the years rule checks it
        out += [violation("grounding", f"“{sentence.text}”: {p}", where, "error")
                for p in sentence_problems(
                    SummarySentence(text=text, citations=sentence.citations), ctx.pool,
                    ctx.allowed_years, ctx.years_statement)]
        if len(oc.words(sentence.text)) > MAX_PROOF_WORDS:
            out.append(violation("proof_length", f"{len(oc.words(sentence.text))} words: one "
                                 f"sentence of about {MAX_PROOF_WORDS} words reads best", where))
        run, source = copy_run(sentence.text, facts, ctx.references)
        if run >= COPY_RUN:
            out.append(violation("cv_copy", f"“{sentence.text}” copies {run} words in a row "
                                 f"from {source}: summarize in your own words", where))
        if not _FIRST_PERSON.get(ctx.language, _FIRST_PERSON["en"]).search(sentence.text):
            out.append(violation("fragment", f"“{sentence.text}” isn't a sentence about you: "
                                 "write it with “I”", where))
        terms = _item_terms(ctx.pool, sentence.citations)
        if terms and not any(re.search(rf"\b{re.escape(t)}\b", oc.fold(sentence.text))
                             for t in terms):
            out.append(violation("vague", f"“{sentence.text}” is vague: say what it is and "
                                 "with which tools", where))
    part = " ".join(s.text for s in plan.experience)
    run = ic._longest_run(part, ctx.job_text)
    if run >= 7 or _overlap(part, ctx.job_text) >= RESTATE_THRESHOLD:
        out.append(violation("restates", f"The proof restates the listing ({run} words in a "
                             "row): say it in your own words", "experience"))
    out += projects_track_problems(plan, ctx)
    subject = subject_line(plan.role, ctx.candidate_name, ctx.language, ctx.company)
    if recruiter:
        out += recruiter_problems(plan)
    return out + text_rules(subject, body(plan), ctx, visa_in_whole_text=False, v17=True)


def check_text(subject: str, text: str, ctx: ic.Context) -> list[dict[str, str]]:
    """After you edit: citations are gone, so every number and tool must be in your pool, the
    signals or the listing; the text rules still apply."""
    rest = _facts_without_statement(text, ctx).split("\n", 1)[-1]
    out = [violation("grounding", p, "body", "error")
           for p in oc._source_problems(rest, _source_text(ctx))]
    return (out + _visa_in_edited_text(text, ctx)
            + text_rules(subject, text, ctx, visa_in_whole_text=False, v17=True))

