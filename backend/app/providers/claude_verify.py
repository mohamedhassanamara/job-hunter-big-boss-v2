"""The claim verifier on Claude Code headless mode (`claude -p`): the same isolation and
subscription check as the CV generator (never an API key). A separate call from the one that
wrote the text: it gets only the final text and its sources, never the drafting prompt."""

import re
from pathlib import Path
from typing import Any

from app.providers.base import CVGenerationFailed, DraftFailed, VerifyPlan
from app.providers.claude_cv import ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "verify.md"
VERIFY_TIMEOUT = 300  # long letters with many claims take a while on the strongest model


def load_prompt() -> tuple[str, str]:
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    return f"verify/v{version.group(1) if version else '0'}", \
        text.split("## system", 1)[1].strip()


def message(request: dict[str, Any]) -> str:
    """TEXT first, then each source as its own labelled block (ids the verdicts cite)."""
    blocks = [f"KIND: {request['kind']}", f"TEXT\n{request['text']}"]
    for source_id, body in request["sources"].items():
        blocks.append(f"SOURCE {source_id}\n{body}")
    return "\n\n".join(blocks)


class ClaudeVerifier(ClaudeCVGenerator):
    via = "claude -p"

    def __init__(self, model: str = "claude-opus-5-5", *, timeout: int = VERIFY_TIMEOUT,
                 **kw: Any):
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, self.system = load_prompt()

    def verify(self, request: dict[str, Any]) -> VerifyPlan:
        try:
            return self._call(self.command(self.system, VerifyPlan), message(request),
                              VerifyPlan)
        except CVGenerationFailed as exc:
            raise DraftFailed(str(exc).replace("plan", "verification")) from exc
