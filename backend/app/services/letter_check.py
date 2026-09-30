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
DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS = 250, 350
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


def _grounding(sentence: EmailSentence, ctx: Context) -> list[str]:
    email = ctx.email_context()
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


def lint(salutation: str, paragraphs: list[str], ask: str | None,
         ctx: Context) -> list[dict[str, str]]:
    """Checks on the text, whoever wrote it. `ask` is None when it's part of the last paragraph
    (after you edit)."""
    out: list[dict[str, str]] = []
    body = [p for p in paragraphs if p.strip()]
    everything = " ".join([salutation, *body, ask or ""])
    n = len(oc.words(" ".join([*body, ask or ""])))
    if n < ctx.min_words or n > ctx.max_words:
        out.append(violation("length", f"{n} words (aim for {ctx.min_words}-{ctx.max_words})",
                             "letter", "error"))
    if not 3 <= len(body) <= 4:
        out.append(violation("structure", f"{len(body)} paragraphs (3-4 expected)", "letter",
                             "error"))
    if body and oc.fold(ctx.company) not in oc.fold(body[0]):
        out.append(violation("opening", f"The first paragraph doesn't name {ctx.company}",
                             "paragraph 1", "error"))
    if not salutation.strip():
        out.append(violation("salutation", "The salutation is empty", "salutation", "error"))
    elif ctx.contact_name and oc.fold(ctx.contact_name.split(" ")[-1]) not in oc.fold(salutation):
        out.append(violation("salutation", f"The salutation doesn't name {ctx.contact_name}",
                             "salutation"))
    questions = sum(p.count("?") for p in (body if ask is not None else body[:-1]))
    if questions:
        out.append(violation("ask", "Only one ask, at the end: a question appears earlier",
                             "letter", "error"))
    closing = ask if ask is not None else (body[-1] if body else "")
    if not closing.strip() or not _ASK.search(closing):
        out.append(violation("ask", "End with one clear ask (an interview or a call)",
                             "letter", "error"))
    folded = oc.fold(everything)
    for other in ctx.other_companies:
        if other and oc.fold(other) != oc.fold(ctx.company) and re.search(
                rf"\b{re.escape(oc.fold(other))}\b", folded):
            out.append(violation("company", f"Mentions “{other}”, the company of another "
                                 "letter", "letter", "error"))
    out += _banned(everything, ctx)
    if "!" in everything:
        out.append(violation("tone", "Exclamation mark", "letter"))
    out += [violation("years", _years_message(c, ctx), "letter", "error")
            for c in years_problems(everything, ctx)]
    return out


def check_letter(salutation: str, paragraphs: list[dict[str, Any]], ask: str | None,
                 ctx: Context) -> list[dict[str, str]]:
    """`paragraphs`: {"sentences": [...]} as generated, or {"text": ...} once edited. Generated
    paragraphs keep citation-level grounding; edited ones get the text-level source check."""
    out: list[dict[str, str]] = []
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
                out.append(violation("opening", "The opening should say something specific "
                                     "from the listing", where, "error"))
        else:
            text = str(p.get("text") or "")
            clean = _strip_fr(text, ctx.years_statement_fr)
            out += [violation("grounding", problem, where, "error")
                    for problem in oc._source_problems(clean, email)]
            texts.append(text)
    if ask is not None:
        out += [violation("grounding", f"The ask: {p}", "ask", "error")
                for p in oc._source_problems(ask, email)]
    if generated and all("sentences" in p for p in paragraphs):
        builds = len(_built_items(generated, ctx))
        if builds < 2:
            out.append(violation("builds", f"{builds} concrete build from your CV (show 2-3)",
                                 "letter"))
        elif builds > 3:
            out.append(violation("builds", f"{builds} different builds: focus on 2-3", "letter"))
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

