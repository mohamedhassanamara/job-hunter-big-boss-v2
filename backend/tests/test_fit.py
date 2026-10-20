import dataclasses
from pathlib import Path

import pytest

from app.providers.base import CoreRequirement, FitAssessment, RedFlag, SubScore
from app.services.fit import (
    ScoringConfig,
    build_record,
    cache_key,
    cap_reason,
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


def assessment(flags: list[RedFlag] | None = None, core: list[CoreRequirement] | None = None,
               **scores: int) -> FitAssessment:
    base = {"role_match": 9, "skills_match": 8, "seniority_fit": 8,
            "location_eligibility": 5, "language_requirements": 5}
    base.update(scores)
    subs = {d: SubScore(score=s, reason=f"{d} reason", evidence="build pipelines with Spark and dbt")
            for d, s in base.items()}
    return FitAssessment(**subs, red_flags=flags or [], core_requirements=core or [],
                         strengths=["Spark"], gaps=[], summary="ok")


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
    assert experience_version([{"id": 1, "kind": "job"}], {}) != \
        experience_version([{"id": 2, "kind": "job"}], {})


def test_truncate_keeps_head_and_tail() -> None:
    text = "HEAD " + "x" * 10_000 + " TAIL"
    out = truncate_description(text, 1000)
    assert out.startswith("HEAD") and out.endswith("TAIL") and len(out) < 1100


LISTING_C1 = (Path(__file__).parent / "fixtures" / "listings" / "ai_engineer_de_c1.md").read_text()
C1_LINE = "Sehr gute Deutschkenntnisse (C1) in Wort und Schrift"


def test_a_real_6900_char_listing_goes_in_whole_and_keeps_the_c1_requirement() -> None:
    """#765: the C1 line sits at character 4,410 and used to be cut by the 6,000 limit."""
    assert len(LISTING_C1) > 6000 and LISTING_C1.index(C1_LINE) > 4200
    out = truncate_description(LISTING_C1)
    assert out == LISTING_C1 and C1_LINE in out


def test_over_the_limit_boilerplate_sections_go_first_and_requirements_stay() -> None:
    out = truncate_description(LISTING_C1, 5500)
    assert len(out) <= 5500
    assert C1_LINE in out and "## Dein Profil" in out and "## Deine Aufgaben" in out
    assert "[section omitted: Einige unserer Benefits]" in out and "LunchIt" not in out
    assert "Level: Senior" in out  # the small 'what we offer' block is kept: it stops as soon as it fits
    assert "Mehrjährige Erfahrung" in out  # the profile section is whole


def test_a_padded_listing_over_15000_drops_benefit_sections_not_the_middle() -> None:
    padding = "".join(f"\n## Benefits {i}\n" + "Free snacks and a rooftop terrace. " * 40
                      for i in range(8))
    padding += "\n## Equal opportunity\n" + "We welcome everyone. " * 60
    text = LISTING_C1 + padding
    assert len(text) > 15000
    out = truncate_description(text)
    assert len(out) <= 15000 and C1_LINE in out and "## Dein Profil" in out
    assert "[section omitted: Equal opportunity]" in out and "[section omitted: Benefits 7]" in out
    assert "[…]" not in out  # no head/tail cut was needed


def test_a_section_that_is_both_perk_like_and_a_requirement_is_never_dropped() -> None:
    text = ("## Your role\n" + "Build things. " * 400 + "\n## Why you will love our tech stack\n" + "Go and Rust. " * 600
            + "\n## Benefits\n" + "Snacks. " * 600)
    out = truncate_description(text, 9000)
    assert "Go and Rust." in out and "[section omitted: Benefits]" in out


def test_the_head_tail_cut_is_only_a_last_resort() -> None:
    text = "## Requirements\n" + "must know Go. " * 3000
    out = truncate_description(text, 5000)
    assert "[…]" in out and len(out) < 5100 and "[section omitted" not in out


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


@pytest.mark.parametrize(
    ("flag_type", "quote", "severity"),
    [
        # quotes that capped good jobs in the model benchmark: they mention a place, a mode or perks
        ("must_be_based_in", "we work together onsite 5 days a week.", "soft"),
        ("must_be_based_in", "Paris", "soft"),
        ("must_be_based_in", "Wellness activities in our Paris office", "soft"),
        ("must_be_based_in", "A vibrant in-office culture in Munich", "soft"),
        ("must_be_based_in", "hybrid work model within Germany", "soft"),
        ("must_be_based_in",
         "A workplace in the heart of Vienna or remote options with quarterly office weeks in "
         "Vienna", "soft"),
        ("work_authorization_required", "Remote & Home-Office innerhalb Deutschlands", "soft"),
        ("language_required", "Wir suchen erfahrene AI Engineers", "soft"),
        ("language_required", "Die gesamte Stellenanzeige ist auf Deutsch verfasst.", "soft"),
        ("no_visa_sponsorship", "We offer visa sponsorship and relocation support", "soft"),
        # explicit requirements stay hard
        ("must_be_based_in", "Candidates must be located in Germany", "hard"),
        ("must_be_based_in", "Du bist bereits wohnhaft in Deutschland", "hard"),
        ("must_be_based_in", "Remote, but you must reside in the EU", "hard"),
        ("must_be_based_in", "Remote - US based candidates only", "hard"),
        ("work_authorization_required", "You must have the right to work in the UK", "hard"),
        ("work_authorization_required", "Gültige Arbeitserlaubnis für Deutschland erforderlich",
         "hard"),
        ("no_visa_sponsorship", "We do not offer visa sponsorship", "hard"),
        ("no_visa_sponsorship", "Unfortunately we cannot sponsor work permits", "hard"),
        ("nationality_restricted", "Open to UAE nationals only", "hard"),
        ("nationality_restricted", "Emiratisation role", "hard"),
        ("nationality_restricted", "Riyadh, Saudi Arabia", "soft"),
        ("language_required", "Fließende Deutschkenntnisse in Wort und Schrift", "hard"),
        ("language_required", "Fluent German is required", "hard"),
    ],
)
def test_hard_flag_needs_a_quote_that_states_the_requirement(
    flag_type: str, quote: str, severity: str
) -> None:
    config = ScoringConfig.from_settings({}, PROFILE)
    assert flag_severity(flag_type, True, config, f"Requires something: {quote}", quote) == severity


SPARK = "build pipelines with Spark and dbt"  # a quote that is in TEXT


def core(name: str = "Kafka", quote: str = SPARK, missing: bool = True) -> CoreRequirement:
    return CoreRequirement(requirement=name, evidence=quote, missing=missing)


def record_for(cores: list[CoreRequirement], config=CONFIG, flags=None, experience: str = ""):
    return build_record(assessment(flags, cores), job_text=TEXT, description_level="full",
                        remote_type="onsite", config=config, experience_text=experience)


def test_a_verified_missing_core_requirement_caps_the_score_at_60() -> None:
    assert record_for([])["score"] == 76  # uncapped: 9,8,8,5,5
    rec = record_for([core()])
    assert rec["score"] == 60 and rec["core_requirements"][0]["counts"] is True
    assert cap_reason(rec["red_flags"], rec["core_requirements"]) == "missing_core"


def test_a_core_requirement_that_is_covered_or_unsupported_does_not_cap() -> None:
    partly = record_for([core(missing=False)])
    assert partly["score"] == 76 and partly["core_requirements"][0]["counts"] is False
    unsupported = record_for([core(quote="five years of Kafka at scale")])
    assert unsupported["score"] == 76
    assert "isn't in the listing" in unsupported["core_requirements"][0]["note"]
    named = record_for([core("Kafka")], experience="- [skill] Streaming\n  Skills: Kafka, Flink")
    assert named["score"] == 76 and "names it" in named["core_requirements"][0]["note"]
    assert record_for([core(quote="")])["score"] == 76  # no quote, no cap


def test_the_missing_core_cap_is_configurable_and_the_lower_cap_wins() -> None:
    low = dataclasses.replace(CONFIG, missing_core_cap=50)
    assert record_for([core()], low)["score"] == 50
    assert record_for([core()], dataclasses.replace(CONFIG, missing_core_cap=100))["score"] == 76
    assert ScoringConfig.from_settings({"missing_core_cap": 55}, PROFILE).missing_core_cap == 55
    assert ScoringConfig.from_settings({}, PROFILE).missing_core_cap == 60  # default, older settings
    hard = RedFlag(type="no_visa_sponsorship", text="no sponsorship",
                   evidence="we do not offer visa sponsorship")
    rec = record_for([core()], flags=[hard])
    assert rec["score"] == 35 and cap_reason(rec["red_flags"], rec["core_requirements"]) == "hard_flag"


def test_recompute_reapplies_the_missing_core_cap_from_stored_rows() -> None:
    rec = record_for([core()])
    assert recompute(rec["sub_scores"], rec["red_flags"], CONFIG, rec["core_requirements"])[0] == 60
    low = dataclasses.replace(CONFIG, missing_core_cap=45)
    assert recompute(rec["sub_scores"], rec["red_flags"], low, rec["core_requirements"])[0] == 45
    assert recompute(rec["sub_scores"], rec["red_flags"], CONFIG, [])[0] == 76  # older rows


def test_german_compounds_name_a_language_but_deutschland_does_not() -> None:
    from app.services.fit import languages_mentioned

    assert languages_mentioned("Sehr gute Deutschkenntnisse (C1) in Wort und Schrift") == {"german"}
    assert languages_mentioned("mit unseren deutschsprachigen Kunden") == {"german"}
    assert languages_mentioned("Gute Englischkenntnisse") == {"english"}
    assert languages_mentioned("Büro in Deutschland, Remote innerhalb Deutschlands") == set()
    config = ScoringConfig.from_settings({}, PROFILE)
    quote = "Sehr gute Deutschkenntnisse (C1) in Wort und Schrift"
    assert flag_severity("language_required", True, config, quote, quote) == "hard"


def test_downgraded_flag_is_noted_and_recompute_applies_the_same_rule(caplog) -> None:
    flag = RedFlag(type="must_be_based_in", text="Requires living in a specific place: Paris",
                   evidence="Wellness activities in our Paris office")
    text = "Wellness activities in our Paris office. Data Engineer."
    config = ScoringConfig.from_settings({}, PROFILE)
    import logging

    logging.getLogger("app.services.fit").disabled = False  # the test migration's fileConfig
    with caplog.at_level("INFO", logger="app.services.fit"):
        record = build_record(assessment([flag]), job_text=text, description_level="full",
                              remote_type="onsite", config=config)
    stored = record["red_flags"][0]
    assert stored["severity"] == "soft"
    assert "doesn't state the requirement" in stored["severity_note"]
    assert any("downgraded to soft" in m for m in caplog.messages)
    # an older stored flag: the description says "living in", the quote alone does not
    old = {"type": "must_be_based_in", "text": "Requires living in a specific place: Paris",
           "evidence": "Paris", "evidence_verified": True, "severity": "hard"}
    score, flags = recompute({"role_match": {"score": 10}, "skills_match": {"score": 10},
                              "seniority_fit": {"score": 10}, "location_eligibility": {"score": 10},
                              "language_requirements": {"score": 10}}, [old], config)
    assert score == 100 and flags[0]["severity"] == "soft" and flags[0]["severity_note"]


def test_cv_header_fields_do_not_make_scores_stale() -> None:
    items = [{"kind": "job", "title": "Dev"}]
    base = {"based_in": "City", "languages": [], "full_name": "A"}
    v = experience_version(items, base)
    assert experience_version(items, {**base, "full_name": "B", "phone": "1", "links": [{}],
                                      "email": "x@y.z"}) == v
    assert experience_version(items, {**base, "based_in": "Other city"}) != v


def test_only_structural_experience_changes_make_scores_stale() -> None:
    from app.services.fit import experience_version

    role = {"id": 1, "kind": "job", "title": "Mobile Developer", "bullets": ["Built x by 30%"],
            "tags": ["flutter"], "start": "2022-10-01", "end": "2025-02-28"}
    skill = {"id": 2, "kind": "skill", "title": "Mobile", "bullets": [], "tags": ["dart"]}
    tracks = [{"name": "Mobile", "years_experience": 3, "roles": [{"title": "Flutter Developer"}]}]
    base = experience_version([role, skill], {}, tracks)
    reworded = {**role, "title": "Mobile Developer (Flutter)", "bullets": ["Built x, easier"],
                "tags": ["flutter", "dart"]}
    assert experience_version([reworded, skill], {}, tracks) == base  # rewording, typos, tags
    assert experience_version([role], {}, tracks) != base  # removed an item
    assert experience_version([role, skill, {"id": 3, "kind": "project"}], {}, tracks) != base
    assert experience_version([role, {**skill, "tags": ["dart", "kotlin"]}], {}, tracks) != base
    assert experience_version([{**role, "end": None}, skill], {}, tracks) != base  # dates/years
    assert experience_version([role, skill], {}, [{**tracks[0], "years_experience": 4}]) != base
    assert experience_version([role, skill], {"full_name": "X"}, tracks) == base  # header only
