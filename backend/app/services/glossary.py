"""The career-changer glossary (Settings → Candidate): terms YOU wrote that translate how your
experience is written (e.g. mobile/Flutter work) into the words of the field you are moving to.

It is only ever your own text. Code never writes an entry, and an entry adds nothing but a name:
the generators may use the "to" term for a sentence that cites an experience item containing the
"from" term, and the checks and the claim verifier treat that term as known for that item. It
never adds a tool, a number, a scale or a year, and the honesty rules still apply on top.
"""

import re
from typing import Any

MAX_ENTRIES = 60
MAX_TERM = 80
MAX_NOTE = 200


def clean(raw: Any) -> list[dict[str, str]]:
    """Valid entries only ({from, to, note}), whitespace-folded, first of a repeated "from"."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        src, dst = " ".join(str(item.get("from") or "").split()), " ".join(
            str(item.get("to") or "").split())
        key = src.lower()
        if src and dst and key not in seen and key != dst.lower():
            seen.add(key)
            note = " ".join(str(item.get("note") or "").split())
            out.append({"from": src, "to": dst, "note": note})
    return out[:MAX_ENTRIES]


def entries(profile: dict[str, Any] | None) -> list[dict[str, str]]:
    return clean((profile or {}).get("glossary"))


def _has(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I))


def known_terms(text: str, profile: dict[str, Any] | None) -> list[str]:
    """The "to" terms of every entry whose "from" term the text contains."""
    return [e["to"] for e in entries(profile) if _has(text, e["from"])]


def expand(text: str, profile: dict[str, Any] | None) -> str:
    """The text plus the terms your glossary equates with words it contains."""
    extra = known_terms(text, profile)
    return text + ("\n" + "\n".join(extra) if extra else "")


def prompt_facts(profile: dict[str, Any] | None) -> dict[str, Any]:
    """FACTS.glossary for the generators: only when you wrote entries."""
    found = entries(profile)
    return {"glossary": [{"from": e["from"], "to": e["to"], **({"note": e["note"]}
                                                             if e["note"] else {})}
                         for e in found]} if found else {}


def verifier_lines(profile: dict[str, Any] | None) -> str:
    """What the claim verifier is told (in its FACTS source): the candidate's own equivalences."""
    found = entries(profile)
    if not found:
        return ""
    return ("Glossary (written by the candidate: a term their experience uses = the term of the "
            "field they are moving into; it adds no tool, number, scale or year):\n"
            + "\n".join(f"- “{e['from']}” = “{e['to']}”" for e in found))
