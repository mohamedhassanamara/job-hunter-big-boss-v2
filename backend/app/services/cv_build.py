"""Plan + pool + user overrides + fit state → CVDocument, and the one-page fit loop (in code, no
model call): compile, measure, then drop or add bullets until the CV fits one page.

Every entry gets a bullet allowance by role type (services/cv_rules.py: the current role 3-4,
roles over a year 2-3, graduation/short roles 1-3 by relevance, internships at most 2, at most 2
projects with 2-3 bullets each). Each entry starts at its minimum; inside an entry the job's most
relevant bullets come first and generic ones last.
Underfill (below the fill target, 88%): add the next strongest bullet within the allowances, never
beyond them; a CV that can't reach the target stays shorter rather than padded.
Overflow, in order: trim entries back to their minimum → drop the weaker project → the short
summary → drop volunteering → below the minimums (roles keep one bullet, projects never one).
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.providers.base import CVPlan, PlanBullet, PlanEntry
from app.services import cv_rules
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


@dataclass
class Layout:
    """Bullet allowances per entry key ("role:12" → (min, max)) and the rules they came from."""

    bounds: dict[str, tuple[int, int]]
    rules: dict[str, Any]
    merges: list[str]


def layout(plan: CVPlan, pool: Pool | None, rules: dict[str, Any] | None = None,
           merges: list[str] | None = None, today: Any = None) -> Layout:
    rules = rules or dict(cv_rules.DEFAULT_STRUCTURE)
    bounds: dict[str, tuple[int, int]] = {}
    for kind, entries in (("role", plan.roles), ("project", plan.projects),
                          ("volunteering", plan.volunteering)):
        for e in entries:
            item = pool.get(e.item_id) if pool else None
            bounds[_key(kind, e)] = cv_rules.allowance(
                "job" if kind == "role" else kind, item, e.relevance, rules, len(e.bullets), today)
    return Layout(bounds, rules, cv_rules.DEFAULT_SKILL_MERGES if merges is None else merges)


def _project_ok(p: PlanEntry, lay: Layout) -> bool:
    lo, _hi = lay.bounds.get(_key("project", p), (0, 0))
    return p.relevance >= 5 and len(p.bullets) >= max(2, lo)


def initial_state(plan: CVPlan, lay: Layout | None = None) -> FitState:
    """Every role at its minimum; the strongest projects (at most projects_max, each with at
    least 2 bullets) at their minimum; volunteering only when clearly relevant."""
    lay = lay or layout(plan, None)
    state = FitState()
    for e in plan.roles:
        state.counts[_key("role", e)] = max(1, lay.bounds[_key("role", e)][0])
    shown = 0
    for p in sorted(plan.projects, key=lambda x: -x.relevance):
        key = _key("project", p)
        if shown < int(lay.rules["projects_max"]) and _project_ok(p, lay):
            state.counts[key] = max(2, lay.bounds[key][0])
            shown += 1
        else:
            state.counts[key] = 0
    vol = 0
    for v in sorted(plan.volunteering, key=lambda x: -x.relevance):
        ok = v.relevance >= 7 and v.bullets and vol < int(lay.rules["volunteering_max"])
        state.counts[_key("volunteering", v)] = 1 if ok else 0
        vol += bool(ok)
    return state


def clamp(plan: CVPlan, state: FitState, lay: Layout) -> FitState:
    """A layout carried over from an older version (or older rules) is brought back inside the
    allowances: at most each entry's max, roles keep one bullet, no 1-bullet project, at most
    projects_max projects (the most relevant kept) and volunteering_max volunteering entries."""
    out = FitState.from_dict(state.to_dict())
    for kind, entries in (("role", plan.roles), ("project", plan.projects),
                          ("volunteering", plan.volunteering)):
        for e in entries:
            key = _key(kind, e)
            _lo, hi = lay.bounds.get(key, (0, 0))
            count = min(out.counts.get(key, 0), hi)
            if kind == "role":
                count = max(count, 1)
            elif kind == "project" and count == 1:
                count = 0
            out.counts[key] = count
    for kind, cap, entries in (("project", int(lay.rules["projects_max"]), plan.projects),
                               ("volunteering", int(lay.rules["volunteering_max"]),
                                plan.volunteering)):
        shown = sorted((e for e in entries if out.counts.get(_key(kind, e), 0)),
                       key=lambda e: -e.relevance)
        for e in shown[cap:]:
            out.counts[_key(kind, e)] = 0
    return out


def ordered(entry: PlanEntry) -> list[PlanBullet]:
    """Most relevant to the job first; generic process bullets last (used only if needed)."""
    return sorted(entry.bullets, key=lambda b: (b.strength <= 1 or cv_rules.is_generic(b.text),
                                                b.priority))


def _visible(entry: PlanEntry, key: str, count: int, overrides: dict[str, Any],
             keep_one: bool) -> list[tuple[str, str]]:
    """(override key, text) of the bullets shown for an entry, most relevant first: bullets the
    user forced in, then the best-ranked others up to `count`; never a forced-out one."""
    forced_in = set(overrides.get("force_in") or [])
    forced_out = set(overrides.get("force_out") or [])
    texts = overrides.get("text") or {}
    ranked = [(f"{key}:{b.source_index}", b.text) for b in ordered(entry)]
    forced = [b for b in ranked if b[0] in forced_in]
    rest = [b for b in ranked if b[0] not in forced_in and b[0] not in forced_out]
    shown = forced + rest[: max(0, count - len(forced))]
    if keep_one and not shown and ranked:
        shown = [ranked[0]]
    return [(k, texts.get(k, t)) for k, t in shown]


def _spell(term: str, pool: Pool) -> str:
    from app.services.cv_claims import Canon

    canon = getattr(pool, "_canon", None)
    if canon is None:
        canon = Canon(pool)
        pool._canon = canon  # type: ignore[attr-defined]
    return cv_rules.display(term, canon.word(term))


def build_document(plan: CVPlan, pool: Pool, state: FitState,
                   overrides: dict[str, Any] | None = None, max_stack: int = 6,
                   lay: Layout | None = None) -> CVDocument:
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
        bullets = _visible(p, key, max(count, 2), overrides, keep_one=False)
        if len(bullets) < 2 and key not in forced_in:
            continue  # never a 1-bullet project
        stack = [_spell(x, pool) for x in (list(p.stack) or item.tags)[:max_stack]]
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
    groups = []
    for g in plan.skills:
        item = pool.get(g.item_id, "skill")
        if item and g.items:
            groups.append((item.title, [_spell(x, pool) for x in g.items]))
    lay = lay or layout(plan, pool)
    skills = [CVSkillGroup(category=c, items=items)
              for c, items in cv_rules.shape_skills(groups, lay.rules, lay.merges)]
    return CVDocument(summary=summary, skills=skills, roles=roles, projects=projects,
                      certifications=certifications, education=education,
                      volunteering=volunteering)


# ------------------------------------------------------------------------------------ fitting


def _entries(plan: CVPlan) -> list[tuple[str, PlanEntry, bool]]:
    """(key, entry, must_keep_one) for every entry the loop may grow or shrink."""
    return ([(_key("role", e), e, True) for e in plan.roles]
            + [(_key("project", p), p, False) for p in plan.projects]
            + [(_key("volunteering", v), v, False) for v in plan.volunteering])


def _next_generic(entry: PlanEntry, count: int) -> bool:
    ranked = ordered(entry)
    return count < len(ranked) and (ranked[count].strength <= 1
                                    or cv_rules.is_generic(ranked[count].text))


def shrink(plan: CVPlan, state: FitState, n: int, lay: Layout, floor: bool = True) -> int:
    """Remove up to n of the least valuable bullets. With `floor`, entries stay at their
    minimum; without, roles keep one bullet and a project at 2 is dropped entirely."""
    removed = 0
    for _ in range(n):
        candidates = []
        for k, e, keep in _entries(plan):
            count = state.counts.get(k, 0)
            lo = lay.bounds.get(k, (1, 1))[0] if floor else (1 if keep else 2)
            if count > max(lo, 1 if keep else 0) and count > 0:
                candidates.append((e.relevance * 10 - count, k))
        if not candidates:
            break
        _, key = min(candidates)
        state.counts[key] -= 1
        if key.startswith("project:") and state.counts[key] < 2:
            state.counts[key] = 0
        removed += 1
    return removed


def drop_entry(plan: CVPlan, state: FitState, kind: str) -> bool:
    """Remove the least relevant visible project (or volunteering entry)."""
    candidates = [(e.relevance, k) for k, e, keep in _entries(plan)
                  if k.startswith(kind + ":") and state.counts.get(k, 0) > 0]
    if not candidates:
        return False
    state.counts[min(candidates)[1]] = 0
    return True


def grow(plan: CVPlan, state: FitState, n: int, lay: Layout) -> int:
    """Add up to n of the strongest hidden bullets, only within each entry's allowance. A new
    project (if under projects_max) comes in with 2 bullets."""
    added = 0
    for _ in range(n):
        candidates = []
        shown_projects = sum(1 for p in plan.projects if state.counts.get(_key("project", p), 0))
        for k, e, _keep in _entries(plan):
            count = state.counts.get(k, 0)
            lo, hi = lay.bounds.get(k, (0, 0))
            if k.startswith("project:") and count == 0:
                if shown_projects < int(lay.rules["projects_max"]) and _project_ok(e, lay):
                    candidates.append((e.relevance * 10 - 6, k))
            elif 0 < count < hi:
                penalty = 15 if _next_generic(e, count) else 0
                candidates.append((e.relevance * 10 - count - 1 - penalty, k))
        if not candidates:
            break
        _, key = max(candidates)
        state.counts[key] = 2 if key.startswith("project:") and not state.counts.get(key) else \
            state.counts.get(key, 0) + 1
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
                overrides: dict[str, Any] | None = None, lay: Layout | None = None) -> FitResult:
    """Compile, measure, adjust, up to MAX_PASSES adjustments. Grows only while under the fill
    target and within the allowances; keeps the best one-page result seen; if none fit, returns
    the last (with its page count, flagged by the caller)."""
    lay = lay or layout(plan, pool)
    state = clamp(plan, state, lay) if state is not None else initial_state(plan, lay)
    target = float(lay.rules.get("fill_min") or template.min_fill)
    max_stack = int(template.config.get("max_stack_items") or 6)
    best: FitResult | None = None
    history: list[dict[str, Any]] = []
    last: FitResult | None = None
    stage = 0  # overflow escalation: 0 trim to minimums, 1 drop a project, 2 short summary,
    # 3 drop volunteering, 4 below minimums
    for attempt in range(MAX_PASSES + 3):
        doc = build_document(plan, pool, state, overrides, max_stack, lay)
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
        if attempt == MAX_PASSES + 2:
            break
        if result.pages > 1:
            overflow_lines = ((result.pages - 2) + result.fill) * LINES_PER_PAGE
            need = max(1, math.ceil(overflow_lines / LINES_PER_BULLET))
            removed = shrink(plan, state, need, lay)
            while removed < need and stage < 5:
                if stage == 0:
                    stage = 1
                elif stage == 1:
                    removed += 3 * drop_entry(plan, state, "project")
                    stage = 2
                elif stage == 2:
                    if not state.short_summary:
                        state.short_summary, removed = True, removed + 2
                    stage = 3
                elif stage == 3:
                    removed += 2 * drop_entry(plan, state, "volunteering")
                    stage = 4
                else:
                    removed += shrink(plan, state, need - removed, lay, floor=False)
                    stage = 5
            if removed == 0:
                break  # nothing left to trim
        else:
            gap_lines = (target + 0.02 - result.fill) * LINES_PER_PAGE
            if not grow(plan, state, max(1, math.floor(gap_lines / LINES_PER_BULLET)), lay):
                break  # the allowances are used up: shorter beats padded
    chosen = best or last
    assert chosen is not None
    if chosen is not last:  # re-render the best one-page state so files on disk match it
        tex = render_tex(chosen.document, profile, template)
        chosen.compiled = compile_tex(tex, out_dir, "cv")
        chosen.tex = tex
    chosen.passes = len(history) - 1
    chosen.history = history
    return chosen
