"""Ollama-backed fit scorer (local LLM, structured JSON output).

- The FitAssessment JSON schema is passed as `format`: local Ollama constrains decoding to it
  (structured output). Cloud models (`…-cloud`, run on ollama.com) ignore `format`, so for them
  only the schema is also spelled out in the system message. Stripping a Markdown ```json fence
  is a harmless fallback for any model.
- Thinking is disabled (`think: false`): reasoning models would otherwise spend time and tokens
  on hidden reasoning before the JSON.
- Invalid output (bad JSON / schema violation) gets ONE retry with the validation error fed
  back; after that ScoringFailed is raised. We never fall back to a default score.
"""

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from app.providers.base import (
    ConcurrencyLimited,
    FitAssessment,
    JobSnapshot,
    QuotaExceeded,
    ScoringFailed,
    TransientError,
)

DEFAULT_URL = "http://localhost:11434"
# Ollama Cloud limit messages (https://docs.ollama.com/api/errors): both are HTTP 429.
_QUOTA_WORDS = ("usage limit", "quota", "upgrade for higher", "limit reached")
_CONCURRENCY_WORDS = ("concurrent", "too many requests", "rate limit")


def classify_error(status: int, body: str) -> str | None:
    """None (not an error) | concurrency | quota | transient | fatal.

    - 429 "too many concurrent requests" → concurrency (retry the same job, lower parallelism)
    - 429 "…reached your hourly/session/weekly usage limit…", 402 → quota (switch to local)
    - 5xx → transient; an unrecognised 429 is treated as concurrency (retried, never failed)
    """
    if status < 400:
        return None
    text = body.lower()
    if status == 402 or (status in (403, 429) and any(w in text for w in _QUOTA_WORDS)):
        return "quota"
    if status == 429 or any(w in text for w in _CONCURRENCY_WORDS):
        return "concurrency"
    if status >= 500:
        return "transient"
    return "fatal"


def _error_text(res: httpx.Response) -> str:
    try:
        return str(res.json().get("error") or res.text)[:200]
    except ValueError:
        return res.text[:200]
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


def strip_fence(content: str) -> str:
    """'```json\n{...}\n```' → '{...}' (cloud models often wrap JSON in a fence)."""
    match = _FENCE.match(content)
    return match.group(1) if match else content.strip()


def is_cloud(model: str) -> bool:
    return model.endswith(("-cloud", ":cloud"))


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

    out = resolve(schema)
    # Every check must be answered: required even though Python gives them defaults.
    if "flag_checks" in out.get("properties", {}):
        out["required"] = sorted(set(out.get("required", [])) | {"flag_checks"})
        checks = out["properties"]["flag_checks"]
        checks["required"] = sorted(checks.get("properties", {}))
        for check in checks.get("properties", {}).values():
            check["required"] = ["present", "evidence"]
    return out


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
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._transport = transport
        # Output-quality counters for this scorer's lifetime (one queue run): model calls, invalid
        # answers, jobs valid on the first try / after the retry / failed. Shared by worker threads.
        self.stats = {"calls": 0, "invalid": 0, "valid_first_try": 0, "valid_after_retry": 0,
                      "failed_invalid": 0}
        self._stats_lock = threading.Lock()
        self._schema = inline_schema(FitAssessment)
        self.last_duration_ms: int | None = None

    def _count(self, key: str) -> None:
        with self._stats_lock:
            self.stats[key] += 1

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
            "think": False,
            "format": self._schema,
            "options": {"temperature": 0, "seed": 42, "num_ctx": self.num_ctx},
        }
        try:
            with self._client() as client:
                res = client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise TransientError(f"Timed out after {self.timeout:g}s") from exc
        except httpx.TransportError as exc:
            raise TransientError(self._not_running()) from exc
        kind = classify_error(res.status_code, res.text)
        if kind == "concurrency":
            raise ConcurrencyLimited(f"Ollama {res.status_code}: {_error_text(res)}")
        if kind == "quota":
            raise QuotaExceeded(f"Cloud usage limit: {_error_text(res)}")
        if kind == "transient":
            raise TransientError(f"Ollama error {res.status_code}: {_error_text(res)}")
        if res.status_code == 404:
            raise ScoringFailed(self.pull_hint())
        if res.status_code >= 400:
            raise ScoringFailed(f"Ollama error {res.status_code}: {res.text[:200]}")
        try:
            return res.json()["message"]["content"]
        except (ValueError, KeyError) as exc:
            raise ScoringFailed(f"Unexpected Ollama response: {res.text[:200]}") from exc

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        if is_cloud(self.model):
            system += schema_instruction(self._schema)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        started = time.monotonic()
        last_error = ""
        try:
            for attempt in range(2):
                content = self._chat(messages)
                self._count("calls")
                try:
                    result = FitAssessment.model_validate_json(strip_fence(content))
                    self._count("valid_first_try" if attempt == 0 else "valid_after_retry")
                    return result
                except (ValidationError, json.JSONDecodeError) as exc:
                    self._count("invalid")
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
            self._count("failed_invalid")
            raise ScoringFailed(f"Invalid model output after a retry: {last_error}")
        finally:
            self.last_duration_ms = int((time.monotonic() - started) * 1000)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        return f"{where}: {first.get('msg')}" if where else str(first.get("msg"))
    return str(exc)[:200]


