"""CV versions: generate (one Claude call), re-render after user changes (no Claude call),
lazy PDFs for sandbox versions, download names. Rendering and fitting: cv_build / cv_render."""

import re
import time
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.config import DATA_DIR
from app.models import Application, AppSetting, Company, CVVersion, FitScore, Job
from app.models.enums import CVStatus, EventKind
from app.providers.base import (
    CVGenerationFailed,
    CVGenerator,
    CVPlan,
    CVRequest,
    SummarySentence,
)
from app.services import cv_rules, pipeline
from app.services.cv_build import FitState, Layout, fit_to_page, layout
from app.services.cv_check import (
    canonicalize,
    check_plan,
    feedback,
    ground_sentences,
    violation,
)
from app.services.cv_pool import (
    Pool,
    cv_profile,
    load_pool,
    prompt_pool,
    readiness,
    years_facts,
)
from app.services.cv_render import CVDocument, compile_tex, load_template, render_tex
from app.services.cv_templates import validate

CV_DIR = DATA_DIR / "cv"
DEFAULT_SETTINGS = {
    "default_template": "default",
    "filename_pattern": "{full_name}_CV_{company}.pdf",
    "track_emphasis": {},  # track name → {"skill_groups": [...], "tags": [...]}
    # Writing guide (given to the model), structure rules and skill merges (applied in code).
    "writing_guide": cv_rules.DEFAULT_GUIDE,
    "structure": cv_rules.DEFAULT_STRUCTURE,
    "skill_merges": cv_rules.DEFAULT_SKILL_MERGES,
}


class CVError(RuntimeError):
    """Shown to the user (e.g. missing full name, template not valid, generator failed)."""


def cv_settings(s: Session) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == "cv")).first()
    return {**DEFAULT_SETTINGS, **(dict(row.value) if row else {})}


def versions(s: Session, app_id: int) -> list[CVVersion]:
    return list(s.exec(select(CVVersion).where(CVVersion.application_id == app_id)
                       .order_by(col(CVVersion.version).desc())).all())


def _template(name: str | None, s: Session) -> str:
    name = name or cv_settings(s)["default_template"]
    status = validate(name)
    if not status.valid:
        raise CVError(f"Template '{name}' can't be used yet: {status.error}")
    return name


def build_request(s: Session, app: Application, pool: Pool) -> CVRequest:
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id) if job else None
    fit = s.exec(select(FitScore).where(FitScore.job_id == app.job_id)
                 .order_by(col(FitScore.created_at).desc())).first()
    track = job.matched_track if job else None
    return CVRequest(
        job={
            "title": job.title if job else "", "company": company.name if company else "",
            "location": job.location if job else "",
            "description": (job.description or "")[:8000] if job else "",
            "matched_track": track or "(none)", "matched_role": job.matched_role if job else None,
            "strengths": fit.strengths if fit else [], "gaps": fit.gaps if fit else [],
        },
        pool=prompt_pool(pool),
        emphasis=(cv_settings(s).get("track_emphasis") or {}).get(track or "", {}),
        facts={"years": years_facts(pool, _tracks(s))},
        guide=cv_rules.guide(cv_settings(s)),
        style=cv_rules.style_exemplar(),
        layout=layout_hints(pool, cv_rules.structure(cv_settings(s))),
    )


def layout_hints(pool: Pool, rules: dict[str, Any]) -> dict[str, Any]:
    """What code will show, so the model ranks every entry's facts with that in mind."""
    roles = {}
    for item in pool.of("job"):
        kind = cv_rules.role_type(item, rules)
        lo, hi = rules[kind]
        roles[str(item.id)] = f"{kind.replace('_', ' ')}: {lo}-{hi} bullets"
    lo, hi = rules["project_bullets"]
    return {
        "roles": roles,
        "projects": f"at most {rules['projects_max']} projects, {lo}-{hi} bullets each",
        "skills": f"at most {rules['skill_groups_max']} groups, {rules['skill_items_max']} "
                  "skills each",
        "summary": f"at most {rules['summary_max_sentences']} sentences, about "
                   f"{rules['summary_max_words']} words",
    }


def fit_layout(s: Session, plan: CVPlan, pool: Pool) -> Layout:
    settings = cv_settings(s)
    return layout(plan, pool, cv_rules.structure(settings), cv_rules.merges(settings))


