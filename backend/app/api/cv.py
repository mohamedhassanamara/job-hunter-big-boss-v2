import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import EngineDep, SessionDep, WorkspaceDep, get_or_404
from app.models import Application, Company, CVVersion, Job
from app.models.enums import CVStatus, EventKind, Route, Stage
from app.providers.base import CVPlan
from app.providers.gemini_generate import generation_failure
from app.providers.registry import cv_generator
from app.schemas.cv import (
    CVApproveResult,
    CVGenerateIn,
    CVLeftOut,
    CVPatch,
    CVRegenEstimate,
    CVRegenIn,
    CVRegenOut,
    CVRegenRetryIn,
    CVReviewRow,
    CVStudio,
    CVVersionOut,
    ReadinessItem,
    SummaryCheckIn,
    SummaryIn,
    SummaryRestoreIn,
    TemplateIn,
    TemplateOut,
)
from app.services import (
    cv_fit,
    cv_regen,
    cv_review,
    cv_service,
    cv_templates,
    generation,
    model_choice,
    pipeline,
    verifier,
)
from app.services.cv_pool import load_pool, readiness

router = APIRouter(tags=["cv"])


def _out(v: CVVersion) -> CVVersionOut:
    return CVVersionOut(
        id=v.id, application_id=v.application_id, version=v.version, status=v.status,
        content=v.content or {}, page_count=v.page_count, fill=v.fill,
        fit_passes=v.fit_passes or 0, template=v.template or "default",
        generator_model=v.generator_model, violations=v.violations or [],
        duration_ms=v.duration_ms, error=v.error,
        has_pdf=bool(v.pdf_path and Path(v.pdf_path).exists()),
        approved_summary_warnings=((v.plan or {}).get("approved_summary_warnings") or []
                                   if v.status == CVStatus.approved else []),
        created_at=v.created_at, updated_at=v.updated_at,
    )


def _templates(session: Session) -> list[TemplateOut]:
    default = cv_service.cv_settings(session)["default_template"]
    return [TemplateOut(name=t.name, description=t.description, paper=t.paper,
                        builtin=t.builtin, valid=t.valid, pages=t.pages, error=t.error,
                        is_default=t.name == default)
            for t in cv_templates.list_templates()]


@router.get("/cv/review", response_model=list[CVReviewRow])
def cv_review_list(session: SessionDep) -> list[CVReviewRow]:
    """The CV drafts of shortlisted jobs, with the Approve gate evaluated (Review CVs page)."""
    return cv_review.rows(session)


@router.get("/cv/regenerate-batch/estimate", response_model=CVRegenEstimate)
def regenerate_estimate(session: SessionDep, engine: EngineDep, count: int = 1,
                        mode: str = "whole", feedback: str | None = None,
                        use: str | None = None) -> CVRegenEstimate:
    """About how many model requests a batch takes, against the Gemini daily cap left."""
    if mode not in cv_regen.MODES or use not in model_choice.USES or count < 0:
        raise HTTPException(422, "Unknown mode or model")
    return CVRegenEstimate(**cv_regen.estimate(session, engine, count, mode, feedback, use))


@router.post("/cv/regenerate-batch", response_model=CVRegenOut)
def regenerate_batch(body: CVRegenIn, session: SessionDep, engine: EngineDep) -> CVRegenOut:
    """Queue a regeneration for each selected CV (background, existing CV model and retry rules).
    Every result is a new draft: approved CVs stay approved. Above 20 CVs `confirm` is required."""
    if body.use not in model_choice.USES:
        raise HTTPException(422, "use must be gemini or claude")
    if not body.application_ids:
        raise HTTPException(422, "Select at least one CV")
    if len(set(body.application_ids)) > cv_regen.CONFIRM_ABOVE and not body.confirm:
        raise HTTPException(409, f"More than {cv_regen.CONFIRM_ABOVE} CVs: confirm first")
    if body.use == "gemini":
        try:
            model_choice.choice(session, "cv", "gemini")
        except ValueError as exc:  # Gemini paused
            raise HTTPException(409, str(exc)) from exc
    try:
        out = cv_regen.enqueue_batch(session, body.application_ids, body.mode, body.feedback,
                                     body.use, uuid.uuid4().hex[:8])
    except cv_regen.RegenError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    return CVRegenOut(**out)


