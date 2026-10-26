"""One listing per real job: which description the main listing keeps, marking a score stale
when it changes, and the one-off backfill that folds old duplicate rows into their main listing
and recomputes every dedupe key (migration 0033).

Duplicate rows are never deleted or changed in their own text: they stay hidden
(`duplicate_of_id`), and the main listing gets all their sources and URLs.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, text

from app.services.dedupe import _LEGAL_SUFFIXES, _ascii_words, dedupe_key, normalize_title

SNIPPET_CHARS = 1500  # below this a description is a snippet (the same bound as applied_check)
STALE_MARK = "stale:description-changed"
# What the branch's first dedupe change stripped on top of the real legal forms: descriptive
# words that are part of a company's name.
_BRANCH_EXTRA = {"co", "corporation", "limited", "holding", "holdings", "technologies",
                 "solutions", "kg", "ab", "oy", "corp", "llp"}


def should_take_description(main_text: str | None, other_text: str | None) -> bool:
    """The main listing keeps its own text unless it is a snippet (under ~1,500 characters) and
    the other one is clearly longer (a full listing)."""
    main, other = len(main_text or ""), len(other_text or "")
    return main < SNIPPET_CHARS and other >= SNIPPET_CHARS and other > main * 1.5


def mark_score_stale(conn: Connection, job_id: int) -> bool:
    """The job's description changed: its latest score no longer matches it. Nothing is rescored
    (the user decides); the score shows as stale (counts/views compare `experience_version`)."""
    latest = conn.execute(text("SELECT id, experience_version FROM fit_score WHERE job_id = :j "
                               "ORDER BY id DESC LIMIT 1"), {"j": job_id}).first()
    if latest is None or latest[1] == STALE_MARK:
        return False
    conn.execute(text("UPDATE fit_score SET experience_version = :m WHERE id = :i"),
                 {"m": STALE_MARK, "i": latest[0]})
    return True


def _company_key(name: str, suffixes: set[str]) -> str:
    words = [w for w in _ascii_words(name) if w not in suffixes]
    return " ".join(words) or name.strip().lower()


def _load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    return json.loads(value) if isinstance(value, str) else value


@dataclass
class Report:
    counts: dict[str, int] = field(default_factory=dict)
    samples: dict[str, list[Any]] = field(default_factory=dict)

    def add(self, key: str, n: int = 1, sample: Any = None) -> None:
        self.counts[key] = self.counts.get(key, 0) + n
        if sample is not None and len(self.samples.setdefault(key, [])) < 5:
            self.samples[key].append(sample)


def backfill(conn: Connection, *, apply: bool,
             originals: dict[int, str] | None = None) -> Report:
    """Recompute every dedupe key (country kept) and fold duplicate rows into their main row.

    `originals`: the main rows' descriptions as they were before migration 0032 overwrote some
    of them with a duplicate's text (read from a backup, optional). With `apply=False` nothing
    is written: it only counts."""
    rep = Report()
    rows = conn.execute(text(
        "SELECT j.id, j.source, j.url, j.title, j.country, j.description, j.description_level, "
        "j.full_fetched_at, j.dedupe_key, j.duplicate_of_id, j.sources, j.source_urls, "
        "c.name AS company FROM job j JOIN company c ON c.id = j.company_id")).mappings().all()
    by_id = {r["id"]: r for r in rows}
    dups: dict[int, list[Any]] = {}
    for r in rows:
        if r["duplicate_of_id"]:
            dups.setdefault(r["duplicate_of_id"], []).append(r)
    mains = [r for r in rows if not r["duplicate_of_id"]]
    rep.add("jobs", len(rows))
    rep.add("main_listings", len(mains))
    rep.add("duplicate_rows", len(rows) - len(mains))
    rep.add("duplicate_rows_without_a_main", sum(
        1 for r in rows if r["duplicate_of_id"] and r["duplicate_of_id"] not in by_id))

    # ---- keys (country kept)
    new_key = {r["id"]: dedupe_key(r["company"], r["title"], r["country"]) for r in rows}
    rep.add("keys_changed", sum(1 for r in rows if r["dedupe_key"] != new_key[r["id"]]))
    # ---- groups: what the suffix list changes, and what stays separate
    def groups(suffixes: set[str]) -> dict[str, set[int]]:
        out: dict[str, set[int]] = {}
        for r in mains:
            key = (f"{_company_key(r['company'], suffixes)}::{normalize_title(r['title'])}"
                   f"::{(r['country'] or '').lower()}")
            out.setdefault(key, set()).add(r["id"])
        return out
    current, branch = groups(_LEGAL_SUFFIXES), groups(_LEGAL_SUFFIXES | _BRANCH_EXTRA)
    rep.add("main_groups_by_key", len(current))
    rep.add("groups_the_branch_suffix_list_would_have_merged",
            sum(1 for ids in branch.values() if len({k for k, v in current.items()
                                                     if v & ids}) > 1))
    rep.add("main_rows_with_the_same_key_not_folded", sum(len(v) for v in current.values()
                                                          if len(v) > 1))
    rep.add("groups_with_the_same_key_not_folded", sum(1 for v in current.values()
                                                       if len(v) > 1))
    spans: dict[str, set[str]] = {}
    for r in mains:
        fp = f"{_company_key(r['company'], _LEGAL_SUFFIXES)}::{normalize_title(r['title'])}"
        spans.setdefault(fp, set()).add((r["country"] or "").lower())
    rep.add("company_title_groups_in_several_countries_kept_apart",
            sum(1 for v in spans.values() if len(v) > 1))

    # ---- fold the duplicates into their main listing
    for main in mains:
        sources = list(_load(main["sources"], []))
        urls = dict(_load(main["source_urls"], {}))
        own = str(main["source"])
        if own not in sources:
            sources.append(own)
        urls.setdefault(own, main["url"])
        children = dups.get(main["id"], [])
        for d in children:
            if str(d["source"]) not in sources:
                sources.append(str(d["source"]))
            urls.setdefault(str(d["source"]), d["url"])
        if children:
            rep.add("mains_with_duplicates")
        if len(sources) > 1:
            rep.add("mains_with_several_sources")
        # description: its own text, unless it is a snippet and a duplicate has the full listing
        text_now = main["description"] or ""
        # Only a main row whose text IS a duplicate's (migration 0032 copied it over) goes back to
        # its own text; anything else that differs from the backup was changed on purpose since
        # (a fetched or pasted listing, an edit) and is the main listing's own text now.
        was = (originals or {}).get(main["id"])
        copied = was is not None and was != text_now and any(
            (d["description"] or "") == text_now for d in children)
        own_text = was if copied else text_now
        best = max(children, key=lambda d: len(d["description"] or ""), default=None)
        desc, level, fetched = own_text, main["description_level"], main["full_fetched_at"]
        if best is not None and should_take_description(own_text, best["description"]):
            desc, level = best["description"], best["description_level"]
            fetched = best["full_fetched_at"] or fetched
            rep.add("descriptions_taken_from_a_duplicate", sample=main["id"])
        elif own_text != text_now:
            rep.add("descriptions_restored_to_the_main_listings_own_text", sample=main["id"])
        changed = desc != text_now
        if changed:
            rep.add("descriptions_changed")
        if apply:
            conn.execute(text(
                "UPDATE job SET dedupe_key = :k, sources = :s, source_urls = :u, "
                "description = :d, description_level = :l, full_fetched_at = :f WHERE id = :i"),
                {"k": new_key[main["id"]], "s": json.dumps(sources), "u": json.dumps(urls),
                 "d": desc, "l": level, "f": fetched, "i": main["id"]})
            if changed and mark_score_stale(conn, main["id"]):
                rep.add("scores_marked_stale")
        elif changed and conn.execute(text("SELECT 1 FROM fit_score WHERE job_id = :j"),
                                      {"j": main["id"]}).first():
            rep.add("scores_that_would_be_marked_stale")
    for r in rows:
        if not r["duplicate_of_id"]:
            continue
        if apply:  # a hidden duplicate keeps its own text; it just knows its own source
            conn.execute(text("UPDATE job SET dedupe_key = :k, sources = :s, source_urls = :u "
                              "WHERE id = :i"),
                         {"k": new_key[r["id"]], "s": json.dumps([str(r["source"])]),
                          "u": json.dumps({str(r["source"]): r["url"]}), "i": r["id"]})
    return rep
