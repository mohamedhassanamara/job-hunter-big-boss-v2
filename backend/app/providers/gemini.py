"""Gemini-backed fit scorer (Google AI Studio API, free tier, bulk scoring).

- Native JSON output: `responseMimeType` + `responseJsonSchema` with the same inlined FitAssessment
  schema the other providers use. Temperature 0, no thinking (measured: no better, slower, and one
  runaway of 60K thinking tokens).
- Keys and limits live in `services/gemini_keys.KeyPool` (15 RPM / 250K TPM / 500 RPD per key, day
  resets at midnight Pacific; key 1 until its quota is used, then key 2). When every key is out of
  quota the scorer raises `QuotaWait`: the queue waits for the reset, it never switches model.
- Errors: 500/503/timeouts are retried here with backoff (then `TransientError`: the queue tries
  again); a minute-limit 429 is `ConcurrencyLimited` (the queue backs off and slows down); a daily
  429 parks the key and the next request moves to the next key; a refused key (invalid, suspended)
  is disabled and never retried; anything else is a plain `ScoringFailed`.
- Invalid JSON gets ONE retry with the validation error fed back, like the Ollama scorer.
"""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from app.providers.base import (
    ConcurrencyLimited,
    ConfirmationAnswer,
    FitAssessment,
    JobSnapshot,
    ScoringFailed,
    TransientError,
)
from app.providers.ollama import (
    _short_error,
    _unwrap_properties,
    inline_schema,
    schema_instruction,
    strip_fence,
)
from app.services.gemini_keys import KeyPool

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
HTTP_ATTEMPTS = 3  # per model call, then give up: 5xx / timeouts retry after 5 s, 10 s
BACKOFF = (5.0, 10.0)
_REFUSED = ("api key not valid", "api_key_invalid", "permission_denied", "suspended", "leaked",
            "has been denied", "api key expired")


def classify_error(status: int, body: str) -> str | None:
    """None (ok) | daily | rate | refused | transient | fatal.

    - 429 with a per-day quota → `daily` (park the key until the reset, use the next key)
    - any other 429 (per minute, tokens per minute) → `rate`
    - any 403 (permission denied, suspended, restricted account…) and 400/401 about the key
      itself → `refused` (disable the key, pause Gemini, never retry it)
    - 5xx and 408 → `transient`; everything else ≥ 400 → `fatal`
    """
    if status < 400:
        return None
    text = body.lower()
    if status == 429:
        return "daily" if ("perday" in text or "per day" in text or "daily" in text) else "rate"
    if status == 403 or (status in (400, 401) and any(w in text for w in _REFUSED)):
        return "refused"
    if status >= 500 or status == 408:
        return "transient"
    return "fatal"


def _error_text(res: httpx.Response) -> str:
    try:
        return str((res.json().get("error") or {}).get("message") or res.text)[:200]
    except ValueError:
        return res.text[:200]


@dataclass
class ProviderHealth:
    ok: bool
    message: str


