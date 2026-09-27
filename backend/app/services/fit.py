"""Turn an LLM FitAssessment into a stored fit score — all the arithmetic lives here, in code:

- score = round(10 · Σ wᵢ·sᵢ / Σ wᵢ) from the 0-10 sub-scores and configurable weights
- hard red flags (verified, and disqualifying for this candidate) cap the score
- evidence quotes are checked against the job text; unverifiable quotes are marked
- confidence comes from how much of the listing we actually saw
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.models.enums import Confidence, DescriptionLevel
from app.providers.base import DIMENSIONS, FitAssessment
from app.services.geo import fold

DEFAULT_WEIGHTS = {
    "role_match": 0.30,
    "skills_match": 0.30,
    "seniority_fit": 0.15,
    "location_eligibility": 0.15,
    "language_requirements": 0.10,
}
DEFAULT_CAP = 35
# Flag types that disqualify a candidate who needs visa sponsorship.
_AUTH_FLAGS = {"no_visa_sponsorship", "work_authorization_required", "must_be_based_in"}
MAX_DESCRIPTION = 6000


@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float]
    hard_flag_cap: int = DEFAULT_CAP
    work_authorization: str = "needs_sponsorship"

    @classmethod
    def from_settings(cls, scoring: dict[str, Any] | None, profile: dict[str, Any] | None):
        scoring = scoring or {}
        return cls(
            weights={**DEFAULT_WEIGHTS, **(scoring.get("weights") or {})},
            hard_flag_cap=int(scoring.get("hard_flag_cap", DEFAULT_CAP)),
            work_authorization=(profile or {}).get("work_authorization", "needs_sponsorship"),
        )


# ---------------------------------------------------------------------------------- arithmetic


def weighted_score(sub_scores: dict[str, int], weights: dict[str, float]) -> int:
    total = sum(max(0.0, weights.get(d, 0.0)) for d in DIMENSIONS)
    if total <= 0:
        return 0
    value = sum(max(0.0, weights.get(d, 0.0)) * sub_scores.get(d, 0) for d in DIMENSIONS)
    return max(0, min(100, round(10 * value / total)))


def flag_severity(flag_type: str, verified: bool, config: ScoringConfig) -> str:
    """'hard' flags cap the score. Only verified quotes can be hard: a hallucinated
    disqualifier must never sink a job."""
    if not verified:
        return "soft"
    if flag_type in _AUTH_FLAGS and config.work_authorization == "needs_sponsorship":
        return "hard"
    return "soft"


def final_score(sub_scores: dict[str, int], red_flags: list[dict], config: ScoringConfig) -> int:
    score = weighted_score(sub_scores, config.weights)
    if any(f.get("severity") == "hard" for f in red_flags):
        score = min(score, config.hard_flag_cap)
    return score


# ------------------------------------------------------------------------------------ evidence


def _norm(text: str) -> str:
    return fold(text)  # lowercase, accents stripped, punctuation → spaces


def evidence_found(quote: str, text: str) -> bool:
    """Is the quote really in the job text? Exact (normalized) substring, or ≥80% of its words
    appearing in order (tolerates small paraphrase/punctuation differences)."""
    q = _norm(quote)
    if not q:
        return False
    t = _norm(text)
    if q in t:
        return True
    words, hay = q.split(), t.split()
    if len(words) < 3:
        return False
    matched, pos = 0, 0
    for w in words:
        try:
            pos = hay.index(w, pos) + 1
            matched += 1
        except ValueError:
            continue
    return matched / len(words) >= 0.8


# ---------------------------------------------------------------------------------- confidence


def confidence(level: str, text: str) -> str:
    order = [Confidence.high, Confidence.medium, Confidence.low]
    base = {
        DescriptionLevel.full: 0,
        DescriptionLevel.summary: 1,
        DescriptionLevel.snippet: 2,
    }.get(DescriptionLevel(level), 1)
    if len(text) < 800:
        base = min(2, base + 1)
    return order[base].value


# ---------------------------------------------------------------------------------- the record


def build_record(
    assessment: FitAssessment,
    *,
    job_text: str,
    description_level: str,
    remote_type: str,
    config: ScoringConfig,
) -> dict[str, Any]:
    subs = {}
    for dim, sub in assessment.sub_scores().items():
        subs[dim] = {
            "score": sub.score,
            "reason": sub.reason.strip(),
            "evidence": sub.evidence.strip(),
            "evidence_verified": evidence_found(sub.evidence, job_text),
        }
    flags = []
    for flag in assessment.red_flags:
        verified = evidence_found(flag.evidence, job_text)
        flags.append(
            {
                "type": flag.type,
                "text": flag.text.strip(),
                "evidence": flag.evidence.strip(),
                "evidence_verified": verified,
                "severity": flag_severity(flag.type, verified, config),
            }
        )
    raw = {d: s["score"] for d, s in subs.items()}
    return {
        "score": final_score(raw, flags, config),
        "sub_scores": subs,
        "red_flags": flags,
        "strengths": [s.strip() for s in assessment.strengths if s.strip()][:3],
        "gaps": [g.strip() for g in assessment.gaps if g.strip()][:3],
        "summary": assessment.summary.strip(),
        "confidence": confidence(description_level, job_text),
    }


def recompute(sub_scores: dict[str, Any], red_flags: list[dict], config: ScoringConfig):
    """New weights/cap/work authorization → new score from stored sub-scores (no LLM call)."""
    flags = [
        {**f, "severity": flag_severity(f["type"], f.get("evidence_verified", False), config)}
        for f in red_flags
    ]
    raw = {d: int(v.get("score", 0)) for d, v in sub_scores.items()}
    return final_score(raw, flags, config), flags


# ------------------------------------------------------------------------------ prompt inputs


def truncate_description(text: str, limit: int = MAX_DESCRIPTION) -> str:
    """Keep the head (context, responsibilities) and the tail (requirements often come last)."""
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    return f"{text[:head].rstrip()}\n[…]\n{text[-(limit - head):].lstrip()}"


def content_hash(title: str, company: str, location: str, remote: str, description: str) -> str:
    raw = "\x1f".join([title, company, location, remote, description])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def experience_version(items: list[dict[str, Any]], profile: dict[str, Any]) -> str:
    candidate = {k: v for k, v in (profile or {}).items() if k not in ("email",)}
    raw = json.dumps({"items": items, "profile": candidate}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_key(content: str, experience: str, model: str, prompt_version: str) -> str:
    return hashlib.sha256(f"{content}|{experience}|{model}|{prompt_version}".encode()).hexdigest()[
        :24
    ]


_WS = re.compile(r"\s+")


def one_line(text: str | None, limit: int = 240) -> str:
    value = _WS.sub(" ", text or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"
