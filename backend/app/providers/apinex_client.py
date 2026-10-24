"""APInex gateway client for OpenAI-compatible LLM endpoints (MiniMax M3.1 Flash / DeepSeek).

Base URL: https://apinex.bond/v1
Primary model: free/minimax-m3.1-flash
Fallback model: free/deepseek-v4.1-flash
Strict Rate Limit: 15 RPM (rolling 60s window)
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

from app.config import get_settings
from app.providers.base import (
    ConcurrencyLimited,
    FitAssessment,
    FitScorer,
    JobSnapshot,
    QuotaExceeded,
    ScoringFailed,
)

log = logging.getLogger("jobhunter.apinex")

DEFAULT_BASE_URL = "https://apinex.bond/v1"
PRIMARY_MODEL = "free/minimax-m3.1-flash"
FALLBACK_MODEL = "free/deepseek-v4.1-flash"
TIMEOUT = 60.0
RATE_LIMIT_RPM = 15
RATE_LIMIT_WINDOW = 60.0
BACKOFF_429_SECONDS = 10.0


def strip_code_fence(text: str) -> str:
    """Strip markdown code fence wrapping (```json ... ``` or ``` ... ```)."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def sanitize_and_parse_json(content: str) -> dict[str, Any]:
    """Cleanly parse model output content into JSON."""
    unfenced = strip_code_fence(content)
    try:
        data = json.loads(unfenced)
        if isinstance(data, dict):
            return data
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid JSON from model: {exc}") from exc


@dataclass
class ProviderHealth:
    ok: bool
    message: str


