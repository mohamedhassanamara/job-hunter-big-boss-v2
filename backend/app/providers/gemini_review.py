"""The constructive draft reviewer (`gemini-3.5-flash-lite` on your Google Gemini key).

It replaces the binary claim verifier for the approval flow: it never approves or rejects, it
returns feedback, suggestions and an informational `has_unverified_claims` flag. A model that
can't answer gives a `DraftReview` with an `error`, never an exception, so nothing blocks.
(Not on APInex: the gateway doesn't serve this model.)
"""

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "review.md"


class DraftReview(BaseModel):
    feedback: str = ""
    suggestions: str = ""
    revised_body: str = ""  # the whole message with the suggestions applied ("" = no change)
    has_unverified_claims: bool = False  # informational only: never blocks anything


def load_prompt() -> tuple[str, str]:
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    return f"review/v{version.group(1) if version else '0'}", \
        text.split("## system", 1)[1].strip()


def message(request: dict[str, Any]) -> str:
    blocks = [f"KIND: {request['kind']}", f"TEXT\n{request['text']}"]
    for source_id, body in request["sources"].items():
        blocks.append(f"SOURCE {source_id}\n{body}")
    return "\n\n".join(blocks)


class GeminiReviewer:
    """Google Gemini on your own key and quota (`gemini_generate.GeminiRunner`, single-key pool)."""

    via = "gemini api"

    def __init__(self, runner: Any):
        self.runner = runner
        self.model = runner.model
        self.prompt_version, self.system = load_prompt()

    def review(self, request: dict[str, Any]) -> tuple[DraftReview, str]:
        """(review, error): the error is "" when the model answered; nothing is ever raised."""
        try:
            out = self.runner.call(self.system, message(request), DraftReview, "review")
            return out, ""
        except Exception as exc:  # paused key, quota, refused request, bad answer: reported only
            return DraftReview(), str(exc)[:300]


class MockReviewer:
    """Sandbox and tests: no model call."""

    model = "mock-reviewer"
    prompt_version = "review/mock"
    via = "mock"

    def review(self, request: dict[str, Any]) -> tuple[DraftReview, str]:
        return DraftReview(
            feedback="Clear and short. Strength: it names the role. Improve: add one concrete "
                     "proof point from your experience.",
            suggestions="Open with the strongest relevant project in one sentence.",
            revised_body="", has_unverified_claims=False), ""
