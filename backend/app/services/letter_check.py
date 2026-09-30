"""Automatic checks for a cover letter and for application answers. No model calls.

Grounding is the cold email's: every candidate sentence cites pool items and states only what
they say (numbers, tools, capabilities, scope, years); a sentence about the company or the role
states only what the listing says. A paragraph you edited loses its citations, so its numbers and
tools must appear in your experience or the listing. Then the letter rules: word range, 3-4
paragraphs, an opening that names the company and something from the listing, 2-3 concrete
builds, exactly one ask at the end, per-language banned phrases, and the exact years wording
(also in French: "3 ans d'expérience en ingénierie logicielle").
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.providers.base import EmailSentence, SummarySentence
from app.services import outreach_check as oc
from app.services.cv_check import sentence_problems, violation
from app.services.cv_claims import bad_years, strip_statement
from app.services.cv_pool import Pool

DEFAULT_BANNED: dict[str, list[str]] = {
    "fr": [
        "je me permets de", "passionné", "passionnée", "passion pour", "dynamique et motivé",
        "dynamique et motivée", "motivé et dynamique", "n'hésitez pas", "force de proposition",
        "vif intérêt", "c'est avec un grand intérêt", "c'est avec enthousiasme",
        "je suis convaincu que je suis le candidat idéal", "candidat idéal", "rigoureux et",
        "esprit d'équipe", "sens du relationnel", "polyvalent", "curieux et",
        "dans l'attente de votre réponse", "veuillez agréer", "à qui de droit",
        "je vous écris pour",
        "relever de nouveaux défis", "sortir de ma zone de confort",
    ],
    "en": [
        "i am writing to express my interest", "i am writing to apply", "i'm writing to",
        "to whom it may concern", "dear sir or madam", "passionate", "passion for",
        "hardworking", "hard-working", "hard worker", "team player", "fast learner",
        "quick learner", "self-starter", "results-driven", "detail-oriented", "go-getter",
        "think outside the box", "synergy", "perfect fit", "ideal candidate", "dream job",
        "i believe i would be a great fit", "i am confident that i am", "look no further",
        "thank you for your time and consideration", "i would love the opportunity",
        "dynamic", "rockstar", "ninja", "guru",
    ],
}
DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS = 150, 260  # one listing sentence + 2 short examples
FORM_MIN_WORDS, FORM_MAX_WORDS = 80, 220
# CV shorthand that reads badly in a letter (checked in both languages; Settings can extend it).
DEFAULT_JARGON = [
    "schema drift", "collision class", "collision classes", "idempotent", "star schema",
    "entity resolution", "retry-safe", "dependency-chained", "end-to-end local",
    "dérive de schéma", "classes de collisions", "schéma en étoile", "résolution d'entités",
    "idempotents", "chaînés par dépendances",
]
_TEST_COUNT = re.compile(r"\b\d+\s*/\s*\d+\s+(?:tests?|checks?)\b|\b\d+\s*/\s*\d+\s+tests?\s+"
                         r"réussis\b|\btests? réussis\b", re.I)
# Letter furniture that doesn't belong in a form's text box.
_FORM_FURNITURE = re.compile(
    r"\b(?:madame,? monsieur|dear\b|objet\s*:|cordialement|salutations|je vous prie|"
    r"kind regards|best regards|sincerely|to whom)", re.I)
RESTATE_THRESHOLD = 0.5  # 3-word overlap of a sentence with the listing / a CV bullet
FR_STATEMENT = "{n} ans d'expérience en ingénierie logicielle"

_FR_NUMBERS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
               "sept": 7, "huit": 8, "neuf": 9, "dix": 10}
_FR_YEARS = re.compile(r"\b(?:plus de|près de|environ|presque)?\s*(\d+|"
                       + "|".join(_FR_NUMBERS) + r")\s*(\+)?\s*ans?\b", re.I)
_FR_STATEMENT = re.compile(r"^(\d+) ans d'expérience en (.+)$", re.I)
# A request that ends a letter without a question mark ("I'd welcome a call…").
_ASK = re.compile(
    r"\?|\b(?:welcome|glad|happy|keen|available|discuss|talk|conversation|interview|call|"
    r"meet|serais|serai|ravi|ravie|heureux|heureuse|disponible|échanger|entretien|"
    r"rencontrer|discuter)\b", re.I)


@dataclass
class Context:
    pool: Pool
    allowed_years: set[int]
    job_text: str  # title + listing
    company: str
    language: str = "en"  # fr | en
    banned: list[str] = field(default_factory=list)
    min_words: int = DEFAULT_MIN_WORDS
    max_words: int = DEFAULT_MAX_WORDS
    years_statement: str | None = None  # English exact wording (Settings → Candidate)
    years_statement_fr: str | None = None  # its French equivalent
    other_companies: list[str] = field(default_factory=list)  # in your other letters
    contact_name: str = ""
    format: str = "pdf"  # pdf | form
    char_limit: int | None = None  # form: the text box's limit
    jargon: list[str] = field(default_factory=lambda: list(DEFAULT_JARGON))
    current_role_id: int | None = None  # your current role, when it matches this listing
    current_role_org: str = ""
    facts_text: str = ""  # Settings → Candidate: where you're based, authorization, languages
    mention_authorization: bool = False  # Settings → Letters and emails (and the listing)
    company_reason: str = ""  # your one-line reason for this company (the job's field)

    def email_context(self) -> oc.Context:
        return oc.Context(pool=self.pool, allowed_years=self.allowed_years,
                          job_text=self.job_text, company=self.company, first_name="",
                          banned=[], years_statement=self.years_statement)


def french_statement(statement: str | None, override: str = "") -> str | None:
    """The French wording of the exact years statement (Settings → Cover letter can set it)."""
    if not statement:
        return None
    if override.strip():
        return override.strip()
    m = re.match(r"^(\d+) years? of software engineering experience$", statement.strip(), re.I)
    return FR_STATEMENT.format(n=m.group(1)) if m else None


def _strip_fr(text: str, statement: str | None) -> str:
    """Remove the French exact wording, and "3 ans d'expérience" in a sentence that already says
    "ingénieur logiciel" (the short form, as in English)."""
    if not statement:
        return text
    m = _FR_STATEMENT.match(statement)
    short = f"{m.group(1)} ans d'expérience" if m else None
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.replace("’", "'")):
        sentence = re.sub(re.escape(statement), " ", sentence, flags=re.I)
        if short and re.search(r"\bingénieur(?:e)? logiciel", sentence, re.I):
            sentence = re.sub(re.escape(short), " ", sentence, flags=re.I)
        out.append(sentence)
    return " ".join(out)


def years_problems(text: str, ctx: Context) -> list[str]:
    """Years claims other than the allowed wording, in English or French."""
    text = _strip_fr(text, ctx.years_statement_fr)
    out = bad_years(text, ctx.allowed_years, ctx.years_statement)
    if ctx.years_statement:
        text = strip_statement(text, ctx.years_statement)
    for m in _FR_YEARS.finditer(text):
        raw = m.group(1).lower()
        value = int(_FR_NUMBERS.get(raw, raw))
        if ctx.years_statement or value not in ctx.allowed_years:
            out.append(m.group(0).strip())
    return out


def _years_message(claim: str, ctx: Context) -> str:
    wording = ctx.years_statement_fr if ctx.language == "fr" else ctx.years_statement
    return f"Years claim “{claim}” isn't allowed" + (f": write exactly “{wording}”"
                                                     if wording else "")


_GROUPED = re.compile(r"(?<![\d.,])(\d{1,3})(?:[ \u00a0\u202f,](\d{3}))+(?![\d])")


def _ungroup(text: str) -> str:
    """"2 000" (French) and "2,000" → "2000", so a number compares with the pool's "~2,000"."""
    return _GROUPED.sub(lambda m: re.sub(r"[ \u00a0\u202f,]", "", m.group(0)), text)


