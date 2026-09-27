import pytest

from app.providers.base import FitAssessment, RedFlag, SubScore
from app.services.fit import (
    ScoringConfig,
    build_record,
    cache_key,
    confidence,
    evidence_found,
    experience_version,
    flag_severity,
    recompute,
    truncate_description,
    weighted_score,
)

TEXT = """We are hiring a Data Engineer in Madrid. You will build pipelines with Spark and dbt.
Requirements: 3+ years of Python and SQL. Fluent Spanish required.
Candidates must have the right to work in the EU; we do not offer visa sponsorship."""
CONFIG = ScoringConfig(weights={
    "role_match": 0.30, "skills_match": 0.30, "seniority_fit": 0.15,
    "location_eligibility": 0.15, "language_requirements": 0.10,
})


def assessment(flags: list[RedFlag] | None = None, **scores: int) -> FitAssessment:
    base = {"role_match": 9, "skills_match": 8, "seniority_fit": 8,
            "location_eligibility": 5, "language_requirements": 5}
    base.update(scores)
    subs = {d: SubScore(score=s, reason=f"{d} reason", evidence="build pipelines with Spark and dbt")
            for d, s in base.items()}
    return FitAssessment(**subs, red_flags=flags or [], strengths=["Spark"], gaps=[], summary="ok")


def test_weighted_score() -> None:
    subs = {"role_match": 10, "skills_match": 10, "seniority_fit": 10,
            "location_eligibility": 10, "language_requirements": 10}
    assert weighted_score(subs, CONFIG.weights) == 100
    subs["skills_match"] = 0
    assert weighted_score(subs, CONFIG.weights) == 70
    assert weighted_score(subs, {**CONFIG.weights, "skills_match": 0}) == 100  # weight 0 ignored
    assert weighted_score(subs, {}) == 0


def test_evidence_verification() -> None:
    assert evidence_found("build pipelines with Spark and dbt", TEXT)
    assert evidence_found("BUILD  pipelines, with spark & DBT", TEXT)  # case/punctuation/spaces
    assert evidence_found("we do not offer visa sponsorship", TEXT)
    assert not evidence_found("5+ years of Kubernetes experience", TEXT)  # fabricated
    assert not evidence_found("", TEXT)
    assert evidence_found("Canditates must have right to work in the EU", TEXT)  # ≥80% words in order


def test_hard_flag_caps_score_only_when_verified_and_disqualifying() -> None:
    real = RedFlag(type="no_visa_sponsorship", text="No sponsorship",
                   evidence="we do not offer visa sponsorship")
    record = build_record(assessment([real]), job_text=TEXT, description_level="full",
                          remote_type="hybrid", config=CONFIG)
    assert record["red_flags"][0]["severity"] == "hard"
    assert record["score"] == 35  # capped (uncapped would be 76)

    fake = RedFlag(type="no_visa_sponsorship", text="No sponsorship",
                   evidence="sponsorship is never available for anyone")
    record = build_record(assessment([fake]), job_text=TEXT, description_level="full",
                          remote_type="hybrid", config=CONFIG)
    assert record["red_flags"][0]["severity"] == "soft"  # hallucinated disqualifier can't sink it
    assert record["score"] == 76

    authorized = ScoringConfig(weights=CONFIG.weights, work_authorization="eu_authorized")
    record = build_record(assessment([real]), job_text=TEXT, description_level="full",
                          remote_type="hybrid", config=authorized)
    assert record["score"] == 76  # sponsorship language doesn't matter with EU authorization


def test_recompute_with_new_weights_needs_no_llm() -> None:
    record = build_record(assessment(), job_text=TEXT, description_level="full",
                          remote_type="hybrid", config=CONFIG)
    only_role = ScoringConfig(weights={"role_match": 1.0})
    score, _ = recompute(record["sub_scores"], record["red_flags"], only_role)
    assert score == 90


def test_confidence_levels() -> None:
    long_text = "x " * 600
    assert confidence("full", long_text) == "high"
    assert confidence("summary", long_text) == "medium"
    assert confidence("snippet", long_text) == "low"
    assert confidence("full", "short") == "medium"  # little text → one level down


