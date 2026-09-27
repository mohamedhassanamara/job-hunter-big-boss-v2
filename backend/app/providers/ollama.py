"""Ollama-backed fit scorer (local LLM, structured JSON output).

- The FitAssessment JSON schema is passed as `format`, so a local model's output is constrained.
  Cloud models (`…-cloud`, run on ollama.com through the local daemon) ignore `format`, so the
  schema is also spelled out in the system message, and a Markdown ```json fence is stripped.
- Invalid output (bad JSON / schema violation) gets ONE retry with the validation error fed
  back; after that ScoringFailed is raised. We never fall back to a default score.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from app.providers.base import FitAssessment, JobSnapshot, ScoringFailed

DEFAULT_URL = "http://localhost:11434"
RATE_LIMIT_WAITS = (2.0, 5.0, 10.0, 20.0, 30.0)  # seconds between retries after HTTP 429
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


def strip_fence(content: str) -> str:
    """'```json\n{...}\n```' → '{...}' (cloud models often wrap JSON in a fence)."""
    match = _FENCE.match(content)
    return match.group(1) if match else content.strip()


def schema_instruction(schema: dict[str, Any]) -> str:
    return (
        "\n\nOutput format: reply with ONE JSON object and nothing else (no Markdown, no code "
        "fence). Every sub-score is an object with score, reason and evidence. It must match "
        f"this JSON schema exactly:\n{json.dumps(schema, separators=(',', ':'))}"
    )


def inline_schema(model: type[FitAssessment]) -> dict[str, Any]:
    """Pydantic's JSON schema with $refs inlined (plain schemas are safest for grammar
    conversion), titles/descriptions stripped to keep the prompt small."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k not in ("title", "description")}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


@dataclass
class OllamaHealth:
    reachable: bool
    model: str
    model_present: bool
    message: str
    models: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.reachable and self.model_present


class OllamaFitScorer:
    def __init__(
        self,
        model: str = "qwen2.5:7b",
        *,
        base_url: str = DEFAULT_URL,
        timeout: float = 120.0,
        num_ctx: int = 8192,
        transport: httpx.BaseTransport | None = None,
        sleep: Any = time.sleep,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._transport = transport
        self._sleep = sleep
        self._schema = inline_schema(FitAssessment)
        self.last_duration_ms: int | None = None

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self._transport)

    def _not_running(self) -> str:
        return (
            f"Ollama isn't reachable at {self.base_url}. Start it (open the Ollama app or run "
            "`ollama serve`)."
        )

    def pull_hint(self) -> str:
        return f"Model {self.model} isn't pulled. Run: ollama pull {self.model}"

    def health(self) -> OllamaHealth:
        try:
            with self._client() as client:
                tags = client.get(f"{self.base_url}/api/tags", timeout=5).json()
        except (httpx.HTTPError, ValueError):
            return OllamaHealth(False, self.model, False, self._not_running())
        names = [m.get("name", "") for m in tags.get("models", [])]
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        present = wanted in names
        message = "Ready" if present else self.pull_hint()
        return OllamaHealth(True, self.model, present, message, names)

    def _chat(self, messages: list[dict[str, str]]) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": self._schema,
            "options": {"temperature": 0, "seed": 42, "num_ctx": self.num_ctx},
        }
        # Cloud models answer 429 when too many requests run at once (plan limit): wait and retry
        # instead of failing the job, so a high "Parallel jobs" setting slows down, not breaks.
        for attempt in range(len(RATE_LIMIT_WAITS) + 1):
            try:
                with self._client() as client:
                    res = client.post(f"{self.base_url}/api/chat", json=body)
            except httpx.TimeoutException as exc:
                raise ScoringFailed(f"Timed out after {self.timeout:g}s") from exc
            except httpx.TransportError as exc:
                raise ScoringFailed(self._not_running()) from exc
            if res.status_code != 429 or attempt == len(RATE_LIMIT_WAITS):
                break
            self._sleep(RATE_LIMIT_WAITS[attempt])
        if res.status_code == 404:
            raise ScoringFailed(self.pull_hint())
        if res.status_code >= 400:
            raise ScoringFailed(f"Ollama error {res.status_code}: {res.text[:200]}")
        try:
            return res.json()["message"]["content"]
        except (ValueError, KeyError) as exc:
            raise ScoringFailed(f"Unexpected Ollama response: {res.text[:200]}") from exc

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        messages = [
            {"role": "system", "content": system + schema_instruction(self._schema)},
            {"role": "user", "content": user},
        ]
        started = time.monotonic()
        last_error = ""
        try:
            for attempt in range(2):
                content = self._chat(messages)
                try:
                    return FitAssessment.model_validate_json(strip_fence(content))
                except (ValidationError, json.JSONDecodeError) as exc:
                    last_error = _short_error(exc)
                    if attempt == 0:
                        messages += [
                            {"role": "assistant", "content": content},
                            {
                                "role": "user",
                                "content": "Your answer was invalid: "
                                f"{last_error}. Reply again with JSON that matches the schema.",
                            },
                        ]
            raise ScoringFailed(f"Invalid model output after a retry: {last_error}")
        finally:
            self.last_duration_ms = int((time.monotonic() - started) * 1000)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        return f"{where}: {first.get('msg')}" if where else str(first.get("msg"))
    return str(exc)[:200]
