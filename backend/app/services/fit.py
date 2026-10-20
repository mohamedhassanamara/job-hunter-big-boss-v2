"""Turn an LLM FitAssessment into a stored fit score — all the arithmetic lives here, in code:

- score = round(10 · Σ wᵢ·sᵢ / Σ wᵢ) from the 0-10 sub-scores and configurable weights
- a missing core requirement (prompt v5: the primary language/stack or central skill of the role,
  verified quote, not named in the experience text) caps the score softly (default 60)
- hard red flags (verified, disqualifying for this candidate, and whose quote states the
  requirement itself) cap the score: work authorization when the candidate needs sponsorship,
  nationality-restricted roles, and a required language the candidate doesn't speak at a working
  level; otherwise the flag stays soft
- evidence quotes are checked against the job text; unverifiable quotes are marked
- confidence comes from how much of the listing we actually saw
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.models.enums import Confidence, DescriptionLevel
from app.providers.base import DIMENSIONS, FitAssessment, RedFlag
from app.services.geo import fold

log = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "role_match": 0.30,
    "skills_match": 0.30,
    "seniority_fit": 0.15,
    "location_eligibility": 0.15,
    "language_requirements": 0.10,
}
DEFAULT_CAP = 35
# Soft cap when a verified core requirement of the role is missing from the candidate's experience
# (prompt v5; Settings → Scoring; 100 turns it off).
DEFAULT_MISSING_CORE_CAP = 60
# Flag types that disqualify a candidate who needs visa sponsorship.
_AUTH_FLAGS = {"no_visa_sponsorship", "work_authorization_required", "must_be_based_in"}
# Requirement-type dimensions: a penalty (below the neutral 5) must be backed by a verified quote.
# Without one, the listing doesn't state the requirement, so it's unknown, not a mismatch.
_EVIDENCE_REQUIRED_TO_PENALIZE = ("location_eligibility", "language_requirements")
NEUTRAL = 5
MAX_DESCRIPTION = 15000


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


# German compounds name a language too ("Deutschkenntnisse", "deutschsprachig"), but never
# "Deutschland". Folded stems → language.
_COMPOUND_STEMS = {"deutsch": "german", "englisch": "english", "franzosisch": "french",
                   "niederlandisch": "dutch", "spanisch": "spanish", "italienisch": "italian",
                   "portugiesisch": "portuguese", "arabisch": "arabic"}
_COMPOUND = re.compile(
    r"\b(" + "|".join(_COMPOUND_STEMS) + r")(?:kenntnisse|sprachkenntnisse|sprachig\w*|sprache)\b")


def languages_mentioned(text: str) -> set[str]:
    folded = f" {fold(text)} "
    found = {lang for lang, words in LANGUAGE_WORDS.items()
             if any(f" {w} " in folded for w in words)}
    return found | {_COMPOUND_STEMS[m] for m in _COMPOUND.findall(folded)}


@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float]
    hard_flag_cap: int = DEFAULT_CAP
    missing_core_cap: int = DEFAULT_MISSING_CORE_CAP
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
            missing_core_cap=int(scoring.get("missing_core_cap", DEFAULT_MISSING_CORE_CAP)),
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


# A hard flag (score cap) must be backed by a quote that states the requirement itself. Patterns
# run on folded text (lowercase, no accents or punctuation; "ß" is dropped: "fließend" → "flieend").
_NEGATION = (r"(?:no|not|cannot|can t|cant|unable|without|unfortunately|unavailable|n a|nicht|"
             r"kein\w*|ohne|pas de|sans|aucun\w*|sin)")
_VISA_WORDING = (r"(?:sponsor\w*|visa\w*|visum|work permits?|permits?|arbeitserlaubnis|"
                 r"arbeitsgenehmigung|aufenthalts\w+|permis de travail|permis de sejour|"
                 r"autorisation de travail|titre de sejour|permiso de \w+|vergunning)")
_AUTH_WORDING = (r"(?:right to work|authori[sz]\w* to work|work authori[sz]ation|eligible to work|"
                 r"legally (?:entitled|allowed|permitted|able|authori[sz]ed) to work|legal right|"
                 r"employment authori[sz]ation|droit de travailler|"
                 r"(?:eu|european|uk|us) citizen\w*|"
                 r"citizens? of|residence permit|work permit|permis de travail|arbeitserlaubnis|"
                 r"arbeitsgenehmigung|aufenthalts\w+|titre de sejour|permiso de \w+|"
                 r"valid visa|visa required|resident permit|(?:eu|european) residents?|"
                 r"passport)")
_BASED_WORDING = (
    r"(?:(?:must|need to|needs to|have to|has to|required to|should|muss|mussen|doit|devez)"
    r"(?: \w+){0,4} (?:be )?(?:located|based|resident|residents|reside|residing|live|living|"
    r"wohnen|wohnhaft|ansassig|residir|habiter|resider)|"
    r"(?:already|currently|bereits|derzeit|actuellement)(?: \w+){0,3} "
    r"(?:living|based|located|resident|residing|wohnhaft|ansassig|domicilie\w*)|"
    r"residents? (?:of|in)|wohnsitz in|wohnhaft in|ansassig in|domicilie\w* en|"
    r"residence in|residency|only (?:for )?(?:candidates|applicants)? ?(?:in|from|based in|within)|"
    r"based (?:candidates|applicants|residents) only|(?:candidates|applicants) only|"
    r"local candidates only)")
_NATIONAL_WORD = (r"(?:nationals?|citizens?|emirati\w*|qatari\w*|kuwaiti\w*|bahraini\w*|omani\w*|"
                  r"saudi\w*|jordanian\w*|gcc|staatsangehor\w*|staatsburger\w*|nationalite|"
                  r"ressortissants?)")
_NATIONAL_QUALIFIER = (r"(?:only|must|required|restricted|exclusively|reserved|limited|solely|"
                       r"nur|uniquement|seulement)")
_QUALIFIED_FIRST = r"\b" + _NATIONAL_QUALIFIER + r"\b"
_ZATION = (r"\b(?:emirati[sz]\w*|qatari[sz]\w*|kuwaiti[sz]\w*|bahraini[sz]\w*|saudi[sz]\w*|"
           r"omani[sz]\w*)\b")
_LANG_REQUIREMENT = (r"(?:fluen\w*|native|mother tongue|proficien\w*|working knowledge|"
                     r"business level|business fluent|command of|verhandlungssicher\w*|"
                     r"flie\w{0,3}end\w*|muttersprach\w*|\w*kenntnisse|courant\w*|bilingue|"
                     r"maitris\w*|langue maternelle|must speak|speak|required|mandatory|"
                     r"essential|a must|"
                     r"erforderlich|vorausgesetzt|zwingend|obligatoire|indispensable|requis\w*|"
                     r"c1|c2|b2)")


def _has(pattern: str, folded: str) -> bool:
    return re.search(rf"\b{pattern}\b", folded) is not None


def requirement_stated(flag_type: str, quote: str) -> bool | None:
    """Does the quote itself state the requirement (not just mention an office, a city or perks)?
    None: this type has no wording rule. Used only to decide whether a flag may be hard."""
    folded = fold(quote)
    if flag_type == "no_visa_sponsorship":
        return _has(_NEGATION, folded) and _has(_VISA_WORDING, folded)
    if flag_type == "work_authorization_required":
        return _has(_AUTH_WORDING, folded)
    if flag_type == "must_be_based_in":
        return _has(_BASED_WORDING, folded)
    if flag_type == "nationality_restricted":
        qualified = _has(_NATIONAL_WORD, folded) and re.search(_QUALIFIED_FIRST, folded)
        return re.search(_ZATION, folded) is not None or qualified is not None
    if flag_type == "language_required":
        return bool(languages_mentioned(quote)) and _has(_LANG_REQUIREMENT, folded)
    return None


NOT_STATED = "The quote doesn't state the requirement (it mentions a place, mode or perk)."


def flag_severity_detail(flag_type: str, verified: bool, config: ScoringConfig, text: str = "",
                         evidence: str | None = None) -> tuple[str, str]:
    """(severity, note). 'hard' flags cap the score. Only verified quotes that state the
    requirement can be hard: a hallucinated or off-topic disqualifier must never sink a job. A flag
    that would otherwise be hard but whose quote lacks requirement wording is soft, with a note and
    a log line. `text` is the flag's description plus its quote; `evidence` is the quote alone
    (defaults to `text`)."""
    if not verified:
        return "soft", ""
    severity = "soft"
    if flag_type in _AUTH_FLAGS and config.work_authorization == "needs_sponsorship":
        severity = "hard"
    elif flag_type == "nationality_restricted":
        # "UAE nationals only", Emiratization roles… unless the candidate holds that nationality.
        own = config.nationality and f" {config.nationality} " in f" {fold(text)} "
        severity = "soft" if own else "hard"
    elif flag_type == "language_required" and language_blocks(text, config):
        severity = "hard"
    if severity == "hard":
        quote = text if evidence is None else evidence
        if requirement_stated(flag_type, quote) is False:
            log.info("hard flag %s downgraded to soft: quote doesn't state the requirement: %r",
                     flag_type, quote[:140])
            return "soft", NOT_STATED
    return severity, ""


def flag_severity(flag_type: str, verified: bool, config: ScoringConfig, text: str = "",
                  evidence: str | None = None) -> str:
    return flag_severity_detail(flag_type, verified, config, text, evidence)[0]


def final_score(sub_scores: dict[str, int], red_flags: list[dict], config: ScoringConfig,
                missing_core: bool = False) -> int:
    """Weighted sub-scores, then the caps: a verified hard flag caps at `hard_flag_cap`, a missing
    core requirement at `missing_core_cap`; the lower one wins."""
    score = weighted_score(sub_scores, config.weights)
    if any(f.get("severity") == "hard" for f in red_flags):
        score = min(score, config.hard_flag_cap)
    if missing_core:
        score = min(score, config.missing_core_cap)
    return score


def cap_reason(red_flags: list[dict], core_requirements: list[dict] | None) -> str | None:
    """Which cap decides the score: 'hard_flag', 'missing_core' or None."""
    if any(f.get("severity") == "hard" for f in red_flags or []):
        return "hard_flag"
    if any(c.get("counts") for c in core_requirements or []):
        return "missing_core"
    return None


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


def in_experience(requirement: str, experience_text: str) -> bool:
    """Does the candidate's experience text name the requirement itself ('Go', 'Kubernetes')? A
    whole-phrase match on folded text. A multi-word requirement is rarely repeated verbatim, so
    this only overrides a model that says 'missing' about something the pool plainly names."""
    phrase = fold(requirement)
    return bool(phrase) and f" {phrase} " in f" {fold(experience_text)} "


def evaluate_core(assessment: FitAssessment, job_text: str,
                  experience_text: str) -> list[dict[str, Any]]:
    """Stored form of the model's core requirements. `counts` = missing from the candidate AND
    the job-text quote is verified AND the pool doesn't name it. Only counted requirements cap the
    score: an unsupported claim must never sink a job."""
    out = []
    for core in assessment.core_requirements[:4]:
        name, quote = core.requirement.strip(), core.evidence.strip()
        if not name:
            continue
        verified = evidence_found(quote, job_text)
        named = core.missing and in_experience(name, experience_text)
        counts = core.missing and verified and not named
        note = ""
        if core.missing and not counts:
            note = ("Not counted: your experience names it." if named
                    else "Not counted: the quote isn't in the listing.")
        out.append({"requirement": name, "evidence": quote, "evidence_verified": verified,
                    "missing": core.missing, "counts": counts, **({"note": note} if note else {})})
    return out


def build_record(
    assessment: FitAssessment,
    *,
    job_text: str,
    description_level: str,
    remote_type: str,
    config: ScoringConfig,
    experience_text: str = "",
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
        severity, note = flag_severity_detail(
            flag.type, verified, config, f"{flag.text} {flag.evidence}", flag.evidence)
        flags.append(
            {
                "type": flag.type,
                "text": flag.text.strip(),
                "evidence": flag.evidence.strip(),
                "evidence_verified": verified,
                "severity": severity,
                **({"severity_note": note} if note else {}),
            }
        )
    raw = {d: s["score"] for d, s in subs.items()}
    core = evaluate_core(assessment, job_text, experience_text)
    return {
        "score": final_score(raw, flags, config, missing_core=any(c["counts"] for c in core)),
        "sub_scores": subs,
        "red_flags": flags,
        "core_requirements": core,
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


def recompute(sub_scores: dict[str, Any], red_flags: list[dict], config: ScoringConfig,
              core_requirements: list[dict] | None = None):
    """New weights/caps/work authorization → new score from stored sub-scores (no LLM call).
    Stored core requirements keep their `counts` verdict."""
    flags = []
    for f in red_flags:
        severity, note = flag_severity_detail(
            f["type"], f.get("evidence_verified", False), config,
            f"{f.get('text', '')} {f.get('evidence', '')}", f.get("evidence", ""))
        flags.append({**{k: v for k, v in f.items() if k != "severity_note"}, "severity": severity,
                      **({"severity_note": note} if note else {})})
    raw = {d: int(v.get("score", 0)) for d, v in sub_scores.items()}
    missing = any(c.get("counts") for c in core_requirements or [])
    return final_score(raw, flags, config, missing_core=missing), flags


# ------------------------------------------------------------------------------ prompt inputs


# Sections that never help a fit judgement (company pitch, perks, legal, how to apply). Dropped only
# when a listing is over the limit. Matched on the heading text, English, German, French, Spanish.
_BOILERPLATE_HEADING = re.compile(
    r"benefit|perks|we offer|what we offer|what you get|what s in it|why (?:us|join|work|you)|"
    r"about (?!the (?:job|role|position|team|opportunity)|you|this)|who we are|"
    r"our (?:story|values|mission|culture)|life at|company culture|"
    r"equal (?:opportunit|employment)|diversity|inclusion|\beeo\b|"
    r"how to apply|how we hire|application process|interview process|hiring process|next steps|"
    r"closing|contact|wir bieten|was bieten wir|deine vorteile|ihre vorteile|uber uns|unsere werte|"
    r"bewerbung|so bewirbst|chancengleichheit|kontakt|nous offrons|ce que nous offrons|avantages|"
    r"a propos|notre mission|processus de recrutement|postuler|pourquoi nous|que ofrecemos|"
    r"sobre nosotros|beneficios|proceso de seleccion")
# Sections that carry the judgement. These win over the boilerplate pattern and are never dropped.
_PROTECTED_HEADING = re.compile(
    r"requirement|qualification|profile|skills?\b|experience|must|nice.to.have|preferred|language|"
    r"sprach|anforderung|profil|voraussetzung|qualifikation|kenntnis|competence|exigence|requisito|"
    r"perfil|responsib|aufgaben|what you.ll do|your role|the role|tasks|stack|tech|looking for|"
    r"suchen|recherch|mission du poste|missions")
_HEADING_LINE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading, block) pairs; the text before the first heading has an empty heading."""
    marks = list(_HEADING_LINE.finditer(text))
    if not marks:
        return [("", text)]
    out = [("", text[: marks[0].start()])] if marks[0].start() > 0 else []
    for i, m in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), text[m.start():stop]))
    return out


def truncate_description(text: str, limit: int = MAX_DESCRIPTION) -> str:
    """Up to `limit` characters the listing goes in whole. Above it, drop boilerplate sections
    (benefits, about us, equal opportunity, how to apply) from the end of the listing backwards,
    leaving a marker, until it fits; requirement, qualification, language and responsibility
    sections are never dropped. Only if it still doesn't fit (no real listing is that long) is the
    middle cut as a last resort, keeping the head and the tail."""
    if len(text) <= limit:
        return text
    sections = _sections(text)
    dropped: set[int] = set()
    size = len(text)
    for i in range(len(sections) - 1, -1, -1):
        heading, block = sections[i]
        if size <= limit:
            break
        folded = fold(heading)
        boilerplate = _BOILERPLATE_HEADING.search(folded)
        if heading and boilerplate and not _PROTECTED_HEADING.search(folded):
            dropped.add(i)
            size -= len(block) - len(f"[section omitted: {heading}]\n")
    if dropped:
        text = "".join(f"[section omitted: {h}]\n" if i in dropped else b
                       for i, (h, b) in enumerate(sections))
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)  # last resort: should never trigger on real listings (longest: 9,309)
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
