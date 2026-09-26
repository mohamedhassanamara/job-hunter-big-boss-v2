"""Cheap rule-based pre-filter so obvious noise never reaches the (future) LLM scorer.

Every dropped job carries a reason code so the filter can be tuned from the UI:
  incomplete · too_old · title_excluded:<kw> · title_no_role_match ·
  location_outside:<cc|unknown> · not_remote
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.models.enums import RemotePolicy, RemoteType
from app.providers.base import ProfileSpec, RawJob
from app.services.geo import EU_EEA, fold, region_allows

# Title normalization: map multilingual / synonym words onto a small vocabulary.
_PHRASES = [
    (r"\bmachine learning\b", "ml"),
    (r"\bartificial intelligence\b", "ai"),
    (r"\bintelligence artificielle\b", "ai"),
    (r"\binteligencia artificial\b", "ai"),
    (r"\bintelligenza artificiale\b", "ai"),
    (r"\bgen ai\b", "ai"),
    (r"\bml ops\b", "ml ops"),
]
_WORDS = {
    "mlops": "ml ops",
    "genai": "ai",
    "llm": "ai",
    "llms": "ai",
    "ia": "ai",
    "engineering": "engineer",
    "engineers": "engineer",
    "ingenieur": "engineer",
    "ingenieure": "engineer",
    "ingeniero": "engineer",
    "ingeniera": "engineer",
    "ingegnere": "engineer",
    "engenheiro": "engineer",
    "engenheira": "engineer",
    "donnees": "data",
    "datos": "data",
    "dati": "data",
    "dados": "data",
    "analytique": "analytics",
}
_MAX_GAP = 2  # words allowed between role tokens ("data platform engineer" ~ "data engineer")


def normalize_title(title: str) -> list[str]:
    text = fold(title)
    for pattern, repl in _PHRASES:
        text = re.sub(pattern, repl, text)
    words: list[str] = []
    for w in text.split():
        words.extend(_WORDS.get(w, w).split())
    return words


def _in_order(words: list[str], tokens: list[str]) -> bool:
    """tokens appear in `words` in order, with at most _MAX_GAP words between neighbours."""
    for start, w in enumerate(words):
        if w != tokens[0]:
            continue
        pos, ok = start, True
        for tok in tokens[1:]:
            window = words[pos + 1 : pos + 2 + _MAX_GAP]
            if tok not in window:
                ok = False
                break
            pos = pos + 1 + window.index(tok)
        if ok:
            return True
    return False


def matches_role(title: str, roles: list[str]) -> str | None:
    words = normalize_title(title)
    for role in roles:
        tokens = normalize_title(role)
        if not tokens:
            continue
        # Romance languages put the noun first: "Ingeniero de datos" → engineer … data.
        if _in_order(words, tokens) or (len(tokens) > 1 and _in_order(words, tokens[::-1])):
            return role
    return None


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
    if profile.roles and not matches_role(job.title, profile.roles):
        return "title_no_role_match"

    targets = {c.upper() for c in profile.locations}
    is_remote = job.remote_type == RemoteType.remote
    if targets and job.country not in targets:
        if not is_remote:
            return f"location_outside:{job.country or 'unknown'}"
        if job.country and job.country not in EU_EEA:
            return f"location_outside:{job.country}"
        allowed, code = region_allows(job.location, targets)
        if not allowed:
            return f"location_outside:{code or 'unknown'}"
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
