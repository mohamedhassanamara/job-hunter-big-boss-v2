"""Automatic checks for a cold-email draft. No model calls.

Grounding reuses the CV checks: every candidate sentence must be supported by the pool items it
cites (numbers, tools, capabilities, scope, years); sentences about the company/role may only
state what the listing says. Then the lint: length, exactly one ask, the contact's first name and
the company's name, banned phrases and generic openers, and near-duplicates of drafts written to
other people.
"""

import re
from dataclasses import dataclass, field

from app.providers.base import EmailDraftPlan, SummarySentence
from app.services.cv_check import new_tools, numbers, sentence_problems, violation
from app.services.cv_claims import Vocabulary
from app.services.cv_pool import Pool
from app.services.dedupe import _ascii_words

DEFAULT_BANNED = [
    "i hope this email finds you well", "i hope this finds you well", "hope you are well",
    "hope you're doing well", "my name is", "i am writing to", "i'm writing to",
    "to whom it may concern", "dear sir or madam", "i am passionate", "i'm passionate",
    "passionate about", "i would love the opportunity", "i'd love the opportunity",
    "team player", "fast learner", "quick learner", "hard worker", "hardworking",
    "think outside the box", "synergy", "go-getter", "results-driven", "self-starter",
    "detail-oriented", "dynamic", "rockstar", "ninja", "guru", "touch base", "circle back",
    "reach out to you today", "i came across your profile", "perfect fit", "dream job",
    "j'espère que vous allez bien", "je me permets de vous contacter", "espero que estés bien",
]
DEFAULT_MAX_WORDS = 150
DUPLICATE_THRESHOLD = 0.5  # 3-word shingle overlap with a draft to someone else


