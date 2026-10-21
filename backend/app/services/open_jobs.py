"""What counts as an open job. Bulk rescoring and the background queue only spend model calls on
open jobs; the per-job Rescore button and `recompute_all` ignore this.

A job is NOT open when it is:
- in the closed stage (dismissed is a close reason, so it is covered),
- a duplicate of another job,
- hidden by the location/remote filters (e.g. a remote job outside the target countries),
- from a paused source and past the profile's max age (its listing can't be refreshed, so it
  has most likely expired).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models import Application, Job
from app.models.base import utcnow
from app.models.enums import Stage
from app.providers.base import RawJob
from app.services import discovery, prefilter

_FILTER_CODES = {"remote_outside", "location_outside", "not_remote"}


@dataclass
class OpenSplit:
    open: list[int]
    skipped: int


def open_ids(session: Session, job_ids: Iterable[int] | None = None) -> set[int]:
    """The open jobs among `job_ids` (every job when None)."""
    stmt = select(Job)
    if job_ids is not None:
        ids = list(dict.fromkeys(job_ids))
        if not ids:
            return set()
        stmt = stmt.where(col(Job.id).in_(ids))
    jobs = session.exec(stmt).all()
    if not jobs:
        return set()
    closed = set(session.exec(
        select(Application.job_id).where(Application.stage == Stage.closed)).all())
    paused = set(discovery.paused_sources(session))
    _, profile = discovery.active_profile(session)
    now = utcnow()
    out: set[int] = set()
    for job in jobs:
        if job.id in closed or job.duplicate_of_id is not None:
            continue
        raw = RawJob(source=job.source, external_id=job.external_id, url=job.url,
                     title=job.title,
                     company="-", location=job.location, country=job.country,
                     remote_type=job.remote_type, posted_at=job.posted_at)
        reason = prefilter.check(raw, profile, now)
        if reason and reason.split(":", 1)[0] in _FILTER_CODES:
            continue
        if str(job.source) in paused:
            posted = job.posted_at or job.discovered_at
            if posted and (now - posted).days > profile.max_age_days:
                continue
        out.add(job.id)
    return out


def is_open(session: Session, job_id: int) -> bool:
    return job_id in open_ids(session, [job_id])


def split_open(session: Session, job_ids: Iterable[int]) -> OpenSplit:
    """Keep the order of `job_ids`; count the ones dropped as not open."""
    ids = list(dict.fromkeys(job_ids))
    keep = open_ids(session, ids)
    return OpenSplit(open=[i for i in ids if i in keep], skipped=len(ids) - len(keep))
