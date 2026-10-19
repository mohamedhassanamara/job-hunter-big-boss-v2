"""Light tailoring of CV bullets, in the CV copy only. The pool keeps your exact text.

Claude may adapt a bullet to the job: another verb, reordered clauses, the listing's term for
something you did ("REST APIs" for "RESTful backend services"). Code enforces the limits against
the pool original of that exact bullet (`pool.facts(item)[source_index]`):

- every number, tool and named product of the original is still there;
- no number, tool or skill that isn't in the pool, no years claim;
- length within ±15% of the original, most of its words kept, little added;
- the Claude verifier judges each adapted bullet against its original (`verify`).

Any failure puts the original text back for that bullet (and the reason is recorded). Nothing
here ever writes to the pool.
"""

import re
from typing import Any

from app.providers.base import CVPlan, PlanBullet, PlanEntry
from app.services.cv_check import _NOT_TOOLS, _TECHY, _TOOLS, new_tools, numbers
from app.services.cv_claims import Vocabulary, pool_vocabulary, years_claims
from app.services.cv_pool import Pool, norm, terms_of

LENGTH_TOLERANCE = 0.15
KEEP_WORDS = 0.6  # share of the original's content words that must survive
ADD_WORDS = 0.3  # share of the adapted bullet's content words that may be new

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.'-]*")
_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "across", "over", "while",
         "using", "their", "its", "was", "were", "has", "have", "had", "been", "being", "are",
         "our", "your", "all", "any", "per", "via", "then", "than", "also", "both", "each"}


def plain(text: str) -> str:
    """Markdown marks (`code`, **bold**) are formatting, not wording."""
    return text.replace("`", "").replace("**", "").strip()


