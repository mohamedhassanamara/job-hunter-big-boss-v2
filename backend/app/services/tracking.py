"""After the CV: applying, replies, interviews, closing, reminders and stats. No model calls.

Every stage change goes through `pipeline.transition` (it writes the stage event); everything else
logs its own `application_event`, so a timeline shows the whole story.
"""

import csv
import hashlib
import io
import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from app.models import (
    Application,
    ApplicationResponse,
    AppSetting,
    Company,
    CVVersion,
    Interview,
    Job,
    ReminderAction,
)
from app.models.base import utcnow
from app.models.enums import (
    ApplyMethod,
    CloseReason,
    CVStatus,
    EventKind,
    InterviewOutcome,
    InterviewType,
    ResponseKind,
    Route,
    Stage,
)
from app.services import pipeline

DEFAULT_TRACKING = {"followup_days": [7, 14], "ghost_after_days": 30}
AFTER_APPLY_REASONS = {CloseReason.rejected, CloseReason.no_response, CloseReason.withdrawn,
                       CloseReason.offer_accepted, CloseReason.offer_declined}
APPLIED_STAGES = (Stage.done, Stage.interview)


class TrackingError(ValueError):
    """Shown to the user (invalid move, wrong CV version…)."""


def tracking_settings(s: Session) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == "tracking")).first()
    return {**DEFAULT_TRACKING, **(dict(row.value) if row else {})}


def _at(day: date | datetime | None) -> datetime:
    """A user-chosen date → an aware datetime (noon UTC, so the day never shifts)."""
    if day is None:
        return utcnow()
    if isinstance(day, datetime):
        return day if day.tzinfo else day.replace(tzinfo=UTC)
    return datetime.combine(day, time(12), tzinfo=UTC)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


# ----------------------------------------------------------------------------------- applying


def approved_cv(s: Session, app: Application) -> CVVersion | None:
    return s.exec(select(CVVersion).where(CVVersion.application_id == app.id,
                                          CVVersion.status == CVStatus.approved)
                  .order_by(col(CVVersion.version).desc())).first()


def ready_to_apply(s: Session) -> list[Application]:
    """Approved CV, no contact (web apply), not applied yet."""
    apps = s.exec(select(Application).where(
        col(Application.stage).in_([Stage.cv_ready, Stage.ready]),
        Application.route == Route.web_apply,
    ).order_by(col(Application.stage_changed_at).desc())).all()
    return [a for a in apps if approved_cv(s, a) is not None]


def lock_cv(v: CVVersion) -> None:
    """The version sent with an application: never re-rendered, re-approved or superseded."""
    if v.locked_at is None:
        v.locked_at = utcnow()
    if v.pdf_path and Path(v.pdf_path).exists() and not v.pdf_sha256:
        v.pdf_sha256 = hashlib.sha256(Path(v.pdf_path).read_bytes()).hexdigest()


def mark_applied(s: Session, app: Application, *, applied_on: date | None,
                 method: ApplyMethod, cv_version_id: int | None = None,
                 notes: str = "") -> Application:
    if Stage(app.stage) not in (Stage.cv_ready, Stage.ready):
        raise TrackingError("Only jobs with an approved CV (CV ready / Ready to apply) can be "
                            "marked applied")
    cv = s.get(CVVersion, cv_version_id) if cv_version_id else approved_cv(s, app)
    if cv is None or cv.application_id != app.id:
        raise TrackingError("Pick an approved CV version of this job")
    if cv.status != CVStatus.approved:
        raise TrackingError("Only an approved CV version can be sent")
    if Stage(app.stage) == Stage.cv_ready:
        pipeline.transition(s, app, Stage.ready)
    lock_cv(cv)
    s.add(cv)
    pipeline.transition(s, app, Stage.done)
    app.applied_at = _at(applied_on)  # the date you applied, not the click time
    app.applied_method = method
    app.applied_cv_version_id = cv.id
    app.applied_notes = notes.strip()
    s.add(app)
    pipeline.log_event(s, app, EventKind.applied,
                       f"Applied via {method.replace('_', ' ')} with CV v{cv.version}",
                       method=method, cv_version_id=cv.id, cv_version=cv.version,
                       applied_on=app.applied_at.date().isoformat(), notes=notes.strip())
    return app


