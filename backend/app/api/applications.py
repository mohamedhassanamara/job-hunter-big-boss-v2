from fastapi import APIRouter, HTTPException, Query, Response
from sqlmodel import col, func, select

from app.api.deps import SessionDep, get_or_404
from app.models import Application
from app.models.enums import CloseReason, EventKind, Route, Stage
from app.schemas.jobs import ApplicationPatch, PipelineCard
from app.services import pipeline, tracking
from app.services.views import pipeline_cards

router = APIRouter(prefix="/applications", tags=["pipeline"])


OPEN_STAGES = [s for s in Stage if s not in (Stage.new, Stage.closed)]


def _stage_filter(stage: str) -> list[Stage] | None:
    """`open` (default: past New and not closed), `all`, or a comma-separated list of stages."""
    if stage == "all":
        return None
    if stage == "open":
        return OPEN_STAGES
    try:
        return [Stage(s.strip()) for s in stage.split(",") if s.strip()]
    except ValueError as exc:
        raise HTTPException(422, f"Unknown stage in {stage!r}") from exc


@router.get("", response_model=list[PipelineCard])
def list_applications(session: SessionDep, response: Response, stage: str = "open",
                      limit: int | None = Query(default=None, ge=1, le=500),
                      offset: int = Query(default=0, ge=0)) -> list[PipelineCard]:
    """Cards, newest stage change first. By default only what you are working on (not New, not
    closed: the other stages have thousands of rows); `stage=all`, `stage=new` or a list picks
    others, `limit`/`offset` page. The filtered total is in the X-Total-Count header."""
    stages = _stage_filter(stage)
    base = select(Application)
    if stages is not None:
        base = base.where(col(Application.stage).in_(stages))
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    query = base.order_by(col(Application.stage_changed_at).desc(), col(Application.id).desc())
    if limit is not None:
        query = query.limit(limit).offset(offset)
    response.headers["X-Total-Count"] = str(total)
    return pipeline_cards(session, session.exec(query).all())


@router.get("/counts", response_model=dict[str, int])
def application_counts(session: SessionDep) -> dict[str, int]:
    """How many applications are in each stage (the board's column counts)."""
    rows = session.exec(select(Application.stage, func.count()).group_by(Application.stage)).all()
    return {str(stage): n for stage, n in rows}


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
