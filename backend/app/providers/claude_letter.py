"""Cover letters and application answers on Claude Code headless mode, with the same isolation
and subscription check as the CV generator (it reuses that call path). One job at a time."""

import json
import re
from pathlib import Path

from app.providers.base import (
    AnswersPlan,
    AnswersRequest,
    CoverLetterPlan,
    CVGenerationFailed,
    DraftFailed,
    LetterRequest,
)
from app.providers.claude_cv import TIMEOUT, ClaudeCVGenerator

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "cover_letter.md"


def load_prompts() -> tuple[str, dict[str, str]]:
    """(version id, {section: text}) from app/prompts/cover_letter.md."""
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    sections = dict(re.findall(r"^## (\w+)\n(.*?)(?=^## \w+\n|\Z)", text, re.M | re.S))
    return (f"cover_letter/v{version.group(1) if version else '0'}",
            {k: v.strip() for k, v in sections.items()})


def _message(feedback: str, sections: list[tuple[str, object]]) -> str:
    head = f"REJECTED PROBLEMS\n{feedback}\n\n" if feedback else ""
    return head + "\n\n".join(f"{name}\n{json.dumps(value, ensure_ascii=False, indent=1)}"
                              for name, value in sections)


def letter_message(request: LetterRequest, feedback: str = "") -> str:
    return _message(feedback, [("RULES", request.rules), ("FACTS", request.candidate),
                               ("JOB", request.job), ("EXPERIENCE POOL", request.pool)])


def answers_message(request: AnswersRequest, feedback: str = "") -> str:
    return _message(feedback, [("RULES", request.rules), ("FACTS", request.candidate),
                               ("QUESTIONS", request.questions), ("JOB", request.job),
                               ("EXPERIENCE POOL", request.pool)])


class ClaudeLetterDrafter(ClaudeCVGenerator):
    def __init__(self, model: str = "claude-sonnet-5", *, timeout: int = TIMEOUT, **kw):  # noqa: ANN003
        super().__init__(model, timeout=timeout, **kw)
        self.prompt_version, self.sections = load_prompts()

    def _run(self, system: str, message: str, schema: type):  # noqa: ANN202
        try:
            return self._call(self.command(system, schema), message, schema)
        except CVGenerationFailed as exc:  # same call path; don't say "plan" to the user
            raise DraftFailed(str(exc).replace("plan", "answer")) from exc

    def draft_letter(self, request: LetterRequest, feedback: str = "") -> CoverLetterPlan:
        system = self.sections["system"] + (f"\n\n{self.sections['retry']}" if feedback else "")
        return self._run(system, letter_message(request, feedback), CoverLetterPlan)

    def answer(self, request: AnswersRequest, feedback: str = "") -> AnswersPlan:
        system = self.sections["answers"] + (
            f"\n\n{self.sections['answers_retry']}" if feedback else "")
        return self._run(system, answers_message(request, feedback), AnswersPlan)
