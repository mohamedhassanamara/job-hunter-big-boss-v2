"""APInex gateway client for OpenAI-compatible LLM endpoints (MiniMax M3.1 Flash).

Base URL: https://apinex.bond/v1
Default Model: free/minimax-m3.1-flash
Strict Rate Limit: 15 RPM (rolling 60s window)
Fallback: Directly escalates to Ollama on persistent 429 or quota exhaustion.
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.providers.base import (
    FitAssessment,
    JobSnapshot,
    QuotaExceeded,
    ScoringFailed,
)
from app.services import apinex_status

log = logging.getLogger("jobhunter.apinex")

DEFAULT_BASE_URL = "https://apinex.bond/v1"
DEFAULT_MODEL = "free/minimax-m3.1-flash"
TIMEOUT = 60.0
RATE_LIMIT_RPM = 15
RATE_LIMIT_WINDOW = 60.0
MAX_ATTEMPTS = 3
RETRY_DELAY_RE = re.compile(r"Retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)
EXHAUSTION_KEYWORDS = (
    "insufficient_quota",
    "daily_limit",
    "quota_exceeded",
    "insufficient balance",
    "quota exceeded",
    "exceeded your current quota",
)


def strip_code_fence(text: str) -> str:
    """Strip markdown code fence wrapping (```json ... ``` or ``` ... ```)."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def repair_json(text: str) -> str:
    """Fix the structural slips this model makes, never touching string contents: text around
    the outer object, a trailing comma, and a missing comma between two values."""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    out: list[str] = []
    in_str = escaped = False
    prev = ""  # last significant char outside strings
    gap = False  # whitespace since prev
    for ch in text:
        if in_str:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str, prev = False, '"'
            continue
        if ch.isspace():
            out.append(ch)
            gap = True
            continue
        if ch in "}]" and prev == ",":  # trailing comma
            for i in range(len(out) - 1, -1, -1):
                if out[i] == ",":
                    del out[i]
                    break
        value_start = ch in '"{[' or ch.isdigit() or ch == "-" or ch in "tfn"
        if value_start and (prev in ('"', "}", "]") or (prev.isalnum() and gap)):
            out.append(",")  # a value directly after a value
        out.append(ch)
        gap = False
        if ch == '"':
            in_str = True
        else:
            prev = ch
    return "".join(out)


def sanitize_and_parse_json(content: str) -> dict[str, Any]:
    """Cleanly parse model output content into JSON (one structural repair if needed)."""
    unfenced = strip_code_fence(content)
    try:
        try:
            data = json.loads(unfenced)
        except json.JSONDecodeError:
            data = json.loads(repair_json(unfenced))
            log.warning("APInex JSON needed a structural repair")
        if isinstance(data, dict):
            return data
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid JSON from model: {exc}") from exc