def words(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ'’-]+", text)


def fold(text: str) -> str:
    return " ".join(_ascii_words(text))


def shingles(text: str, n: int = 3) -> set[str]:
    w = _ascii_words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def similarity(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


@dataclass
class Context:
    pool: Pool
    allowed_years: set[int]
    job_text: str  # title + listing
    company: str
    first_name: str
    banned: list[str] = field(default_factory=lambda: list(DEFAULT_BANNED))
    max_words: int = DEFAULT_MAX_WORDS
    other_companies: list[str] = field(default_factory=list)  # in drafts to other companies
    others: list[tuple[int, str, str]] = field(default_factory=list)  # (draft id, to, text)


# "a 15-minute call", "20 minutes", "30 min", "2 hours": a request's duration, not a claim.
_DURATION = re.compile(r"\b\d+\s*[-–]?\s*(?:minutes?|mins?|hours?|hrs?|h|minuten|stunden?|"
                       r"heures?|minutos?|horas?|minuti|ore)\b", re.I)


def _claims_only(text: str, ctx: "Context") -> str:
    """Drop what isn't a claim: durations of the ask and the company's own name ("3E")."""
    text = _DURATION.sub(" ", text)
    if ctx.company:
        text = re.sub(re.escape(ctx.company), " ", text, flags=re.I)
    return text


def _about_job_problems(text: str, ctx: Context) -> list[str]:
    text = _claims_only(text, ctx)
    listing_digits = {re.sub(r"[^\d]", "", n) for n in numbers(ctx.job_text)}
    out = [f"“{n}” isn't in the listing" for n in numbers(text)
           if re.sub(r"[^\d]", "", n) not in listing_digits]
    vocab = Vocabulary(ctx.job_text + " " + ctx.company)
    out += [f"“{t}” isn't in the listing" for t in new_tools(text, vocab)]
    return out


def lint(subject: str, greeting: str, body_parts: list[str], ask: str | None,
         ctx: Context) -> list[dict[str, str]]:
    """Checks that apply to any text (generated or edited by you)."""
    out: list[dict[str, str]] = []
    everything = " ".join([subject, greeting, *body_parts, ask or ""])
    folded = fold(everything)
    n_words = len(words(" ".join([greeting, *body_parts, ask or ""])))
    if n_words > ctx.max_words:
        out.append(violation("length", f"{n_words} words (limit {ctx.max_words})", "body",
                             "error"))
    if not subject.strip():
        out.append(violation("subject", "The subject is empty", "subject", "error"))
    elif len(subject) > 80 or len(words(subject)) > 10:
        out.append(violation("subject", "The subject is long; keep it under ~8 words",
                             "subject"))
    asks = sum(p.count("?") for p in body_parts) + (ask or "").count("?")
    if ask is not None and "?" in " ".join(body_parts):
        out.append(violation("ask", "Only one ask: a question appears outside the ask", "body",
                             "error"))
    elif ask is None and asks != 1:
        out.append(violation("ask", f"Exactly one clear ask expected ({asks} questions found)",
                             "body", "error"))
    if ctx.first_name and fold(ctx.first_name) not in fold(greeting):
        out.append(violation("name", f"The greeting doesn't use {ctx.first_name}'s first name",
                             "greeting", "error"))
    if fold(ctx.company) not in folded:
        out.append(violation("company", f"The company name “{ctx.company}” isn't mentioned",
                             "body", "error"))
    for other in ctx.other_companies:
        if other and fold(other) != fold(ctx.company) and re.search(
                rf"\b{re.escape(fold(other))}\b", folded):
            out.append(violation("company", f"Mentions “{other}”, the company of another draft",
                                 "body", "error"))
    for phrase in ctx.banned:
        if phrase.strip() and fold(phrase) and re.search(rf"\b{re.escape(fold(phrase))}\b",
                                                         folded):
            out.append(violation("banned", f"Banned phrase: “{phrase}”", "body", "error"))
    if "!" in everything:
        out.append(violation("tone", "Exclamation mark", "body"))
    text = " ".join([*body_parts, ask or ""])
    for draft_id, to, other_text in ctx.others:
        score = similarity(text, other_text)
        if score >= DUPLICATE_THRESHOLD:
            out.append(violation("duplicate", f"{round(score * 100)}% the same as your draft to "
                                 f"{to} (#{draft_id}): make it specific", "body"))
    return out


def check_plan(plan: EmailDraftPlan, ctx: Context) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i, s in enumerate(plan.sentences, 1):
        where = f"sentence {i}"
        if s.about_job and not s.citations:
            problems = _about_job_problems(s.text, ctx)
        else:
            problems = sentence_problems(
                SummarySentence(text=_claims_only(s.text, ctx), citations=s.citations),
                ctx.pool, ctx.allowed_years)
        out += [violation("grounding", f"“{s.text}”: {p}", where, "error") for p in problems]
    out += [violation("grounding", f"The ask: {p}", "ask", "error")
            for p in _source_problems(plan.ask, ctx)]
    return out + lint(plan.subject, plan.greeting, [s.text for s in plan.sentences], plan.ask,
                      ctx)


def _source_problems(text: str, ctx: Context) -> list[str]:
    """Numbers and tools that are neither in your experience nor in the listing."""
    text = _claims_only(text, ctx)
    source = ctx.pool.all_text() + "\n" + ctx.job_text + "\n" + ctx.company
    digits = {re.sub(r"[^\d]", "", n) for n in numbers(source)}
    out = [f"“{n}” isn't in your experience or the listing" for n in numbers(text)
           if re.sub(r"[^\d]", "", n) not in digits]
    return out + [f"“{t}” isn't in your experience or the listing"
                  for t in new_tools(text, Vocabulary(source))]


def check_text(subject: str, body: str, ctx: Context) -> list[dict[str, str]]:
    """After you edit a draft (the body without signature/opt-out, which code adds): citations
    are gone, so every number and tool must appear in your experience or in the listing."""
    lines = body.split("\n")
    first = next((i for i, ln in enumerate(lines) if ln.strip()), 0)
    greeting, rest = lines[first] if lines else "", "\n".join(lines[first + 1:])
    out = [violation("grounding", p, "body", "error") for p in _source_problems(rest, ctx)]
    return out + lint(subject, greeting, [rest], None, ctx)


def feedback(violations: list[dict[str, str]]) -> str:
    return "\n".join(f"- {v['message']}" for v in violations if v["severity"] == "error")


def errors(violations: list[dict[str, str]]) -> list[dict[str, str]]:
    return [v for v in violations if v["severity"] == "error"]
