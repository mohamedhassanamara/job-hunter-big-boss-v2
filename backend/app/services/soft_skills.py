"""Soft skills on a job CV's skills list: shown only when the listing names them AND your pool
backs them.

Your pool backs one when a job or volunteering item lists it in `soft_skills` and that item has at
least one bullet (the supporting text lives in the item's own bullets). The field is read only
here: it is not a tag, never printed in a section and never counts as something you did.

Matching is deterministic and uses equivalence groups only: different words for the SAME thing,
in English, French and German (collaboration = teamwork = Teamfähigkeit = travail d'équipe). A
group never implies another: leadership does not match mentoring, ownership does not match
adaptability. A soft skill of yours that is in no group matches only its own words. The spelling
that prints is always yours, never the listing's.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services import fit_lexical
from app.services.cv_pool import Pool

MAX_SOFT = 4
TITLE_BONUS = 20
CUE_LINE = 3
PLAIN_LINE = 1

# concept → every form that means it (lower case). Equivalence only: add a word here only when it
# means the same thing as the others in its group, never when it merely suggests it.
GROUPS: dict[str, tuple[str, ...]] = {
    "communication": (
        "communication", "communicating", "communicator", "communicate", "communiquer",
        "kommunikation", "kommunikationsstärke", "kommunikationsfähigkeit",
        "kommunikationsfähig", "kommunikativ"),
    "teamwork": (
        "teamwork", "collaboration", "collaborating", "collaborative", "collaborate",
        "team player", "team spirit", "travail d'équipe", "travail en équipe",
        "esprit d'équipe", "collaboratif", "collaborer", "teamfähigkeit", "teamfähig",
        "teamarbeit", "zusammenarbeit", "teamgeist"),
    "leadership": (
        "leadership", "leadership skills", "sens du leadership", "führung", "führungsstärke",
        "führungskompetenz", "führungsqualitäten"),
    "mentoring": ("mentoring", "mentorship", "mentor", "mentorat"),
    "ownership": ("ownership", "sense of ownership", "eigenverantwortung", "eigenverantwortlich"),
    "problem-solving": (
        "problem-solving", "problem solving", "problem solver", "problemlösung",
        "problemlösungskompetenz", "problemlösungsfähigkeit", "résolution de problèmes",
        "résolution de problème", "resolution de problemes"),
    "adaptability": (
        "adaptability", "adaptable", "adaptabilité", "anpassungsfähigkeit", "anpassungsfähig"),
}


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'").replace("-", " ")).strip()


_CONCEPT_OF = {_fold(form): concept for concept, forms in GROUPS.items() for form in forms}


def concept_of(term: str) -> str | None:
    """The group a skill of yours belongs to ("Teamwork" → teamwork), None when it is in none."""
    return _CONCEPT_OF.get(_fold(term))


def forms_of(term: str) -> tuple[str, ...]:
    """The words that count as naming this skill: its group's, or just its own."""
    concept = concept_of(term)
    return GROUPS[concept] if concept else (term,)


def named_in(text: str, term: str) -> bool:
    """Does `text` (a listing) name this skill, in any of its equivalent words?"""
    folded = text.replace("’", "'")
    return any(re.search(rf"(?<!\w){re.escape(form)}(?!\w)", folded, re.I)
               for form in forms_of(term))


@dataclass
class SoftEntry:
    display: str  # as you wrote it on the item
    concept: str | None
    item_ids: list[int] = field(default_factory=list)
    score: int = 0


def ledger(pool: Pool) -> list[SoftEntry]:
    """Soft skills your pool backs: listed on a job or volunteering item that has a bullet. One
    entry per skill (two spellings of one group count once, the first spelling wins)."""
    entries: dict[str, SoftEntry] = {}
    for kind in ("job", "volunteering"):
        for item in pool.of(kind):
            if not any(b.strip() for b in item.bullets or []):
                continue  # no supporting text: not evidence
            for tag in item.soft_skills or []:
                tag = tag.strip()
                if not tag:
                    continue
                concept = concept_of(tag)
                key = concept or _fold(tag)
                found = entries.setdefault(key, SoftEntry(tag, concept))
                if item.id is not None and item.id not in found.item_ids:
                    found.item_ids.append(item.id)
    return list(entries.values())


def select(pool: Pool, title: str, description: str, limit: int = MAX_SOFT) -> list[SoftEntry]:
    """The soft skills this listing names that your pool backs, most relevant first (title, then
    requirement lines, then how early), at most `limit`."""
    lines = fit_lexical.requirement_lines(description)
    scored = []
    for order, entry in enumerate(ledger(pool)):
        in_title = named_in(title, entry.display)
        in_text = named_in(description, entry.display)
        if not (in_title or in_text):
            continue
        score = TITLE_BONUS if in_title else 0
        for line in lines:
            if named_in(line, entry.display):
                score += CUE_LINE if fit_lexical.has_cue(line) else PLAIN_LINE
        entry.score = max(score, PLAIN_LINE)
        first = min((m.start() for form in forms_of(entry.display)
                     if (m := re.search(rf"(?<!\w){re.escape(form)}(?!\w)", description, re.I))),
                    default=len(description))
        scored.append((-entry.score, first, order, entry))
    return [e for *_k, e in sorted(scored, key=lambda x: x[:3])][:limit]