def parse_retry_delay(res: httpx.Response, default: float = 4.0) -> float:
    """Extract retry delay from Retry-After header or 'Retry in Xs' body text."""
    retry_header = res.headers.get("retry-after")
    if retry_header:
        try:
            return float(retry_header)
        except ValueError:
            pass
    match = RETRY_DELAY_RE.search(res.text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return default


def is_permanent_quota_exhausted(text: str) -> bool:
    """Check if the error body indicates permanent quota/balance exhaustion rather than transient 429."""
    lower = text.lower()
    return any(keyword in lower for keyword in EXHAUSTION_KEYWORDS)


def _gateway_message(res: httpx.Response) -> str:
    """The gateway's own sentence (OpenAI-style error body), else the start of the body."""
    try:
        return str(res.json()["error"]["message"])[:300]
    except (ValueError, KeyError, TypeError):
        return res.text[:300]


@dataclass
class ProviderHealth:
    ok: bool
    message: str


class RollingRateLimiter:
    """Thread-safe and async-safe rolling rate limiter.
    Strictly limits calls to `limit` requests within `window` seconds.
    Timestamp is recorded before network dispatch."""

    def __init__(
        self,
        limit: int = RATE_LIMIT_RPM,
        window: float = RATE_LIMIT_WINDOW,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.limit = limit
        self.window = window
        self._sleep_fn = sleep_fn
        self._timestamps: deque[float] = deque()
        self._sync_lock = threading.Lock()
        self._async_lock: asyncio.Lock | None = None

    def acquire_sync(self) -> float:
        """Acquires a slot synchronously, blocking if the limit has been reached. Returns waited seconds."""
        with self._sync_lock:
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] >= self.window:
                self._timestamps.popleft()

            waited = 0.0
            if len(self._timestamps) >= self.limit:
                wait_time = (self._timestamps[0] + self.window) - now
                if wait_time > 0:
                    waited = wait_time
                    log.info("APInex 15 RPM limit reached. Waiting %.2fs for slot...", wait_time)
                    self._sleep_fn(wait_time)
                    now = time.monotonic()
                    while self._timestamps and now - self._timestamps[0] >= self.window:
                        self._timestamps.popleft()

            self._timestamps.append(time.monotonic())
            return waited

    async def acquire_async(self) -> float:
        """Acquires a slot asynchronously, waiting if the limit has been reached."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        async with self._async_lock:
            now = time.monotonic()
            while self._timestamps and now - self._timestamps[0] >= self.window:
                self._timestamps.popleft()

            waited = 0.0
            if len(self._timestamps) >= self.limit:
                wait_time = (self._timestamps[0] + self.window) - now
                if wait_time > 0:
                    waited = wait_time
                    log.info("APInex 15 RPM limit reached. Awaiting %.2fs for slot...", wait_time)
                    await asyncio.sleep(wait_time)
                    now = time.monotonic()
                    while self._timestamps and now - self._timestamps[0] >= self.window:
                        self._timestamps.popleft()

            self._timestamps.append(time.monotonic())
            return waited


# Shared singleton rate limiter across workers
_shared_limiter = RollingRateLimiter(limit=RATE_LIMIT_RPM, window=RATE_LIMIT_WINDOW)


class APInexClient:
    """Async & sync OpenAI-compatible client for APInex gateway with 15 RPM throttle and intelligent 429 retry."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = TIMEOUT,
        limiter: RollingRateLimiter | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = (
            api_key
            or os.environ.get("APINEX_API_KEY")
            or getattr(get_settings(), "apinex_api_key", "")
        ).strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.limiter = limiter or _shared_limiter
        self._sleep_fn = sleep_fn
        self._transport = transport
        self._async_transport = async_transport

    def health(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(
                False, "No APInex API key configured (APINEX_API_KEY in .env or environment)."
            )
        return ProviderHealth(True, f"Ready (APInex {self.model} · 15 RPM)")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, model_name: str, system_prompt: str, user_prompt: str,
                       *, raw: bool = False, temperature: float = 0.0) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if not raw:  # plain text answers (the Copilot) skip the JSON mode
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _extract_content(self, data: dict[str, Any]) -> str:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Malformed response structure: {data}") from exc

    # Synchronous execution with retry ---------------------------------------------------------

    def complete_sync(
        self, system_prompt: str, user_prompt: str, model: str | None = None
    ) -> dict[str, Any]:
        """One call with its own retries (502s, timeouts, 429) and, when the last answer was a
        broken object, ONE more full call: gateway errors use up attempts, and a bad answer that
        arrives on the last of them would otherwise never be asked again."""
        try:
            return self._complete_sync_once(system_prompt, user_prompt, model)
        except ValueError as exc:
            if not str(exc).startswith("Invalid JSON"):
                raise
            log.warning("APInex answered invalid JSON after its retries: asking once more")
            return self._complete_sync_once(system_prompt, user_prompt, model)

    def text_sync(self, system_prompt: str, user_prompt: str, model: str | None = None,
                  temperature: float = 0.3,
                  messages: list[dict[str, str]] | None = None) -> str:
        """A plain-text answer (no JSON mode), same limiter, retries and error types. `messages`
        replaces the system/user pair with a whole conversation."""
        return self._complete_sync_once(system_prompt, user_prompt, model, raw=True,
                                        temperature=temperature, messages=messages)

    def _complete_sync_once(
        self, system_prompt: str, user_prompt: str, model: str | None = None,
        *, raw: bool = False, temperature: float = 0.0,
        messages: list[dict[str, str]] | None = None,
    ) -> Any:
        """Call model with up to 3 attempts, backing off on HTTP 429. Raises QuotaExceeded on persistent 429."""
        target_model = model or self.model
        payload = self._build_payload(target_model, system_prompt, user_prompt, raw=raw,
                                      temperature=temperature)
        if messages is not None:
            payload["messages"] = messages
        last_error = ""

        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            for attempt in range(MAX_ATTEMPTS):
                self.limiter.acquire_sync()
                try:
                    res = client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=self._headers(),
                    )
                except httpx.TimeoutException as exc:
                    last_error = f"Timeout ({exc})"
                    if attempt < MAX_ATTEMPTS - 1:
                        log.warning(
                            "APInex timeout on %s. Retrying (%d/%d)...",
                            target_model,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        self._sleep_fn(2.0)
                        continue
                    raise ScoringFailed(f"APInex request timed out after {MAX_ATTEMPTS} attempts: {exc}") from exc
                except httpx.HTTPError as exc:
                    last_error = f"HTTP error ({exc})"
                    if attempt < MAX_ATTEMPTS - 1:
                        log.warning(
                            "APInex HTTP error on %s: %s. Retrying (%d/%d)...",
                            target_model,
                            exc,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        self._sleep_fn(2.0)
                        continue
                    raise ScoringFailed(f"APInex request failed: {exc}") from exc

                if res.status_code == 200:
                    data = res.json()
                    content = self._extract_content(data)
                    if raw:
                        apinex_status.note_success()
                        return content.strip()
                    try:
                        parsed = sanitize_and_parse_json(content)
                    except ValueError as exc:
                        # The model sometimes emits a broken object (a missing comma): ask again.
                        last_error = str(exc)
                        # Length and ending tell a cut-off answer from a broken one.
                        log.warning("APInex invalid JSON on %s: %s (%d chars, ends %r)",
                                    target_model, exc, len(content), content[-80:])
                        if attempt < MAX_ATTEMPTS - 1:
                            log.warning("Retrying (%d/%d)...", attempt + 1, MAX_ATTEMPTS)
                            continue
                        raise
                    apinex_status.note_success()
                    return parsed

                if res.status_code == 429:
                    last_error = f"HTTP 429: {res.text[:200]}"
                    if is_permanent_quota_exhausted(res.text):
                        raise QuotaExceeded(f"APInex quota exhausted: {res.text[:200]}")

                    if attempt < MAX_ATTEMPTS - 1:
                        delay = parse_retry_delay(res)
                        sleep_sec = delay + 1.5
                        log.warning(
                            "APInex 15 RPM throttled. Sleeping %.2fs before retry (%d/%d)...",
                            sleep_sec,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        self._sleep_fn(sleep_sec)
                        continue

                    raise QuotaExceeded(
                        f"APInex quota or persistent rate limit exhausted after {MAX_ATTEMPTS} attempts: {last_error}"
                    )

                if res.status_code >= 500:
                    last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    if attempt < MAX_ATTEMPTS - 1:
                        log.warning(
                            "APInex server error %d. Retrying (%d/%d)...",
                            res.status_code,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        self._sleep_fn(2.0)
                        continue
                    raise ScoringFailed(f"APInex server error after {MAX_ATTEMPTS} attempts: {last_error}")

                if res.status_code == 402:  # e.g. "Daily check-in required to use free models"
                    message = _gateway_message(res)
                    apinex_status.mark_checkin_needed(message)
                    raise QuotaExceeded(f"APInex needs the daily check-in (HTTP 402): {message}")
                raise ScoringFailed(f"APInex request failed with HTTP {res.status_code}: {res.text[:300]}")

        raise ScoringFailed(f"APInex request failed: {last_error}")

    # Asynchronous execution with retry --------------------------------------------------------

    async def complete(
        self, system_prompt: str, user_prompt: str, model: str | None = None
    ) -> dict[str, Any]:
        """Async call with up to 3 attempts, backing off on HTTP 429."""
        target_model = model or self.model
        payload = self._build_payload(target_model, system_prompt, user_prompt)
        last_error = ""

        async with httpx.AsyncClient(timeout=self.timeout, transport=self._async_transport) as client:
            for attempt in range(MAX_ATTEMPTS):
                await self.limiter.acquire_async()
                try:
                    res = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=self._headers(),
                    )
                except httpx.TimeoutException as exc:
                    last_error = f"Timeout ({exc})"
                    if attempt < MAX_ATTEMPTS - 1:
                        log.warning(
                            "APInex timeout on %s. Retrying (%d/%d)...",
                            target_model,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        await asyncio.sleep(2.0)
                        continue
                    raise ScoringFailed(f"APInex request timed out after {MAX_ATTEMPTS} attempts: {exc}") from exc
                except httpx.HTTPError as exc:
                    last_error = f"HTTP error ({exc})"
                    if attempt < MAX_ATTEMPTS - 1:
                        log.warning(
                            "APInex HTTP error on %s: %s. Retrying (%d/%d)...",
                            target_model,
                            exc,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        await asyncio.sleep(2.0)
                        continue
                    raise ScoringFailed(f"APInex request failed: {exc}") from exc

                if res.status_code == 200:
                    data = res.json()
                    content = self._extract_content(data)
                    apinex_status.note_success()
                    return sanitize_and_parse_json(content)

                if res.status_code == 429:
                    last_error = f"HTTP 429: {res.text[:200]}"
                    if is_permanent_quota_exhausted(res.text):
                        raise QuotaExceeded(f"APInex quota exhausted: {res.text[:200]}")

                    if attempt < MAX_ATTEMPTS - 1:
                        delay = parse_retry_delay(res)
                        sleep_sec = delay + 1.5
                        log.warning(
                            "APInex 15 RPM throttled. Sleeping %.2fs before retry (%d/%d)...",
                            sleep_sec,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        await asyncio.sleep(sleep_sec)
                        continue

                    raise QuotaExceeded(
                        f"APInex quota or persistent rate limit exhausted after {MAX_ATTEMPTS} attempts: {last_error}"
                    )

                if res.status_code >= 500:
                    last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    if attempt < MAX_ATTEMPTS - 1:
                        log.warning(
                            "APInex server error %d. Retrying (%d/%d)...",
                            res.status_code,
                            attempt + 1,
                            MAX_ATTEMPTS,
                        )
                        await asyncio.sleep(2.0)
                        continue
                    raise ScoringFailed(f"APInex server error after {MAX_ATTEMPTS} attempts: {last_error}")

                if res.status_code == 402:  # e.g. "Daily check-in required to use free models"
                    message = _gateway_message(res)
                    apinex_status.mark_checkin_needed(message)
                    raise QuotaExceeded(f"APInex needs the daily check-in (HTTP 402): {message}")
                raise ScoringFailed(f"APInex request failed with HTTP {res.status_code}: {res.text[:300]}")

        raise ScoringFailed(f"APInex request failed: {last_error}")


class APInexFitScorer:
    """FitScorer implementation routing through APInexClient."""

    def __init__(self, model: str = DEFAULT_MODEL, client: APInexClient | None = None):
        self.model = model
        self.client = client or APInexClient(model=model)

    def health(self) -> ProviderHealth:
        return self.client.health()

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        """One retry when the answer is missing a sub-score or has an invalid one; then it
        fails (`ScoringFailed`). A sub-score is never defaulted."""
        error = ""
        for attempt in range(2):
            ask = user
            if attempt:
                ask += (
                    f"\n\nYour previous answer was invalid: {error}. Reply again with the full "
                    "JSON, every dimension with an integer score from 0 to 10."
                )
            data = self.client.complete_sync(system, ask, model=self.model)
            try:
                return FitAssessment.model_validate(data)
            except ValidationError as exc:
                error = _short_validation(exc)
        raise ScoringFailed(f"Invalid FitAssessment from APInex after a retry: {error}")


def _short_validation(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first.get("loc", ()))
    return f"{where}: {first.get('msg', 'invalid')}"


def json_instruction(schema: type) -> str:
    """The output-format paragraph for any pydantic schema (APInex has no native schema mode)."""
    from app.providers.ollama import inline_schema

    return ("Output format: reply with ONE JSON object and nothing else (no Markdown, no code "
            "fence) that matches this JSON schema exactly:\n"
            + json.dumps(inline_schema(schema), separators=(",", ":")))


class APInexStructured:
    """A schema-validated call on APInex for the steps that used the Ollama cloud model (company
    research, the hook check): the schema goes in the prompt, one retry when the answer doesn't
    match, errors typed like scoring's. Returns (object, meta) like `ollama.structured`."""

    def __init__(self, model: str = DEFAULT_MODEL, client: APInexClient | None = None):
        self.model = model
        self.client = client or APInexClient(model=model)

    def call(self, system: str, user: str, schema: type) -> tuple[Any, dict[str, Any]]:
        sys_prompt = f"{system}\n\n{json_instruction(schema)}"
        started = time.monotonic()
        ask, error = user, ""
        for attempt in range(2):
            if attempt:
                ask = (f"{user}\n\nYour previous answer didn't match the schema: {error}. "
                       "Answer again with the full JSON only.")
            data = self.client.complete_sync(sys_prompt, ask, model=self.model)
            try:
                out = schema.model_validate(data)
                return out, {"model": self.model, "calls": attempt + 1,
                             "duration_ms": int((time.monotonic() - started) * 1000)}
            except ValidationError as exc:
                error = _short_validation(exc)
        raise ScoringFailed(f"Invalid answer from APInex after a retry: {error}")
