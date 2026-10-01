"""Critique on Claude Code headless mode (the same isolation and subscription check as the CV):
one call per click, a list of weak points, never a rewrite."""

import json
import re
from pathlib import Path
from typing import Any

from app.providers.base import CritiquePlan, CVGenerationFailed, DraftFailed
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "critique.md"


def load_prompt() -> tuple[str, str]:
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    return f"critique/v{version.group(1) if version else '0'}", \
        text.split("## system", 1)[1].strip()


class ClaudeCritic(ClaudeCVGenerator):
    via = "claude -p"

    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, self.system = load_prompt()

    def critique(self, request: dict[str, Any]) -> CritiquePlan:
        message = "\n\n".join(f"{k.upper()}\n{v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1)}"  # noqa: E501
                              for k, v in request.items())
        try:
            return self._call(self.command(self.system, CritiquePlan), message, CritiquePlan)
        except CVGenerationFailed as exc:
            raise DraftFailed(str(exc).replace("plan", "critique")) from exc
