"""Which model writes the CV and the email: Settings → Models (`models.cv`, `models.email`).

`{provider: "gemini" | "anthropic", model, thinking_level}`. The default is Gemini
(gemini-3.5-flash-lite, thinking minimal). A call can override it once with `use="claude"`
("Generate with Claude" after a failure): the setting never changes and nothing falls back on
its own.
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
        return {"provider": "gemini", "model": model,
                "thinking_level": cfg.get("thinking_level") or DEFAULT_THINKING}
    return {"provider": "anthropic", "model": model, "thinking_level": None}


def check(value: dict[str, Any]) -> None:
    """Validation for `PUT /settings/models` (cv / email entries). Raises ValueError."""
    from app.providers.gemini_generate import THINKING_LEVELS

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