@router.post("/cv/regenerate-batch/retry", response_model=CVRegenOut)
def regenerate_retry(body: CVRegenRetryIn, session: SessionDep) -> CVRegenOut:
    """Retry one failed row (same request), optionally with Gemini for this one call."""
    if body.use not in model_choice.USES:
        raise HTTPException(422, "use must be gemini or claude")
    try:
        if body.use == "gemini":
            model_choice.choice(session, "cv", "gemini")
        task = cv_regen.retry(session, body.application_id, body.use)
    except (cv_regen.RegenError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    session.commit()
    batch = (task.details.get("request") or {}).get("batch_id", "")
    return CVRegenOut(queued=1, already_queued=0, skipped=[], batch_id=batch)


@router.get("/cv/{cv_id}/left-out", response_model=CVLeftOut)
def cv_left_out(cv_id: int, session: SessionDep) -> CVLeftOut:
    """Pool bullets and projects this CV leaves out, with the model's relevance for this job."""
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    return CVLeftOut(items=cv_service.left_out(v, load_pool(session)),
                     force_in=list((v.overrides or {}).get("force_in") or []), fill=v.fill,
                     page_count=v.page_count)


@router.get("/applications/{app_id}/cv", response_model=CVStudio)
def get_cv_studio(app_id: int, session: SessionDep) -> CVStudio:
    app = get_or_404(session, Application, app_id, "Application")
    job = get_or_404(session, Job, app.job_id)
    company = get_or_404(session, Company, job.company_id)
    versions = cv_service.versions(session, app.id)
    pool = load_pool(session)
    current = next((v for v in versions if v.status != CVStatus.superseded), None)
    return CVStudio(
        application_id=app.id, job_id=job.id, job_title=job.title, company_name=company.name,
        matched_track=job.matched_track, stage=app.stage, route=app.route,
        has_contact=app.contact_id is not None,
        versions=[_out(v) for v in versions],
        readiness=[ReadinessItem(**r) for r in readiness(pool)],
        templates=_templates(session),
        usage=cv_service.pool_usage(current, pool) if current else None,
        download_name=cv_service.download_name(session, current) if current else None,
    )


@router.get("/cv/readiness", response_model=list[ReadinessItem])
def cv_readiness(session: SessionDep) -> list[ReadinessItem]:
    return [ReadinessItem(**r) for r in readiness(load_pool(session))]


@router.post("/applications/{app_id}/cv/generate", response_model=CVVersionOut)
def generate_cv(
    app_id: int, body: CVGenerateIn, session: SessionDep, engine: EngineDep,
    workspace: WorkspaceDep,
) -> CVVersionOut:
    """One job at a time: one generator call (Claude; mock in the sandbox/tests), then checks and
    the one-page fit loop in code."""
    get_or_404(session, Application, app_id, "Application")
    if body.use not in model_choice.USES:
        raise HTTPException(422, "use must be empty, 'claude' or 'gemini'")
    generator = _generator(session, engine, workspace, body.use)
    try:
        version = cv_service.generate(engine, app_id, generator, body.template,
                                      verifier=verifier.for_workspace(session, workspace))
    except cv_service.CVError as exc:
        # 503: the model didn't answer (after the retries): the page offers Retry and
        # "Generate with Claude"; it never switches model by itself.
        raise HTTPException(503 if generation_failure(exc) else 422, str(exc)) from exc
    return _out(version)


def _generator(session: Session, engine, workspace: str, use: str | None = None):  # noqa: ANN001, ANN202
    """The CV generator from Settings → Models (`use="claude"`: this call only)."""
    try:
        pick = model_choice.choice(session, "cv", use)
    except ValueError as exc:  # "gemini" while Gemini is paused
        raise HTTPException(409, str(exc)) from exc
    return cv_generator(mock=True if workspace == "demo" else None, model=pick["model"],
                        thinking_level=pick["thinking_level"], engine=engine)


@router.patch("/cv/{cv_id}", response_model=CVVersionOut)
def patch_cv(cv_id: int, body: CVPatch, session: SessionDep, engine: EngineDep) -> CVVersionOut:
    """Force items in/out, edit text or switch template, then re-fit (no generator call)."""
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    overrides = dict(v.overrides or {})
    for key in ("force_in", "force_out", "text", "revert", "original_only"):
        value = getattr(body, key)
        if value is not None:
            overrides[key] = value
    try:
        version = cv_service.rerender(engine, cv_id, overrides=overrides, template=body.template)
    except cv_service.CVError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(version)


@router.get("/cv/{cv_id}/pdf")
def cv_pdf(cv_id: int, session: SessionDep, engine: EngineDep, download: bool = False):  # noqa: ANN201
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    path = cv_service.ensure_pdf(engine, v)
    if path is None:
        raise HTTPException(404, "No PDF for this version (LaTeX failed; see the error)")
    name = cv_service.download_name(session, v)
    # Drafts are re-rendered in place (same URL): never let the browser keep an older copy.
    return FileResponse(path, media_type="application/pdf", filename=name,
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "no-store, max-age=0"})


