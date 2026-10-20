"""Ask Claude: a second opinion on one job on Claude Code headless mode (`claude -p`).

Same isolation and subscription check as the CV generator (no tools, no settings, empty temp
directory, never an API key: an `apiKeySource` other than "none" stops before anything is billed).
The prompt is the scoring prompt (so the score is comparable with the main one) plus a short
verdict addendum; the answer is the scoring schema plus `verdict`.
"""

import json
from typing import Any

from app.providers.base import ConfirmationAnswer
from app.providers.claude_cv import ClaudeCVGenerator
from app.providers.ollama import inline_schema

DEFAULT_MODEL = "claude-sonnet-5-5"
CONFIRM_TIMEOUT = 240


class ClaudeConfirmer(ClaudeCVGenerator):
    via = "claude -p"

    def __init__(self, model: str = DEFAULT_MODEL, *, timeout: int = CONFIRM_TIMEOUT,
                 **kw: Any):
        super().__init__(model, timeout=timeout, **kw)

    def command(self, system: str | None = None, schema: type = ConfirmationAnswer) -> list[str]:
        return [
            self.binary, "-p", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence",
            "--model", self.model, "--system-prompt", system or "",
            "--tools", "", "--setting-sources", "", "--strict-mcp-config",
            "--json-schema", json.dumps(inline_schema(ConfirmationAnswer)),
        ]

    def confirm(self, system: str, user: str) -> ConfirmationAnswer:
        return self._call(self.command(system), user, ConfirmationAnswer)
