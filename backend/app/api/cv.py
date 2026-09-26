from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from app.api.deps import SessionDep, get_or_404
from app.models import Application, Company, CVVersion, Job
from app.models.enums import CVStatus, EventKind, Route, Stage
from app.providers.base import CVContent, JobSnapshot
from app.providers.registry import cv_generator, cv_renderer
from app.schemas.cv import CVApproveResult, CVPatch, CVStudio, CVVersionOut
from app.services import pipeline
from app.services.experience import experience_snapshots

router = APIRouter(tags=["cv"])


def _out(v: CVVersion) -> CVVersionOut:
    return CVVersionOut(
        id=v.id,
        application_id=v.application_id,
        version=v.version,
        status=v.status,
        content=v.content,
        page_count=v.page_count,
        generator_model=v.generator_model,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _versions(session: SessionDep, app_id: int) -> list[CVVersion]:
    return list(
        session.exec(
            select(CVVersion)
            .where(CVVersion.application_id == app_id)
            .order_by(col(CVVersion.version).desc())
        ).all()
    )


@router.get("/applications/{app_id}/cv", response_model=CVStudio)
def get_cv_studio(app_id: int, session: SessionDep) -> CVStudio:
    app = get_or_404(session, Application, app_id, "Application")
    job = get_or_404(session, Job, app.job_id)
    company = get_or_404(session, Company, job.company_id)
    return CVStudio(
        application_id=app.id,
        job_id=job.id,
        job_title=job.title,
        company_name=company.name,
        stage=app.stage,
        route=app.route,
        has_contact=app.contact_id is not None,
        versions=[_out(v) for v in _versions(session, app.id)],
    )


@router.post("/applications/{app_id}/cv/generate", response_model=CVVersionOut)
def generate_cv(app_id: int, session: SessionDep) -> CVVersionOut:
    """Create a new draft version with the (mock) CV generator."""
    app = get_or_404(session, Application, app_id, "Application")
    job = get_or_404(session, Job, app.job_id)
    company = get_or_404(session, Company, job.company_id)
    existing = _versions(session, app.id)
    for v in existing:
        if v.status == CVStatus.draft:
            v.status = CVStatus.superseded
            session.add(v)
    gen = cv_generator()
    content = gen.generate(
        JobSnapshot(title=job.title, company=company.name, description=job.description),
        experience_snapshots(session),
    )
    rendered = cv_renderer().render(content, f"job-{job.id}")
    version = CVVersion(
        application_id=app.id,
        version=(existing[0].version + 1) if existing else 1,
        content=content.model_dump(),
        tex=rendered.tex,
        pdf_path=rendered.pdf_path,
        page_count=rendered.page_count,
        status=CVStatus.draft,
        generator_model=gen.model,
    )
    session.add(version)
    session.flush()
    pipeline.log_event(session, app, EventKind.cv_generated, f"CV v{version.version} generated")
    session.commit()
    session.refresh(version)
    return _out(version)


@router.patch("/cv/{cv_id}", response_model=CVVersionOut)
def patch_cv(cv_id: int, body: CVPatch, session: SessionDep) -> CVVersionOut:
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    if v.status != CVStatus.draft:
        raise HTTPException(
            409, "Only draft versions can be edited. Regenerate to start a new draft."
        )
    try:
        v.content = CVContent.model_validate(body.content).model_dump()
    except ValueError as exc:
        raise HTTPException(422, "Invalid CV content") from exc
    session.add(v)
    session.commit()
    session.refresh(v)
    return _out(v)


@router.post("/cv/{cv_id}/approve", response_model=CVApproveResult)
def approve_cv(cv_id: int, session: SessionDep) -> CVApproveResult:
    v = get_or_404(session, CVVersion, cv_id, "CV version")
    app = get_or_404(session, Application, v.application_id)
    if v.page_count is not None and v.page_count != 1:
        raise HTTPException(409, "The CV must fit on exactly one page before approval")
    for other in _versions(session, app.id):
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
    session.add(app)
    session.commit()
    session.refresh(v)
    return CVApproveResult(
        version=_out(v),
        stage=app.stage,
        route=app.route,
        next_step="draft_email" if app.route == Route.cold_email else "mark_ready_to_apply",
    )
