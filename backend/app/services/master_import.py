"""Import of the master experience document (data/import/master_experience.md) into the pool.

Explicit and user-run only (`scripts/import_master.py`, after a preview): the text is taken
verbatim, with one exception, the tool-citation markers some exports append to every line
(`[cite: 1]`), which are not content. Every write goes through `experience_write` (history +
undo). Old items the document doesn't contain are archived (inactive, restorable), and old
bullets replaced by new text stay in the item's history; nothing is deleted.

Not imported: contact information (your Candidate profile stays as it is), the target profile
summaries (they conflict with the honesty and years rules), and a languages section (Settings →
Candidate owns it).

The mapping of document entries to existing pool ids, and the suggested tags, are data
(`data/import/master_mapping.json`), not code: they name your employers.
"""

import calendar
import re
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.models import ExperienceItem
from app.services import experience_write

_CITE = re.compile(r"[ \t]*\[cite: ?\d+(?:, ?\d+)*\]")
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def clean(text: str) -> str:
    return _CITE.sub("", text)


def split_top(text: str) -> list[str]:
    """Split on commas outside parentheses ("LLMs (Mistral 7B, Ollama), RAG" → 2 items)."""
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return [x for x in [*out, cur.strip()] if x]


def _point(token: str, end: bool) -> date | None:
    token = token.strip()
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", token):
        month, year = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"([A-Za-z]+)\.? (\d{4})", token):
        month, year = MONTHS.get(m.group(1)[:3].lower(), 0), int(m.group(2))
    elif m := re.fullmatch(r"(\d{4})", token):
        month, year = (12 if end else 1), int(m.group(1))
    else:
        return None
    if not 1 <= month <= 12:
        return None
    return date(year, month, calendar.monthrange(year, month)[1] if end else 1)


def parse_dates(label: str | None) -> tuple[date | None, date | None]:
    """'Sep 2025 – Present' · 'Sep 2020 – June 2025' · '07/2023 – 05/2024' · '2022 – Present'.
    A lone year ('2020') has no usable months: both None (the label alone is shown)."""
    if not label or " – " not in label:
        return None, None
    left, right = label.split(" – ", 1)
    end = None if right.strip().lower() in ("present", "now", "current") else _point(right, True)
    return _point(left, False), end


def _sections(text: str) -> dict[str, str]:
    return {m.group(1).strip(): m.group(2).strip()
            for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.S | re.M)}


def _blocks(body: str) -> list[str]:
    return re.split(r"^### ", body, flags=re.M)[1:]


def _bullets(text: str) -> list[str]:
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]


def _italic(block: str) -> str:
    m = re.search(r"^\*(.+?)\*\s*$", block, re.M)
    return m.group(1).strip() if m else ""


def parse(markdown: str) -> list[dict[str, Any]]:
    """The importable sections as pool item dicts (ExperienceItem fields + `key`, the string the
    mapping file uses to refer to the entry)."""
    sections = _sections(clean(markdown))
    items: list[dict[str, Any]] = []

    def add(kind: str, key: str, **fields: Any) -> None:
        start, end = parse_dates(fields.get("date_label"))
        items.append({"kind": kind, "key": key, "start_date": start, "end_date": end,
                      "bullets": [], "tags": [], **fields})

    for block in _blocks(sections.get("Professional Experience", "")):
        head, rest = block.split("\n", 1)
        org, title = (x.strip() for x in head.split(" — ", 1))
        location, _, dates = (x.strip() for x in _italic(rest).rpartition("|"))
        add("job", org, org=org, title=title, location=location, date_label=dates,
            bullets=_bullets(rest))
    for block in _blocks(sections.get("Technical Projects", "")):
        head, rest = block.split("\n", 1)
        add("project", head.strip(), title=head.strip(), tags=split_top(_italic(rest)),
            bullets=_bullets(rest))
    skills = next((v for k, v in sections.items() if k.startswith("Technical Skills")), "")
    for line in _bullets(skills):
        if m := re.match(r"\*\*(.+?):\*\*\s*(.+)", line):
            add("skill", m.group(1), title=m.group(1), tags=split_top(m.group(2)))
    edu = sections.get("Education", "")
    for chunk in re.split(r"^- (?=\*\*)", edu, flags=re.M)[1:]:
        school = re.match(r"\*\*(.+?)\*\*(?: — (.+))?", chunk)
        name, place = school.group(1), school.group(2)
        degree = re.search(r"^\s+- \*(.+?)\*\s*\|\s*(.+)$", chunk, re.M)
        bullets = [x.replace("**", "").strip() for x in re.findall(r"^\s+- (\*\*.+)$", chunk, re.M)]
        if degree:
            add("education", name, org=name, location=place, title=degree.group(1).strip(),
                date_label=degree.group(2).strip(), bullets=bullets)
        else:
            m = re.search(r"\|\s*(\d{4})\s*$", chunk.split("\n", 1)[0])
            add("education", name, org=None, title=name.split(" | ")[0],
                date_label=m and m.group(1), bullets=bullets)
    for line in _bullets(sections.get("Certifications", "")):
        if m := re.match(r"\*\*(.+?)\*\* — (.+?) \*\(ID: (.+?)\)\*", line):
            add("certification", m.group(2), title=m.group(1), org=m.group(2),
                credential_id=m.group(3))
    vol = next((v for k, v in sections.items() if k.startswith("Volunteering")), "")
    for line in _bullets(vol):
        if m := re.match(r"\*\*(.+?) — (.+?) \((.+?)\):\*\* (.+)", line):
            add("volunteering", m.group(1), org=m.group(1), title=m.group(2),
                date_label=m.group(3), bullets=[m.group(4).strip()])
    return items


