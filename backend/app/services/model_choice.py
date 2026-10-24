"""Which model writes the CV and the email: Settings → Models (`models.cv`, `models.email`).

`{provider: "gemini" | "anthropic", model, thinking_level}`. The default is Gemini
(gemini-3.5-flash-lite, thinking minimal). A call can override it once with `use="claude"`
("Generate with Claude" after a failure): the setting never changes and nothing falls back on
its own.

While Gemini is paused (`services/gemini_keys.is_paused`: the key was refused, or the switch in
Settings → Models) a Gemini choice resolves to Claude Code (subscription) instead.
"""

from typing import Any

from sqlmodel import Session, select

from app.models import AppSetting

DEFAULT_GEMINI = "gemini-3.5-flash-lite"
DEFAULT_CLAUDE = "claude-sonnet-5"
DEFAULT_THINKING = "minimal"
TASKS = ("cv", "email")
USES = (None, "claude")


def choice(s: Session, task: str, use: str | None = None) -> dict[str, Any]:
    """{provider, model, thinking_level} for a task, honouring a one-shot `use="claude"`."""
    row = s.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    cfg = dict(((row.value if row else {}) or {}).get(task) or {})
    model = str(cfg.get("model") or DEFAULT_GEMINI)
    if model.startswith("claude-haiku"):
        model = DEFAULT_CLAUDE
    if use == "claude":
        claude = model if model.startswith("claude-") else DEFAULT_CLAUDE
        return {"provider": "anthropic", "model": claude, "thinking_level": None}
    if model.startswith("gemini-"):
        from app.services.gemini_keys import is_paused

        if is_paused(s):  # Google refused the key, or you flipped the switch: Claude writes
            return {"provider": "anthropic", "model": DEFAULT_CLAUDE, "thinking_level": None}
        return {"provider": "gemini", "model": model,
                "thinking_level": cfg.get("thinking_level") or DEFAULT_THINKING}
    return {"provider": "anthropic", "model": model, "thinking_level": None}


def claude_model(s: Session, key: str) -> str:
    """The Claude model for a step that only ever runs through `claude -p` (`models.<key>`:
    letter, interview, rewrite). Never reads the CV or email setting; a non-Claude value
    (e.g. a Gemini id) is ignored."""
    row = s.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    model = str(((((row.value if row else {}) or {}).get(key)) or {}).get("model") or "")
    return model if model.startswith("claude-") and not model.startswith("claude-haiku") \
        else DEFAULT_CLAUDE


def check(value: dict[str, Any]) -> None:
    """Validation for `PUT /settings/models` (cv / email entries). Raises ValueError."""
    from app.providers.gemini_generate import THINKING_LEVELS

    letter = ((value or {}).get("letter") or {}).get("model")
    if letter and not str(letter).startswith("claude-"):
        raise ValueError("models.letter.model must be a claude-* model (it runs through claude -p)")
    for task in TASKS:
        cfg = (value or {}).get(task)
        if cfg is None:
            continue
        model = str(cfg.get("model") or "")
        if not model.startswith(("gemini-", "claude-")):
            raise ValueError(f"models.{task}.model must be a gemini-* or claude-* model")
        level = cfg.get("thinking_level")
        if level is not None and level not in THINKING_LEVELS:
            raise ValueError(f"models.{task}.thinking_level must be one of "
                             f"{', '.join(THINKING_LEVELS)}")