def stem(word: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", word.lower())[:5]


def content_stems(text: str) -> set[str]:
    return {stem(w) for w in _WORD.findall(text) if len(w) > 3 and w.lower() not in _STOP}


def pool_terms_in(text: str, pool: Pool) -> set[str]:
    """Skills and tools of the pool (as written there) that the text mentions."""
    found = set()
    for item in pool.items.values():
        for term in terms_of(item.tags):
            if len(norm(term)) < 3:
                continue
            pattern = r"(?<![\w])" + re.escape(term).replace(r"\-", r"[\s-]?") + r"(?![\w])"
            if re.search(pattern, text, re.I):
                found.add(term)
    return found


def protected(original: str, pool: Pool) -> list[str]:
    """Tools and named products of the original that the adapted bullet must keep: acronyms and
    CamelCase tools, known tools, pool skills, and capitalised names after the first word."""
    terms = set(_TECHY.findall(original))
    terms |= {w for w in _WORD.findall(original) if w.lower() in _TOOLS}
    terms |= pool_terms_in(original, pool)
    words = _WORD.findall(original)
    terms |= {w for w in words[1:] if w[0].isupper() and w.lower() not in _NOT_TOOLS}
    kept: list[str] = []  # "Spring Boot" covers "Spring", "Boot" and "spring-boot"
    for t in sorted((t for t in terms if norm(t) and t.lower() not in _NOT_TOOLS),
                    key=lambda x: (-len(norm(x)), x)):
        if not any(norm(t) in norm(k) for k in kept):
            kept.append(t)
    return sorted(kept)


def _kept(term: str, adapted: str) -> bool:
    n, text = norm(term), norm(adapted)
    if n in text:
        return True
    # "REST APIs" for "RESTful": the listing's own form of the same word
    return any(len(norm(w)) >= 4 and (n.startswith(norm(w)) or norm(w).startswith(n))
               for w in _WORD.findall(adapted))


def problems(original: str, adapted: str, pool: Pool, vocab: Vocabulary | None = None
             ) -> list[str]:
    """Why `adapted` isn't an allowed adaptation of `original` (empty = allowed)."""
    if plain(adapted) == plain(original):
        return []
    out: list[str] = []
    vocab = vocab or pool_vocabulary(pool)
    have = {re.sub(r"[^\d]", "", n) for n in numbers(adapted)}
    want = {re.sub(r"[^\d]", "", n) for n in numbers(original)}
    if missing := sorted(want - have):
        out.append(f"drops the number {', '.join(missing)}")
    if extra := sorted(have - want):
        out.append(f"adds the number {', '.join(extra)}")
    if lost := [t for t in protected(original, pool) if not _kept(t, adapted)]:
        out.append(f"drops {', '.join(lost)}")
    if tools := new_tools(adapted, vocab):
        out.append(f"adds {', '.join(tools)}, which isn't in your experience")
    if claims := [c for c, _ in years_claims(adapted) if c not in original]:
        out.append(f"adds a years claim ({claims[0]})")
    ratio = len(adapted) / max(1, len(original))
    if not 1 - LENGTH_TOLERANCE <= ratio <= 1 + LENGTH_TOLERANCE:
        out.append(f"length {ratio - 1:+.0%} (limit ±{LENGTH_TOLERANCE:.0%})")
    kept, now = content_stems(original), content_stems(adapted)
    if kept and len(kept & now) / len(kept) < KEEP_WORDS:
        out.append("drops too much of the original wording")
    if now and len(now - kept) / len(now) > ADD_WORDS:
        out.append("adds wording that isn't in the original")
    return out


def entries(plan: CVPlan) -> list[tuple[str, list[PlanEntry]]]:
    return [("job", plan.roles), ("project", plan.projects),
            ("volunteering", plan.volunteering)]


def original_of(pool: Pool, item_id: int, index: int) -> str | None:
    item = pool.get(item_id)
    facts = pool.facts(item) if item else []
    return facts[index] if 0 <= index < len(facts) else None


def enforce(plan: CVPlan, pool: Pool, *, original_only: bool = False
            ) -> tuple[CVPlan, list[dict[str, Any]], dict[str, Any]]:
    """Check every bullet against its pool original; the original comes back where the
    adaptation fails (or everywhere with `original_only`). Returns the plan, the violations to
    show (warnings: nothing broken, the original was used) and a report."""
    vocab = pool_vocabulary(pool)
    issues: list[dict[str, Any]] = []
    report: dict[str, Any] = {"adapted": 0, "original": 0, "fallbacks": []}

    def fix(entry: PlanEntry) -> PlanEntry:
        item = pool.get(entry.item_id)
        bullets = []
        for b in entry.bullets:
            original = original_of(pool, entry.item_id, b.source_index)
            if original is None:
                bullets.append(b)
                continue
            why = [] if original_only else problems(original, b.text, pool, vocab)
            if original_only or why or plain(b.text) == plain(original):
                if why:
                    report["fallbacks"].append({"bullet": f"{entry.item_id}:{b.source_index}",
                                                "reasons": why, "tried": b.text})
                    issues.append({"type": "tailoring", "severity": "warning",
                                   "where": f"{item.title if item else entry.item_id}: bullet "
                                            f"{b.source_index}",
                                   "message": f"Adapted wording rejected ({'; '.join(why)}): "
                                              "your original text is used"})
                report["original"] += 1
                bullets.append(b.model_copy(update={"text": original, "adapted": False,
                                                    "fallback": "; ".join(why) or None}))
            else:
                report["adapted"] += 1
                bullets.append(b.model_copy(update={"adapted": True, "fallback": None}))
        return entry.model_copy(update={"bullets": bullets})

    update = {field: [fix(e) for e in group]
              for (field, group) in (("roles", plan.roles), ("projects", plan.projects),
                                     ("volunteering", plan.volunteering))}
    return plan.model_copy(update=update), issues, report


# --------------------------------------------------------------------- the Claude verifier


def adapted_bullets(plan: CVPlan, pool: Pool) -> dict[str, tuple[PlanBullet, str]]:
    """key → (bullet, its original) for the bullets whose text differs from the pool."""
    out = {}
    for _kind, group in entries(plan):
        for e in group:
            for b in e.bullets:
                original = original_of(pool, e.item_id, b.source_index)
                if original is not None and b.adapted and plain(b.text) != plain(original):
                    out[f"{e.item_id}:{b.source_index}"] = (b, original)
    return out


def verify(plan: CVPlan, pool: Pool, verifier: Any) -> tuple[CVPlan, list[dict[str, Any]],
                                                              dict[str, Any] | None]:
    """The Claude verifier checks each adapted bullet against its original (one call per CV).
    A bullet with any blocking claim, or one the verifier didn't judge, goes back to the
    original. A verifier that can't run leaves the code-checked adaptations in place, flagged."""
    from app.services import verifier as verifier_service

    todo = adapted_bullets(plan, pool)
    if not todo or verifier is None:
        return plan, [], None
    sources = {f"bullet:{key}": original for key, (_b, original) in todo.items()}
    text = "\n".join(b.text.rstrip(".") + "." for b, _o in todo.values())
    record = verifier_service.run(verifier, "cv_bullets", text, sources)
    issues: list[dict[str, Any]] = []
    if record["status"] == "error":
        issues.append({"type": "tailoring", "severity": "warning", "where": "verifier",
                       "message": f"The claim verifier couldn't check the adapted bullets "
                                  f"({record.get('error')}): re-render with 'Use original "
                                  "bullets only' or regenerate"})
        return plan, issues, record
    bad = {c["sentence"] for c in record["claims"] if c["verdict"] in verifier_service.BLOCKING}
    failed = {key for key, (b, _o) in todo.items()
              if any(s and (s in b.text or b.text.rstrip(".") in s) for s in bad)}

    def fix(entry: PlanEntry) -> PlanEntry:
        item = pool.get(entry.item_id)
        bullets = []
        for b in entry.bullets:
            key = f"{entry.item_id}:{b.source_index}"
            if key in failed:
                reason = next((c["reason"] for c in record["claims"]
                               if c["verdict"] in verifier_service.BLOCKING
                               and c["sentence"] and c["sentence"] in b.text), "not verified")
                issues.append({"type": "tailoring", "severity": "warning",
                               "where": f"{item.title if item else entry.item_id}: bullet "
                                        f"{b.source_index}",
                               "message": f"The claim verifier rejected the adapted wording "
                                          f"({reason.rstrip('.')}): your original text is used"})
                b = b.model_copy(update={"text": todo[key][1], "adapted": False,
                                         "fallback": f"verifier: {reason}"})
            bullets.append(b)
        return entry.model_copy(update={"bullets": bullets})

    plan = plan.model_copy(update={f: [fix(e) for e in g] for f, g in (
        ("roles", plan.roles), ("projects", plan.projects),
        ("volunteering", plan.volunteering))})
    return plan, issues, record


def pin_originals(plan: CVPlan, pool: Pool) -> CVPlan:
    """Bullets that are not adaptations carry their pool text exactly (canonical respelling of a
    whole plan must not touch them)."""
    def fix(entry: PlanEntry) -> PlanEntry:
        bullets = []
        for b in entry.bullets:
            original = original_of(pool, entry.item_id, b.source_index)
            bullets.append(b.model_copy(update={"text": original})
                           if original is not None and not b.adapted else b)
        return entry.model_copy(update={"bullets": bullets})

    return plan.model_copy(update={f: [fix(e) for e in g] for f, g in (
        ("roles", plan.roles), ("projects", plan.projects),
        ("volunteering", plan.volunteering))})
