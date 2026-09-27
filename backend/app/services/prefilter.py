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
from app.services.geo import fold, remote_allows

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
# Romance-language job words: only these titles put the noun first ("Ingeniero de datos").
_ROMANCE = {"ingenieur", "ingenieure", "ingeniero", "ingeniera", "ingegnere", "engenheiro",
            "engenheira"}


def _normalize(title: str) -> list[tuple[str, bool]]:
    """(token, came_from_a_romance_word) pairs after synonym/translation mapping."""
    text = fold(title)
    for pattern, repl in _PHRASES:
        text = re.sub(pattern, repl, text)
    out: list[tuple[str, bool]] = []
    for w in text.split():
        out.extend((tok, w in _ROMANCE) for tok in _WORDS.get(w, w).split())
    return out


def normalize_title(title: str) -> list[str]:
    return [tok for tok, _ in _normalize(title)]


def _in_order(words: list[str], tokens: list[str], starts: set[int] | None = None) -> bool:
    """tokens appear in `words` in order, with at most _MAX_GAP words between neighbours.
    `starts` restricts where the first token may be matched."""
    for start, w in enumerate(words):
        if w != tokens[0] or (starts is not None and start not in starts):
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
    pairs = _normalize(title)
    words = [tok for tok, _ in pairs]
    romance = {i for i, (_, is_romance) in enumerate(pairs) if is_romance}
    for role in roles:
        tokens = normalize_title(role)
        if not tokens:
            continue
        if _in_order(words, tokens):
            return role
        # Romance languages put the noun first ("Ingeniero de datos" → engineer … data). Only
        # allow reversed order there: in English "Backend Engineer Kotlin & Data" is noise.
        if len(tokens) > 1 and romance and _in_order(words, tokens[::-1], starts=romance):
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
