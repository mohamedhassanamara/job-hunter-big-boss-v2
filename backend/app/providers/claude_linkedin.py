"""LinkedIn connection notes and follow-ups on Claude Code headless mode: the same isolation and
subscription check as the CV and email (it reuses that call path). One person at a time."""

import json
import re
from pathlib import Path

from app.providers.base import CVGenerationFailed, DraftFailed, LinkedInMessage, LinkedInRequest
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "linkedin.md"


def load_prompts() -> tuple[str, dict[str, str]]:
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## \w+\n|\Z)", text, re.M | re.S))
    return f"linkedin/v{version.group(1) if version else '0'}", {
        k: v.strip() for k, v in sections.items()}


def user_message(request: LinkedInRequest, feedback: str = "") -> str:
    return (
        (f"REJECTED DRAFT PROBLEMS\n{feedback}\n\n" if feedback else "")
        + "RULES\n" + json.dumps({k: v for k, v in request.rules.items() if k != "revision"},
                                  ensure_ascii=False)
        + "\n\nPERSON\n" + json.dumps(request.person, ensure_ascii=False)
        + "\n\nFACTS\n" + json.dumps(request.candidate, ensure_ascii=False)
        + "\n\nJOB\n" + json.dumps(request.job, ensure_ascii=False, indent=1)
        + "\n\nEXPERIENCE POOL\n" + json.dumps(request.pool, ensure_ascii=False, indent=1)
        + revision_block(request)
    )


def revision_block(request: LinkedInRequest) -> str:
    """PREVIOUS MESSAGE + the user's feedback (a regeneration with feedback), else nothing."""
    rev = (request.rules or {}).get("revision")
    if not rev:
        return ""
    return ("\n\nPREVIOUS MESSAGE (edit this)\n"
            + (f"Subject: {rev['previous_subject']}\n\n" if rev.get("previous_subject") else "")
            + str(rev.get("previous_text", ""))
            + "\n\nWHAT THE USER WANTS CHANGED\n" + str(rev.get("feedback", "")))


class ClaudeLinkedInDrafter(ClaudeCVGenerator):
    via = "claude -p"

    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, self.sections = load_prompts()

    def draft(self, request: LinkedInRequest, feedback: str = "") -> LinkedInMessage:
        system = "\n\n".join(x for x in (
            self.sections["system"], self.sections[request.kind],
            self.sections["revise"] if (request.rules or {}).get("revision") else "",
            self.sections["retry"] if feedback else "") if x)
        try:
            return self._call(self.command(system, LinkedInMessage),
                              user_message(request, feedback), LinkedInMessage)
        except CVGenerationFailed as exc:
            raise DraftFailed(str(exc).replace("plan", "message")) from exc