def _unwrap_properties(content: str, schema: type) -> str:
    """Cloud models sometimes answer in the schema's own shape ({"properties": {...}}): unwrap
    it when the real fields are only found inside."""
    try:
        data = json.loads(content)
    except ValueError:
        return content
    fields = set(getattr(schema, "model_fields", {}))
    if isinstance(data, dict) and "properties" in data and not fields & set(data) \
            and isinstance(data["properties"], dict) and fields & set(data["properties"]):
        return json.dumps(data["properties"])
    return content


def structured(model: str, system: str, user: str, schema: type, *, base_url: str = DEFAULT_URL,
               timeout: float = 180.0, num_ctx: int = 16384,
               transport: httpx.BaseTransport | None = None) -> tuple[Any, dict[str, Any]]:
    """One Ollama chat returning a validated pydantic object, with the scorer's conventions:
    cloud models get the schema in the prompt, local ones native `format` and `think: false`;
    errors are typed like scoring's (ConcurrencyLimited, QuotaExceeded, TransientError,
    ScoringFailed). One retry when the answer doesn't match the schema. Returns (object, meta)."""
    json_schema = inline_schema(schema)
    sys_prompt = system + (f"\n\n{schema_instruction(json_schema)}" if is_cloud(model) else "")
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}]
    meta: dict[str, Any] = {"model": model, "calls": 0}
    started = time.monotonic()
    for attempt in range(2):
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False,
                                "options": {"temperature": 0, "seed": 42, "num_ctx": num_ctx}}
        if not is_cloud(model):
            body["format"], body["think"] = json_schema, False
        try:
            with httpx.Client(timeout=timeout, transport=transport) as client:
                res = client.post(f"{base_url.rstrip('/')}/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise TransientError(f"Timed out after {timeout:g}s") from exc
        except httpx.TransportError as exc:
            raise TransientError(f"Ollama isn't reachable at {base_url}") from exc
        meta["calls"] += 1
        kind = classify_error(res.status_code, res.text)
        if kind == "concurrency":
            raise ConcurrencyLimited(f"Ollama {res.status_code}: {_error_text(res)}")
        if kind == "quota":
            raise QuotaExceeded(f"Cloud usage limit: {_error_text(res)}")
        if kind == "transient":
            raise TransientError(f"Ollama error {res.status_code}: {_error_text(res)}")
        if res.status_code >= 400:
            raise ScoringFailed(f"Ollama error {res.status_code}: {res.text[:200]}")
        data = res.json()
        meta["prompt_tokens"] = meta.get("prompt_tokens", 0) + (data.get("prompt_eval_count") or 0)
        meta["output_tokens"] = meta.get("output_tokens", 0) + (data.get("eval_count") or 0)
        content = strip_fence((data.get("message") or {}).get("content") or "")
        content = _unwrap_properties(content, schema)
        try:
            out = schema.model_validate_json(content)
            meta["duration_ms"] = int((time.monotonic() - started) * 1000)
            return out, meta
        except ValidationError as exc:
            if attempt:
                raise ScoringFailed(f"Invalid answer: {str(exc)[:200]}") from exc
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": f"That didn't match the schema: "
                                                     f"{str(exc)[:500]}. Answer again, JSON only."}]
    raise ScoringFailed("unreachable")