def test_cache_inputs_change_the_key() -> None:
    base = cache_key("c1", "e1", "qwen2.5:7b", "fit_score/v1")
    assert base == cache_key("c1", "e1", "qwen2.5:7b", "fit_score/v1")
    assert len({base, cache_key("c2", "e1", "qwen2.5:7b", "fit_score/v1"),
                cache_key("c1", "e2", "qwen2.5:7b", "fit_score/v1"),
                cache_key("c1", "e1", "llama3", "fit_score/v1"),
                cache_key("c1", "e1", "qwen2.5:7b", "fit_score/v2")}) == 5
    assert experience_version([{"t": 1}], {"email": "a"}) == experience_version([{"t": 1}], {"email": "b"})
    assert experience_version([{"t": 1}], {}) != experience_version([{"t": 2}], {})


def test_truncate_keeps_head_and_tail() -> None:
    text = "HEAD " + "x" * 10_000 + " TAIL"
    out = truncate_description(text, 1000)
    assert out.startswith("HEAD") and out.endswith("TAIL") and len(out) < 1100


def test_unsupported_requirement_penalties_become_unknown() -> None:
    subs = {d: SubScore(score=8, reason="r", evidence="build pipelines with Spark and dbt")
            for d in ("role_match", "skills_match", "seniority_fit")}
    a = FitAssessment(
        **subs,
        location_eligibility=SubScore(score=0, reason="Requires EU work authorization", evidence=""),
        language_requirements=SubScore(score=0, reason="Needs Spanish", evidence="Fluent Spanish required"),
        summary="x",
    )
    record = build_record(a, job_text=TEXT, description_level="full", remote_type="hybrid", config=CONFIG)
    loc, lang = record["sub_scores"]["location_eligibility"], record["sub_scores"]["language_requirements"]
    assert loc["score"] == 5 and loc["adjusted_from"] == 0 and "Adjusted" in loc["reason"]
    assert lang["score"] == 0 and "adjusted_from" not in lang  # verified quote → penalty stands


PROFILE = {
    "work_authorization": "needs_sponsorship",
    "languages": [
        {"language": "Arabic", "level": "Native"},
        {"language": "English", "level": "Full professional"},
        {"language": "French", "level": "Full professional"},
        {"language": "Spanish", "level": "Limited working"},
    ],
}


def test_working_languages_from_profile() -> None:
    config = ScoringConfig.from_settings({}, PROFILE)
    assert config.working_languages == {"arabic", "english", "french"}  # Spanish is below B2


@pytest.mark.parametrize(
    ("quote", "severity"),
    [
        ("Fluent German is required", "hard"),
        ("Verhandlungssicheres Deutsch", "hard"),
        ("Fluency in Dutch and English", "hard"),  # both needed, no Dutch
        ("Dutch or French is required", "soft"),  # French is enough
        ("Néerlandais ou français courant", "soft"),
        ("German/French speaker", "soft"),
        ("Fluent French required", "soft"),  # spoken at a working level: model over-flagged
        ("Fluent Spanish required", "hard"),  # only Limited working
        ("Excellent communication skills", "soft"),  # no language named: can't verify
    ],
)
def test_language_flag_is_hard_only_when_candidate_lacks_it(quote: str, severity: str) -> None:
    config = ScoringConfig.from_settings({}, PROFILE)
    assert flag_severity("language_required", True, config, quote) == severity
    assert flag_severity("language_required", False, config, quote) == "soft"  # unverified


def test_nationality_restricted_is_hard_unless_own_nationality() -> None:
    config = ScoringConfig.from_settings({}, PROFILE)
    quote = "This role is open to UAE nationals only (Emiratisation)"
    assert flag_severity("nationality_restricted", True, config, quote) == "hard"
    eu = ScoringConfig.from_settings({}, {**PROFILE, "work_authorization": "eu_authorized"})
    assert flag_severity("nationality_restricted", True, eu, quote) == "hard"  # not about visas
    jordanian = ScoringConfig.from_settings({}, {**PROFILE, "nationality": "Jordanian"})
    assert flag_severity(
        "nationality_restricted", True, jordanian, "Jordanian nationals only"
    ) == "soft"
    assert flag_severity("nationality_restricted", False, config, quote) == "soft"
