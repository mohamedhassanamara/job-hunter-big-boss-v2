"""The skills list of a job CV: what the listing asks for, intersected with what you can claim.

Pure code, no model, no network. Every entry of the list is one of YOUR skills spelled as you
spell it; a term the listing names that none of your evidence backs is never shown (it comes back
in `gaps`, for the summary prompt's "do not name these" rule and the "JD asks for X, not in your
pool" hint). Nothing is inferred: no synonym, no glossary mapping, no "related" skill.

Evidence tiers (internal gating only: the CV never shows which tier a skill came from):
  1  your skills inventory (the `skill` groups in Experience: curated and spelled by you, which is
     also what a CV printed before). The free-form tags on jobs and projects are working labels
     ("mentoring", "web"), not skills: they are not read
  2  `skill_proof` items (small real projects, never printed in Experience)
  3  tags of your certifications (studied, not necessarily built with)
A skill takes the best tier any of its sources has. Tiers 2 and 3 enter the list only when the
listing names them. The list is built in this order, up to the target size,
and on to the max so the page's line fit can add or cut at the tail (JD matches are cut last):
  1  the listing's matches (any tier), most relevant first: title, requirement lines, frequency
  2  tier 1 skills that appear in the same job or project as a matched skill ("cooc"), ranked by
     how many matched skills they appear with, then by the items they share
  3  tier 1 skills pinned for the track ("pin"): `cv.skill_keep`, then the track's
     `cv.track_emphasis` tags
  4  the remaining tier 1 skills ("fill"): the track's emphasized skill groups first, in your
     order, then the other groups in pool order
Group membership alone promotes nothing in steps 1-3. Steps 2-4 only ever draw on your skill
groups: never a tag, a skill proof, a certification topic or a term from the listing. Under the
minimum the caller keeps the grouped list.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services import cv_check, fit_lexical
from app.services.cv_pool import Pool, norm, terms_of

T_EXPERIENCE, T_PROOF, T_STUDY = 1, 2, 3
DEFAULT_MAX = 30
DEFAULT_TARGET = 14
DEFAULT_MIN = 10
TITLE_BONUS = 20
CUE_LINE = 3  # a hit on a line that states a requirement
PLAIN_LINE = 1
# English words that are also skill names: matched only as written in your pool (case-sensitive)
# S3, C++, C#, Node.js, D3.js, .NET, DP-600: a letter first, then a digit or a tool suffix
_SYMBOLIC = re.compile(r"[A-Za-z]{1,6}\d{1,3}(?:\.js)?|[A-Za-z]{1,10}\+\+|[A-Za-z]#|"
                       r"[A-Za-z]{2,10}\.js|\.NET|[A-Z]{2,3}-\d{2,4}")
# shouted words that are tools; any other ALL-CAPS word is a heading, a currency or a unit
_ACRONYMS = {"sql", "aws", "gcp", "rest", "grpc", "sap", "jvm", "css", "html", "yaml", "json",
             "xml", "orm", "oauth", "jwt", "sso"}
AMBIGUOUS = {"go", "swift", "ray", "chef", "puppet", "flow", "spark", "dash", "rust", "r", "c"}


@dataclass
class LedgerEntry:
    display: str  # one of your skills, exactly as you wrote it (a parenthesised one stays whole)
    terms: list[str]  # the names it answers to: itself, its base, the names inside parentheses
    tier: int
    item_ids: list[int] = field(default_factory=list)


@dataclass
class SelectedSkill:
    skill: str
    tier: int
    item_ids: list[int]
    reason: str  # "jd" (the listing names it) | "cooc" | "pin" | "fill"
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"skill": self.skill, "tier": self.tier, "item_ids": self.item_ids,
                "reason": self.reason}


@dataclass
class SkillSelection:
    skills: list[SelectedSkill]  # every candidate up to the max, in display order
    gaps: list[str]  # the listing's checkable terms none of your evidence backs
    enough: bool = True  # False: under the minimum even after the fill (keep the grouped list)
    target: int = 0  # how many of `skills` a page shows before the line fit adjusts it
    cut_order: list[int] = field(default_factory=list)  # indexes of `skills`, first cut first

    @property
    def display(self) -> list[str]:
        return [s.skill for s in self.skills]


# ------------------------------------------------------------------------------------ ledger


def build_ledger(pool: Pool) -> list[LedgerEntry]:
    """Every claimable skill with its best tier. Spelling comes from the first source: your skill
    groups, then skill proofs, then certification topics."""
    entries: dict[str, LedgerEntry] = {}

    def add(tags: list[str], tier: int, item_id: int | None) -> None:
        for tag in tags:
            tag = tag.strip()
            if not tag or not norm(tag):
                continue
            key = norm(tag)
            found = entries.get(key)
            if found is None:
                found = entries[key] = LedgerEntry(display=tag, terms=terms_of([tag]), tier=tier)
            found.tier = min(found.tier, tier)
            if item_id is not None and item_id not in found.item_ids:
                found.item_ids.append(item_id)

    for item in pool.of("skill"):
        add(item.tags, T_EXPERIENCE, item.id)
    for item in pool.skill_proofs:
        add(item.tags, T_PROOF, item.id)
    for item_id, tags in pool.study_tags.items():
        add(tags, T_STUDY, item_id)
    return list(entries.values())


# ----------------------------------------------------------------------------------- matching


def _mentions(text: str, term: str) -> bool:
    """Whole-word match; an ambiguous English word only as you wrote it (Go, not "go to")."""
    if norm(term) in AMBIGUOUS or len(norm(term)) <= 1:
        # also not the start of a hyphenated phrase ("Go-to-Market")
        return re.search(rf"(?<![A-Za-z0-9-]){re.escape(term)}(?![A-Za-z0-9]|-[A-Za-z])",
                         text) is not None
    return fit_lexical.has_term(text, term)


def _boundary(term: str) -> tuple[str, str]:
    """Lookarounds for a whole-word match. Short or ambiguous terms (Git, R, Go) also refuse a
    hyphenated phrase ("Go-to-market"), and a one-letter term refuses "R&D" and "C/C++"."""
    short = len(norm(term)) <= 3 or norm(term) in AMBIGUOUS
    left, right = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"
    if short:
        left, right = r"(?<![A-Za-z0-9-])", r"(?![A-Za-z0-9]|-[A-Za-z])"
    if len(norm(term)) <= 1:
        left, right = r"(?<![A-Za-z0-9&/.+#-])", r"(?![A-Za-z0-9&/.+#-])"
    return left, right


def word_exact(text: str, term: str) -> bool:
    """`term` as you wrote it (same case), as a whole word: bullet evidence."""
    left, right = _boundary(term)
    return re.search(left + re.escape(term) + right, text) is not None


def word_any_case(text: str, term: str) -> bool:
    """`term` in any case, as a whole word: your tags are working labels in lower case."""
    left, right = _boundary(term)
    return re.search(left + re.escape(term) + right, text, re.I) is not None


def item_mentions(item: Any, entry: LedgerEntry, facts: list[str]) -> bool:
    """Does this job or project use the skill: it is a tag (any case) or it is written in a
    bullet exactly as you spell it (whole word, same case, so "providers" is not "Provider")."""
    tags = "\n".join(item.tags or [])
    bullets = "\n".join([item.title or "", *facts])
    return any(word_any_case(tags, t) or word_exact(bullets, t) for t in entry.terms)


def _first_pos(text: str, term: str) -> int:
    m = re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}", text, re.I)
    return m.start() if m else len(text)


def _score(entry: LedgerEntry, title: str, lines: list[str], description: str
           ) -> tuple[int, int, list[str]]:
    """(relevance, position of the first mention, the terms the listing names)."""
    hit = [t for t in entry.terms if _mentions(description, t) or _mentions(title, t)]
    if not hit:
        return 0, 0, []
    score = 0
    for term in hit:
        if _mentions(title, term):
            score += TITLE_BONUS
        counted = False
        for line in lines:
            if _mentions(line, term):
                score += CUE_LINE if fit_lexical.has_cue(line) else PLAIN_LINE
                counted = True
        if not counted:
            score += PLAIN_LINE  # named in a fragment too short to be a requirement line
    return score, min(_first_pos(description, t) for t in hit), hit


def _cooccurring(pool: Pool, seeds: list[LedgerEntry], candidates: list[LedgerEntry]
                 ) -> list[LedgerEntry]:
    """Candidates that share a job or project with a matched skill, best first: the number of
    matched skills they appear with, then the number of items they share."""
    items = [(item, pool.facts(item)) for kind in ("job", "project") for item in pool.of(kind)]
    uses = {id(item): {norm(e.display) for e in [*seeds, *candidates]
                       if item_mentions(item, e, facts)} for item, facts in items}
    scored = []
    for order, cand in enumerate(candidates):
        together: set[str] = set()
        shared = 0
        for item, _facts in items:
            have = uses[id(item)]
            if norm(cand.display) not in have:
                continue
            seeds_here = {norm(s.display) for s in seeds} & have
            if seeds_here:
                shared += 1
                together |= seeds_here
        if together:
            scored.append((-len(together), -shared, order, cand))
    return [c for *_key, c in sorted(scored, key=lambda x: x[:3])]


def select_skills(pool: Pool, *, title: str, description: str, company: str = "",
                  location: str = "", keep: dict[str, list[str]] | None = None,
                  emphasis: dict[str, list[str]] | None = None,
                  max_items: int = DEFAULT_MAX, min_items: int = DEFAULT_MIN,
                  target_items: int = DEFAULT_TARGET) -> SkillSelection:
    """The flat skills list for one listing, most relevant first (see the module docstring).
    `enough` is False when even the fill stays under `min_items`."""
    ledger = build_ledger(pool)
    lines = fit_lexical.requirement_lines(description)
    scored = []
    for order, entry in enumerate(ledger):
        score, pos, hit = _score(entry, title, lines, description)
        if score:
            scored.append((-score, entry.tier, pos, order, entry, hit))
    scored.sort(key=lambda x: x[:4])

    chosen: list[SelectedSkill] = []
    claimed: set[str] = set()  # a name two entries answer to is shown once, by the best of them
    by_display: dict[str, LedgerEntry] = {norm(e.display): e for e in ledger}

    def take(entry: LedgerEntry, reason: str, score: int = 0) -> None:
        claimed.update(norm(t) for t in entry.terms)
        chosen.append(SelectedSkill(entry.display, entry.tier, list(entry.item_ids), reason,
                                    score))

    for neg, _tier, _pos, _order, entry, hit in scored:
        names = {norm(t) for t in hit}
        if names <= claimed:
            continue
        claimed |= names
        chosen.append(SelectedSkill(entry.display, entry.tier, list(entry.item_ids), "jd", -neg))
        if len(chosen) >= max_items:
            break

    n_jd = len(chosen)
    target = min(max(target_items, min_items, n_jd), max_items)
    if len(chosen) < max_items:  # candidates up to the max: the line fit may add or cut at the tail
        # your skill groups, the emphasized ones first (in your order), then the rest as stored
        wanted = [norm(g) for g in (emphasis or {}).get("skill_groups", [])]
        stored = list(pool.of("skill"))
        ordered = [g for w in wanted for g in stored if norm(g.title) == w]
        ordered += [g for g in stored if g not in ordered]
        groups = [[by_display[k] for tag in item.tags if (k := norm(tag)) in by_display
                   and by_display[k].tier == T_EXPERIENCE] for item in ordered]
        tier1 = [e for g in groups for e in g]

        def free(entry: LedgerEntry) -> bool:
            return norm(entry.display) not in {norm(s.skill) for s in chosen} \
                and not {norm(t) for t in entry.terms} & claimed

        def fill(entries: list[LedgerEntry], reason: str) -> None:
            for entry in entries:
                if len(chosen) >= max_items:
                    return
                if free(entry):
                    take(entry, reason)

        seeds = [by_display[norm(s.skill)] for s in chosen]
        fill(_cooccurring(pool, seeds, [e for e in tier1 if free(e)]), "cooc")
        by_term = {norm(t): e for e in tier1 for t in e.terms}
        pins = [p for grp in (keep or {}).values() for p in grp] + list(
            (emphasis or {}).get("tags", []))
        fill([by_term[norm(p)] for p in pins if norm(p) in by_term], "pin")
        fill(tier1, "fill")

    return SkillSelection(skills=chosen, gaps=_gaps(pool, ledger, title, description, lines,
                                                    company, location),
                          enough=len(chosen) >= min_items, target=min(target, len(chosen)),
                          cut_order=list(range(len(chosen) - 1, -1, -1)))  # tail first


# ------------------------------------------------------------------------------------- gaps


def _gaps(pool: Pool, ledger: list[LedgerEntry], title: str, description: str,
          lines: list[str], company: str, location: str) -> list[str]:
    """Checkable terms the listing names that nothing of yours backs: not a skill of any tier,
    and not a word of the experience text you may write about."""
    own = {norm(t) for e in ledger for t in e.terms}
    known = pool.vocabulary()
    vocab = {t.lower() for e in ledger for t in e.terms} | fit_lexical.vocabulary(pool)
    skip = fit_lexical.ignored(company, title, location)
    out: list[str] = []
    for line in lines:
        for term in fit_lexical.salient_terms(line, vocab, skip):
            n = norm(term)
            if not n or n in own or n in known or any(norm(g) == n for g in out):
                continue
            m = re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", line, re.I)
            if m and _tool_shaped(m.group(0)):
                out.append(m.group(0))
    return out[:12]


def _tool_shaped(word: str) -> bool:
    """A name that is clearly a tool: a well-known one (Azure, Kafka), a short acronym (SQL, AWS),
    or one with a digit or symbol (S3, C++, Node.js). Capitalised ordinary words ("Rolle"), shouted
    headings ("ABOUT"), hyphenated compounds and CamelCase brand names are not: `salient_terms`
    keeps them, a gap list must not (the checks still catch a tool the summary invents)."""
    low = word.lower()
    if low in cv_check._NOT_TOOLS:
        return False
    if low in cv_check._TOOLS:
        return True
    if word.isalpha() and word.isupper():
        return low in _ACRONYMS
    return _SYMBOLIC.fullmatch(word) is not None
