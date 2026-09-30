"""Cold-email drafter on Claude Code headless mode, with the same isolation and subscription check
as the CV generator (it reuses that call path). One job at a time; never in bulk."""

import json
import re
from pathlib import Path

from app.providers.base import CVGenerationFailed, DraftFailed, EmailDraftPlan, EmailRequest
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "outreach.md"


def load_prompts() -> tuple[str, str, str]:
    """(version id, system prompt, retry instructions) from app/prompts/outreach.md."""
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    body = text.split("## system", 1)[1]
    system, _, retry = body.partition("## retry")
    return f"outreach/v{version.group(1) if version else '0'}", system.strip(), retry.strip()


def user_message(request: EmailRequest, feedback: str = "") -> str:
    return (
        (f"REJECTED DRAFT PROBLEMS\n{feedback}\n\n" if feedback else "")
        + "RULES\n" + json.dumps(request.rules, ensure_ascii=False)
        + "\n\nFACTS\n" + json.dumps(request.candidate, ensure_ascii=False)
        + "\n\nCONTACT\n" + json.dumps(request.contact, ensure_ascii=False)
        + "\n\nJOB\n" + json.dumps(request.job, ensure_ascii=False, indent=1)
        + "\n\nEXPERIENCE POOL\n" + json.dumps(request.pool, ensure_ascii=False, indent=1)
    )


class ClaudeEmailDrafter(ClaudeCVGenerator):
    via = "claude -p"  # Claude Code headless on your subscription (never Ollama)
    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, self.email_prompt, self.retry_prompt = load_prompts()

    def draft(self, request: EmailRequest, feedback: str = "") -> EmailDraftPlan:
        system = self.email_prompt + (f"\n\n{self.retry_prompt}" if feedback else "")
        try:
            return self._call(self.command(system, EmailDraftPlan),
                              user_message(request, feedback), EmailDraftPlan)
        except CVGenerationFailed as exc:  # same call path; say "email" to the user
            raise DraftFailed(str(exc).replace("plan", "draft")) from exc