def summary_style(plan: CVPlan, pool: Pool, rules: dict[str, Any], text: str,
                  short: bool = False) -> list[str]:
    """The guide's summary rules, checked in code (see cv_rules.summary_problems)."""
    bullets = [b.text for e in [*plan.roles, *plan.projects] for b in e.bullets]
    internships = [i for i in pool.of("job") if cv_rules.role_type(i, rules) == "internship"]
    tools = {t for i in pool.items.values() for t in i.tags if len(t) > 2}
    tools |= {x for g in plan.skills for x in g.items if len(x) > 2}
    return cv_rules.summary_problems(
        text, rules=rules, bullet_texts=bullets, certifications=pool.of("certification"),
        internships=internships, tools=tools, max_sentences=1 if short else None,
        max_words=max(15, int(rules["summary_max_words"]) // 2) if short else None)


def _tracks(s: Session) -> list[dict[str, Any]]:
    from app.models import SearchProfile

    profile = s.exec(select(SearchProfile).where(SearchProfile.is_active)).first()
    return list(profile.tracks or []) if profile else []


def _save_render(s: Session, v: CVVersion, plan: CVPlan, pool: Pool, template_name: str,
                 overrides: dict[str, Any], state: FitState | None) -> None:
    template = load_template(template_name)
    out_dir = CV_DIR / str(v.application_id) / f"v{v.version}"
    result = fit_to_page(plan, pool, cv_profile(pool), template, out_dir, state=state,
                         overrides=overrides, lay=fit_layout(s, plan, pool))
    v.content = result.document.model_dump()
    v.tex = result.tex
    v.template = template_name
    v.overrides = overrides
    v.plan = {**(v.plan or {}), "plan": plan.model_dump(), "fit": result.state.to_dict(),
              "history": result.history}
    v.page_count = result.compiled.pages or None
    v.fill = round(result.compiled.fill, 3) if result.compiled.ok else None
    v.fit_passes = result.passes
    v.pdf_path = str(result.compiled.pdf_path) if result.compiled.pdf_path else None
    v.error = None if result.compiled.ok else f"{result.compiled.error}\n{result.compiled.log_tail}"


def generate(engine: Engine, app_id: int, generator: CVGenerator,
             template: str | None = None) -> CVVersion:
    """One Claude call → plan → checks → fit loop → a new draft version."""
    started = time.monotonic()
    with Session(engine) as s:
        app = s.get(Application, app_id)
        if app is None:
            raise CVError("Application not found")
        pool = load_pool(s)
        blockers = [r["message"] for r in readiness(pool) if r["severity"] == "blocker"]
        if blockers:
            raise CVError(" ".join(blockers))
        template_name = _template(template, s)
        request = build_request(s, app, pool)
        rules = cv_rules.structure(cv_settings(s))
    try:
        plan = generator.generate(request)
        plan, issues = check_plan(plan, pool)
        plan, summary_issues, grounding = ground_summary(plan, pool, request, generator, rules)
    except CVGenerationFailed as exc:
        raise CVError(str(exc)) from exc
    plan = canonicalize(plan, pool)
    issues += summary_issues
    with Session(engine) as s:
        app = s.get(Application, app_id)
        existing = versions(s, app_id)
        for old in existing:
            if old.status == CVStatus.draft:
                old.status = CVStatus.superseded
                s.add(old)
        v = CVVersion(application_id=app_id, version=(existing[0].version + 1) if existing else 1,
                      status=CVStatus.draft, generator_model=generator.model,
                      violations=issues)
        v.plan = {"prompt_version": getattr(generator, "prompt_version", None),
                  "summary_grounding": grounding,
                  "cost_usd": getattr(generator, "last_cost_usd", None),
                  "generation_ms": getattr(generator, "last_duration_ms", None)}
        s.add(v)
        s.flush()
        _save_render(s, v, plan, pool, template_name, {}, None)
        v.duration_ms = int((time.monotonic() - started) * 1000)
        if v.page_count and v.page_count > 1:
            v.violations = [*v.violations, {
                "type": "overflow", "severity": "error", "where": "page",
                "message": f"Still {v.page_count} pages after fitting"}]
        pipeline.log_event(s, app, EventKind.cv_generated,
                           f"CV v{v.version} generated ({generator.model})")
        s.add(v)
        s.commit()
        s.refresh(v)
        return v


def ground_summary(plan: CVPlan, pool: Pool, request: CVRequest, generator: CVGenerator,
                   rules: dict[str, Any] | None = None,
                   ) -> tuple[CVPlan, list[dict[str, Any]], dict[str, Any]]:
    """Every summary sentence must cite pool items and say only what they say, and the summary
    must follow the writing guide (length, no repeated numbers, certifications, internships or
    tool lists). Any problem → the summary is regenerated once (told why). Grounding still
    failing → the user's summary snippet verbatim (or only the grounded sentences); guide
    problems still there → kept, with a warning to review."""
    rules = rules or dict(cv_rules.DEFAULT_STRUCTURE)
    allowed = {int(f["years"]) for f in (request.facts or {}).get("years", [])}
    report: dict[str, Any] = {"attempts": 1, "rejected": [], "fallback": None, "style": []}

    def join(items: list[SummarySentence]) -> str:
        return " ".join(s.text.strip() for s in items)

    good, bad = ground_sentences(plan.summary_sentences, pool, allowed)
    short_good, short_bad = ground_sentences(plan.summary_short_sentences, pool, allowed)
    style = summary_style(plan, pool, rules, join(plan.summary_sentences))
    short_style = summary_style(plan, pool, rules, join(plan.summary_short_sentences), True)
    if bad or short_bad or style or short_style:
        report["rejected"].append([{"text": s.text, "citations": s.citations, "reasons": r}
                                   for s, r in bad + short_bad])
        report["style"].append({"summary": style, "short": short_style})
        notes = feedback(bad + short_bad)
        if style or short_style:
            notes += ("\n" if notes else "") + "\n".join(
                [f"- Summary: {p}" for p in style] + [f"- Short summary: {p}" for p in short_style])
        retry = generator.generate_summary(request, notes)
        report["attempts"] = 2
        good2, bad2 = ground_sentences(retry.summary_sentences, pool, allowed)
        short2, short_bad2 = ground_sentences(retry.summary_short_sentences, pool, allowed)
        style2 = summary_style(plan, pool, rules, join(retry.summary_sentences))
        short_style2 = summary_style(plan, pool, rules, join(retry.summary_short_sentences), True)
        report["style"].append({"summary": style2, "short": short_style2})
        if bad2:
            report["rejected"].append([{"text": s.text, "citations": s.citations, "reasons": r}
                                       for s, r in bad2])
        if not bad2 and good2 and (bad or len(style2) <= len(style)):
            good, bad, style = good2, [], style2
        elif bad:
            good = good2 if len(good2) >= len(good) else good
        if not short_bad2 and short2 and (short_bad or len(short_style2) <= len(short_style)):
            short_good, short_bad, short_style = short2, [], short_style2
    issues: list[dict[str, Any]] = []
    snippets = pool.of("summary")
    if bad:
        cited = [pool.get(i, "summary") for s in plan.summary_sentences for i in s.citations]
        snippet = next((i for i in cited if i), snippets[0] if snippets else None)
        if snippet is not None and (snippet.summary or "").strip():
            good = [SummarySentence(text=snippet.summary.strip(), citations=[snippet.id])]
            short_good = good
            report["fallback"] = f"snippet {snippet.id}"
            issues.append(violation("summary_fallback", "The generated summary failed the "
                                    "grounding check twice: using your summary snippet verbatim",
                                    "summary"))
        else:
            report["fallback"] = "grounded sentences only"
            issues.append(violation("summary_fallback", "Summary sentences failed the grounding "
                                    "check twice and you have no summary snippet: kept only the "
                                    f"{len(good)} grounded sentence(s)", "summary"))
    elif style:
        issues.append(violation("summary_style", "The summary still breaks the writing guide "
                                f"after one retry: {'; '.join(style)}", "summary"))
    if bad or short_bad:
        short_good = short_good if short_good and not short_bad else good[:1]
    return plan.model_copy(update={
        "summary_sentences": good, "summary_short_sentences": short_good,
        "summary": join(good), "summary_short": join(short_good),
        "summary_source_ids": sorted({c for s in good for c in s.citations}),
    }), issues, report


def rerender(engine: Engine, cv_id: int, *, overrides: dict[str, Any] | None = None,
             template: str | None = None) -> CVVersion:
    """User changes (force in/out, edited text, template): re-fit and re-render, no Claude call.
    Drafts change in place; an approved version gets a new draft copy."""
    with Session(engine) as s:
        v = s.get(CVVersion, cv_id)
        if v is None:
            raise CVError("CV version not found")
        if not (v.plan or {}).get("plan"):
            raise CVError("This version has no generator plan; regenerate it")
        plan = CVPlan.model_validate(v.plan["plan"])
        pool = load_pool(s)
        new_overrides = overrides if overrides is not None else dict(v.overrides or {})
        plan = with_forced_projects(plan, pool, new_overrides)
        template_name = _template(template or v.template, s)
        if v.status != CVStatus.draft:
            existing = versions(s, v.application_id)
            v = CVVersion(application_id=v.application_id, version=existing[0].version + 1,
                          status=CVStatus.draft, generator_model=v.generator_model,
                          plan=dict(v.plan), violations=list(v.violations or []))
            s.add(v)
            s.flush()
        issues = [i for i in (v.violations or []) if i.get("type") not in ("edit", "overflow")]
        allowed = {int(f["years"]) for f in years_facts(pool, _tracks(s))}
        issues += edit_violations(plan, pool, new_overrides, allowed)
        _save_render(s, v, plan, pool, template_name, new_overrides,
                     FitState.from_dict(v.plan.get("fit")))
        if v.page_count and v.page_count > 1:
            issues.append({"type": "overflow", "severity": "error",
                           "message": f"Still {v.page_count} pages after fitting", "where": "page"})
        v.violations = issues
        s.add(v)
        s.commit()
        s.refresh(v)
        return v


def with_forced_projects(plan: CVPlan, pool: Pool, overrides: dict[str, Any]) -> CVPlan:
    """A project the generator didn't pick but the user forced in joins the plan with its
    original facts (least relevant, so the fit loop trims it first)."""
    from app.providers.base import PlanBullet, PlanProject

    planned = {p.item_id for p in plan.projects}
    extra = []
    for key in overrides.get("force_in") or []:
        kind, _, rest = key.partition(":")
        if kind != "project" or ":" in rest or not rest.isdigit() or int(rest) in planned:
            continue
        item = pool.get(int(rest), "project")
        if item:
            extra.append(PlanProject(item_id=item.id, relevance=1, stack=item.tags[:6], bullets=[
                PlanBullet(source_index=n, text=f, priority=n + 1)
                for n, f in enumerate(pool.facts(item))]))
    return plan.model_copy(update={"projects": [*plan.projects, *extra]}) if extra else plan


def edit_violations(plan: CVPlan, pool: Pool, overrides: dict[str, Any],
                    allowed_years: set[int] | None = None) -> list[dict[str, Any]]:
    """User-edited text goes through the same number/tool/claim checks as generated text."""
    from app.services.cv_check import new_tools, numbers
    from app.services.cv_claims import bad_years, capability_gaps, pool_vocabulary, scope_inflation

    out = []
    vocab, text_all = pool_vocabulary(pool), pool.all_text()
    all_numbers = {n.lower() for n in numbers(text_all)}
    for key, text in (overrides.get("text") or {}).items():
        def add(message: str, severity: str = "error", key: str = key) -> None:
            out.append({"type": "edit", "severity": severity, "where": key,
                        "message": f"Edited text: {message}"})
        for n in numbers(text):
            if n.lower() not in all_numbers and not re.search(rf"{re.escape(n)}\s*\+?\s*years?",
                                                              text):
                add(f"“{n}” isn't anywhere in your experience")
        for claim in bad_years(text, allowed_years or set()):
            add(f"years claim “{claim}” isn't one of your allowed years facts")
        if tools := new_tools(text, vocab):
            add(f"not in your experience: {', '.join(tools)}", "warning")
        for phrase in capability_gaps(text, text_all):
            add(f"claims “{phrase}”, which your experience never mentions", "warning")
        for phrase in scope_inflation(text, text_all):
            add(f"“{phrase}” overstates your experience", "warning")
    return out


def ensure_pdf(engine: Engine, v: CVVersion) -> Path | None:
    """Versions created without a PDF (tour sandbox) are compiled on first view."""
    if v.pdf_path and Path(v.pdf_path).exists():
        return Path(v.pdf_path)
    with Session(engine) as s:
        row = s.get(CVVersion, v.id)
        pool = load_pool(s)
        profile = cv_profile(pool)
        if not profile.full_name:
            profile = profile.model_copy(update={"full_name": "Your Name"})
        doc = CVDocument.model_validate(row.content or {})
        template = load_template(row.template or "default")
        result = compile_tex(render_tex(doc, profile, template),
                             CV_DIR / f"{id(engine)}-{row.application_id}" / f"v{row.version}",
                             "cv")
        if not result.ok:
            return None
        row.pdf_path, row.page_count = str(result.pdf_path), result.pages
        row.fill = round(result.fill, 3)
        s.add(row)
        s.commit()
        return result.pdf_path


def download_name(s: Session, v: CVVersion) -> str:
    pattern = cv_settings(s).get("filename_pattern") or DEFAULT_SETTINGS["filename_pattern"]
    app = s.get(Application, v.application_id)
    job = s.get(Job, app.job_id) if app else None
    company = s.get(Company, job.company_id) if job else None
    profile = load_pool(s).profile
    values = {
        "full_name": (profile.get("full_name") or "CV").strip(),
        "company": company.name if company else "Company",
        "job_title": job.title if job else "Job",
        "version": str(v.version),
    }
    try:
        name = pattern.format(**values)
    except (KeyError, IndexError, ValueError):
        name = DEFAULT_SETTINGS["filename_pattern"].format(**values)
    name = re.sub(r"[^\w.\- ]+", "", name).strip().replace(" ", "_")
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def pool_usage(v: CVVersion, pool: Pool) -> dict[str, Any]:
    """For CV Studio: every pool item/bullet, and whether this version shows it."""
    plan = CVPlan.model_validate((v.plan or {}).get("plan") or {"summary": "", "summary_short": ""})
    doc = CVDocument.model_validate(v.content or {})
    overrides = v.overrides or {}
    shown_roles = {r.item_id: set(r.bullets) for r in doc.roles}
    shown_projects = {p.item_id: set(p.bullets) for p in doc.projects}
    texts = overrides.get("text") or {}

    def entries(kind: str, plan_entries: list, shown: dict[int, set[str]]) -> list[dict[str, Any]]:
        out = []
        for e in plan_entries:
            item = pool.get(e.item_id)
            if item is None:
                continue
            key = f"{kind}:{e.item_id}"
            out.append({
                "key": key, "item_id": e.item_id, "title": item.title, "org": item.org,
                "relevance": e.relevance, "shown": e.item_id in shown,
                "bullets": [{"key": f"{key}:{b.source_index}",
                             "text": texts.get(f"{key}:{b.source_index}", b.text),
                             "source": pool.facts(item)[b.source_index]
                             if b.source_index < len(pool.facts(item)) else "",
                             "priority": b.priority,
                             "shown": texts.get(f"{key}:{b.source_index}", b.text)
                             in shown.get(e.item_id, set())}
                            for b in sorted(e.bullets, key=lambda x: x.priority)],
            })
        return out

    planned_projects = {p.item_id for p in plan.projects}
    unused_projects = [{"key": f"project:{i.id}", "item_id": i.id, "title": i.title,
                        "org": i.org, "relevance": 0, "shown": False, "bullets": []}
                       for i in pool.of("project") if i.id not in planned_projects]
    shown_certs = {c.item_id for c in doc.certifications}
    return {
        "summary": {
            "text": doc.summary, "full": plan.summary, "short": plan.summary_short,
            "edited": bool((overrides.get("text") or {}).get("summary")),
            "sentences": [{"text": s.text, "citations": [
                {"id": c, "title": pool.get(c).title if pool.get(c) else f"#{c} (missing)",
                 "kind": pool.get(c).kind if pool.get(c) else "?"} for c in s.citations]}
                for s in plan.summary_sentences],
            "grounding": (v.plan or {}).get("summary_grounding"),
        },
        "roles": entries("role", plan.roles, shown_roles),
        "projects": entries("project", plan.projects, shown_projects) + unused_projects,
        "certifications": [{"key": f"cert:{i.id}", "item_id": i.id, "title": i.title,
                            "org": i.org, "shown": i.id in shown_certs}
                           for i in pool.of("certification")],
        "force_in": overrides.get("force_in") or [],
        "force_out": overrides.get("force_out") or [],
    }
