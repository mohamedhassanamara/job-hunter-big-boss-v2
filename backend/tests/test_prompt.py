from app.services.prompt import PROMPTS_DIR, load_prompt, registered_hashes


def test_every_prompt_change_bumps_the_version() -> None:
    """Editing a prompt without bumping `version` would silently mix results in the cache and in
    eval reports. If this fails: bump `version:` in the prompt file and register the new hash."""
    registry = registered_hashes()
    for path in PROMPTS_DIR.glob("*.md"):
        prompt = load_prompt(path.stem)
        known = registry.get(prompt.name, {})
        assert str(prompt.version) in known, (
            f"{path.name} v{prompt.version} is not registered in prompts/versions.json "
            f'(add "{prompt.version}": "{prompt.body_hash}")'
        )
        assert known[str(prompt.version)] == prompt.body_hash, (
            f"{path.name} changed without a version bump: bump `version:` to "
            f"{max(map(int, known)) + 1} and register hash {prompt.body_hash}"
        )


def test_fit_prompt_renders_all_placeholders() -> None:
    prompt = load_prompt("fit_score")
    values = {name: f"<{name}>" for name in prompt.user.get_identifiers()}
    text = prompt.render(**values)
    assert "$" not in text.replace("$ ", "")
    assert prompt.version_id == f"fit_score/v{prompt.version}"


def test_v3_render_carries_the_matched_track(seeded: None) -> None:
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Company, Job
    from app.services.scoring import load_context, render

    with Session(engine) as s:
        ctx = load_context(s)
        job = s.exec(select(Job)).first()
        job.matched_track, job.matched_role = "Mobile", "Flutter Developer"
        system, user = render(job, s.get(Company, job.company_id), ctx)
    assert "Track: Mobile" in user and "Flutter Developer" in user
    assert "Years in this track: 2.5" in user
    assert "flag_checks" in system and "Data Engineering" not in system


def test_schema_requires_every_flag_check() -> None:
    from app.providers.base import FitAssessment
    from app.providers.ollama import inline_schema

    schema = inline_schema(FitAssessment)
    assert "flag_checks" in schema["required"]
    checks = schema["properties"]["flag_checks"]
    assert set(checks["required"]) >= {"no_visa_sponsorship", "nationality_restricted",
                                       "language_required"}
    assert "core_requirements" in schema["required"]  # prompt v5
    item = schema["properties"]["core_requirements"]["items"]
    assert set(item["required"]) == {"requirement", "evidence", "missing"}


def test_v5_asks_for_core_requirements_any_integer_and_explicit_language_levels() -> None:
    prompt = load_prompt("fit_score")
    assert prompt.version == 5
    for needle in ("core_requirements:", "caps the score in code", "ANY integer from 0 to 10",
                   "A stated level counts as stating the requirement",
                   "sehr gute Deutschkenntnisse"):
        assert needle in prompt.system


def test_flag_checks_become_verified_flags() -> None:
    from app.providers.base import FitAssessment, FlagCheck, FlagChecks, SubScore
    from app.services.fit import ScoringConfig, build_record

    sub = SubScore(score=8, reason="r", evidence="")
    text = ("Data role in Dubai. This position is open to UAE nationals only. "
            "Fluent German required.")
    assessment = FitAssessment(
        role_match=sub, skills_match=sub, seniority_fit=sub, location_eligibility=sub,
        language_requirements=sub, summary="s",
        flag_checks=FlagChecks(
            nationality_restricted=FlagCheck(present=True, evidence="open to UAE nationals only"),
            language_required=FlagCheck(present=True, evidence="Fluent German required"),
            no_visa_sponsorship=FlagCheck(present=True, evidence="we never sponsor anyone"),
        ),
    )
    config = ScoringConfig.from_settings({}, {"languages": [
        {"language": "English", "level": "Full professional"}]})
    record = build_record(assessment, job_text=text, description_level="full",
                          remote_type="onsite", config=config)
    by_type = {f["type"]: f for f in record["red_flags"]}
    assert by_type["nationality_restricted"]["severity"] == "hard"
    assert by_type["language_required"]["severity"] == "hard"
    assert by_type["no_visa_sponsorship"]["severity"] == "soft"  # quote not in the listing
    assert record["score"] <= 35


def test_the_longest_scoring_prompt_fits_the_ollama_context() -> None:
    """15,000 chars of listing + a large experience pool + the system prompt and the schema
    instruction, at a pessimistic 3 characters per token, plus room for the answer."""
    from app.providers.ollama import OllamaFitScorer

    prompt = load_prompt("fit_score")
    # schema text, candidate header, a large experience pool, 15,000 chars of listing
    chars = len(prompt.system) + 2500 + 1500 + 14_000 + 15_000
    assert chars / 3 + 1500 < OllamaFitScorer().num_ctx