# ------------------------------------------------------------------------------- apply


def _key(kind: str, key: str) -> str:
    return f"{kind}|{key}"


def plan(s: Session, items: list[dict[str, Any]], mapping: dict[str, Any]) -> dict[str, Any]:
    """What applying would do: per document entry the pool item it replaces (or None = new), and
    the old items the document doesn't contain (to archive). Writes nothing."""
    match = mapping.get("match", {})
    existing = {i.id: i for i in s.exec(select(ExperienceItem)).all() if i.kind != "summary"}
    rows, used = [], set()
    for it in items:
        old_id = match.get(_key(it["kind"], it["key"]))
        if old_id is None:  # an earlier run of this import already created it
            old_id = next((i.id for i in existing.values()
                           if i.kind == it["kind"] and i.title == it["title"]
                           and (i.org or None) == (it.get("org") or None)
                           and i.id not in used and i.id not in match.values()), None)
        if old_id is not None and old_id not in existing:
            raise ValueError(f"Mapping points at pool item {old_id}, which doesn't exist")
        if old_id is not None and old_id in used:
            raise ValueError(f"Pool item {old_id} is the target of two document entries")
        if old_id is not None:
            used.add(old_id)
        rows.append({"entry": it, "item_id": old_id})
    archive = [i for i in existing.values() if i.id not in used and i.is_active]
    return {"rows": rows, "archive": archive}


def fields(it: dict[str, Any], old: ExperienceItem | None, mapping: dict[str, Any]
           ) -> dict[str, Any]:
    out = {k: it.get(k) for k in ("kind", "title", "org", "location", "start_date", "end_date",
                                  "date_label", "bullets", "credential_id")}
    out["summary"] = None  # not in the document: the old one-liner is archived in the history
    out["is_active"] = True
    tags = mapping.get("tags", {}).get(_key(it["kind"], it["key"]))
    out["tags"] = list(tags) if tags is not None else list(it.get("tags") or [])
    if it["kind"] == "project":  # the CV's project label: kept, it isn't pool text
        out["org"] = (old.org if old else None) or mapping.get("project_label") or None
    if it["kind"] == "certification":
        out["credential_id"] = it.get("credential_id")
    return out


def apply(s: Session, items: list[dict[str, Any]], mapping: dict[str, Any],
          note: str = "master document import") -> dict[str, int]:
    """Write the pool (caller commits). Idempotent: running it twice changes nothing."""
    todo = plan(s, items, mapping)
    counts = {"updated": 0, "created": 0, "archived": 0, "unchanged": 0}
    for n, row in enumerate(todo["rows"]):
        it = row["entry"]
        old = s.get(ExperienceItem, row["item_id"]) if row["item_id"] is not None else None
        data = fields(it, old, mapping)
        if old is None:
            experience_write.create(s, {**data, "position": n + 1}, source="master_import",
                                    note=note)
            counts["created"] += 1
            continue
        before = experience_write.snapshot(old)
        experience_write.update(s, old, {**data, "position": n + 1}, source="master_import",
                                note=note)
        counts["updated" if experience_write.snapshot(old) != before else "unchanged"] += 1
    for old in todo["archive"]:
        experience_write.archive(s, old, source="master_import",
                                 note="not in the master document")
        counts["archived"] += 1
    return counts