def _use(body: "SummaryIn | None") -> str | None:
    use = body.use if body else None
    if use not in model_choice.USES:
        raise HTTPException(422, "use must be empty, 'claude' or 'gemini'")
    return use


@router.post("/cv/{cv_id}/summary", response_model=CVVersionOut)
def regenerate_summary(cv_id: int, session: SessionDep, engine: EngineDep,
                       workspace: WorkspaceDep, body: SummaryIn | None = None) -> CVVersionOut:
    """New summary for a draft, written by the CV model from Settings → Models; bullets and layout
    stay as they are. With `feedback` the model edits the current summary toward it."""
    get_or_404(session, CVVersion, cv_id, "CV version")
    generator = _generator(session, engine, workspace, _use(body))
    try:
        v = cv_service.regenerate_summary(engine, cv_id, generator, body.feedback if body else None)
    except cv_service.CVError as exc:
        raise HTTPException(503 if generation_failure(exc) else 422, str(exc)) from exc
    return _out(v)


@router.post("/cv/{cv_id}/revise-summary", response_model=CVVersionOut)
def revise_summary(cv_id: int, session: SessionDep, engine: EngineDep,
                   workspace: WorkspaceDep, body: SummaryIn | None = None) -> CVVersionOut:
    """A corrected draft of an approved CV: same bullets and layout, a new summary."""
    get_or_404(session, CVVersion, cv_id, "CV version")
    generator = _generator(session, engine, workspace, _use(body))
    try:
        v = cv_service.revise_summary(engine, cv_id, generator, body.feedback if body else None)
    except cv_service.CVError as exc:
        raise HTTPException(503 if generation_failure(exc) else 422, str(exc)) from exc
    return _out(v)


@router.post("/cv/{cv_id}/summary/check")
def check_summary(cv_id: int, body: SummaryCheckIn, session: SessionDep,
                  engine: EngineDep) -> dict[str, list[dict[str, Any]]]:
    """The checks on a summary text while it is typed: information only, no model call."""
    get_or_404(session, CVVersion, cv_id, "CV version")
    try:
        return {"warnings": cv_service.check_summary(engine, cv_id, body.text)}
    except cv_service.CVError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cv/{cv_id}/summary/restore", response_model=CVVersionOut)
def restore_summary(cv_id: int, body: SummaryRestoreIn, session: SessionDep,
                    engine: EngineDep) -> CVVersionOut:
    """Go back to an earlier summary of this draft."""
    get_or_404(session, CVVersion, cv_id, "CV version")
    try:
        return _out(cv_service.restore_summary(engine, cv_id, body.index))
    except cv_service.CVError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/cv/{cv_id}/approve", response_model=CVApproveResult)
def approve_cv(cv_id: int, session: SessionDep, engine: EngineDep,
               workspace: WorkspaceDep) -> CVApproveResult:
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    app = get_or_404(session, Application, v.application_id)
    if v.page_count is not None and v.page_count != 1:
        raise HTTPException(409, "The CV must fit on exactly one page before approval")
    # Summary checks are information: only bullet, skill, number and tool errors block.
    found = cv_review.blocking_errors(v.violations)
    if found:  # the same rule as letters and emails
        raise HTTPException(409, f"Fix {len(found)} problem{'s' if len(found) > 1 else ''} first: "
                            + found[0]["message"])
    for other in cv_service.versions(session, app.id):
        if other.locked_at is not None:
            continue  # the CV that was sent with the application never changes
        if other.id != v.id and other.status in (CVStatus.approved, CVStatus.draft):
            other.status = CVStatus.superseded
            session.add(other)
    v.status = CVStatus.approved
    if (v.plan or {}).get("plan"):  # keep what the summary was warned about at approval
        warnings = cv_service.summary_warnings(
            session, app, load_pool(session), CVPlan.model_validate(v.plan["plan"]),
            (v.content or {}).get("summary") or "")
        v.plan = {**v.plan, "approved_summary_warnings": warnings}
    session.add(v)
    pipeline.log_event(session, app, EventKind.cv_approved,
                       f"CV v{v.version} approved" + (" with summary warnings"
                                                      if (v.plan or {}).get(
                                                          "approved_summary_warnings") else ""))
    if app.route == Route.undecided:
        app.route = Route.cold_email if app.contact_id else Route.web_apply
    if app.stage in (Stage.new, Stage.shortlisted):
        if app.stage == Stage.new:
            pipeline.transition(session, app, Stage.shortlisted)
        pipeline.transition(session, app, Stage.cv_ready)
    session.add(app)
    session.flush()
    generation.maybe_enqueue_email(session, app, "cv_approved")  # whichever comes last
    session.commit()
    session.refresh(v)
    # Fit before/after: the job scored against this CV, in the background (one model call).
    cv_fit.start(engine, v.id, mock=_mock_scoring(workspace))
    return CVApproveResult(
        version=_out(v), stage=app.stage, route=app.route,
        next_step="draft_email" if app.route == Route.cold_email else "apply",
    )


