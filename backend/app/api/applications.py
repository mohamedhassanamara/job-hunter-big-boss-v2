from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from app.api.deps import SessionDep, get_or_404
from app.models import Application
from app.models.enums import CloseReason, EventKind, Route, Stage
from app.schemas.jobs import ApplicationPatch, PipelineCard
from app.services import pipeline, tracking
from app.services.views import pipeline_cards

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
    if body.company_reason is not None:
        reason = body.company_reason.strip()
        if len(reason) > 300:
            raise HTTPException(422, "Keep your reason to one line (at most 300 characters)")
        app.company_reason = reason
    if body.stage is not None:
        try:
            stage = Stage(body.stage)
            reason = CloseReason(body.close_reason) if body.close_reason else None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if stage == Stage.done:
            raise HTTPException(409, "Use “Mark applied” (records the date, method and CV sent), "
                                     "or send the email (the send queue, or “I sent it myself”)")
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
