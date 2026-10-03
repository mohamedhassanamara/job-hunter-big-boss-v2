"""Read-only views for the Motiv Center: one tiny task to start with (the 5-minute rule) and
your wins, from real data."""

from datetime import timedelta
from typing import Any

from sqlmodel import Session, col, func, select

from app.models import (
    Application,
    ApplicationResponse,
    ChestOpen,
    Company,
    CVVersion,
    Interview,
    Job,
)
from app.models.base import utcnow
from app.models.enums import CVStatus, ResponseKind, Stage
from app.services.motivation import activity, local_day, today
from app.services.motivation.streak import compute

REJECTION_DAYS = 14  # a rejection this recent shows the "volume beats any single result" note


def _job(s: Session, app: Application) -> tuple[Job, Company]:
    job = s.get(Job, app.job_id)
    return job, s.get(Company, job.company_id)


def suggestion(s: Session) -> dict[str, Any]:
    """One small next step from your queue: a contact to verify or find, a job ready to apply
    to, a CV to review, or a job to shortlist."""
    from app.services import get_contact

    rows = get_contact.queue(s)
    if rows:
        r = rows[0]
        verb = "Verify one contact" if r.state == "verify" else "Find one contact"
        return {"label": f"{verb} at {r.company.name}", "detail": r.job.title,
                "href": f"/jobs/{r.job.id}"}
    ready = s.exec(select(Application).where(
        col(Application.stage).in_([Stage.cv_ready, Stage.ready]),
        col(Application.web_applied_at).is_(None))
        .order_by(col(Application.stage_changed_at))).first()
    if ready:
        job, company = _job(s, ready)
        return {"label": f"Apply to one job at {company.name}", "detail": job.title,
                "href": f"/jobs/{job.id}"}
    draft = s.exec(select(CVVersion).where(CVVersion.status == CVStatus.draft)
                   .order_by(col(CVVersion.created_at))).first()
    if draft:
        job, company = _job(s, s.get(Application, draft.application_id))
        return {"label": f"Review one CV for {company.name}", "detail": job.title,
                "href": f"/jobs/{job.id}/cv"}
    return {"label": "Shortlist one job", "detail": "From today's discoveries",
            "href": "/discover"}


def wins(s: Session, cfg: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    day = today(cfg, now)
    week_start = day - timedelta(days=day.weekday())
    applied = [at for at, kind in activity.moments(s, {**cfg, "count_emails": False,
                                                        "count_linkedin": False})
               if kind == "application"]
    counts = activity.per_day(s, cfg)
    latest = s.exec(select(ApplicationResponse)
                    .order_by(col(ApplicationResponse.received_at).desc())).first()
    recent = latest is not None and latest.kind == ResponseKind.rejection and \
        local_day(latest.received_at, cfg) >= day - timedelta(days=REJECTION_DAYS)
    return {
        "applications_week": sum(1 for at in applied if local_day(at, cfg) >= week_start),
        "applications_total": len(applied),
        "replies": s.exec(select(func.count()).select_from(ApplicationResponse)).one(),
        "positive_replies": s.exec(select(func.count()).select_from(ApplicationResponse)
                                   .where(ApplicationResponse.kind == ResponseKind.positive)
                                   ).one(),
        "interviews": s.exec(select(func.count()).select_from(Interview)).one(),
        "longest_streak": compute(counts, day, cfg["daily_goal"]).longest,
        "chests_opened": s.exec(select(func.count()).select_from(ChestOpen)).one(),
        "recent_rejection": recent,
    }