class _GeminiClient:
    """One Gemini model behind a KeyPool. `native` = the API enforces the JSON schema (Gemini
    models); Gemma rejects that, so its schema goes into the prompt instead.
    `priority`: bulk scoring is "background" (yields to work the user triggered)."""

    priority = "background"

    def __init__(self, model: str, pool: KeyPool, *, native: bool = True, timeout: float = 120.0,
                 transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self.pool = pool
        self.native = native
        self.timeout = timeout
        self._transport = transport
        self._sleep = sleep
        self._schema = inline_schema(FitAssessment)
        self.last_duration_ms: int | None = None
        self.stats = {"calls": 0, "invalid": 0, "valid_first_try": 0, "valid_after_retry": 0,
                      "failed_invalid": 0, "http_retries": 0}
        self._stats_lock = threading.Lock()

    def _count(self, key: str, n: int = 1) -> None:
        with self._stats_lock:
            self.stats[key] += n

    def health(self) -> ProviderHealth:
        keys = self.pool.keys
        if not keys:
            return ProviderHealth(False, "No Gemini API key configured (GEMINI_API_KEYS in .env).")
        return ProviderHealth(True, "Ready")

    # one HTTP call, with key handling ---------------------------------------------------------

    def _generate(self, system: str, contents: list[dict[str, Any]]) -> str:
        config: dict[str, Any] = {"temperature": 0}
        if self.native:
            config.update(responseMimeType="application/json", responseJsonSchema=self._schema)
        else:
            system = system + schema_instruction(self._schema)
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "generationConfig": config}
        est = (len(system) + sum(len(p["text"]) for c in contents for p in c["parts"])) // 3 + 1500
        last = ""
        for attempt in range(HTTP_ATTEMPTS):
            with self.pool.one_at_a_time():
                lease = self.pool.acquire(est, priority=self.priority)  # may raise QuotaWait
                try:
                    with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                        res = client.post(f"{BASE_URL}/{self.model}:generateContent",
                                          params={"key": lease.key}, json=body)
                except httpx.HTTPError as exc:
                    res = exc
            if isinstance(res, httpx.HTTPError):
                exc = res
                last = f"{exc.__class__.__name__}"
                if not self._backoff(attempt):
                    break
                continue
            kind = classify_error(res.status_code, res.text)
            if kind is None:
                data = res.json()
                self.pool.report(lease, (data.get("usageMetadata") or {}).get("promptTokenCount"))
                try:
                    parts = data["candidates"][0]["content"]["parts"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise TransientError(
                        f"Gemini returned no answer ({_finish_reason(data)})") from exc
                return "".join(p.get("text", "") for p in parts if not p.get("thought"))
            last = f"{res.status_code}: {_error_text(res)}"
            if kind == "daily":
                self.pool.mark_exhausted(lease)  # the next acquire() raises QuotaWait
                continue
            if kind == "refused":  # one refusal is enough: key disabled, Gemini paused
                reason = f"HTTP {res.status_code}: {_error_text(res)}"
                self.pool.disable(lease, reason)
                raise ScoringFailed(f"Gemini refused the key ({reason}). Gemini is paused.")
            if kind == "rate":
                raise ConcurrencyLimited(f"Gemini {last}")
            if kind == "transient":
                if not self._backoff(attempt):
                    break
                continue
            raise ScoringFailed(f"Gemini error {last}")
        raise TransientError(f"Gemini did not answer after {HTTP_ATTEMPTS} tries ({last})")

    def _backoff(self, attempt: int) -> bool:
        """Sleep before the next try; False when the tries are used up."""
        if attempt >= HTTP_ATTEMPTS - 1:
            return False
        self._count("http_retries")
        self._sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
        return True

    def _answer(self, system: str, user: str, parse: Callable[[str], Any]) -> Any:
        """One validated answer; invalid JSON gets ONE retry with the error fed back."""
        contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": user}]}]
        started = time.monotonic()
        last_error = ""
        try:
            for attempt in range(2):
                text = self._generate(system, contents)
                self._count("calls")
                try:
                    result = parse(text)
                    self._count("valid_first_try" if attempt == 0 else "valid_after_retry")
                    return result
                except (ValidationError, json.JSONDecodeError) as exc:
                    self._count("invalid")
                    last_error = _short_error(exc)
                    if attempt == 0:
                        contents += [
                            {"role": "model", "parts": [{"text": text or "{}"}]},
                            {"role": "user", "parts": [{"text": "Your answer was invalid: "
                             f"{last_error}. Reply again with JSON that matches the schema."}]},
                        ]
            self._count("failed_invalid")
            raise ScoringFailed(f"Invalid model output after a retry: {last_error}")
        finally:
            self.last_duration_ms = int((time.monotonic() - started) * 1000)


class GeminiFitScorer(_GeminiClient):
    """Bulk scoring (the FitScorer protocol)."""

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        return self._answer(system, user, _parse)


class GeminiConfirmer(_GeminiClient):
    """"Ask" fallback: the scoring answer plus a verdict from a Gemini-API model (Gemma)."""

    via = "gemini api"
    priority = "user"  # a click on "Ask", not bulk work

    def __init__(self, model: str, pool: KeyPool, **kw: Any):
        super().__init__(model, pool, **kw)
        self._schema = inline_schema(ConfirmationAnswer)

    def confirm(self, system: str, user: str) -> ConfirmationAnswer:
        return self._answer(system, user, parse_confirmation)


def _parse(text: str) -> FitAssessment:
    content = _unwrap_properties(strip_fence(text), FitAssessment)
    return FitAssessment.model_validate_json(content)


def parse_confirmation(text: str) -> ConfirmationAnswer:
    """Also accepts a fenced or {"properties": ...}-wrapped answer (Gemma, a pasted reply)."""
    content = _unwrap_properties(strip_fence(text), ConfirmationAnswer)
    return ConfirmationAnswer.model_validate_json(content)


def _finish_reason(data: dict[str, Any]) -> str:
    cand = (data.get("candidates") or [{}])[0]
    block = (data.get("promptFeedback") or {}).get("blockReason")
    return str(block or cand.get("finishReason") or "empty response")