def _states_years(text: str, ctx: Context) -> bool:
    folded = text.replace("’", "'").lower()
    return any(s and s.lower() in folded for s in (ctx.years_statement, ctx.years_statement_fr)) \
        or bool(years_problems(text, Context(pool=ctx.pool, allowed_years=set(),
                                             job_text="", company="")))


_RELOCATION = re.compile(r"\b(?:relocat\w*|move to|moving to|m'install\w*|installer|"
                         r"déménag\w*|demenag\w*|mobilité géographique)", re.I)


def _candidate_fact_problems(text: str, ctx: Context) -> list[str]:
    """A fit sentence from Settings → Candidate: only what the profile says (your exact years
    statement counts)."""
    stripped = strip_statement(_strip_fr(text, ctx.years_statement_fr), ctx.years_statement) \
        if ctx.years_statement else text
    if stripped.strip(" .") != text.strip(" .") and len(oc.words(stripped)) <= 3:
        return []  # just your years statement
    out = []
    if _RELOCATION.search(text.replace("’", "'")):
        out.append("relocating isn't in your profile (Settings → Candidate)")
    facts = oc.fold(ctx.facts_text)
    words = [w for w in oc.fold(text).split() if len(w) >= 4]
    if not any(w in facts for w in words):
        out.append("states nothing from your profile (where you're based, work authorization, "
                   "languages)")
    source = Context(pool=ctx.pool, allowed_years=ctx.allowed_years,
                     job_text=f"{ctx.job_text}\n{ctx.facts_text}", company=ctx.company)
    return out + oc._source_problems(text, source.email_context())


