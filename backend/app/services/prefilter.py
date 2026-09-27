"""Cheap rule-based pre-filter so obvious noise never reaches the (future) LLM scorer.

Every dropped job carries a reason code so the filter can be tuned from the UI:
  incomplete · too_old · title_excluded:<kw> · title_no_role_match ·
  location_outside:<cc|unknown> · not_remote
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.models.enums import RemotePolicy, RemoteType
from app.providers.base import ProfileSpec, RawJob
from app.services.geo import fold, remote_allows
from app.services.roles import match_track, matches_role, tracks_of  # noqa: F401 (re-export)

# Role matching (titles, variants, languages) lives in services/roles.py; roles come from Settings.


def excluded_keyword(title: str, keywords: list[str]) -> str | None:
    folded = f" {fold(title)} "
    for kw in keywords:
        k = fold(kw)
        if k and f" {k} " in folded:
            return kw
    return None


@dataclass
class Dropped:
    job: RawJob
    reason: str

    @property
    def code(self) -> str:
        return self.reason.split(":", 1)[0]


@dataclass
class FilterResult:
    kept: list[RawJob] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)

    def reason_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.dropped:
            counts[d.reason] = counts.get(d.reason, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def check(job: RawJob, profile: ProfileSpec, now: datetime) -> str | None:
    """Return a drop reason, or None to keep the job."""
    if not (job.title.strip() and job.company.strip() and job.url.strip()):
        return "incomplete"
    if job.posted_at and job.posted_at < now - timedelta(days=profile.max_age_days):
        return "too_old"
    if kw := excluded_keyword(job.title, profile.excluded_keywords):
        return f"title_excluded:{kw}"
    tracks = tracks_of(profile)
    if tracks:
        hit = match_track(job.title, tracks)
        if hit is None:
            return "title_no_role_match"
        job.matched_track, job.matched_role = hit

    targets = {c.upper() for c in profile.locations}
    is_remote = job.remote_type == RemoteType.remote
    if is_remote:
        allowed, code = remote_allows(job.location, job.country, targets, profile.remote_scope)
        if not allowed:
            return f"remote_outside:{code or 'unknown'}"
    elif targets and job.country not in targets:
        return f"location_outside:{job.country or 'unknown'}"
    if profile.remote_policy == RemotePolicy.remote_only and not is_remote:
        return "not_remote"
    return None


def prefilter(
    jobs: list[RawJob], profile: ProfileSpec, now: datetime | None = None
) -> FilterResult:
    now = now or datetime.now(UTC)
    result = FilterResult()
    for job in jobs:
        reason = check(job, profile, now)
        if reason:
            result.dropped.append(Dropped(job, reason))
        else:
            result.kept.append(job)
    return result