# ------------------------------------------------------------------------------ after applying


def _require_applied(app: Application) -> None:
    if Stage(app.stage) not in APPLIED_STAGES:
        raise TrackingError("Only applied jobs (Applied / Interview) can log this")


def log_response(s: Session, app: Application, *, kind: ResponseKind,
                 received_on: date | None, notes: str = "") -> ApplicationResponse:
    _require_applied(app)
    response = ApplicationResponse(application_id=app.id, kind=kind,
                                   received_at=_at(received_on), notes=notes.strip())
    s.add(response)
    label = {"positive": "Positive reply", "rejection": "Rejection", "other": "Reply"}[kind]
    pipeline.log_event(s, app, EventKind.response, f"{label} received", response_kind=kind,
                       received_on=response.received_at.date().isoformat(), notes=notes.strip())
    return response


def log_interview(s: Session, app: Application, *, scheduled_at: datetime,
                  type: InterviewType, notes: str = "",
                  outcome: InterviewOutcome = InterviewOutcome.pending) -> Interview:
    _require_applied(app)
    rounds = s.exec(select(Interview).where(Interview.application_id == app.id)).all()
    interview = Interview(application_id=app.id, round=len(rounds) + 1,
                          scheduled_at=_at(scheduled_at), type=type, notes=notes.strip(),
                          outcome=outcome)
    s.add(interview)
    if Stage(app.stage) == Stage.done:
        pipeline.transition(s, app, Stage.interview)
    pipeline.log_event(s, app, EventKind.interview,
                       f"Interview round {interview.round} ({type.replace('_', ' ')}) logged",
                       round=interview.round, type=type,
                       scheduled_at=interview.scheduled_at.isoformat(), outcome=outcome)
    return interview


def update_interview(s: Session, interview: Interview, **changes: Any) -> Interview:
    app = s.get(Application, interview.application_id)
    for key, value in changes.items():
        if value is not None:
            setattr(interview, key, _at(value) if key == "scheduled_at" else value)
    s.add(interview)
    if app is not None and "outcome" in changes and changes["outcome"] is not None:
        pipeline.log_event(s, app, EventKind.interview,
                           f"Interview round {interview.round}: {interview.outcome}",
                           round=interview.round, outcome=interview.outcome)
    return interview


def close(s: Session, app: Application, reason: CloseReason, notes: str = "") -> Application:
    applied = app.applied_at is not None or Stage(app.stage) in APPLIED_STAGES
    if applied and reason not in AFTER_APPLY_REASONS:
        raise TrackingError("After applying, close as rejected, no response, withdrew, "
                            "offer accepted or offer declined")
    message = {
        CloseReason.rejected: "Closed: rejected", CloseReason.no_response: "Closed: no response",
        CloseReason.withdrawn: "Closed: withdrew", CloseReason.offer_accepted:
        "Closed: offer accepted", CloseReason.offer_declined: "Closed: offer declined",
        CloseReason.dismissed: "Dismissed",
    }.get(reason)
    pipeline.transition(s, app, Stage.closed, close_reason=reason,
                        message=f"{message}{f' ({notes.strip()})' if notes.strip() else ''}")
    return app


# ---------------------------------------------------------------------------------- reminders


@dataclass
class Reminder:
    application_id: int
    job_id: int
    job_title: str
    company: str
    key: str  # followup:7 · followup:14 · ghost
    kind: str  # followup | ghost
    days: int
    due_at: datetime
    applied_at: datetime


