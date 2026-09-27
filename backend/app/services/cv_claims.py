"""Claim-level checks for generated CV text, all in code:

- `Vocabulary`: what the pool says, tolerant of plurals and word parts ("UIs" → UI,
  "REST" ⊂ rest-api), so real wording isn't flagged as an invented tool.
- years claims ("3+ years", "over two years"): only the values computed in code are allowed.
- capability phrases (object-oriented programming, Unix, CI/CD, microservices…): flagged when the
  pool never mentions them.
- scope inflation ("mentored developers" when the pool says "mentoring a junior developer").
- canonical spelling: skills/tools are written exactly as the pool writes them (dbt, spaCy).
"""

import re
from collections import Counter

from app.services.cv_pool import Pool, norm

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*")


def singular(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 2 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


class Vocabulary:
    """Normalised words/phrases of a text body: whole tokens, their hyphen/slash parts,
    singulars, and 2-3 word phrases (so "Spring Boot" matches the slug spring-boot)."""

    def __init__(self, text: str, extra: list[str] | None = None):
        self.words: set[str] = set()
        body = text + " " + " ".join(extra or [])
        for chunk in re.findall(r"[A-Za-z0-9][A-Za-z0-9+#./\-]*", body):
            whole = norm(chunk)
            self.words |= {whole, singular(whole)}
            for part in re.split(r"[-/.]", chunk):
                n = norm(part)
                if n:
                    self.words |= {n, singular(n)}
        tokens = [norm(t) for t in _WORD.findall(text)]
        for size in (2, 3):
            for i in range(len(tokens) - size + 1):
                self.words.add("".join(tokens[i:i + size]))

    def knows(self, term: str) -> bool:
        n = norm(term)
        return bool(n) and (n in self.words or singular(n) in self.words)


def pool_vocabulary(pool: Pool) -> Vocabulary:
    return Vocabulary(pool.all_text())


# -------------------------------------------------------------------------------------- years

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_YEARS = re.compile(
    r"\b(?:over|more than|nearly|almost|about|around)?\s*"
    r"(\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")\s*(\+)?\s*(?:years?|yrs?)\b", re.I)


def years_claims(text: str) -> list[tuple[str, float]]:
    """[(matched text, value)] for every "N years"-style claim."""
    out = []
    for m in _YEARS.finditer(text):
        raw = m.group(1).lower()
        value = float(_NUMBER_WORDS.get(raw, raw))
        out.append((m.group(0).strip(), value))
    return out


def bad_years(text: str, allowed: set[int]) -> list[str]:
    """Years claims whose number isn't one of the values computed in code."""
    return [claim for claim, value in years_claims(text)
            if not (value.is_integer() and int(value) in allowed)]


# -------------------------------------------------------------------------- capability phrases

# phrase → the words that count as the pool mentioning it (any of them, normalised).
CAPABILITIES: dict[str, list[str]] = {
    "object-oriented programming": ["object-oriented", "oop", "object oriented"],
    "OOP": ["object-oriented", "oop"],
    "functional programming": ["functional programming"],
    "Unix": ["unix"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous delivery",
              "continuous deployment"],
    "continuous integration": ["continuous integration", "ci/cd"],
    "DevOps": ["devops"],
    "microservices": ["microservice", "microservices"],
    "distributed systems": ["distributed system"],
    "system design": ["system design"],
    "test-driven development": ["test-driven", "tdd"],
    "TDD": ["tdd", "test-driven"],
    "pair programming": ["pair programming"],
    "code review": ["code review"],
    "Kubernetes": ["kubernetes", "k8s"],
    "cloud-native": ["cloud-native", "cloud native"],
    "scalability": ["scalab", "scale"],
    "high availability": ["high availability"],
    "security": ["security", "secure"],
    "stakeholder management": ["stakeholder"],
    "people management": ["people management", "managed a team", "line manag"],
    "team leadership": ["led a team", "team lead", "leading a team"],
    "mentoring": ["mentor"],
    "open source": ["open source", "open-source"],
    "A/B testing": ["a/b test", "ab test"],
    "data warehousing": ["warehouse"],
    "real-time streaming": ["stream"],
}


def capability_gaps(text: str, pool_text: str) -> list[str]:
    """Capability phrases the text claims but the pool never mentions."""
    lowered_text, lowered_pool = text.lower(), pool_text.lower()
    out = []
    for phrase, evidence in CAPABILITIES.items():
        pattern = rf"(?<![\w-]){re.escape(phrase.lower())}(?![\w-])"
        if re.search(pattern, lowered_text) and not any(e in lowered_pool for e in evidence):
            out.append(phrase)
    return out


# --------------------------------------------------------------------------- scope inflation

_SCOPE = re.compile(
    r"\b(mentor(?:ed|ing|s)?|coach(?:ed|ing)?|led|leading|lead|managed|managing|manage)\s+"
    r"(?:(?:a|an|the|other|several|multiple|junior|senior|new|\d+)\s+){0,3}"
    r"(developers?|engineers?|teams?|people|interns?|juniors?|members?|students?)\b", re.I)


def _verb(word: str) -> str:
    w = word.lower()
    for stem, key in (("mentor", "mentor"), ("coach", "coach"), ("lead", "lead"), ("led", "lead"),
                      ("manag", "manage")):
        if w.startswith(stem):
            return key
    return w


def scope_inflation(text: str, pool_text: str) -> list[str]:
    """"mentored developers" when the pool only says "mentoring a junior developer": the text's
    verb+object must appear in the pool with the same plurality."""
    pool_claims = {(_verb(m.group(1)), singular(m.group(2).lower()),
                    m.group(2).lower().endswith("s") or "team" in m.group(2).lower())
                   for m in _SCOPE.finditer(pool_text)}
    out = []
    for m in _SCOPE.finditer(text):
        verb, noun = _verb(m.group(1)), m.group(2).lower()
        plural = noun.endswith("s") and noun not in ("people",)
        same = any(v == verb and n == singular(noun) for v, n, _ in pool_claims)
        widened = plural and not any(v == verb and n == singular(noun) and p
                                     for v, n, p in pool_claims)
        if not same or widened:
            out.append(m.group(0))
    return out


# -------------------------------------------------------------------------- canonical spelling


class Canon:
    """Exact spellings from the pool. Prose (bullets, summaries, titles) wins: it's how the user
    writes a term ("dbt", "spaCy", "Spring Boot"). A tag is used only when it has capitals: an
    all-lowercase slug (python, spring-boot) isn't a spelling."""

    def __init__(self, pool: Pool):
        terms = {norm(t) for t in pool.skill_terms()} | {norm(t) for i in pool.items.values()
                                                         for t in i.tags}
        prose = "\n".join(p for i in pool.items.values()
                          for p in [i.title, i.summary or "", *i.bullets] if p)
        counts: dict[str, Counter] = {}
        words = [w.strip(".,;:()") for w in re.findall(r"[^\s,;:()]+", prose)]
        for size in (1, 2, 3):
            for i in range(len(words) - size + 1):
                phrase = " ".join(words[i:i + size])
                key = norm(phrase)
                if key in terms and not phrase.islower() or key in terms and size == 1:
                    counts.setdefault(key, Counter())[phrase] += 1
        self.spelling: dict[str, str] = {}
        for key, variants in counts.items():
            best = variants.most_common(1)[0][0]
            self.spelling[key] = best
        for item in pool.items.values():
            for tag in item.tags:
                if tag != tag.lower() and norm(tag) not in self.spelling:
                    self.spelling[norm(tag)] = tag

    def word(self, term: str) -> str:
        return self.spelling.get(norm(term), term)

    def text(self, text: str) -> str:
        """Replace 1-3 word runs that are pool skills with their pool spelling."""
        tokens = re.split(r"(\s+)", text)
        words = tokens[0::2]
        out, i = [], 0
        while i < len(words):
            done = False
            for size in (3, 2, 1):
                chunk = words[i:i + size]
                if len(chunk) < size:
                    continue
                core = " ".join(w.strip(".,;:()") for w in chunk)
                key = norm(core)
                if key in self.spelling and core.lower() == self.spelling[key].lower() and \
                        core != self.spelling[key]:
                    lead = chunk[0][: len(chunk[0]) - len(chunk[0].lstrip("(\"“"))]
                    trail = chunk[-1][len(chunk[-1].rstrip(".,;:)\"”")):]
                    out.append(lead + self.spelling[key] + trail)
                    i += size
                    done = True
                    break
            if not done:
                out.append(words[i])
                i += 1
        return " ".join(out)
