"""Plan + pool + user overrides + fit state → CVDocument, and the one-page fit loop (in code, no
model call): compile, measure, then drop or add bullets until the CV is exactly one full page.

Overflow, in order: drop the least valuable extra bullets (roles keep at least one) → drop the
least relevant projects/volunteering → switch to the short summary.
Underfill: add the next most valuable bullets, then the next project.
Value of a bullet = entry relevance × 10 − its rank inside the entry.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.providers.base import CVPlan, PlanEntry
from app.services.cv_pool import Pool, span
from app.services.cv_render import (
    CompileResult,
    CVCertification,
    CVDocument,
    CVEducation,
    CVProfile,
    CVProject,
    CVRole,
    CVSkillGroup,
    CVTemplate,
    compile_tex,
    render_tex,
)

MAX_PASSES = 4
LINES_PER_PAGE = 55  # rough line capacity of a 10pt letter page with these margins
LINES_PER_BULLET = 1.7


@dataclass
class FitState:
    counts: dict[str, int] = field(default_factory=dict)  # "role:12" → visible bullets
    short_summary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"counts": dict(self.counts), "short_summary": self.short_summary}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FitState":
        data = data or {}
        return cls(counts=dict(data.get("counts") or {}),
                   short_summary=bool(data.get("short_summary")))


def _key(kind: str, entry: PlanEntry) -> str:
    return f"{kind}:{entry.item_id}"


def initial_state(plan: CVPlan, max_bullets: int = 5) -> FitState:
    state = FitState()
    for e in plan.roles:
        k = 4 if e.relevance >= 8 else 3 if e.relevance >= 5 else 2
        state.counts[_key("role", e)] = max(1, min(k, max_bullets, len(e.bullets)))
    for n, p in enumerate(plan.projects):
        state.counts[_key("project", p)] = min(2, len(p.bullets)) if n < 2 and p.relevance >= 5 \
            else 0
    for v in plan.volunteering:
        state.counts[_key("volunteering", v)] = 1 if v.relevance >= 7 and v.bullets else 0
    return state


def _visible(entry: PlanEntry, key: str, count: int, overrides: dict[str, Any],
             keep_one: bool) -> list[tuple[str, str]]:
    """(override key, text) of the bullets shown for an entry, most relevant first: bullets the
    user forced in, then the best-ranked others up to `count`; never a forced-out one."""
    forced_in = set(overrides.get("force_in") or [])
    forced_out = set(overrides.get("force_out") or [])
    texts = overrides.get("text") or {}
    ranked = [(f"{key}:{b.source_index}", b.text)
              for b in sorted(entry.bullets, key=lambda x: x.priority)]
    forced = [b for b in ranked if b[0] in forced_in]
    rest = [b for b in ranked if b[0] not in forced_in and b[0] not in forced_out]
    shown = forced + rest[: max(0, count - len(forced))]
    if keep_one and not shown and ranked:
        shown = [ranked[0]]
    return [(k, texts.get(k, t)) for k, t in shown]


def build_document(plan: CVPlan, pool: Pool, state: FitState,
                   overrides: dict[str, Any] | None = None, max_stack: int = 6) -> CVDocument:
    overrides = overrides or {}
    forced_in = set(overrides.get("force_in") or [])
    forced_out = set(overrides.get("force_out") or [])
    texts = overrides.get("text") or {}
    summary = texts.get("summary") or (plan.summary_short if state.short_summary and
                                       plan.summary_short else plan.summary)
    roles = []
    for e in plan.roles:
        item = pool.get(e.item_id, "job")
        if item is None:
            continue
        key = _key("role", e)
        start, end = span(item)
        bullets = _visible(e, key, state.counts.get(key, 1), overrides, keep_one=True)
        roles.append(CVRole(item_id=item.id, title=item.title, org=item.org or "",
                            location=item.location or "", start=start, end=end,
                            bullets=[t for _, t in bullets]))
    projects = []
    for p in plan.projects:
        item = pool.get(p.item_id, "project")
        key = _key("project", p)
        if item is None or key in forced_out:
            continue
        count = state.counts.get(key, 0)
        if count <= 0 and key not in forced_in:
            continue
        bullets = _visible(p, key, max(count, 1), overrides, keep_one=False)
        stack = (list(p.stack) or item.tags)[:max_stack]
        projects.append(CVProject(item_id=item.id, name=item.title,
                                  stack=stack, label=item.org or "",
                                  bullets=[t for _, t in bullets]))
    volunteering = []
    for v in plan.volunteering:
        item = pool.get(v.item_id, "volunteering")
        key = _key("volunteering", v)
        if item is None or key in forced_out or (state.counts.get(key, 0) <= 0
                                                 and key not in forced_in):
            continue
        start, end = span(item)
        bullets = _visible(v, key, max(1, state.counts.get(key, 0)), overrides, keep_one=False)
        volunteering.append(CVRole(item_id=item.id, title=item.title, org=item.org or "",
                                   location=item.location or "", start=start, end=end,
                                   bullets=[t for _, t in bullets]))
    certs = [i for i in plan.certification_ids if f"cert:{i}" not in forced_out]
    certs += [int(k.split(":")[1]) for k in forced_in
              if k.startswith("cert:") and int(k.split(":")[1]) not in certs]
    certifications = []
    for cid in certs:
        item = pool.get(cid, "certification")
        if item:
            certifications.append(CVCertification(
                item_id=item.id, name=item.title, issuer=item.org or "",
                credential_id=item.credential_id or "", url=item.url or ""))
    education = []
    for eid in plan.education_ids:
        item = pool.get(eid, "education")
        if item:
            start, end = span(item)
            education.append(CVEducation(item_id=item.id, school=item.org or "",
                                         degree=item.title, location=item.location or "",
                                         start=start, end=end))
    skills = []
    for g in plan.skills:
        item = pool.get(g.item_id, "skill")
        if item and g.items:
            skills.append(CVSkillGroup(category=item.title, items=list(g.items)))
    return CVDocument(summary=summary, skills=skills, roles=roles, projects=projects,
                      certifications=certifications, education=education,
                      volunteering=volunteering)


# ------------------------------------------------------------------------------------ fitting


def _entries(plan: CVPlan) -> list[tuple[str, PlanEntry, bool]]:
    """(key, entry, must_keep_one) for every entry the loop may grow or shrink."""
    return ([(_key("role", e), e, True) for e in plan.roles]
            + [(_key("project", p), p, False) for p in plan.projects]
            + [(_key("volunteering", v), v, False) for v in plan.volunteering])


def shrink(plan: CVPlan, state: FitState, n: int) -> int:
    """Remove up to n of the least valuable extra bullets (never a role's last one). Returns how
    many were removed."""
    removed = 0
    for _ in range(n):
        candidates = [(e.relevance * 10 - state.counts[k], k)
                      for k, e, _keep in _entries(plan) if state.counts.get(k, 0) > 1]
        if not candidates:
            break
        _, key = min(candidates)
        state.counts[key] -= 1
        removed += 1
    return removed


def drop_entry(plan: CVPlan, state: FitState) -> bool:
    """Remove the least relevant visible project/volunteering entry."""
    candidates = [(e.relevance, k) for k, e, keep in _entries(plan)
                  if not keep and state.counts.get(k, 0) > 0]
    if not candidates:
        return False
    state.counts[min(candidates)[1]] = 0
    return True


def grow(plan: CVPlan, state: FitState, n: int, max_bullets: int) -> int:
    """Add up to n of the most valuable hidden bullets; a hidden project counts as 3 lines."""
    added = 0
    for _ in range(n):
        candidates = []
        for k, e, keep in _entries(plan):
            count = state.counts.get(k, 0)
            if count == 0 and keep is False and e.bullets and e.relevance >= 3:
                candidates.append((e.relevance * 10 - 5, k))  # show a new project
            elif 0 < count < min(len(e.bullets), max_bullets):
                candidates.append((e.relevance * 10 - count - 1, k))
        if not candidates:
            break
        _, key = max(candidates)
        state.counts[key] = state.counts.get(key, 0) + 1
        added += 1
    return added


@dataclass
class FitResult:
    document: CVDocument
    state: FitState
    compiled: CompileResult
    tex: str
    passes: int
    history: list[dict[str, Any]]


def fit_to_page(plan: CVPlan, pool: Pool, profile: CVProfile, template: CVTemplate,
                out_dir: Path, *, state: FitState | None = None,
                overrides: dict[str, Any] | None = None) -> FitResult:
    """Compile, measure, adjust, up to MAX_PASSES adjustments. Keeps the fullest one-page
    result seen; if none fit, returns the last (with its page count, flagged by the caller)."""
    max_bullets = int(template.config.get("max_bullets_per_role") or 5)
    state = state or initial_state(plan, max_bullets)
    target = template.min_fill
    best: FitResult | None = None
    history: list[dict[str, Any]] = []
    last: FitResult | None = None
    for attempt in range(MAX_PASSES + 1):
        doc = build_document(plan, pool, state, overrides,
                             int(template.config.get("max_stack_items") or 6))
        tex = render_tex(doc, profile, template)
        result = compile_tex(tex, out_dir, "cv")
        history.append({"pass": attempt, "pages": result.pages, "fill": round(result.fill, 3),
                        "ok": result.ok})
        last = FitResult(doc, FitState.from_dict(state.to_dict()), result, tex, attempt, history)
        if not result.ok:
            return last
        if result.pages == 1 and (best is None or result.fill > best.compiled.fill):
            best = last
        if result.pages == 1 and result.fill >= target:
            break
        if attempt == MAX_PASSES:
            break
        if result.pages > 1:
            overflow_lines = ((result.pages - 2) + result.fill) * LINES_PER_PAGE
            need = max(1, math.ceil(overflow_lines / LINES_PER_BULLET))
            removed = shrink(plan, state, need)
            while removed < need and drop_entry(plan, state):
                removed += 3
            if removed == 0 and not state.short_summary:
                state.short_summary = True
            elif removed == 0:
                break  # nothing left to trim
        else:
            gap_lines = (min(0.97, target + 0.04) - result.fill) * LINES_PER_PAGE
            if not grow(plan, state, max(1, math.floor(gap_lines / LINES_PER_BULLET)),
                        max_bullets):
                break  # nothing left to add: this is as full as the pool allows
    chosen = best or last
    assert chosen is not None
    if chosen is not last:  # re-render the best one-page state so files on disk match it
        tex = render_tex(chosen.document, profile, template)
        chosen.compiled = compile_tex(tex, out_dir, "cv")
        chosen.tex = tex
    chosen.passes = len(history) - 1
    chosen.history = history
    return chosen
