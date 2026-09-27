from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.api.deps import EngineDep, SessionDep, WorkspaceDep, get_or_404
from app.models import Application, AppSetting, Company, CVVersion, Job
from app.models.enums import CVStatus, EventKind, Route, Stage
from app.providers.registry import cv_generator
from app.schemas.cv import (
    CVApproveResult,
    CVGenerateIn,
    CVPatch,
    CVStudio,
    CVVersionOut,
    ReadinessItem,
    TemplateIn,
    TemplateOut,
)
from app.services import cv_service, cv_templates, pipeline
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
        created_at=v.created_at, updated_at=v.updated_at,
    )


def _templates(session: Session) -> list[TemplateOut]:
    default = cv_service.cv_settings(session)["default_template"]
    return [TemplateOut(name=t.name, description=t.description, paper=t.paper,
                        builtin=t.builtin, valid=t.valid, pages=t.pages, error=t.error,
                        is_default=t.name == default)
            for t in cv_templates.list_templates()]


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
    generator = cv_generator(mock=True if workspace == "demo" else None, model=_cv_model(session))
    try:
        version = cv_service.generate(engine, app_id, generator, body.template)
    except cv_service.CVError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(version)


def _cv_model(session: Session) -> str:
    row = session.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    return ((row.value if row else {}).get("cv") or {}).get("model") or "claude-sonnet-5"


@router.patch("/cv/{cv_id}", response_model=CVVersionOut)
def patch_cv(cv_id: int, body: CVPatch, session: SessionDep, engine: EngineDep) -> CVVersionOut:
    """Force items in/out, edit text or switch template, then re-fit (no generator call)."""
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    overrides = dict(v.overrides or {})
    for key in ("force_in", "force_out", "text"):
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
    return FileResponse(path, media_type="application/pdf", filename=name,
                        content_disposition_type="attachment" if download else "inline")


@router.post("/cv/{cv_id}/approve", response_model=CVApproveResult)
def approve_cv(cv_id: int, session: SessionDep) -> CVApproveResult:
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    app = get_or_404(session, Application, v.application_id)
    if v.page_count is not None and v.page_count != 1:
        raise HTTPException(409, "The CV must fit on exactly one page before approval")
    for other in cv_service.versions(session, app.id):
        if other.locked_at is not None:
            continue  # the CV that was sent with the application never changes
        if other.id != v.id and other.status in (CVStatus.approved, CVStatus.draft):
            other.status = CVStatus.superseded
            session.add(other)
    v.status = CVStatus.approved
    session.add(v)
    pipeline.log_event(session, app, EventKind.cv_approved, f"CV v{v.version} approved")
    if app.route == Route.undecided:
        app.route = Route.cold_email if app.contact_id else Route.web_apply
    if app.stage in (Stage.new, Stage.shortlisted):
        if app.stage == Stage.new:
            pipeline.transition(session, app, Stage.shortlisted)
        pipeline.transition(session, app, Stage.cv_ready)
    if app.route == Route.web_apply and app.stage == Stage.cv_ready:
        pipeline.transition(session, app, Stage.ready)  # approved CV, no contact: ready to apply
    session.add(app)
    session.commit()
    session.refresh(v)
    return CVApproveResult(
        version=_out(v), stage=app.stage, route=app.route,
        next_step="draft_email" if app.route == Route.cold_email else "apply",
    )


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
