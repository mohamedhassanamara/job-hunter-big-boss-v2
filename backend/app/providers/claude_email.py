"""Cold-email drafter on Claude Code headless mode, with the same isolation and subscription check
as the CV generator (it reuses that call path). One job at a time; never in bulk."""

import json
import re
from pathlib import Path

from app.providers.base import (
    CVGenerationFailed,
    DraftFailed,
    EmailDraftPlan,
    EmailRequest,
    IntroEmailPlan,
)
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "outreach.md"


def load_prompts() -> tuple[str, str, str]:
    """(version id, system prompt, retry instructions) from app/prompts/outreach.md."""
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## \w+\n|\Z)", text, re.M | re.S))
    return (f"outreach/v{version.group(1) if version else '0'}", sections["system"].strip(),
            sections["retry"].strip())


def user_message(request: EmailRequest, feedback: str = "") -> str:
    signals = (request.rules or {}).get("signals")
    return (
        (f"REJECTED DRAFT PROBLEMS\n{feedback}\n\n" if feedback else "")
        + "RULES\n" + json.dumps({k: v for k, v in request.rules.items() if k != "signals"},
                                  ensure_ascii=False)
        + "\n\nFACTS\n" + json.dumps(request.candidate, ensure_ascii=False)
        + "\n\nCONTACT\n" + json.dumps(request.contact, ensure_ascii=False)
        + ("\n\nSIGNALS\n" + json.dumps(signals, ensure_ascii=False, indent=1)
           if signals is not None else "")
        + "\n\nJOB (private: use it to decide what to talk about, never mention it)\n"
        + json.dumps(request.job, ensure_ascii=False, indent=1)
        + "\n\nEXPERIENCE POOL\n" + json.dumps(request.pool, ensure_ascii=False, indent=1)
    )


class ClaudeEmailDrafter(ClaudeCVGenerator):
    via = "claude -p"  # Claude Code headless on your subscription (never Ollama)
    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, self.email_prompt, self.retry_prompt = load_prompts()

    def draft_intro(self, request: EmailRequest, feedback: str = "") -> IntroEmailPlan:
        """The personal introduction (prompt v4+): hook from signals, value, direct ask."""
        system = self.email_prompt + (f"\n\n{self.retry_prompt}" if feedback else "")
        try:
            return self._call(self.command(system, IntroEmailPlan),
                              user_message(request, feedback), IntroEmailPlan)
        except CVGenerationFailed as exc:
            raise DraftFailed(str(exc).replace("plan", "draft")) from exc

    def draft(self, request: EmailRequest, feedback: str = "") -> EmailDraftPlan:
        system = self.email_prompt + (f"\n\n{self.retry_prompt}" if feedback else "")
        try:
            return self._call(self.command(system, EmailDraftPlan),
                              user_message(request, feedback), EmailDraftPlan)
        except CVGenerationFailed as exc:  # same call path; say "email" to the user
            raise DraftFailed(str(exc).replace("plan", "draft")) from exc
