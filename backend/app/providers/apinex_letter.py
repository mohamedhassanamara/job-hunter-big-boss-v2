"""Cover letters, form text and application answers on APInex (`free/minimax-m3.1-flash`).

Same prompts, schemas and checks as the Claude drafter (`ClaudeLetterDrafter`); only the call
seam is replaced: the schema goes in the prompt, the answer is validated, one retry when it
doesn't match. The text is checked afterwards in code (`letter_check`) and by the claim
verifier before anything is approved, exactly as for Claude.
"""

import time
from typing import Any

from pydantic import ValidationError

from app.providers.apinex_client import (
    DEFAULT_MODEL,
    APInexClient,
    _short_validation,
    json_instruction,
)
from app.providers.apinex_models import reject_non_apinex
from app.providers.base import QuotaExceeded
from app.providers.claude_letter import ClaudeLetterDrafter
from app.providers.gemini_generate import GenerationFailed


class APInexLetterDrafter(ClaudeLetterDrafter):
    via = "apinex"

    def __init__(self, model: str = DEFAULT_MODEL, client: APInexClient | None = None):
        reject_non_apinex(model)
        super().__init__()  # a Claude id passes the base check; this class never calls claude -p
        self.model = model
        self.client = client or APInexClient(model=model)
        self.last_cost_usd = 0.0

    def command(self, system: str | None = None, schema: type = dict) -> list[Any]:
        return ["apinex", system or "", schema]

    def _call(self, cmd: list[Any], message: str, model: type) -> Any:
        system = f"{cmd[1]}\n\n{json_instruction(model)}"
        started, ask, error = time.monotonic(), message, ""
        try:
            for attempt in range(2):
                if attempt:
                    ask = (f"{message}\n\nYour previous answer didn't match the schema: {error}. "
                           "Answer again with the full JSON only.")
                data = self.client.complete_sync(system, ask, model=self.model)
                try:
                    return model.model_validate(data)
                except ValidationError as exc:
                    error = _short_validation(exc)
            raise GenerationFailed(f"APInex answered with an invalid text twice: {error}",
                                   retryable=True)
        except GenerationFailed:
            raise
        except Exception as exc:
            raise GenerationFailed(f"Writing failed on {self.model}: {exc}",
                                   retryable=not isinstance(exc, QuotaExceeded)) from exc
        finally:
            self.last_duration_ms = int((time.monotonic() - started) * 1000)