def _grounding(sentence: EmailSentence, ctx: Context) -> list[str]:
    email = ctx.email_context()
    sentence = sentence.model_copy(update={"text": _ungroup(sentence.text)})
    if sentence.about_candidate and not sentence.citations:
        return _candidate_fact_problems(sentence.text, ctx)
    if sentence.about_job and not sentence.citations:
        return oc._about_job_problems(_strip_fr(sentence.text, ctx.years_statement_fr), email)
    text = oc._claims_only(_strip_fr(sentence.text, ctx.years_statement_fr), email)
    problems = sentence_problems(SummarySentence(text=text, citations=sentence.citations),
                                 ctx.pool, ctx.allowed_years, ctx.years_statement)
    return [p for p in problems if "years claim" not in p]  # reported once, by the lint


def _built_items(sentences: list[EmailSentence], ctx: Context) -> set[int]:
    """Roles/projects cited by candidate sentences: the concrete things the letter shows."""
    kinds = {"job", "project", "volunteering"}
    return {c for s in sentences if not s.about_job for c in s.citations
            if (item := ctx.pool.get(c)) is not None and item.kind in kinds}


def _banned(text: str, ctx: Context) -> list[dict[str, str]]:
    folded = oc.fold(text.replace("’", "'"))
    out = []
    for phrase in ctx.banned:
        key = oc.fold(phrase.replace("’", "'"))
        if key and re.search(rf"\b{re.escape(key)}\b", folded):
            out.append(violation("banned", f"Banned phrase: “{phrase}”", "letter", "error"))
    return out


def _plain(text: str) -> str:
    """Curly apostrophes and quotes as plain ones, so “d’IA” and “d'IA” compare equal."""
    return text.replace("’", "'").replace("‘", "'").replace("‑", "-")


def _overlap(text: str, source: str) -> float:
    """Share of the text's 3-word shingles found in the source (after folding)."""
    mine = oc.shingles(_plain(text))
    return len(mine & oc.shingles(_plain(source))) / len(mine) if len(mine) >= 3 else 0.0


def _jargon(text: str, ctx: Context) -> list[dict[str, str]]:
    folded = oc.fold(text.replace("’", "'"))
    out = [violation("jargon", f"CV jargon “{j}”: say what it means for them in plain words",
                     "letter", "error")
           for j in ctx.jargon if (key := oc.fold(j)) and re.search(rf"\b{re.escape(key)}\b",
                                                                    folded)]
    out += [violation("jargon", f"“{m.group(0)}” is CV detail: say what it changed instead",
                      "letter", "error") for m in _TEST_COUNT.finditer(text)]
    return out


