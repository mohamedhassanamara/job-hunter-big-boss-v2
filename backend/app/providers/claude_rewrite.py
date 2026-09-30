"""Rewrite a Copilot answer you'll send to people with Claude (Claude Code headless, the CV
generator's isolation and subscription check). One text at a time."""

from pydantic import BaseModel, Field

from app.providers.base import CVGenerationFailed
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator


class RewriteOut(BaseModel):
    text: str = Field(description="The rewritten text, ready to copy and send")


class ClaudeRewriter(ClaudeCVGenerator):
    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)

    def rewrite(self, system: str, message: str) -> str:
        try:
            return self._call(self.command(system, RewriteOut), message, RewriteOut).text
        except CVGenerationFailed as exc:
            raise RuntimeError(str(exc).replace("plan", "rewrite")) from exc


class MockRewriter:
    model = "mock-rewriter"

    def rewrite(self, system: str, message: str) -> str:
        original = message.split("ORIGINAL\n", 1)[1].split("\n\nCONTEXT", 1)[0]
        return f"(rewritten) {original.strip()}"
