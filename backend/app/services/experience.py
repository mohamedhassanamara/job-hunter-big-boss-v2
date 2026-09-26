from datetime import date

from sqlmodel import Session, col, select

from app.models import ExperienceItem
from app.providers.base import ExperienceSnapshot


def format_range(start: date | None, end: date | None) -> str | None:
    if start is None:
        return None
    left = start.strftime("%b %Y")
    right = end.strftime("%b %Y") if end else "Present"
    return f"{left} – {right}"


def experience_snapshots(session: Session) -> list[ExperienceSnapshot]:
    items = session.exec(
        select(ExperienceItem)
        .where(col(ExperienceItem.is_active))
        .order_by(col(ExperienceItem.kind), col(ExperienceItem.position))
    ).all()
    return [
        ExperienceSnapshot(
            kind=i.kind,
            title=i.title,
            org=i.org,
            summary=i.summary,
            bullets=i.bullets,
            tags=i.tags,
            dates=format_range(i.start_date, i.end_date),
        )
        for i in items
    ]
