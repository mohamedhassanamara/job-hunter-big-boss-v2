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

from app.providers.base import AppliedEmailPlan, SummarySentence
from app.services import intro_check as ic
from app.services import outreach_check as oc
from app.services.cv_check import numbers, sentence_problems, violation
from app.services.cv_claims import Vocabulary, bad_years

MIN_WORDS, MAX_WORDS = 90, 170  # a warning outside; the prompt aims at 90-120
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
_VISA_DISCLAIMER_WORDS = re.compile(
    r"\b(?:visas?|sponsorship|sponsor\w*|work authori[sz]ation|work permit|right to work|"
    r"rules me out|relocat\w*)\b", re.I)
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
    return " ".join(re.split(r"\s+[–—|]\s+|\s+-\s+", role.strip())[0].split())


def subject_line(role: str, name: str, language: str) -> str:
    """"<Role> application – <your name>" (French: "Candidature <role> – <name>"); editable."""
    role, name = plain_role(role), " ".join((name or "").split())
    if language == "fr":
        head = f"Candidature {role}" if role else "Candidature"
    else:
        head = f"{role} application" if role else "Application"
    return f"{head} – {name}" if name else head


def body(plan: AppliedEmailPlan) -> str:
    """greeting · opening (+ a signal, when one is used) · experience · ask."""
    opening = " ".join(x for x in (plan.opening.strip(), plan.signal.text.strip()) if x)
    experience = " ".join(s.text.strip() for s in plan.experience)
    parts = [plan.greeting.strip(), opening, experience, plan.ask.strip()]
    return clean("\n\n".join(p for p in parts if p))


def _facts_without_statement(text: str, ctx: ic.Context) -> str:
    return ic._without_statement(text, ctx)


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


def text_rules(subject: str, text: str, ctx: ic.Context) -> list[dict[str, str]]:
    """What any version of the email must satisfy (generated or edited by you)."""
    out: list[dict[str, str]] = []
    folded = oc.fold(text)
    everything = f"{subject}\n{text}"
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
    if ctx.company and oc.fold(ctx.company) not in oc.fold(everything) and (not norm_comp or oc.fold(norm_comp) not in oc.fold(everything)):
        out.append(violation("company", f"The company name “{ctx.company}” isn't mentioned",
                             "body"))
    for claim in bad_years(_facts_without_statement(text, ctx), ctx.allowed_years,
                           ctx.years_statement):
        out.append(violation("years", f"Years claim “{claim}” isn't allowed", "body", "error"))
    from app.services import honesty

    out += honesty.violations(text, ctx.honesty)
    if match := _VISA_DISCLAIMER_WORDS.search(text):
        out.append(violation("visa_disclaimer_banned",
                             f"Cold outreach must never mention visa, sponsorship or relocation caveats (found “{match.group(0)}”)",
                             "body", "error"))
    # --- warnings: style
    if len(ctx.job_text or "") < SNIPPET_CHARS:
        out.append(violation("snippet", "Listing is a short snippet: constraints like residency or "
                             "a language requirement can't be detected. Paste the full description "
                             "or fetch it, then regenerate", "body"))
    n = len(oc.words(text)) - len(oc.words(greeting))
    if n < ctx.min_words or n > ctx.max_words:
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
        score = oc.similarity(text, other)
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


