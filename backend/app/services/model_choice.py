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
from app.providers.apinex_models import DRAFT_MODEL, is_apinex

DEFAULT_GEMINI = "gemini-3.5-flash-lite"
DEFAULT_APINEX = "free/minimax-m3.1-flash"
DEFAULT_CLAUDE = "claude-sonnet-5"
DEFAULT_THINKING = "minimal"
TASKS = ("cv", "email", "linkedin")
CLAUDE_ONLY = ("interview", "rewrite", "confirm", "verifier")
USES = (None, "claude", "gemini")


def choice(s: Session, task: str, use: str | None = None) -> dict[str, Any]:
    """{provider, model, thinking_level} for a task, honouring a one-shot `use="claude"`."""
    row = s.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    cfg = dict(((row.value if row else {}) or {}).get(task) or {})
    default_model = DEFAULT_APINEX if task == "cv" else DRAFT_MODEL
    model = str(cfg.get("model") or default_model)
    if model.startswith("claude-haiku"):
        model = DEFAULT_CLAUDE
    if use == "gemini":  # "Generate with Gemini" after an APInex failure: this call only
        from app.services.gemini_keys import is_paused

        if is_paused(s):
            raise ValueError("Gemini is paused (Settings → Models): resume it first")
        return {"provider": "gemini", "model": DEFAULT_GEMINI, "thinking_level": DEFAULT_THINKING}
    if use == "claude":
        claude = model if model.startswith("claude-") else DEFAULT_CLAUDE
        return {"provider": "anthropic", "model": claude, "thinking_level": None}
    if is_apinex(model):
        return {"provider": "apinex", "model": model, "thinking_level": None}
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


def reviewer_model(s: Session) -> str:
    """The constructive reviewer (`models.reviewer`): a Google `gemini-*` id (never APInex)."""
    row = s.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    model = str(((((row.value if row else {}) or {}).get("reviewer")) or {}).get("model") or "")
    return model if model.startswith("gemini-") and not is_apinex(model) else DEFAULT_GEMINI


def letter_model(s: Session) -> str:
    """The model for cover letters, form text and application answers (`models.letter`): APInex
    by default, or a claude-* id (then it runs through `claude -p`)."""
    row = s.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    model = str(((((row.value if row else {}) or {}).get("letter")) or {}).get("model") or "")
    if is_apinex(model) or (model.startswith("claude-") and not model.startswith("claude-haiku")):
        return model
    return DEFAULT_APINEX


def check(value: dict[str, Any]) -> None:
    """Validation for `PUT /settings/models`. Raises ValueError."""
    from app.providers.gemini_generate import THINKING_LEVELS

    scoring_cfg = (value or {}).get("scoring")
    if scoring_cfg:
        scoring_model = str(scoring_cfg.get("model") or "")
        if scoring_model.startswith("gemini-"):
            raise ValueError("Gemini is deprecated for scoring")

    # Everything that runs through `claude -p` takes a claude-* model, never an APInex or Gemini id.
    for key in CLAUDE_ONLY:
        model = str((((value or {}).get(key)) or {}).get("model") or "")
        if model and not model.startswith("claude-"):
            raise ValueError(f"models.{key}.model must be a claude-* model (it runs through "
                             "claude -p)" + (" — APInex is for scoring and the CV only"
                                              if is_apinex(model) else ""))
    reviewer = str((((value or {}).get("reviewer")) or {}).get("model") or "")
    if reviewer and (is_apinex(reviewer) or not reviewer.startswith("gemini-")):
        raise ValueError("models.reviewer.model must be a Google gemini-* model")
    letter = str((((value or {}).get("letter")) or {}).get("model") or "")
    if letter and not (is_apinex(letter) or letter.startswith("claude-")):
        raise ValueError("models.letter.model must be an APInex (free/*) or claude-* model")
    for task in TASKS:
        cfg = (value or {}).get(task)
        if cfg is None:
            continue
        model = str(cfg.get("model") or "")
        if is_apinex(model):
            continue
        if not model.startswith(("gemini-", "claude-")):
            raise ValueError(f"models.{task}.model must be a gemini-*, claude-* or APInex "
                             "(free/*) model")
        level = cfg.get("thinking_level")
        if level is not None and level not in THINKING_LEVELS:
            raise ValueError(f"models.{task}.thinking_level must be one of "
                             f"{', '.join(THINKING_LEVELS)}")
