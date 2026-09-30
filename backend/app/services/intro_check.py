"""Checks for the cold email as a personal introduction (prompt v4+). No model calls.

The email: greeting · hook (how you came across the company + 1-2 verified signals) · intro
(built by code) · value (their problem + 1-2 proofs from your pool) · a direct question about an
opening. Never the listing, the role, your location or visa; company facts only from the
selected signals, facts about you only from your pool. Wording never copied from the reference
examples or from drafts to other people.
"""

import re
from dataclasses import dataclass, field

from app.providers.base import IntroEmailPlan, SummarySentence
from app.services import outreach_check as oc
from app.services.cv_check import new_tools, numbers, sentence_problems, violation
from app.services.cv_claims import Vocabulary, bad_years, short_form, strip_statement
from app.services.cv_pool import Pool

MIN_WORDS, MAX_WORDS = 100, 150
EXAMPLE_SIMILARITY, EXAMPLE_RUN = 0.25, 8
_LISTING = re.compile(
    r"\b(?:job (?:listing|posting|post|ad|offer|description)|listing|the role|this role|your "
    r"role|the position|this position|position you posted|you(?:'ve| have)? posted|opening you "
    r"posted|vacancy|votre offre|l'offre|cette offre|l'annonce|votre annonce|cette annonce|le "
    r"poste|ce poste|votre poste|fiche de poste|candidature|postuler|recrutez)\b", re.I)
_PLACE = re.compile(
    r"\b(?:visa|sponsor\w*|parrainage|work authori[sz]ation|work permit|permis de travail|"
    r"titre de séjour|autorisation de travail|relocat\w*|based in|basé|basée|installé|"
    r"nationalit\w*|citizen\w*)\b", re.I)
_OPENING_ASK = re.compile(
    r"\b(?:opening|openings|opportunit\w*|hiring|position|role|team|place|ouverture|"
    r"opportunité|poste|recrut\w*|besoin|place)\b", re.I)
_SUBJECT_BAD = re.compile(r"^\s*(?:re|fwd?|tr)\s*:|\b(?:role|position|application|apply|"
                          r"job|poste|candidature|offre|recrutement)\b", re.I)


@dataclass
class Context:
    pool: Pool
    allowed_years: set[int]
    job_title: str
    job_text: str  # the listing (private intel: never quoted)
    company: str
    first_name: str  # the contact's
    signals: dict[int, str]  # selected signal id → fact + quote
    intro_line: str  # built by code
    language: str = "en"
    years_statement: str | None = None
    years_statement_fr: str | None = None
    banned: list[str] = field(default_factory=list)
    jargon: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)  # your city, country, nationality
    examples: list[tuple[str, str]] = field(default_factory=list)  # (label, text)
    others: list[tuple[int, str, str]] = field(default_factory=list)  # drafts to others
    min_words: int = MIN_WORDS
    max_words: int = MAX_WORDS


def intro_line(first_name: str, focus: str, language: str, statement: str | None,
               statement_fr: str | None, fallback_years: str | None = None) -> str:
    """"I'm Alex, a software engineer with 3 years of experience in backend, mobile and AI
    systems." (the short form of your years wording sits next to "software engineer", as the CV
    rules allow; French keeps the full wording)."""
    focus = re.sub(r"^(?:in|sur des|sur les|en)\s+", "", focus.strip().rstrip("."), flags=re.I)
    if language == "fr":
        years = statement_fr or (f"{fallback_years} d'expérience" if fallback_years else "")
        line = f"Je suis {first_name}, ingénieur logiciel" + (f" avec {years}" if years else "")
        return f"{line}, sur des {focus}." if focus else f"{line}."
    short = short_form(statement) if statement else None
    years = short[0] if short else (f"{fallback_years} of experience" if fallback_years else "")
    line = f"I'm {first_name}, a software engineer" + (f" with {years}" if years else "")
    return f"{line} in {focus}." if focus else f"{line}."


def body(plan: IntroEmailPlan, intro: str) -> str:
    """greeting · hook · intro · value · ask (the text you review; no signature)."""
    value = " ".join([plan.problem.strip(), *(p.text.strip() for p in plan.proofs)]).strip()
    parts = [plan.greeting.strip(), plan.hook.text.strip(), intro, value, plan.ask.strip()]
    return "\n\n".join(p for p in parts if p)


def _longest_run(a: str, b: str) -> int:
    from app.services.letter_check import _longest_run, _plain

    return _longest_run(oc.fold(_plain(a)).split(), oc.fold(_plain(b)).split())