def reminders(s: Session, now: datetime | None = None) -> list[Reminder]:
    """Due follow-ups and ghosting suggestions for applied jobs with no reply and no interview.
    Snoozed (until later) and dismissed ones are skipped. Computed on read."""
    now = now or utcnow()
    cfg = tracking_settings(s)
    apps = s.exec(select(Application).where(col(Application.stage).in_(APPLIED_STAGES),
                                            col(Application.applied_at).is_not(None))).all()
    out = []
    for app in apps:
        answered = s.exec(select(ApplicationResponse.id).where(
            ApplicationResponse.application_id == app.id)).first() or s.exec(
            select(Interview.id).where(Interview.application_id == app.id)).first()
        if answered:
            continue
        actions = {a.key: a for a in s.exec(select(ReminderAction).where(
            ReminderAction.application_id == app.id)).all()}
        applied = _aware(app.applied_at)
        job = s.get(Job, app.job_id)
        company = s.get(Company, job.company_id) if job else None
        # Only the latest due follow-up counts (the 14-day one replaces the 7-day one), so
        # dismissing or snoozing it never brings an older one back.
        passed = [d for d in sorted(cfg["followup_days"]) if applied + timedelta(days=d) <= now]
        due = [(f"followup:{passed[-1]}", "followup", passed[-1])] if passed else []
        due.append(("ghost", "ghost", int(cfg["ghost_after_days"])))
        for key, kind, days in due:
            at = applied + timedelta(days=days)
            action = actions.get(key)
            if at > now or (action and (action.dismissed_at or (
                    action.snoozed_until and _aware(action.snoozed_until) > now))):
                continue
            out.append(Reminder(app.id, app.job_id, job.title if job else "",
                                company.name if company else "", key, kind, days, at, applied))
    return sorted(out, key=lambda r: r.due_at)


def _action(s: Session, app_id: int, key: str) -> ReminderAction:
    row = s.exec(select(ReminderAction).where(ReminderAction.application_id == app_id,
                                              ReminderAction.key == key)).first()
    return row or ReminderAction(application_id=app_id, key=key)


def snooze(s: Session, app: Application, key: str, until: datetime | None = None,
           days: int = 3) -> ReminderAction:
    row = _action(s, app.id, key)
    row.snoozed_until = _aware(until) or utcnow() + timedelta(days=days)
    s.add(row)
    pipeline.log_event(s, app, EventKind.reminder, f"Reminder {key} snoozed", key=key,
                       until=row.snoozed_until.isoformat())
    return row


def dismiss(s: Session, app: Application, key: str) -> ReminderAction:
    row = _action(s, app.id, key)
    row.dismissed_at = utcnow()
    s.add(row)
    pipeline.log_event(s, app, EventKind.reminder, f"Reminder {key} dismissed", key=key)
    return row


def confirm_ghosted(s: Session, app: Application) -> Application:
    """The only way a ghosting suggestion closes an application: the user's click."""
    return close(s, app, CloseReason.no_response, "no reply")


# ---------------------------------------------------------------------------------- insight


@dataclass
class TrackedRow:
    application: Application
    job: Job
    company: Company
    responses: list[ApplicationResponse] = field(default_factory=list)
    interviews: list[Interview] = field(default_factory=list)

    @property
    def first_answer_at(self) -> datetime | None:
        times = [_aware(r.received_at) for r in self.responses]
        times += [_aware(i.scheduled_at) for i in self.interviews]
        return min(times) if times else None

    @property
    def days_to_first_answer(self) -> float | None:
        first, applied = self.first_answer_at, _aware(self.application.applied_at)
        return (first - applied).total_seconds() / 86400 if first and applied else None


def tracked(s: Session, *, track: list[str] | None = None, country: list[str] | None = None,
            source: list[str] | None = None, stage: list[str] | None = None,
            start: date | None = None, end: date | None = None) -> list[TrackedRow]:
    """Applied applications (applied_at set), newest first, with replies and interviews."""
    apps = s.exec(select(Application).where(col(Application.applied_at).is_not(None))
                  .order_by(col(Application.applied_at).desc())).all()
    out = []
    for app in apps:
        job = s.get(Job, app.job_id)
        if job is None:
            continue
        applied = _aware(app.applied_at).date()
        if (track and (job.matched_track or "NONE") not in track) or \
                (country and (job.country or "REMOTE") not in country) or \
                (source and job.source not in source) or (stage and app.stage not in stage) or \
                (start and applied < start) or (end and applied > end):
            continue
        out.append(TrackedRow(
            app, job, s.get(Company, job.company_id),
            list(s.exec(select(ApplicationResponse).where(
                ApplicationResponse.application_id == app.id)
                .order_by(col(ApplicationResponse.received_at))).all()),
            list(s.exec(select(Interview).where(Interview.application_id == app.id)
                        .order_by(col(Interview.round))).all()),
        ))
    return out


