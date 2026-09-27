from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from app.api.deps import SessionDep, get_or_404
from app.models import Application, Contact, Job
from app.models.enums import CloseReason, ContactTier, EventKind, Route, Stage
from app.schemas.jobs import ApplicationPatch, JobDetail, PipelineCard
from app.services import pipeline, tracking
from app.services.views import job_detail, pipeline_cards

router = APIRouter(prefix="/applications", tags=["pipeline"])


@router.get("", response_model=list[PipelineCard])
def list_applications(session: SessionDep) -> list[PipelineCard]:
    apps = session.exec(select(Application).order_by(col(Application.stage_changed_at).desc()))
    return pipeline_cards(session, apps.all())


@router.patch("/{app_id}", response_model=PipelineCard)
def patch_application(app_id: int, body: ApplicationPatch, session: SessionDep) -> PipelineCard:
    app = get_or_404(session, Application, app_id, "Application")
    if body.route is not None:
        try:
            app.route = Route(body.route)
        except ValueError as exc:
            raise HTTPException(422, f"Unknown route {body.route}") from exc
        pipeline.log_event(
            session, app, EventKind.note,
            "Route set to " + ("web apply" if app.route == Route.web_apply else "cold email"),
        )
    if body.notes is not None and body.notes != app.notes:
        app.notes = body.notes
    if body.stage is not None:
        try:
            stage = Stage(body.stage)
            reason = CloseReason(body.close_reason) if body.close_reason else None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if stage == Stage.done and app.route == Route.web_apply:
            raise HTTPException(409, "Use “Mark applied” (records the date, method and CV sent)")
        if stage == Stage.interview:
            raise HTTPException(409, "Use “Log interview” (records the round)")
        try:
            if stage == Stage.closed:
                tracking.close(session, app, reason or CloseReason.dismissed)
            else:
                pipeline.transition(session, app, stage, close_reason=reason)
        except tracking.TrackingError as exc:
            raise HTTPException(422, str(exc)) from exc
    session.add(app)
    session.commit()
    session.refresh(app)
    return pipeline_cards(session, [app])[0]


@router.post("/{app_id}/lookup", response_model=JobDetail)
def queue_lookup(app_id: int, session: SessionDep) -> JobDetail:
    """Queue a manual Apollo extension lookup (tier b)."""
    app = get_or_404(session, Application, app_id, "Application")
    if app.contact_id is not None:
        raise HTTPException(409, "This job already has a contact")
    app.contact_tier = ContactTier.lookup_queued
    pipeline.log_event(session, app, EventKind.contact_resolved, "Queued for Apollo lookup")
    session.add(app)
    session.commit()
    return job_detail(session, get_or_404(session, Job, app.job_id))


@router.post("/{app_id}/contact/{contact_id}", response_model=JobDetail)
def set_contact(app_id: int, contact_id: int, session: SessionDep) -> JobDetail:
    app = get_or_404(session, Application, app_id, "Application")
    contact = get_or_404(session, Contact, contact_id, "Contact")
    app.contact_id = contact.id
    if app.contact_tier in (ContactTier.none, ContactTier.lookup_queued):
        app.contact_tier = (
            ContactTier.lookup_found
            if app.contact_tier == ContactTier.lookup_queued
            else ContactTier.apollo_dump
        )
    if app.route == Route.undecided:
        app.route = Route.cold_email
    pipeline.log_event(
        session, app, EventKind.contact_resolved, f"Contact set: {contact.full_name}"
    )
    session.add(app)
    session.commit()
    return job_detail(session, get_or_404(session, Job, app.job_id))