def _tools(text: str) -> list[str]:
    return new_tools(text, Vocabulary(""))


def _without_statement(text: str, ctx: Context) -> str:
    from app.services.letter_check import _strip_fr

    text = _strip_fr(text, ctx.years_statement_fr)
    return strip_statement(text, ctx.years_statement) if ctx.years_statement else text


def text_rules(subject: str, text: str, ctx: Context) -> list[dict[str, str]]:
    """The rules any version of the email must pass (generated or edited by you)."""
    out: list[dict[str, str]] = []
    everything = f"{subject}\n{text}"
    for m in _LISTING.finditer(text):
        out.append(violation("listing", f"“{m.group(0)}”: the email never mentions the listing "
                             "or the role (it's an introduction)", "body", "error"))
        break
    title = oc.fold(ctx.job_title)
    if len(title.split()) >= 2 and title in oc.fold(text):
        out.append(violation("listing", f"Names the job title “{ctx.job_title}”", "body",
                             "error"))
    place = _PLACE.search(text)
    folded = oc.fold(text)
    places = [p for p in ctx.places if p and re.search(rf"\b{re.escape(oc.fold(p))}\b", folded)]
    if place or places:
        found = place.group(0) if place else places[0]
        out.append(violation("location", f"“{found}”: never mention where you are, your "
                             "nationality, visa or work authorization", "body", "error"))
    if not subject.strip():
        out.append(violation("subject", "The subject is empty", "subject", "error"))
    elif _SUBJECT_BAD.search(subject):
        out.append(violation("subject", "The subject is about the value, never the role, an "
                             "application or a fake reply", "subject", "error"))
    elif len(oc.words(subject)) > 8:
        out.append(violation("subject", "The subject is long (8 words at most)", "subject"))
    n = len(oc.words(text)) - len(oc.words(text.split("\n", 1)[0]))  # without the greeting
    if n < ctx.min_words or n > ctx.max_words:
        out.append(violation("length", f"{n} words (aim for {ctx.min_words}-{ctx.max_words})",
                             "body", "error"))
    if ctx.first_name and oc.fold(ctx.first_name) not in oc.fold(text.split("\n", 1)[0]):
        out.append(violation("name", f"The greeting doesn't use {ctx.first_name}'s first name",
                             "greeting", "error"))
    if ctx.intro_line and ctx.intro_line not in text:
        out.append(violation("intro", f"The intro line changed: keep “{ctx.intro_line}”",
                             "body", "error"))
    last = [p for p in text.split("\n\n") if p.strip()][-1:] or [""]
    if not (last[0].rstrip().endswith("?") and _OPENING_ASK.search(last[0])):
        out.append(violation("ask", "End with a direct question about an opening", "ask",
                             "error"))
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(_tools(sentence)) > 3:
            out.append(violation("tools", f"“{sentence}” lists {len(_tools(sentence))} tools: at "
                                 "most 3 in a sentence", "body", "error"))
    for phrase in ctx.banned:
        key = oc.fold(phrase.replace("’", "'"))
        if key and re.search(rf"\b{re.escape(key)}\b", oc.fold(everything.replace("’", "'"))):
            out.append(violation("banned", f"Banned phrase: “{phrase}”", "body", "error"))
    for j in ctx.jargon:
        if (key := oc.fold(j)) and re.search(rf"\b{re.escape(key)}\b", folded):
            out.append(violation("jargon", f"CV jargon “{j}”", "body", "error"))
    if "!" in everything:
        out.append(violation("tone", "Exclamation mark", "body"))
    for claim in bad_years(_without_statement(text.replace(ctx.intro_line, " "), ctx),
                           ctx.allowed_years, ctx.years_statement):
        out.append(violation("years", f"Years claim “{claim}” isn't allowed", "body", "error"))
    for label, example in ctx.examples:
        score, run = oc.similarity(text, example), _longest_run(text, example)
        if score >= EXAMPLE_SIMILARITY or run >= EXAMPLE_RUN:
            out.append(violation("example_copy", f"Too close to the example “{label}” "
                                 f"({round(score * 100)}% shared, {run} words in a row): write "
                                 "it fresh", "body", "error"))
    for draft_id, to, other in ctx.others:
        score = oc.similarity(text, other)
        if score >= oc.DUPLICATE_THRESHOLD:
            out.append(violation("duplicate", f"{round(score * 100)}% the same as your draft to "
                                 f"{to} (#{draft_id})", "body"))
    return out