def check_plan(plan: AppliedEmailPlan, ctx: ic.Context) -> list[dict[str, str]]:
    from app.services.letter_check import RESTATE_THRESHOLD, _item_terms, _overlap

    out: list[dict[str, str]] = []
    if not plan.opening.strip():
        out.append(violation("opening", "Say that you applied (or are applying) for the role",
                             "opening", "error"))
    elif match := _VISA_DISCLAIMER_WORDS.search(plan.opening):
        out.append(violation("visa_disclaimer_banned",
                             f"Opening contains banned disclaimer “{match.group(0)}”: cold outreach must never mention visa, sponsorship or relocation",
                             "opening", "error"))
    if not plan.experience:
        out.append(violation("experience", "Add one or two proofs of relevant experience",
                             "experience", "error"))
    elif not MIN_SENTENCES <= len(plan.experience) <= MAX_SENTENCES:  # warning: style
        out.append(violation("experience", f"{len(plan.experience)} experience sentences: at "
                             f"most {MAX_SENTENCES} proofs, one sentence each", "experience"))
    facts = [f for item in ctx.pool.items.values() for f in ctx.pool.facts(item)]
    for i, sentence in enumerate(plan.experience, 1):
        where = f"experience {i}"
        if match := _VISA_DISCLAIMER_WORDS.search(sentence.text):
            out.append(violation("visa_disclaimer_banned",
                                 f"Experience contains banned disclaimer “{match.group(0)}”: cold outreach must never mention visa, sponsorship or relocation",
                                 where, "error"))
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
    if len(oc.words(plan.opening)) > MAX_OPENING_WORDS:
        out.append(violation("opening", f"Keep the opening to saying you applied "
                             f"(about {MAX_OPENING_WORDS} words): reasons and fit belong in the "
                             "experience", "opening"))
    # Company facts: the opening and the ask only restate who and what; any number or tool in
    # them must come from the pool, the listing or the signals.
    source = _source_text(ctx)
    for label, part in (("opening", plan.opening), ("ask", plan.ask)):
        out += [violation("grounding", f"The {label}: {p}", label, "error")
                for p in oc._source_problems(part, source)]
    if plan.signal.text.strip():
        unknown = [i for i in plan.signal.signal_ids if i not in ctx.signals]
        if not plan.signal.signal_ids or unknown:
            out.append(violation("signal", "A company fact must cite a selected signal"
                                 + (f" (not selected: {unknown})" if unknown else ""),
                                 "signal", "error"))
        else:
            cited = " ".join(ctx.signals[i] for i in plan.signal.signal_ids) + f" {ctx.company}"
            digits = {re.sub(r"[^\d]", "", n) for n in numbers(cited)}
            vocab = Vocabulary(cited)
            out += [violation("signal", f"The signal sentence: “{n}” isn't in the signals",
                              "signal", "error")
                    for n in numbers(plan.signal.text)
                    if re.sub(r"[^\d]", "", n) not in digits]
            out += [violation("signal", f"The signal sentence: “{t}” isn't in the signals",
                              "signal", "error")
                    for t in ic._tools(plan.signal.text) if not vocab.knows(t)]
            if _INFERENCE.search(plan.signal.text):
                out.append(violation("signal", "Say what the fact is, not what it shows about "
                                     "them: that is a guess", "signal"))
            if ic._longest_run(plan.signal.text, " ".join(
                    ctx.signals[i] for i in plan.signal.signal_ids)) >= _SIGNAL_RUN:
                out.append(violation("signal", "Don't recite the company's own description back "
                                     "to them: say what struck you, in your words", "signal"))
    for label, part in (("experience", " ".join(s.text for s in plan.experience)),):
        run = ic._longest_run(part, ctx.job_text)
        if run >= 7 or _overlap(part, ctx.job_text) >= RESTATE_THRESHOLD:
            out.append(violation("restates", f"The {label} restates the listing ({run} words in "
                                 "a row): say it in your own words", label))
    subject = subject_line(plan.role, ctx.candidate_name, ctx.language)
    return out + text_rules(subject, body(plan), ctx)


def check_text(subject: str, text: str, ctx: ic.Context) -> list[dict[str, str]]:
    """After you edit: citations are gone, so every number and tool must be in your pool, the
    signals or the listing; the text rules still apply."""
    rest = _facts_without_statement(text, ctx).split("\n", 1)[-1]
    out = [violation("grounding", p, "body", "error")
           for p in oc._source_problems(rest, _source_text(ctx))]
    return out + text_rules(subject, text, ctx)

