"""How a tailored CV is shaped, beyond relevance: the writing guide given to the model, bullet
allowances by role type (recency and duration), skill-section shaping, and the summary checks.
Everything is configurable in Settings → CV; the defaults below are the fallbacks.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.models import ExperienceItem

DEFAULT_GUIDE = "\n".join([
    "Summary: at most 2 sentences, about 45 words. Sentence 1: who I am, positioned for this "
    "job's track. Sentence 2: what I bring to THIS role. No numbers that also appear in bullets, "
    "no certifications, no internships, no tool lists.",
    "Bullets: impact first (what I built and why it mattered), strong and varied verbs, one idea "
    "per bullet. Prefer bullets with concrete outcomes; skip generic ones (\"collaborated in Agile "
    "sprints\") unless nothing else fits.",
    "Don't repeat the same fact in the summary, the skills and the bullets.",
    "Human tone: natural phrasing, no keyword stuffing; not every bullet needs a metric.",
    "Use the style exemplar for tone, bullet length and summary length (its content is already "
    "in the pool).",
])

DEFAULT_STRUCTURE: dict[str, Any] = {
    "current": [3, 4],        # the role you're in now
    "long_role": [2, 3],      # roles longer than long_role_months
    "long_role_months": 12,
    "short_role": [1, 3],     # shorter roles: 1-3 depending on relevance to the track
    "graduation": [1, 3],     # graduation / end-of-studies projects
    "internship": [1, 2],     # never more than 2
    "projects_max": 2,
    "project_bullets": [2, 3],  # never a 1-bullet project
    "volunteering_max": 1,
    "skill_groups_max": 4,
    "skill_items_max": 8,
    "fill_min": 0.88,         # never add filler beyond the allowances to reach it
    "summary_max_words": 45,
    "summary_max_sentences": 2,
}

# One rule per line. "Parent: A, B" = a generic term and its specific tools → "Parent (A, B)"
# (the generic term alone is dropped when a tool is present). "A + B" = a tool and what it
# emulates → "A (B)" when both are present. "A / B" → "A/B" when both are present.
DEFAULT_SKILL_MERGES = [
    "LLMs: Mistral, Ollama, OpenAI, Llama, GPT, Claude, Gemini",
    "LocalStack + S3",
    "Linux / Bash",
    "Docker + Docker Compose",
]
GENERIC_ALIASES = {"llms": {"llm", "llms", "large language models", "large language model"}}

_INTERN = re.compile(r"\b(intern|internship|stage|stagiaire|praktikum|praktikant|prácticas|"
                     r"practicas|tirocinio|tirocinante|apprenti|apprentice|alternance|trainee)\b",
                     re.I)
_GRADUATION = re.compile(r"(graduation|end[- ]of[- ]studies|capstone|thesis|final[- ]year|"
                         r"\bpfe\b|projet de fin|master'?s project|m[ée]moire)", re.I)
_GENERIC_BULLET = re.compile(r"\b(agile|scrum|sprints?|collaborat\w*|stakeholders?|team ?work|"
                             r"cross-functional|daily stand-?ups?|code reviews?)\b", re.I)


def structure(cv_settings: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULT_STRUCTURE, **(cv_settings.get("structure") or {})}


def guide(cv_settings: dict[str, Any]) -> str:
    return (cv_settings.get("writing_guide") or "").strip() or DEFAULT_GUIDE


def merges(cv_settings: dict[str, Any]) -> list[str]:
    rules = cv_settings.get("skill_merges")
    return DEFAULT_SKILL_MERGES if rules is None else list(rules)


# ---------------------------------------------------------------------------- role types


def months(item: ExperienceItem, today: date | None = None) -> int:
    if not item.start_date:
        return 0
    end = item.end_date or today or date.today()
    return max(0, (end.year - item.start_date.year) * 12 + end.month - item.start_date.month + 1)


def role_type(item: ExperienceItem, rules: dict[str, Any], today: date | None = None) -> str:
    """current | internship | graduation | long_role | short_role."""
    text = f"{item.title} {item.org or ''}"
    if _INTERN.search(text):
        return "internship"
    if _GRADUATION.search(text):
        return "graduation"
    today = today or date.today()
    if item.start_date and (item.end_date is None or item.end_date >= today):
        return "current"
    return "long_role" if months(item, today) > int(rules["long_role_months"]) else "short_role"


def allowance(kind: str, item: ExperienceItem | None, relevance: int, rules: dict[str, Any],
              available: int, today: date | None = None) -> tuple[int, int]:
    """(min, max) bullets for an entry, capped by what the pool has."""
    if kind == "project":
        lo, hi = rules["project_bullets"]
    elif kind == "volunteering":
        lo, hi = 1, 1
    else:
        kind_ = role_type(item, rules, today) if item else "short_role"
        lo, hi = rules[kind_]
        if kind_ in ("short_role", "graduation"):  # 1-3 by how much it matters for this job
            hi = min(hi, 3 if relevance >= 8 else 2 if relevance >= 5 else 1)
            lo = min(lo, hi)
    hi = min(hi, available)
    return min(lo, hi), hi


def is_generic(text: str) -> bool:
    """A team-process bullet with no concrete outcome ("Collaborated in Agile sprints")."""
    return bool(_GENERIC_BULLET.search(text)) and not re.search(r"\d", text)


# ----------------------------------------------------------------------------------- skills


@dataclass
class _Merge:
    kind: str  # group | pair | join
    parent: str
    members: list[str]


def parse_merges(lines: list[str]) -> list[_Merge]:
    out = []
    for raw in lines:
        line = raw.strip()
        if ":" in line:
            parent, rest = line.split(":", 1)
            out.append(_Merge("group", parent.strip(), [m.strip() for m in rest.split(",")
                                                        if m.strip()]))
        elif "+" in line:
            a, b = (x.strip() for x in line.split("+", 1))
            out.append(_Merge("pair", a, [b]))
        elif "/" in line:
            a, b = (x.strip() for x in line.split("/", 1))
            out.append(_Merge("join", a, [b]))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def merge_items(items: list[str], rules: list[_Merge]) -> list[str]:
    """Apply merge rules inside one skill group, keeping the order of first appearance."""
    items = list(items)
    for rule in rules:
        index = {_norm(x): i for i, x in enumerate(items)}
        members = [m for m in rule.members if _norm(m) in index]
        if rule.kind == "group":
            aliases = GENERIC_ALIASES.get(_norm(rule.parent), set()) | {_norm(rule.parent)}
            generic = [i for i, x in enumerate(items) if _norm(x) in {_norm(a) for a in aliases}]
            if not members:
                continue
            present = [items[index[_norm(m)]] for m in members]
            positions = sorted(generic + [index[_norm(m)] for m in members])
            merged = f"{rule.parent} ({', '.join(present)})"
        else:
            if _norm(rule.parent) not in index or not members:
                continue
            parent = items[index[_norm(rule.parent)]]
            member = items[index[_norm(members[0])]]
            positions = sorted([index[_norm(rule.parent)], index[_norm(members[0])]])
            merged = f"{parent} ({member})" if rule.kind == "pair" else f"{parent}/{member}"
        keep = positions[0]
        items = [merged if i == keep else x for i, x in enumerate(items)
                 if i == keep or i not in positions]
    return items


def shape_skills(groups: list[tuple[str, list[str]]], rules: dict[str, Any],
                 merge_lines: list[str]) -> list[tuple[str, list[str]]]:
    """At most N groups (in the model's relevance order), merges applied, no item repeated
    across groups, at most M items each, empty groups dropped."""
    parsed = parse_merges(merge_lines)
    seen: set[str] = set()
    out = []
    for category, items in groups:
        merged = merge_items(items, parsed)
        unique = []
        for x in merged:
            key = _norm(x)
            if key and key not in seen:
                seen.add(key)
                unique.append(x)
        if unique:
            out.append((category, unique[: int(rules["skill_items_max"])]))
        if len(out) >= int(rules["skill_groups_max"]):
            break
    return out


# ---------------------------------------------------------------------------------- summary

_NUMBER = re.compile(r"\d[\d,.]*\s*[%kKmM+]*")
_YEARS = re.compile(r"\d+\s*\+?\s*(?:years?|yrs?)", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text.strip()) if s.strip()]


def summary_problems(text: str, *, rules: dict[str, Any], bullet_texts: list[str],
                     certifications: list[ExperienceItem], internships: list[ExperienceItem],
                     tools: set[str], max_sentences: int | None = None,
                     max_words: int | None = None) -> list[str]:
    """Why a summary breaks the guide (empty = fine). Checked in code; the summary is
    regenerated once with these reasons."""
    max_sentences = max_sentences or int(rules["summary_max_sentences"])
    max_words = max_words or int(rules["summary_max_words"])
    out = []
    n_sent, n_words = len(sentences(text)), len(text.split())
    if n_sent > max_sentences:
        out.append(f"{n_sent} sentences (max {max_sentences})")
    if n_words > round(max_words * 1.15):
        out.append(f"{n_words} words (about {max_words} max)")
    without_years = _YEARS.sub(" ", text)

    def metric(m: str) -> str:
        """The digits of a figure worth flagging (40%, 140K+, 2,000); '' for a bare 1-9."""
        digits = re.sub(r"[^\d]", "", m)
        return digits if digits and (int(digits) >= 10 or re.search(r"[%kKmM+]", m)) else ""

    bullet_numbers = {metric(m) for b in bullet_texts
                      for m in _NUMBER.findall(_YEARS.sub(" ", b))} - {""}
    repeated = sorted({m.strip() for m in _NUMBER.findall(without_years)
                       if metric(m) in bullet_numbers})
    if repeated:
        out.append(f"repeats numbers from the bullets ({', '.join(repeated)})")
    low = text.lower()
    if re.search(r"\bcertif", low) or any(
            (c.org and c.org.lower() in low) or (c.title and len(c.title) > 12
                                                 and c.title.lower() in low)
            for c in certifications):
        out.append("mentions certifications")
    if _INTERN.search(text) or any(i.org and i.org.lower() in low for i in internships):
        out.append("mentions an internship")
    for sentence in sentences(text):
        found = sorted({t for t in tools if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])",
                                                      sentence, re.I)})
        if len(found) >= 3:
            out.append(f"lists tools ({', '.join(found[:5])})")
            break
    return out


# ------------------------------------------------------------------------------ exemplar

REFERENCE = Path(__file__).resolve().parents[3] / "templates" / "reference" / "cv.tex"


def _plain(tex: str) -> str:
    text = re.sub(r"\$\\sim\$", "~", tex)
    text = text.replace("\\%", "%").replace("``", "\u201c").replace("''", "\u201d")
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", "", text)
    return re.sub(r"[{}]", "", text).strip()


def style_exemplar(path: Path = REFERENCE) -> dict[str, Any]:
    """The reference CV's summary and bullets as plain text: tone and length only."""
    if not path.exists():
        return {}
    tex = path.read_text()
    summary = re.search(r"\\section\{Summary\}\s*\\small\{(.+?)\}\s*\n", tex, re.S)
    bullets = [_plain(b) for b in re.findall(r"\\resumeItem\{(.+?)\}\s*\n", tex)]
    return {"summary": _plain(summary.group(1)) if summary else "", "bullets": bullets[:10]}