def _mock_scoring(workspace: str) -> bool:
    from app.config import get_settings

    return workspace == "demo" or get_settings().job_sources == "mock"


class CVFitOut(BaseModel):
    cv_version_id: int
    status: str  # pending | ok | failed
    base_score: int | None
    score: int | None
    sub_scores: dict[str, Any]
    base_sub_scores: dict[str, Any]
    model: str | None
    prompt_version: str | None
    error: str | None
    lexical: dict[str, Any]
    scored_at: Any = None


@router.get("/cv/{cv_id}/fit", response_model=CVFitOut | None)
def get_cv_fit(cv_id: int, session: SessionDep) -> CVFitOut | None:
    """Fit before (the job's own fit) and after (scored against this CV), with the evidence
    check. None until the CV is approved."""
    from app.models import CVFit, FitScore

    row = session.exec(select(CVFit).where(CVFit.cv_version_id == cv_id)).first()
    if row is None:
        return None
    base = session.get(FitScore, row.base_fit_id) if row.base_fit_id else None
    return CVFitOut(cv_version_id=cv_id, status=row.status, base_score=row.base_score,
                    score=row.score, sub_scores=row.sub_scores,
                    base_sub_scores=base.sub_scores if base else {}, model=row.model,
                    prompt_version=row.prompt_version, error=row.error, lexical=row.lexical,
                    scored_at=row.scored_at)


@router.post("/cv/{cv_id}/fit", status_code=202)
def rerun_cv_fit(cv_id: int, session: SessionDep, engine: EngineDep,
                 workspace: WorkspaceDep) -> dict[str, bool]:
    """Score again (e.g. after a model problem)."""
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    if v.status != CVStatus.approved:
        raise HTTPException(409, "Fit before/after is for an approved CV")
    return {"started": cv_fit.start(engine, cv_id, mock=_mock_scoring(workspace))}


# ----------------------------------------------------------------------------------- templates


@router.get("/cv/templates", response_model=list[TemplateOut])
def list_cv_templates(session: SessionDep) -> list[TemplateOut]:
    return _templates(session)


@router.post("/cv/templates", response_model=TemplateOut, status_code=201)
def add_cv_template(body: TemplateIn, session: SessionDep) -> TemplateOut:
    """Upload a template (.tex.j2 + config). It's compiled with fictional sample data and can
    only be selected once that works on one page."""
    try:
        status = cv_templates.add_template(body.name, body.tex, body.config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return next(t for t in _templates(session) if t.name == status.name)


@router.post("/cv/templates/{name}/validate", response_model=TemplateOut)
def validate_cv_template(name: str, session: SessionDep) -> TemplateOut:
    try:
        cv_templates.validate(name, force=True)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return next(t for t in _templates(session) if t.name == name)


@router.delete("/cv/templates/{name}", status_code=204)
def delete_cv_template(name: str, session: SessionDep) -> None:
    if cv_service.cv_settings(session)["default_template"] == name:
        raise HTTPException(409, "Choose another default template first")
    try:
        cv_templates.delete_template(name)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/cv/templates/{name}/preview")
def template_preview(name: str):  # noqa: ANN201
    try:
        path = cv_templates.preview_pdf(name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if path is None:
        raise HTTPException(404, "The sample didn't compile; see the template error")
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline",
                        filename=f"{name}-sample.pdf")