class RollingRateLimiter:
    """Thread-safe and async-safe rolling rate limiter.
    Strictly limits calls to `limit` requests within `window` seconds."""

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
    """Async & sync OpenAI-compatible client for APInex gateway with 15 RPM throttle."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        primary_model: str = PRIMARY_MODEL,
        fallback_model: str = FALLBACK_MODEL,
        timeout: float = TIMEOUT,
        backoff_429: float = BACKOFF_429_SECONDS,
        limiter: RollingRateLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = (
            api_key
            or os.environ.get("APINEX_API_KEY")
            or getattr(get_settings(), "apinex_api_key", "")
        ).strip()
        self.base_url = base_url.rstrip("/")
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.backoff_429 = backoff_429
        self.limiter = limiter or _shared_limiter
        self._transport = transport
        self._async_transport = async_transport

    def health(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(
                False, "No APInex API key configured (APINEX_API_KEY in .env or environment)."
            )
        return ProviderHealth(True, f"Ready (APInex {self.primary_model} · 15 RPM)")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, model_name: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

    def _extract_content(self, data: dict[str, Any]) -> str:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Malformed response structure: {data}") from exc

    # Synchronous completion -------------------------------------------------------------------

    def _call_model_sync(
        self, client: httpx.Client, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        self.limiter.acquire_sync()
        payload = self._build_payload(model, system_prompt, user_prompt)
        res = client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        )
        if res.status_code == 429:
            raise ConcurrencyLimited(f"HTTP 429 Too Many Requests: {res.text[:200]}")
        if res.status_code != 200:
            raise RuntimeError(f"HTTP {res.status_code}: {res.text[:300]}")
        data = res.json()
        content = self._extract_content(data)
        return sanitize_and_parse_json(content)

    def complete_sync(
        self, system_prompt: str, user_prompt: str, model: str | None = None
    ) -> dict[str, Any]:
        """Call primary model; retry once with fallback model on non-200, 429, timeout or invalid JSON."""
        target_model = model or self.primary_model
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            try:
                return self._call_model_sync(client, target_model, system_prompt, user_prompt)
            except Exception as primary_exc:
                if target_model != self.fallback_model:
                    # If 429 rate limit or quota hit, back off before retry
                    if isinstance(primary_exc, ConcurrencyLimited):
                        log.warning(
                            "Primary model %s hit rate limit (429). Sleeping %.1fs before fallback...",
                            target_model,
                            self.backoff_429,
                        )
                        time.sleep(self.backoff_429)
                    else:
                        log.warning(
                            "Primary model %s failed (%s). Retrying once with fallback %s...",
                            target_model,
                            primary_exc,
                            self.fallback_model,
                        )
                    try:
                        return self._call_model_sync(
                            client, self.fallback_model, system_prompt, user_prompt
                        )
                    except Exception as fallback_exc:
                        is_quota = (
                            isinstance(primary_exc, ConcurrencyLimited)
                            or isinstance(fallback_exc, ConcurrencyLimited)
                            or "quota" in str(primary_exc).lower()
                            or "quota" in str(fallback_exc).lower()
                            or "429" in str(primary_exc)
                            or "429" in str(fallback_exc)
                        )
                        if is_quota:
                            raise QuotaExceeded(
                                f"APInex quota/rate limit exhausted on primary and fallback: {fallback_exc}"
                            ) from fallback_exc
                        raise ScoringFailed(
                            f"APInex scoring failed on primary ({primary_exc}) and fallback ({fallback_exc})"
                        ) from fallback_exc
                if isinstance(primary_exc, ConcurrencyLimited) or "429" in str(primary_exc):
                    raise QuotaExceeded(f"APInex rate limit exhausted: {primary_exc}") from primary_exc
                raise ScoringFailed(f"APInex scoring failed: {primary_exc}") from primary_exc

    # Asynchronous completion ------------------------------------------------------------------

    async def _call_model_async(
        self, client: httpx.AsyncClient, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        await self.limiter.acquire_async()
        payload = self._build_payload(model, system_prompt, user_prompt)
        res = await client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        )
        if res.status_code == 429:
            raise ConcurrencyLimited(f"HTTP 429 Too Many Requests: {res.text[:200]}")
        if res.status_code != 200:
            raise RuntimeError(f"HTTP {res.status_code}: {res.text[:300]}")
        data = res.json()
        content = self._extract_content(data)
        return sanitize_and_parse_json(content)

    async def complete(
        self, system_prompt: str, user_prompt: str, model: str | None = None
    ) -> dict[str, Any]:
        """Async call with fallback retry and 429 backoff."""
        target_model = model or self.primary_model
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._async_transport) as client:
            try:
                return await self._call_model_async(client, target_model, system_prompt, user_prompt)
            except Exception as primary_exc:
                if target_model != self.fallback_model:
                    if isinstance(primary_exc, ConcurrencyLimited):
                        log.warning(
                            "Primary model %s hit rate limit (429). Awaiting %.1fs before fallback...",
                            target_model,
                            self.backoff_429,
                        )
                        await asyncio.sleep(self.backoff_429)
                    else:
                        log.warning(
                            "Primary model %s failed (%s). Retrying once with fallback %s...",
                            target_model,
                            primary_exc,
                            self.fallback_model,
                        )
                    try:
                        return await self._call_model_async(
                            client, self.fallback_model, system_prompt, user_prompt
                        )
                    except Exception as fallback_exc:
                        is_quota = (
                            isinstance(primary_exc, ConcurrencyLimited)
                            or isinstance(fallback_exc, ConcurrencyLimited)
                            or "quota" in str(primary_exc).lower()
                            or "quota" in str(fallback_exc).lower()
                            or "429" in str(primary_exc)
                            or "429" in str(fallback_exc)
                        )
                        if is_quota:
                            raise QuotaExceeded(
                                f"APInex quota/rate limit exhausted on primary and fallback: {fallback_exc}"
                            ) from fallback_exc
                        raise ScoringFailed(
                            f"APInex scoring failed on primary ({primary_exc}) and fallback ({fallback_exc})"
                        ) from fallback_exc
                if isinstance(primary_exc, ConcurrencyLimited) or "429" in str(primary_exc):
                    raise QuotaExceeded(f"APInex rate limit exhausted: {primary_exc}") from primary_exc
                raise ScoringFailed(f"APInex scoring failed: {primary_exc}") from primary_exc


class APInexFitScorer:
    """FitScorer implementation routing through APInexClient."""

    def __init__(self, model: str = PRIMARY_MODEL, client: APInexClient | None = None):
        self.model = model
        self.client = client or APInexClient(primary_model=model)

    def health(self) -> ProviderHealth:
        return self.client.health()

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        data = self.client.complete_sync(system, user, model=self.model)
        try:
            return FitAssessment.model_validate(data)
        except Exception as exc:
            raise ScoringFailed(f"Invalid FitAssessment structure from APInex: {exc}") from exc