def lint(salutation: str, paragraphs: list[str], ask: str | None,
         ctx: Context) -> list[dict[str, str]]:
    """Checks on the text, whoever wrote it. The ask is its own final paragraph (PDF letter);
    a form text has no salutation or closing formula, and may end without one."""
    out: list[dict[str, str]] = []
    form = ctx.format == "form"
    body = [p for p in paragraphs if p.strip()]
    ask = (ask or "").strip()
    everything = " ".join([salutation, *body, ask])
    n = len(oc.words(" ".join([*body, ask])))
    if n < ctx.min_words or n > ctx.max_words:
        out.append(violation("length", f"{n} words (aim for {ctx.min_words}-{ctx.max_words})",
                             "letter", "error"))
    if form:
        text = "\n\n".join([*body, ask] if ask else body)
        if ctx.char_limit and len(text) > ctx.char_limit:
            out.append(violation("length", f"{len(text)}/{ctx.char_limit} characters", "letter",
                                 "error"))
        if not 1 <= len(body) <= 3:
            out.append(violation("structure", f"{len(body)} paragraphs (1-3 for a form)",
                                 "letter", "error"))
        if salutation.strip() or (m := _FORM_FURNITURE.search(" ".join([*body, ask]))):
            found = salutation.strip() or m.group(0)
            out.append(violation("form", f"“{found}”: a form's text box has no salutation, "
                                 "subject or closing formula", "letter", "error"))
    else:
        if not 2 <= len(body) <= 3:
            out.append(violation("structure", f"{len(body)} paragraphs before the ask (2-3)",
                                 "letter", "error"))
        if not salutation.strip():
            out.append(violation("salutation", "The salutation is empty", "salutation",
                                 "error"))
        elif ctx.contact_name and oc.fold(ctx.contact_name.split(" ")[-1]) not in oc.fold(
                salutation):
            out.append(violation("salutation", f"The salutation doesn't name {ctx.contact_name}",
                                 "salutation"))
        if not ask or not _ASK.search(ask):
            out.append(violation("ask", "End with one clear ask (an interview or a call), in "
                                 "its own short paragraph", "ask", "error"))
    if ask and (len(oc.words(ask)) > 35 or len(re.findall(r"[.!?](?:\s|$)", ask)) > 2):
        out.append(violation("ask", "The ask is one or two short sentences (at most 35 words)",
                             "ask", "error"))
    if body and oc.fold(ctx.company) not in oc.fold(body[0]):
        out.append(violation("opening", f"The first paragraph doesn't name {ctx.company}",
                             "paragraph 1", "warning" if form else "error"))
    if sum(p.count("?") for p in body):
        out.append(violation("ask", "Only one ask, at the end: a question appears earlier",
                             "letter", "error"))
    folded = oc.fold(everything)
    for other in ctx.other_companies:
        if other and oc.fold(other) != oc.fold(ctx.company) and re.search(
                rf"\b{re.escape(oc.fold(other))}\b", folded):
            out.append(violation("company", f"Mentions “{other}”, the company of another "
                                 "letter", "letter", "error"))
    out += _banned(everything, ctx)
    out += _jargon(" ".join([*body, ask]), ctx)
    if "!" in everything:
        out.append(violation("tone", "Exclamation mark", "letter"))
    out += [violation("years", _years_message(c, ctx), "letter", "error")
            for c in years_problems(everything, ctx)]
    return out


# Work authorization / visa talk (Settings → Letters and emails decides when it may appear).
_AUTHORIZATION = re.compile(
    r"\b(?:visa|sponsor\w*|parrainage|work authori[sz]ation|authori[sz]ed to work|"
    r"right to work|work permit|permis de travail|autorisation de travail|titre de séjour|"
    r"autorisé à travailler)", re.I)
# Methods/practices a listing lists as requirements (tools are detected like everywhere else).
_METHODS = {"agile", "scrum", "kanban", "mvc", "tdd", "ci/cd", "devops", "microservices",
            "cloud", "api", "apis", "rest", "restful", "etl", "elt", "sql", "nosql", "git"}


def listing_asks_authorization(job_text: str) -> bool:
    return bool(_AUTHORIZATION.search(job_text or ""))


def _listing_terms(sentence: str, job_text: str) -> set[str]:
    """Tools and methods of the listing that the sentence repeats."""
    from app.services.cv_check import new_tools
    from app.services.cv_claims import Vocabulary

    listing = Vocabulary(job_text)
    empty = Vocabulary("")
    tools = {t.lower() for t in new_tools(sentence, empty) if listing.knows(t)}
    words = {w.lower().strip(".,;:()") for w in sentence.split()}
    methods = {m for m in _METHODS if m in words and m in job_text.lower()}
    return tools | methods


def _item_terms(pool: Pool, ids: list[int]) -> set[str]:
    """What a cited item is made of: its tags and the tools its facts name."""
    from app.services.cv_check import new_tools
    from app.services.cv_claims import Vocabulary

    out: set[str] = set()
    for item_id in ids:
        item = pool.get(item_id)
        if item is None:
            continue
        out |= {oc.fold(t.replace("-", " ")) for t in item.tags if t.strip()}
        out |= {oc.fold(x) for f in pool.facts(item) for x in new_tools(f, Vocabulary(""))}
    return {t for t in out if t}


COPIED_RUN = 7  # consecutive words taken from the listing


