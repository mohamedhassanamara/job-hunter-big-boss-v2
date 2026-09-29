"""Turn an LLM FitAssessment into a stored fit score — all the arithmetic lives here, in code:

- score = round(10 · Σ wᵢ·sᵢ / Σ wᵢ) from the 0-10 sub-scores and configurable weights
- hard red flags (verified, and disqualifying for this candidate) cap the score: work
  authorization when the candidate needs sponsorship, nationality-restricted roles, and a
  required language the candidate doesn't speak at a working level
- evidence quotes are checked against the job text; unverifiable quotes are marked
- confidence comes from how much of the listing we actually saw
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.models.enums import Confidence, DescriptionLevel
from app.providers.base import DIMENSIONS, FitAssessment, RedFlag
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
# Requirement-type dimensions: a penalty (below the neutral 5) must be backed by a verified quote.
# Without one, the listing doesn't state the requirement, so it's unknown, not a mismatch.
_EVIDENCE_REQUIRED_TO_PENALIZE = ("location_eligibility", "language_requirements")
NEUTRAL = 5
MAX_DESCRIPTION = 6000


# Language names (folded) as they appear in listings, in English, French, German, Spanish, Dutch.
LANGUAGE_WORDS: dict[str, list[str]] = {
    "english": ["english", "anglais", "englisch", "ingles", "inglese", "engels"],
    "french": ["french", "francais", "franzosisch", "frances", "francese", "frans"],
    "german": ["german", "deutsch", "allemand", "aleman", "tedesco", "duits"],
    "dutch": ["dutch", "flemish", "nederlands", "vlaams", "neerlandais", "niederlandisch",
              "neerlandes", "olandese"],
    "spanish": ["spanish", "espagnol", "spanisch", "espanol", "castellano", "spagnolo", "spaans"],
    "italian": ["italian", "italien", "italienisch", "italiano", "italiaans"],
    "portuguese": ["portuguese", "portugais", "portugiesisch", "portugues", "portoghese"],
    "arabic": ["arabic", "arabe", "arabisch", "arabo"],
}
# Levels good enough for a job that "requires" the language (CEFR B2+ or the LinkedIn equivalent).
WORKING_LEVELS = {"native", "bilingual", "full professional", "professional working",
                  "c2", "c1", "b2"}
_ANY_OF = (" or ", " ou ", " oder ", " o ")  # not Dutch "of": clashes with English "of"


def languages_mentioned(text: str) -> set[str]:
    folded = f" {fold(text)} "
    return {lang for lang, words in LANGUAGE_WORDS.items()
            if any(f" {w} " in folded for w in words)}


@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float]
    hard_flag_cap: int = DEFAULT_CAP
    work_authorization: str = "needs_sponsorship"
    # Languages the candidate speaks at a working level (folded names, e.g. {"french"}).
    working_languages: frozenset[str] = frozenset()
    nationality: str = ""

    @classmethod
    def from_settings(cls, scoring: dict[str, Any] | None, profile: dict[str, Any] | None):
        scoring, profile = scoring or {}, profile or {}
        working = frozenset(
            lang
            for entry in profile.get("languages") or []
            if fold(str(entry.get("level", ""))) in WORKING_LEVELS
            for lang in languages_mentioned(str(entry.get("language", "")))
        )
        return cls(
            weights={**DEFAULT_WEIGHTS, **(scoring.get("weights") or {})},
            hard_flag_cap=int(scoring.get("hard_flag_cap", DEFAULT_CAP)),
            work_authorization=profile.get("work_authorization", "needs_sponsorship"),
            working_languages=working,
            nationality=fold(str(profile.get("nationality") or "")),
        )


# ---------------------------------------------------------------------------------- arithmetic


def weighted_score(sub_scores: dict[str, int], weights: dict[str, float]) -> int:
    total = sum(max(0.0, weights.get(d, 0.0)) for d in DIMENSIONS)
    if total <= 0:
        return 0
    value = sum(max(0.0, weights.get(d, 0.0)) * sub_scores.get(d, 0) for d in DIMENSIONS)
    return max(0, min(100, round(10 * value / total)))


def language_blocks(text: str, config: ScoringConfig) -> bool:
    """Does a quoted language requirement exclude the candidate? "Dutch or French" is met by
    either language; otherwise every named language is needed. No recognisable language → we
    can't check it, so it doesn't block."""
    required = languages_mentioned(text)
    if not required:
        return False
    folded = f" {fold(text)} "
    missing = required - config.working_languages
    if "/" in text or any(sep in folded for sep in _ANY_OF):
        return missing == required  # none of the alternatives is spoken
    return bool(missing)


def flag_severity(flag_type: str, verified: bool, config: ScoringConfig, text: str = "") -> str:
    """'hard' flags cap the score. Only verified quotes can be hard: a hallucinated
    disqualifier must never sink a job. `text` is the flag's description plus its quote."""
    if not verified:
        return "soft"
    if flag_type in _AUTH_FLAGS and config.work_authorization == "needs_sponsorship":
        return "hard"
    if flag_type == "nationality_restricted":
        # "UAE nationals only", Emiratization roles… unless the candidate holds that nationality.
        own = config.nationality and f" {config.nationality} " in f" {fold(text)} "
        return "soft" if own else "hard"
    if flag_type == "language_required" and language_blocks(text, config):
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
        verified = evidence_found(sub.evidence, job_text)
        entry = {
            "score": sub.score,
            "reason": sub.reason.strip(),
            "evidence": sub.evidence.strip(),
            "evidence_verified": verified,
        }
        if dim in _EVIDENCE_REQUIRED_TO_PENALIZE and sub.score < NEUTRAL and not verified:
            entry["adjusted_from"] = sub.score
            entry["score"] = NEUTRAL
            entry["reason"] += " (Adjusted to unknown: the listing doesn't state this requirement.)"
        subs[dim] = entry
    flags = []
    for flag in _all_flags(assessment):
        verified = evidence_found(flag.evidence, job_text)
        flags.append(
            {
                "type": flag.type,
                "text": flag.text.strip(),
                "evidence": flag.evidence.strip(),
                "evidence_verified": verified,
                "severity": flag_severity(
                    flag.type, verified, config, f"{flag.text} {flag.evidence}"
                ),
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


_CHECK_TEXT = {
    "no_visa_sponsorship": "States it can't sponsor visas",
    "work_authorization_required": "Requires existing work authorization",
    "must_be_based_in": "Requires living in a specific place",
    "nationality_restricted": "Restricted to nationals of a country",
    "language_required": "Requires a language",
    "seniority_mismatch": "Seniority well above the candidate",
}


def _all_flags(assessment: FitAssessment) -> list[RedFlag]:
    """The model's red_flags plus every `flag_checks` entry answered present=true (prompt v3),
    one per type. Same verification and severity rules apply to both."""
    flags = list(assessment.red_flags)
    listed = {f.type for f in flags}
    for kind, check in assessment.flag_checks.model_dump().items():
        if check["present"] and kind not in listed:
            evidence = (check.get("evidence") or "").strip()
            flags.append(RedFlag(type=kind, text=f"{_CHECK_TEXT.get(kind, kind)}: {evidence}"
                                 if evidence else _CHECK_TEXT.get(kind, kind), evidence=evidence))
    return flags


def recompute(sub_scores: dict[str, Any], red_flags: list[dict], config: ScoringConfig):
    """New weights/cap/work authorization → new score from stored sub-scores (no LLM call)."""
    flags = [
        {
            **f,
            "severity": flag_severity(
                f["type"], f.get("evidence_verified", False), config,
                f"{f.get('text', '')} {f.get('evidence', '')}",
            ),
        }
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


_HEADER_ONLY = {"email", "full_name", "phone", "links", "is_placeholder", "total_years_override",
                "experience_statement"}


def experience_version(items: list[dict[str, Any]], profile: dict[str, Any],
                       tracks: list[dict[str, Any]] | None = None) -> str:
    """What makes scores stale: adding/removing an experience item (or changing its dates, i.e.
    years), adding/removing a skill, changing a track (roles or years) or the candidate facts
    the scorer uses. Rewording a bullet, a title or a summary, or fixing a typo, doesn't.
    CV-header-only fields never change a score either."""
    candidate = {k: v for k, v in (profile or {}).items() if k not in _HEADER_ONLY}
    structure = sorted(
        (str(i.get("id", "")), i.get("kind"), str(i.get("start")), str(i.get("end")),
         sorted(i.get("tags") or []) if i.get("kind") == "skill" else [])
        for i in items)
    track_facts = sorted(
        (t.get("name") or "", str(t.get("years_experience")),
         sorted((r.get("title") or "") for r in t.get("roles") or []))
        for t in tracks or [])
    raw = json.dumps({"items": structure, "profile": candidate, "tracks": track_facts},
                     sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_key(content: str, experience: str, model: str, prompt_version: str) -> str:
    return hashlib.sha256(f"{content}|{experience}|{model}|{prompt_version}".encode()).hexdigest()[
        :24
    ]


_WS = re.compile(r"\s+")


def one_line(text: str | None, limit: int = 240) -> str:
    value = _WS.sub(" ", text or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"
