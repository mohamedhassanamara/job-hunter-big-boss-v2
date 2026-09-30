"""The only module allowed to change `application.stage`. Every change writes an event."""

from sqlmodel import Session

from app.models import Application, ApplicationEvent, Company, Job
from app.models.base import utcnow
from app.models.enums import CloseReason, EventKind, Route, Stage

ALLOWED: dict[Stage, set[Stage]] = {
    Stage.new: {Stage.shortlisted, Stage.closed},
    Stage.shortlisted: {Stage.cv_ready, Stage.new, Stage.closed},
    Stage.cv_ready: {Stage.drafted, Stage.ready, Stage.shortlisted, Stage.closed},
    Stage.drafted: {Stage.ready, Stage.cv_ready, Stage.closed},
    Stage.ready: {Stage.done, Stage.drafted, Stage.cv_ready, Stage.closed},
    Stage.done: {Stage.interview, Stage.closed},
    Stage.interview: {Stage.closed, Stage.done},
    Stage.closed: {Stage.new},
}

STAGE_LABELS: dict[Stage, str] = {
    Stage.new: "New",
    Stage.shortlisted: "Shortlisted",
    Stage.cv_ready: "CV ready",
    Stage.drafted: "Email drafted",
    Stage.ready: "Ready",
    Stage.done: "Done",
    Stage.interview: "Interview",
    Stage.closed: "Closed",
}


class TransitionError(ValueError):
    pass


def effective_route(app: Application) -> Route:
    """The route a job is on: the one set, else derived (a contact → cold email, none → web
    apply). Approving the CV fixes it (cv.approve)."""
    if Route(app.route) != Route.undecided:
        return Route(app.route)
    return Route.cold_email if app.contact_id else Route.web_apply


def stage_label(stage: Stage | str, route: Route | str) -> str:
    stage = Stage(stage)
    if stage == Stage.ready:
        return "Ready to apply" if route == Route.web_apply else "Ready to send"
    if stage == Stage.done:
        return "Applied" if route == Route.web_apply else "Sent"
    return STAGE_LABELS[stage]


def can_transition(src: Stage | str, dst: Stage | str) -> bool:
    return Stage(dst) in ALLOWED[Stage(src)]


def transition(
    session: Session,
    app: Application,
    to: Stage,
    *,
    close_reason: CloseReason | None = None,
    message: str | None = None,
) -> ApplicationEvent:
    src = Stage(app.stage)
    if src == to:
        raise TransitionError(f"Already in {stage_label(to, app.route)}")
    if not can_transition(src, to):
        raise TransitionError(
            f"Can't move from {stage_label(src, app.route)} to {stage_label(to, app.route)}"
        )
    if to == Stage.closed and close_reason is None:
        close_reason = CloseReason.dismissed

    now = utcnow()
    app.stage = to
    app.stage_changed_at = now
    app.close_reason = close_reason if to == Stage.closed else None
    if to == Stage.done:
        app.applied_at = now
        job = session.get(Job, app.job_id)
        company = session.get(Company, job.company_id) if job else None
        if company and company.contacted_at is None:
            company.contacted_at = now
            session.add(company)

    if message is None:
        message = f"Moved to {stage_label(to, app.route)}"
        if to == Stage.closed and close_reason:
            message = "Dismissed" if close_reason == CloseReason.dismissed else (
                f"Closed ({close_reason.replace('_', ' ')})"
            )
    event = ApplicationEvent(
        application_id=app.id,
        kind=EventKind.stage_change,
        from_stage=src,
        to_stage=to,
        message=message,
        at=now,
    )
    session.add(app)
    session.add(event)
    return event


def log_event(
    session: Session, app: Application, kind: EventKind, message: str, **payload: object
) -> ApplicationEvent:
    event = ApplicationEvent(application_id=app.id, kind=kind, message=message, payload=payload)
    session.add(event)
    return event
