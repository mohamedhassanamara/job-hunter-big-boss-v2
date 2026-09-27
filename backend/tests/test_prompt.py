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
