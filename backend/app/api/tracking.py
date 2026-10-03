from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session

from app.api.deps import SessionDep, get_or_404
from app.models import Application, Company, Interview, Job
from app.models.enums import ApplyMethod, CloseReason, InterviewOutcome, InterviewType, ResponseKind
from app.schemas.jobs import PipelineCard
from app.schemas.tracking import (
    AppliedIn,
    CloseIn,
    InterviewIn,
    InterviewOut,
    InterviewPatch,
    ReadyItem,
    ReminderOut,
    ResponseIn,
    ResponseOut,
    SnoozeIn,
    StatsOut,
    TrackedItem,
)
from app.services import cover_letter, pipeline, tracking
from app.services.views import pipeline_cards, tracked_item

router = APIRouter(tags=["tracking"])


def _enum(enum, value: str):  # noqa: ANN001, ANN202
    try:
        return enum(value)
    except ValueError as exc:
        raise HTTPException(422, f"Unknown value {value!r}") from exc


def _card(session: Session, app: Application) -> PipelineCard:
    session.commit()
    session.refresh(app)
    return pipeline_cards(session, [app])[0]


def _run(session: Session, fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
    try:
        return fn(session, *args, **kwargs)
    except (tracking.TrackingError, pipeline.TransitionError) as exc:
        raise HTTPException(422, str(exc)) from exc


# ----------------------------------------------------------------------------------- applying


@router.get("/applications/ready", response_model=list[ReadyItem])
def ready(session: SessionDep) -> list[ReadyItem]:
    out = []
    for app in tracking.ready_to_apply(session):
        job = session.get(Job, app.job_id)
        company = session.get(Company, job.company_id)
        cv = tracking.approved_cv(session, app)
        letters = [v for v in cover_letter.versions(session, app.id, "pdf")
                   if v.status != "superseded"]
        letter = next((v for v in letters if v.status == "approved"), None) or next(
            iter(letters), None)
        out.append(ReadyItem(application_id=app.id, job_id=job.id, title=job.title,
                             company=company.name, track=job.matched_track, country=job.country,
                             url=job.url, cv_version_id=cv.id, cv_version=cv.version,
                             stage=app.stage, letter_id=letter.id if letter else None,
                             letter_version=letter.version if letter else None,
                             letter_status=letter.status if letter else "none"))
    return out


@router.post("/applications/{app_id}/applied", response_model=PipelineCard)
def mark_applied(app_id: int, body: AppliedIn, session: SessionDep) -> PipelineCard:
    app = get_or_404(session, Application, app_id, "Application")
    _run(session, tracking.mark_applied, app, applied_on=body.applied_on,
         method=_enum(ApplyMethod, body.method), cv_version_id=body.cv_version_id,
         cover_letter_id=body.cover_letter_id, form_letter_id=body.form_letter_id,
         notes=body.notes)
    return _card(session, app)


@router.delete("/applications/{app_id}/applied", response_model=PipelineCard)
def undo_applied(app_id: int, session: SessionDep) -> PipelineCard:
    """Undo "Mark applied" (the Undo toast): dates, stage and the locks it made go back."""
    app = get_or_404(session, Application, app_id, "Application")
    _run(session, tracking.undo_applied, app)
    return _card(session, app)


# ------------------------------------------------------------------------------ after applying


@router.post("/applications/{app_id}/responses", response_model=ResponseOut, status_code=201)
def log_response(app_id: int, body: ResponseIn, session: SessionDep) -> ResponseOut:
    app = get_or_404(session, Application, app_id, "Application")
    row = _run(session, tracking.log_response, app, kind=_enum(ResponseKind, body.kind),
               received_on=body.received_on, notes=body.notes)
    session.commit()
    session.refresh(row)
    return ResponseOut.model_validate(row, from_attributes=True)


@router.post("/applications/{app_id}/interviews", response_model=InterviewOut, status_code=201)
def log_interview(app_id: int, body: InterviewIn, session: SessionDep) -> InterviewOut:
    app = get_or_404(session, Application, app_id, "Application")
    row = _run(session, tracking.log_interview, app, scheduled_at=body.scheduled_at,
               type=_enum(InterviewType, body.type), notes=body.notes,
               outcome=_enum(InterviewOutcome, body.outcome))
    session.commit()
    session.refresh(row)
    return InterviewOut.model_validate(row, from_attributes=True)


@router.patch("/interviews/{interview_id}", response_model=InterviewOut)
def update_interview(interview_id: int, body: InterviewPatch, session: SessionDep) -> InterviewOut:
    row = get_or_404(session, Interview, interview_id, "Interview")
    tracking.update_interview(
        session, row, scheduled_at=body.scheduled_at, notes=body.notes,
        type=_enum(InterviewType, body.type) if body.type else None,
        outcome=_enum(InterviewOutcome, body.outcome) if body.outcome else None)
    session.commit()
    session.refresh(row)
    return InterviewOut.model_validate(row, from_attributes=True)


@router.post("/applications/{app_id}/close", response_model=PipelineCard)
def close(app_id: int, body: CloseIn, session: SessionDep) -> PipelineCard:
    app = get_or_404(session, Application, app_id, "Application")
    _run(session, tracking.close, app, _enum(CloseReason, body.reason), body.notes)
    return _card(session, app)


# ---------------------------------------------------------------------------------- reminders


@router.get("/reminders", response_model=list[ReminderOut])
def reminders(session: SessionDep) -> list[ReminderOut]:
    return [ReminderOut(**r.__dict__) for r in tracking.reminders(session)]


@router.post("/reminders/{app_id}/{key}/snooze", status_code=204)
def snooze(app_id: int, key: str, body: SnoozeIn, session: SessionDep) -> None:
    app = get_or_404(session, Application, app_id, "Application")
    tracking.snooze(session, app, key, body.until, body.days)
    session.commit()


@router.post("/reminders/{app_id}/{key}/dismiss", status_code=204)
def dismiss(app_id: int, key: str, session: SessionDep) -> None:
    app = get_or_404(session, Application, app_id, "Application")
    tracking.dismiss(session, app, key)
    session.commit()


@router.post("/reminders/{app_id}/ghost/confirm", response_model=PipelineCard)
def confirm_ghosted(app_id: int, session: SessionDep) -> PipelineCard:
    app = get_or_404(session, Application, app_id, "Application")
    _run(session, tracking.confirm_ghosted, app)
    return _card(session, app)


# ------------------------------------------------------------------------------------ insight

Multi = Annotated[list[str] | None, Query()]


def _rows(session: Session, track: Multi, country: Multi, source: Multi, stage: Multi,
          start: date | None, end: date | None) -> list[tracking.TrackedRow]:
    return tracking.tracked(session, track=track, country=country, source=source, stage=stage,
                            start=start, end=end)


@router.get("/applications/tracked", response_model=list[TrackedItem])
def tracked(session: SessionDep, track: Multi = None, country: Multi = None,
            source: Multi = None, stage: Multi = None, start: date | None = None,
            end: date | None = None) -> list[TrackedItem]:
    return [tracked_item(session, r)
            for r in _rows(session, track, country, source, stage, start, end)]


@router.get("/stats", response_model=StatsOut)
def stats(session: SessionDep, track: Multi = None, country: Multi = None, source: Multi = None,
          stage: Multi = None, start: date | None = None, end: date | None = None) -> StatsOut:
    return StatsOut(**tracking.stats(_rows(session, track, country, source, stage, start, end)),
                    **tracking.channel_stats(session))


@router.get("/applications/export.csv")
def export(session: SessionDep, track: Multi = None, country: Multi = None, source: Multi = None,
           stage: Multi = None, start: date | None = None, end: date | None = None) -> Response:
    rows = _rows(session, track, country, source, stage, start, end)
    return Response(tracking.export_csv(session, rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="applications.csv"'})