def _signal_problems(text: str, ids: list[int], ctx: Context) -> list[str]:
    source = " ".join(ctx.signals[i] for i in ids if i in ctx.signals) + f" {ctx.company}"
    digits = {re.sub(r"[^\d]", "", n) for n in numbers(source)}
    out = [f"“{n}” isn't in the selected signals" for n in numbers(text)
           if re.sub(r"[^\d]", "", n) not in digits]
    vocab = Vocabulary(source)
    return out + [f"“{t}” isn't in the selected signals" for t in _tools(text)
                  if not vocab.knows(t)]


def check_plan(plan: IntroEmailPlan, ctx: Context) -> list[dict[str, str]]:
    from app.services.letter_check import (
        DEFAULT_JARGON,
        RESTATE_THRESHOLD,
        _item_terms,
        _overlap,
    )

    out: list[dict[str, str]] = []
    if not ctx.signals:
        out.append(violation("needs_signal", "Needs a signal: pick or add one about the company "
                             "(Signals panel), then regenerate", "hook", "error"))
    elif not plan.hook.text.strip() or not plan.hook.signal_ids:
        out.append(violation("needs_signal", "The hook doesn't use a selected signal", "hook",
                             "error"))
    else:
        unknown = [i for i in plan.hook.signal_ids if i not in ctx.signals]
        if unknown:
            out.append(violation("hook", f"Cites signals that aren't selected: {unknown}",
                                 "hook", "error"))
        out += [violation("hook", f"The hook: {p}", "hook", "error")
                for p in _signal_problems(plan.hook.text, plan.hook.signal_ids, ctx)]
    for label, part in (("hook", plan.hook.text), ("problem", plan.problem)):
        if not part.strip():
            continue
        run = _longest_run(part, ctx.job_text)
        if run >= 7 or _overlap(part, ctx.job_text) >= RESTATE_THRESHOLD:
            out.append(violation("restates", f"The {label} restates the listing ({run} words in "
                                 "a row): say it in your own words", label, "error"))
    listing_source = f"{ctx.job_text}\n" + " ".join(ctx.signals.values())
    email_ctx = oc.Context(pool=ctx.pool, allowed_years=ctx.allowed_years,
                           job_text=listing_source, company=ctx.company, first_name="")
    out += [violation("problem", f"The problem: {p}", "problem", "error")
            for p in oc._about_job_problems(plan.problem, email_ctx)]
    if not 1 <= len(plan.proofs) <= 2:
        out.append(violation("proofs", f"{len(plan.proofs)} proofs: one, at most two", "value",
                             "error"))
    facts = [f for item in ctx.pool.items.values() for f in ctx.pool.facts(item)]
    for i, proof in enumerate(plan.proofs, 1):
        where = f"proof {i}"
        text = _without_statement(proof.text, ctx)
        out += [violation("grounding", f"“{proof.text}”: {p}", where, "error")
                for p in sentence_problems(SummarySentence(text=text, citations=proof.citations),
                                           ctx.pool, ctx.allowed_years, ctx.years_statement)]
        if any(_overlap(proof.text, f) >= RESTATE_THRESHOLD for f in facts):
            out.append(violation("cv_copy", f"“{proof.text}” reads like a CV bullet", where,
                                 "error"))
        terms = _item_terms(ctx.pool, proof.citations)
        if terms and not any(re.search(rf"\b{re.escape(t)}\b", oc.fold(proof.text))
                             for t in terms):
            out.append(violation("vague", f"“{proof.text}” is vague: say what it is and with "
                                 "which tools", where, "error"))
    if not ctx.jargon:
        ctx.jargon = list(DEFAULT_JARGON)
    return out + text_rules(plan.subject, body(plan, ctx.intro_line), ctx)


def check_text(subject: str, text: str, ctx: Context) -> list[dict[str, str]]:
    """After you edit: citations are gone, so every number and tool must be in your pool, the
    signals or the listing; the text rules still apply."""
    source = f"{ctx.job_text}\n" + " ".join(ctx.signals.values())
    email_ctx = oc.Context(pool=ctx.pool, allowed_years=ctx.allowed_years, job_text=source,
                           company=ctx.company, first_name="")
    rest = _without_statement(text.replace(ctx.intro_line, " "), ctx)
    out = [violation("grounding", p, "body", "error")
           for p in oc._source_problems(rest.split("\n", 1)[-1], email_ctx)]
    if not ctx.signals:
        out.append(violation("needs_signal", "Needs a signal: pick or add one about the company",
                             "hook", "error"))
    return out + text_rules(subject, text, ctx)