def _longest_run(words: list[str], source: list[str]) -> int:
    """Length of the longest run of consecutive words shared with the source."""
    best, prev = 0, [0] * (len(source) + 1)
    for w in words:
        cur = [0] * (len(source) + 1)
        for j, s in enumerate(source, 1):
            if w == s:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def writing_rules(paragraphs: list[dict[str, Any]], ctx: Context) -> list[dict[str, str]]:
    """The writing guide, checked in code for letters, form texts and emails alike:
    no restating the listing or its task list, no pasted CV bullets, your reason in the opening
    (rephrased), examples that stay concrete (what it is, with which tools), at most 2 of them,
    your current role when it matches, and no work-authorization talk unless allowed."""
    out: list[dict[str, str]] = []
    facts = [f for item in ctx.pool.items.values() for f in ctx.pool.facts(item)]
    units = []  # (paragraph, sentence): the model's own sentences, or your text split up
    for i, p in enumerate(paragraphs, 1):
        if "sentences" in p:
            units += [(i, str(x.get("text") or "")) for x in p["sentences"]]
        else:
            units += [(i, x) for x in re.split(r"(?<=[.!?])\s+", str(p.get("text") or ""))]
    listing_words = oc.fold(_plain(ctx.job_text)).split()
    for i, sentence in units:
        where = f"paragraph {i}"
        run = _longest_run(oc.fold(_plain(sentence)).split(), listing_words)
        if run >= COPIED_RUN:
            out.append(violation("restates", f"“{sentence}” copies {run} words in a row from the "
                                 "listing: say it in your own words", where, "error"))
        elif _overlap(sentence, ctx.job_text) >= RESTATE_THRESHOLD:
            out.append(violation("restates", f"“{sentence}” restates the listing: say why it "
                                 "matters to you instead", where, "error"))
        elif any(_overlap(sentence, f) >= RESTATE_THRESHOLD for f in facts):
            out.append(violation("cv_copy", f"“{sentence}” reads like a CV bullet: explain what "
                                 "it means for them in plain words", where, "error"))
        if not ctx.mention_authorization and _AUTHORIZATION.search(sentence):
            out.append(violation("authorization", f"“{sentence}”: work authorization isn't "
                                 "mentioned unless the listing asks (Settings → Letters and "
                                 "emails)", where, "error"))
        if ctx.company_reason and _overlap(sentence, ctx.company_reason) >= 0.6:
            out.append(violation("reason", f"“{sentence}” copies your reason word for word: "
                                 "rephrase it", where, "error"))
    first = " ".join(x for i, x in units if i == 1)
    if ctx.company_reason:
        wanted = {w for w in oc.fold(ctx.company_reason).split() if len(w) >= 5}
        if wanted and len(wanted & set(oc.fold(first).split())) < min(2, len(wanted)):
            out.append(violation("reason", "The opening doesn't use your reason for this "
                                 "company", "paragraph 1", "error"))
    generated = [EmailSentence.model_validate(x) for p in paragraphs
                 for x in p.get("sentences") or []]
    for s in generated:
        if s.about_job and len(terms := _listing_terms(s.text, ctx.job_text)) >= 2:
            out.append(violation("task_list", f"“{s.text}” lists the listing's requirements "
                                 f"({', '.join(sorted(terms))}): pick one specific thing",
                                 "paragraph 1", "error"))
    if generated:
        about = [s for s in generated if s.about_job]
        if len(about) > 1:
            out.append(violation("listing", f"{len(about)} sentences about the listing: at most "
                                 "one, in the opening", "letter", "error"))
    if generated and all("sentences" in p for p in paragraphs):
        # Examples are the roles/projects cited after the opening; a sentence stating the years
        # cites roles only to back that number.
        body = [EmailSentence.model_validate(x) for p in paragraphs[1:] for x in p["sentences"]]
        examples = [x for x in body if not _states_years(x.text, ctx)
                    and not x.about_job and not x.about_candidate]
        builds = _built_items(examples, ctx)
        if len(builds) > 2:
            out.append(violation("builds", f"{len(builds)} examples: at most 2", "letter",
                                 "error"))
        elif not builds:
            out.append(violation("builds", "No concrete example from your experience",
                                 "letter"))
        for item_id in builds:
            n = sum(1 for x in examples if item_id in x.citations)
            if n > 2:
                name = (ctx.pool.get(item_id).org or ctx.pool.get(item_id).title)
                out.append(violation("builds", f"The {name} example runs {n} sentences (1-2)",
                                     "letter", "error"))
        for x in examples:
            cited = [c for c in x.citations if c in builds]
            terms = _item_terms(ctx.pool, cited)
            if cited and terms and not any(re.search(rf"\b{re.escape(t)}\b", oc.fold(x.text))
                                           for t in terms):
                out.append(violation("vague", f"“{x.text}” is vague: say what it is and with "
                                     "which tools (e.g. a data lakehouse with dbt and Airflow)",
                                     "letter", "error"))
        cited = {c for x in generated for c in x.citations}
        if ctx.current_role_id and ctx.current_role_id not in cited:
            out.append(violation("current_role", f"Your current role at {ctx.current_role_org} "
                                 "matches this job: use it as an example", "letter", "error"))
    elif ctx.current_role_id and ctx.current_role_org and oc.fold(ctx.current_role_org) not in \
            oc.fold(" ".join(x for _i, x in units)):
        out.append(violation("current_role", f"Your current role at {ctx.current_role_org} "
                             "matches this job: use it as an example", "letter", "error"))
    return out


