"""The skills list of a job CV: what the listing asks for, intersected with what you can claim.

Pure code, no model, no network. Every entry of the list is one of YOUR skills spelled as you
spell it; a term the listing names that none of your evidence backs is never shown (it comes back
in `gaps`, for the summary prompt's "do not name these" rule and the "JD asks for X, not in your
pool" hint). Nothing is inferred: no synonym, no glossary mapping, no "related" skill.

Evidence tiers (internal gating only: the CV never shows which tier a skill came from):
  1  your own skills inventory and the tags of your real jobs, projects, volunteering, education
  2  `skill_proof` items (small real projects, never printed in Experience)
  3  tags of your certifications (studied, not necessarily built with)
A skill takes the best tier any of its sources has. Tiers 2 and 3 enter the list only when the
listing names them; padding (a short match) uses tier 1 skills pinned in `cv.skill_keep` only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services import cv_check, fit_lexical
from app.services.cv_pool import Pool, norm, terms_of

T_EXPERIENCE, T_PROOF, T_STUDY = 1, 2, 3
DEFAULT_MAX = 18
DEFAULT_MIN = 8
TITLE_BONUS = 20
CUE_LINE = 3  # a hit on a line that states a requirement
PLAIN_LINE = 1
# English words that are also skill names: matched only as written in your pool (case-sensitive)
_HEADINGS = {"about", "ready", "make", "role", "team", "what", "your", "join", "who", "why"}
# S3, C++, C#, Node.js, D3.js, .NET, DP-600: a letter first, then a digit or a tool suffix
_SYMBOLIC = re.compile(r"[A-Za-z]+\d+[A-Za-z0-9]*(?:\.js)?|[A-Za-z]+\+\+|[A-Za-z]+#|"
                       r"[A-Za-z]+\.js|\.NET|[A-Z]{2,3}-\d{2,4}")
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
    reason: str  # "jd" (the listing names it) | "pad" (tier 1, pinned for the track)
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"skill": self.skill, "tier": self.tier, "item_ids": self.item_ids,
                "reason": self.reason}


@dataclass
class SkillSelection:
    skills: list[SelectedSkill]
    gaps: list[str]  # the listing's checkable terms none of your evidence backs

    @property
    def display(self) -> list[str]:
        return [s.skill for s in self.skills]


# ------------------------------------------------------------------------------------ ledger


def build_ledger(pool: Pool) -> list[LedgerEntry]:
    """Every claimable skill with its best tier. Spelling comes from the first source: your skill
    groups, then your roles' and projects' tags, then skill proofs, then certification topics."""
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
    for kind in ("job", "project", "volunteering", "education"):
        for item in pool.of(kind):
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


def select_skills(pool: Pool, *, title: str, description: str, company: str = "",
                  location: str = "", keep: dict[str, list[str]] | None = None,
                  max_items: int = DEFAULT_MAX, min_items: int = DEFAULT_MIN) -> SkillSelection:
    """The flat skills list for one listing, most relevant first (see the module docstring)."""
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
    for neg, _tier, _pos, _order, entry, hit in scored:
        names = {norm(t) for t in hit}
        if names <= claimed:
            continue
        claimed |= names
        chosen.append(SelectedSkill(entry.display, entry.tier, list(entry.item_ids), "jd", -neg))
        if len(chosen) >= max_items:
            break

    if len(chosen) < min_items:  # a short match: pinned tier 1 skills only, never tier 2 or 3
        by_term = {norm(t): e for e in ledger if e.tier == T_EXPERIENCE for t in e.terms}
        shown = {norm(s.skill) for s in chosen}
        for pinned in [p for group in (keep or {}).values() for p in group]:
            entry = by_term.get(norm(pinned))
            if entry is None or norm(entry.display) in shown or len(chosen) >= min_items:
                continue
            shown.add(norm(entry.display))
            chosen.append(SelectedSkill(entry.display, entry.tier, list(entry.item_ids), "pad"))

    return SkillSelection(skills=chosen, gaps=_gaps(pool, ledger, title, description, lines,
                                                    company, location))


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
        return 2 <= len(word) <= 5 and low not in _HEADINGS
    return _SYMBOLIC.fullmatch(word) is not None
