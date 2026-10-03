"""What counts as "an application" for the streak and the chests. Read-only on job data.

- Jobs marked Applied: counted on the day you clicked (the latest `applied` event), not the
  applied date you picked; rows without that event (older ones) use the applied date. Undoing
  "Mark applied" clears the date, so the job drops out by itself.
- Optionally sent cold emails (`outreach_draft.sent_at`) and sent LinkedIn requests
  (`linkedin_outreach.sent_at`, cleared when you move the status back).
Nothing is stored: every call reads the history again.
"""

from collections import Counter
from datetime import date, datetime
from typing import Any

from sqlmodel import Session, col, select

from app.models import Application, ApplicationEvent, LinkedInOutreach, OutreachDraft
from app.models.enums import DraftStatus, EventKind
from app.services.motivation import local_day


def moments(s: Session, cfg: dict[str, Any]) -> list[tuple[datetime, str]]:
    """(when, kind) for every counted action; kind is application | email | linkedin."""
    clicked: dict[int, datetime] = {}
    for app_id, at in s.exec(select(ApplicationEvent.application_id, ApplicationEvent.at)
                             .where(ApplicationEvent.kind == EventKind.applied)).all():
        if app_id not in clicked or at > clicked[app_id]:
            clicked[app_id] = at
    out: list[tuple[datetime, str]] = []
    for app_id, applied in s.exec(select(Application.id, Application.web_applied_at)
                                  .where(col(Application.web_applied_at).is_not(None))).all():
        out.append((clicked.get(app_id) or applied, "application"))
    if cfg.get("count_emails"):
        out += [(at, "email") for at in s.exec(select(OutreachDraft.sent_at).where(
            OutreachDraft.status == DraftStatus.sent,
            col(OutreachDraft.sent_at).is_not(None))).all()]
    if cfg.get("count_linkedin"):
        out += [(at, "linkedin") for at in s.exec(select(LinkedInOutreach.sent_at).where(
            col(LinkedInOutreach.sent_at).is_not(None))).all()]
    return out


def per_day(s: Session, cfg: dict[str, Any]) -> Counter[date]:
    return Counter(local_day(at, cfg) for at, _kind in moments(s, cfg))


def total_since(s: Session, cfg: dict[str, Any], since: date) -> int:
    return sum(n for day, n in per_day(s, cfg).items() if day >= since)
