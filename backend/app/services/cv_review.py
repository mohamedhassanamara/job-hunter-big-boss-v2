"""The Review CVs list: the CV draft of every shortlisted job, with the Approve gate evaluated.

The gate is the one in `api/cv.py:approve_cv`: exactly one page and no bullet/skill/number/tool
error (summary findings are information only).
"""

from sqlmodel import Session, col, select

from app.models import Application, Company, CVVersion, Job
from app.models.enums import CVStatus, Stage
from app.schemas.cv import CVReviewRow


def blocking_errors(violations: list[dict] | None) -> list[dict]:
    return [x for x in violations or []
            if x.get("severity") == "error" and x.get("where") != "summary"]


def approvable(v: CVVersion) -> bool:
    return (v.status == CVStatus.draft and v.page_count == 1 and not v.error
            and not blocking_errors(v.violations))


def rows(s: Session) -> list[CVReviewRow]:
    """Latest draft per shortlisted application (oldest first: the order they were made)."""
    apps = s.exec(
        select(Application, Job, Company)
        .join(Job, col(Job.id) == col(Application.job_id))
        .join(Company, col(Company.id) == col(Job.company_id))
        .where(Application.stage == Stage.shortlisted, col(Job.duplicate_of_id).is_(None))
    ).all()
    if not apps:
        return []
    by_app = {a.id: (a, j, c) for a, j, c in apps}
    latest: dict[int, CVVersion] = {}
    for v in s.exec(select(CVVersion).where(col(CVVersion.application_id).in_(list(by_app)),
                                            CVVersion.status != CVStatus.superseded)
                    .order_by(col(CVVersion.version))).all():
        latest[v.application_id] = v  # the highest non-superseded version wins
    out = []
    for app_id, v in latest.items():
        if v.status != CVStatus.draft:
            continue
        _, job, company = by_app[app_id]
        out.append(CVReviewRow(
            application_id=app_id, job_id=job.id, cv_id=v.id, job_title=job.title,
            company_name=company.name, track=job.matched_track, version=v.version,
            page_count=v.page_count, fill=v.fill,
            error_count=len(blocking_errors(v.violations)),
            summary_warnings=sum(1 for x in v.violations or [] if x.get("where") == "summary"
                                 and x.get("severity") != "error"),
            error=v.error, approvable=approvable(v), created_at=v.created_at))
    return sorted(out, key=lambda r: r.created_at)