def check_letter(salutation: str, paragraphs: list[dict[str, Any]], ask: str | None,
                 ctx: Context) -> list[dict[str, str]]:
    """`paragraphs`: {"sentences": [...]} as generated, or {"text": ...} once edited. Generated
    paragraphs keep citation-level grounding; edited ones get the text-level source check.

    The v3 writing rules: one sentence at most about the listing (never restating it), no CV
    bullet copied or translated, your current role used when it matches, at most 2 examples of
    1-2 sentences each, the ask in its own short paragraph."""
    out: list[dict[str, str]] = []
    form = ctx.format == "form"
    generated: list[EmailSentence] = []
    texts = []
    email = ctx.email_context()
    for i, p in enumerate(paragraphs, 1):
        where = f"paragraph {i}"
        if "sentences" in p:
            sentences = [EmailSentence.model_validate(x) for x in p["sentences"]]
            generated += sentences
            for s in sentences:
                out += [violation("grounding", f"“{s.text}”: {problem}", where, "error")
                        for problem in _grounding(s, ctx)]
            texts.append(" ".join(s.text for s in sentences))
            if i == 1 and not any(s.about_job for s in sentences):
                out.append(violation("opening", "Open with why this company and role, citing "
                                     "one specific thing from the listing", where,
                                     "warning" if form else "error"))
        else:
            text = str(p.get("text") or "")
            clean = _ungroup(_strip_fr(text, ctx.years_statement_fr))
            out += [violation("grounding", problem, where, "error")
                    for problem in oc._source_problems(clean, email)]
            texts.append(text)
    if ask:
        out += [violation("grounding", f"The ask: {p}", "ask", "error")
                for p in oc._source_problems(ask, email)]
    out += writing_rules(paragraphs, ctx)
    return out + lint(salutation, texts, ask, ctx)


# ----------------------------------------------------------------------------------- answers


def check_answer(sentences: list[EmailSentence] | None, text: str, char_limit: int | None,
                 ctx: Context) -> list[dict[str, str]]:
    """One application answer: grounded sentences (or the edited text), banned phrases, years,
    and the character limit, a hard check (the text is never cut)."""
    out: list[dict[str, str]] = []
    if sentences is not None:
        for s in sentences:
            out += [violation("grounding", f"“{s.text}”: {p}", "answer", "error")
                    for p in _grounding(s, ctx)]
    else:
        out += [violation("grounding", p, "answer", "error")
                for p in oc._source_problems(_strip_fr(text, ctx.years_statement_fr),
                                             ctx.email_context())]
    if not text.strip():
        out.append(violation("empty", "No answer", "answer", "error"))
    if char_limit and len(text) > char_limit:
        out.append(violation("length", f"{len(text)}/{char_limit} characters", "answer",
                             "error"))
    out += _banned(text, ctx)
    out += [violation("years", _years_message(c, ctx), "answer", "error")
            for c in years_problems(text, ctx)]
    return out


def feedback(violations: list[dict[str, str]]) -> str:
    return "\n".join(f"- {v['where']}: {v['message']}" for v in violations
                     if v["severity"] == "error")


def errors(violations: list[dict[str, str]]) -> list[dict[str, str]]:
    return [v for v in violations if v["severity"] == "error"]