def _rate(rows: list[TrackedRow], hit) -> dict[str, Any]:  # noqa: ANN001
    n = len(rows)
    k = sum(1 for r in rows if hit(r))
    return {"count": k, "total": n, "rate": round(k / n, 3) if n else None}


def stats(rows: list[TrackedRow]) -> dict[str, Any]:
    """Applications per ISO week, response and interview rates (overall and by track, country,
    source) and the median days to the first reply or interview."""
    responded = lambda r: bool(r.responses or r.interviews)  # noqa: E731
    interviewed = lambda r: bool(r.interviews)  # noqa: E731
    weeks: dict[str, int] = {}
    for r in rows:
        year, week, _ = _aware(r.application.applied_at).isocalendar()
        key = f"{year}-W{week:02d}"
        weeks[key] = weeks.get(key, 0) + 1

    def by(attr) -> list[dict[str, Any]]:  # noqa: ANN001
        groups: dict[str, list[TrackedRow]] = {}
        for r in rows:
            groups.setdefault(attr(r) or "(none)", []).append(r)
        return sorted(({"group": g, "applied": len(v), "response": _rate(v, responded),
                        "interview": _rate(v, interviewed)} for g, v in groups.items()),
                      key=lambda x: -x["applied"])

    days = [d for r in rows if (d := r.days_to_first_answer) is not None]
    return {
        "applied": len(rows),
        "per_week": [{"week": k, "count": v} for k, v in sorted(weeks.items())],
        "response": _rate(rows, responded),
        "interview": _rate(rows, interviewed),
        "median_days_to_first_response": round(statistics.median(days), 1) if days else None,
        "by_track": by(lambda r: r.job.matched_track),
        "by_country": by(lambda r: r.job.country),
        "by_source": by(lambda r: r.job.source),
    }


def upcoming_interviews(s: Session, now: datetime | None = None,
                        days: int = 14) -> list[tuple[Interview, Application, Job, Company]]:
    """Pending interviews from today (start of day) to `days` ahead, soonest first."""
    now = now or utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = s.exec(select(Interview, Application, Job, Company)
                  .join(Application, col(Application.id) == col(Interview.application_id))
                  .join(Job, col(Job.id) == col(Application.job_id))
                  .join(Company, col(Company.id) == col(Job.company_id))
                  .where(Interview.outcome == InterviewOutcome.pending,
                         col(Interview.scheduled_at) >= start,
                         col(Interview.scheduled_at) <= now + timedelta(days=days),
                         Application.stage != Stage.closed)
                  .order_by(col(Interview.scheduled_at))).all()
    return list(rows)


def stats_summary(s: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    rows = tracked(s)
    year, week, _ = now.isocalendar()
    this_week = sum(1 for r in rows if _aware(r.application.applied_at).isocalendar()[:2]
                    == (year, week))
    rate = _rate(rows, lambda r: bool(r.responses or r.interviews))
    return {"applied_this_week": this_week, "applied_total": rate["total"],
            "responded": rate["count"], "response_rate": rate["rate"]}


CSV_COLUMNS = ["applied_on", "job_title", "company", "track", "country", "source", "stage",
               "method", "cv_version", "responses", "positive_replies", "interviews",
               "days_to_first_response", "close_reason", "listing_url"]


def export_csv(s: Session, rows: list[TrackedRow]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for r in rows:
        cv = s.get(CVVersion, r.application.applied_cv_version_id) \
            if r.application.applied_cv_version_id else None
        days = r.days_to_first_answer
        writer.writerow([
            _aware(r.application.applied_at).date().isoformat(), r.job.title,
            r.company.name if r.company else "", r.job.matched_track or "", r.job.country or "",
            r.job.source, r.application.stage, r.application.applied_method or "",
            cv.version if cv else "", len(r.responses),
            sum(1 for x in r.responses if x.kind == ResponseKind.positive), len(r.interviews),
            round(days, 1) if days is not None else "", r.application.close_reason or "",
            r.job.url,
        ])
    return buf.getvalue()
