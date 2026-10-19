"""Interview preparation on Claude Code headless mode: the same isolation, subscription-only check
and call path as the CV and the cover letters. One job at a time."""

import json
import re
from pathlib import Path

from app.providers.base import (
    CVGenerationFailed,
    DraftFailed,
    InterviewPrepPlan,
    InterviewRequest,
)
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "interview_prep.md"


def load_prompts() -> tuple[str, dict[str, str]]:
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## \w+\n|\Z)", text, re.M | re.S))
    return (f"interview_prep/v{version.group(1) if version else '0'}",
            {k: v.strip() for k, v in sections.items()})


def message(request: InterviewRequest, feedback: str = "") -> str:
    head = f"REJECTED PROBLEMS\n{feedback}\n\n" if feedback else ""
    parts = [("RULES", request.rules), ("FACTS", request.candidate), ("JOB", request.job),
             ("EXPERIENCE POOL", request.pool)]
    return head + "\n\n".join(f"{n}\n{json.dumps(v, ensure_ascii=False, indent=1)}"
                              for n, v in parts)


class ClaudeInterviewDrafter(ClaudeCVGenerator):
    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, self.sections = load_prompts()

    def prepare(self, request: InterviewRequest, feedback: str = "") -> InterviewPrepPlan:
        system = self.sections["system"] + (f"\n\n{self.sections['retry']}" if feedback else "")
        try:
            return self._call(self.command(system, InterviewPrepPlan),
                              message(request, feedback), InterviewPrepPlan)
        except CVGenerationFailed as exc:
            raise DraftFailed(str(exc).replace("plan", "preparation")) from exc
