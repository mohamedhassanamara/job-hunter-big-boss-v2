"""CV Studio's skills chips (flat job CVs): remove a skill, put one back, from the ledger only.

A chip is one of YOUR skills as you spell it: the ledger's entries (your skill groups, small
projects, certification topics) and the soft skills your pool backs. Free text is refused. Once you
edit the line, the CV prints exactly your list (`overrides.skills.list`): the page fit no longer
cuts or adds skills, it only reports whether the list still meets the line rule (2-3 lines, the
last at least 75% full, at least `skills_min` skills). "Back to automatic" removes the override.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services import skill_ledger, soft_skills
from app.services.cv_pool import Pool, norm
from app.services.skill_fit import MAX_LINES, MIN_LAST_FILL, MIN_LINES

SOURCE = {1: "your skills", 2: "a small project", 3: "a certification (studied)"}


class SkillEditError(ValueError):
    """A chip that is not in the ledger, or an edit that would leave no skills."""


@dataclass
class Chip:
    skill: str
    kind: str  # technical | soft
    tier: int
    source: str


def chips(pool: Pool) -> dict[str, Chip]:
    """Every skill that may be on the line, by normalised spelling."""
    out: dict[str, Chip] = {}
    for entry in skill_ledger.build_ledger(pool):
        out[norm(entry.display)] = Chip(entry.display, "technical", entry.tier,
                                        SOURCE.get(entry.tier, "your pool"))
    for soft in soft_skills.ledger(pool):
        out.setdefault(norm(soft.display), Chip(soft.display, "soft", 1,
                                                "a soft skill (a bullet of your job/volunteering)"))
    return out


def apply(current: list[str], remove: list[str], add: list[str], known: dict[str, Chip]
          ) -> list[str]:
    """`current` without `remove`, then `add` appended (each must be a known chip)."""
    gone = {norm(x) for x in remove}
    kept = [x for x in current if norm(x) not in gone]
    for name in add:
        chip = known.get(norm(name))
        if chip is None:
            raise SkillEditError(f"“{name}” is not one of your skills: pick it from the list")
        if norm(chip.skill) not in {norm(x) for x in kept}:
            kept.append(chip.skill)
    if not kept:
        raise SkillEditError("Keep at least one skill, or use Back to automatic")
    return kept


def describe(printed: list[str], known: dict[str, Chip], plan_list: list[dict[str, Any]]
             ) -> list[Chip]:
    """The printed skills as chips (a skill no longer in the ledger keeps what the plan said)."""
    by_plan = {norm(str(x["skill"])): x for x in plan_list}
    out = []
    for name in printed:
        chip = known.get(norm(name))
        if chip is None:
            planned = by_plan.get(norm(name), {})
            chip = Chip(name, str(planned.get("kind") or "technical"),
                        int(planned.get("tier") or 1), "your pool")
        out.append(chip)
    return out


def fit_report(history: list[dict[str, Any]], count: int, minimum: int, grouped: bool
               ) -> dict[str, Any]:
    """Does the printed line meet the rule? From the last measured fit of this CV."""
    report = next((h["skill_fit"] for h in reversed(history or []) if "skill_fit" in h), [])
    last = report[-1] if report else {}
    measured = last.get("measured")
    lines, fill = (measured[0], measured[1]) if measured else (None, None)
    problems: list[str] = []
    if grouped:
        problems.append("No skills line fits the rule here: the grouped list prints")
    else:
        if count < minimum:
            problems.append(f"{count} skills, under the minimum of {minimum}")
        if lines is not None and not MIN_LINES <= lines <= MAX_LINES:
            problems.append(f"{lines} line{'s' if lines != 1 else ''}: the rule is "
                            f"{MIN_LINES}-{MAX_LINES}")
        if fill is not None and lines is not None and lines >= 2 and fill < MIN_LAST_FILL - 0.01:
            problems.append(f"the last line is {round(fill * 100)}% full, under "
                            f"{round(MIN_LAST_FILL * 100)}%")
    return {"count": count, "minimum": minimum, "lines": lines, "last_fill": fill,
            "ok": not problems, "problems": problems, "manual": bool(last.get("manual")),
            "grouped": grouped}
