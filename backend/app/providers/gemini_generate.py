"""CV and email generation on the Gemini API (free keys), a drop-in for the Claude Code generators.

Same prompts, request builders, schemas and checks as `claude_cv` / `claude_email`: only the
call changes (`ClaudeCVGenerator._call` is replaced). Facts that matter:

- Keys and limits come from `services/gemini_keys.KeyPool` (the pool scoring uses too). These
  calls are "user" priority: they yield to nothing, and background scoring yields to them.
- Native JSON schema (`responseJsonSchema`, the same inlined schema Claude's CLI gets) and a
  `thinkingConfig` from the Settings thinking level (`minimal` = none; `dynamic` = model decides).
- 429/503/timeouts retry with backoff and move to another key; invalid JSON gets ONE retry with
  the error fed back. When the retries are used up it raises `GenerationFailed`: it never falls
  back to another model (the user clicks Retry or "Generate with Claude").
- Privacy: a request containing the profile's email, phone number or link URLs is refused
  before it is sent (`check_private`).
"""

import json
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session

from app.providers.base import CVGenerationFailed, CVPlanDraft, QuotaWait
from app.providers.claude_cv import ClaudeCVGenerator, plan_schema
from app.providers.claude_email import ClaudeEmailDrafter
from app.providers.gemini import BASE_URL, _error_text, classify_error
from app.providers.ollama import strip_fence
from app.services.gemini_keys import KeyPool, pool_for

BACKOFF = (5.0, 10.0, 20.0, 40.0, 60.0)  # seconds before the next try after a 429/503/timeout
THINKING_LEVELS = ("minimal", "low", "medium", "high", "dynamic")
DEFAULT_MODEL, DEFAULT_THINKING = "gemini-3.5-flash-lite", "minimal"


class GenerationFailed(CVGenerationFailed):
    """The model didn't answer (after the retries) or answered garbage twice. `retryable`: a
    Retry may work (busy model, quota); `quota_resume` is set when today's quota is used up."""

    def __init__(self, message: str, *, retryable: bool = True, quota_resume: Any = None):
        super().__init__(message)
        self.retryable, self.quota_resume = retryable, quota_resume


class PrivacyError(CVGenerationFailed):
    """Private contact data was about to be sent to a model: nothing was sent."""


def generation_failure(exc: BaseException | None) -> GenerationFailed | None:
    """The GenerationFailed behind a CVError / OutreachError (they chain it with `from`)."""
    while exc is not None:
        if isinstance(exc, GenerationFailed):
            return exc
        exc = exc.__cause__
    return None


def private_terms(profile: dict[str, Any]) -> list[str]:
    """Lower-cased email, phone digits and link URLs (without scheme) of the profile."""
    out: list[str] = []
    if str(profile.get("email") or "").strip():
        out.append(str(profile["email"]).strip().lower())
    digits = re.sub(r"\D", "", str(profile.get("phone") or ""))
    if len(digits) >= 7:
        out.append(digits)
    for link in profile.get("links") or []:
        url = str(link.get("url") or "").strip().lower().rstrip("/")
        if url:
            out.append(re.sub(r"^https?://(www\.)?", "", url))
    return out


def check_private(text: str, terms: list[str]) -> None:
    low, digits = text.lower(), re.sub(r"\D", "", text)
    for term in terms:
        if (term in digits) if term.isdigit() else (term in low):
            raise PrivacyError("Private contact data (email, phone or a profile link) was found "
                               "in a request to Gemini: nothing was sent.")


def thinking_config(level: str | None) -> dict[str, Any]:
    level = (level or DEFAULT_THINKING).lower()
    if level == "dynamic":
        return {"thinkingBudget": -1}
    return {"thinkingLevel": level if level in THINKING_LEVELS else DEFAULT_THINKING}


class GeminiRunner:
    """One model + thinking level behind the shared key pool. Records every call."""

    def __init__(self, pool: KeyPool, model: str, thinking_level: str | None = None, *,
                 terms: Callable[[], list[str]] | None = None, timeout: float = 300.0,
                 transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, backoff: tuple[float, ...] = BACKOFF):
        self.pool, self.model = pool, model
        self.thinking = thinking_config(thinking_level)
        self._terms, self.timeout, self._transport = terms, timeout, transport
        self._sleep, self.backoff = sleep, backoff
        self.calls: list[dict[str, Any]] = []

    def call(self, system: str, message: str, schema_model: type, label: str = "main") -> Any:
        if self._terms is not None:
            check_private(system + "\n" + message, self._terms())
        schema = plan_schema(schema_model)
        rec: dict[str, Any] = {"label": label, "attempts": [], "tokens_in": 0, "tokens_out": 0,
                               "tokens_thinking": 0, "invalid_retry": False, "seconds": 0.0}
        self.calls.append(rec)
        started = time.monotonic()
        contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": message}]}]
        try:
            for round_ in range(2):
                text = self._generate(system, contents, schema, rec)
                try:
                    return schema_model.model_validate(json.loads(strip_fence(text)))
                except (ValueError, ValidationError) as exc:
                    error = (f"{exc.errors()[0]['loc']}: {exc.errors()[0]['msg']}"
                             if isinstance(exc, ValidationError) else f"not valid JSON ({exc})")
                    if round_ == 1:
                        raise GenerationFailed(
                            f"{self.model} returned invalid output twice ({error})") from exc
                    rec["invalid_retry"] = True
                    contents += [
                        {"role": "model", "parts": [{"text": text or "{}"}]},
                        {"role": "user", "parts": [{"text": f"Your answer was invalid: {error}. "
                                                    "Reply again with JSON that matches the "
                                                    "schema."}]}]
        finally:
            rec["seconds"] = round(time.monotonic() - started, 1)
        raise GenerationFailed("unreachable")  # pragma: no cover

    def _generate(self, system: str, contents: list[dict[str, Any]], schema: dict[str, Any],
                  rec: dict[str, Any]) -> str:
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "generationConfig": {"responseMimeType": "application/json",
                                     "responseJsonSchema": schema,
                                     "thinkingConfig": self.thinking}}
        est = (len(system) + sum(len(p["text"]) for c in contents for p in c["parts"])) // 3 + 2000
        avoid: list[str] = []
        last = ""
        for attempt in range(len(self.backoff) + 1):
            try:
                lease = self.pool.acquire(est, priority="user", avoid=tuple(avoid))
            except QuotaWait as exc:
                raise GenerationFailed(str(exc), quota_resume=exc.resume_at) from exc
            t0 = time.monotonic()
            status, res = 0, None
            try:
                with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                    res = client.post(f"{BASE_URL}/{self.model}:generateContent",
                                      params={"key": lease.key}, json=body)
                status = res.status_code
            except httpx.HTTPError as exc:
                last = exc.__class__.__name__
            rec["attempts"].append({"status": status, "key": lease.label,
                                    "seconds": round(time.monotonic() - t0, 1)})
            if res is not None and status == 200:
                data = res.json()
                u = data.get("usageMetadata") or {}
                self.pool.report(lease, u.get("promptTokenCount"))
                rec["tokens_in"] += u.get("promptTokenCount") or 0
                rec["tokens_out"] += u.get("candidatesTokenCount") or 0
                rec["tokens_thinking"] += u.get("thoughtsTokenCount") or 0
                try:
                    parts = data["candidates"][0]["content"]["parts"]
                except (KeyError, IndexError, TypeError):
                    last, kind = "the model returned no answer", "transient"
                else:
                    return "".join(p.get("text", "") for p in parts if not p.get("thought"))
            else:
                kind = classify_error(status, res.text) if res is not None else "transient"
                if res is not None:
                    last = f"{status}: {_error_text(res)}"
            if kind == "daily":
                self.pool.mark_exhausted(lease)
                continue
            if kind == "refused":
                self.pool.disable(lease, last)
                continue
            if kind == "fatal":
                raise GenerationFailed(f"Gemini error {last}", retryable=False)
            avoid.append(lease.label)  # rate / transient: try another key after a pause
            if attempt < len(self.backoff):
                self._sleep(self.backoff[attempt])
        raise GenerationFailed(f"Gemini did not answer after {len(self.backoff) + 1} tries "
                               f"({last}). Retry, or generate with Claude.")

    def summary(self) -> dict[str, Any]:
        attempts = [a for c in self.calls for a in c["attempts"]]
        return {"calls": len(self.calls), "http_attempts": len(attempts),
                "retries_429": sum(1 for a in attempts if a["status"] == 429),
                "retries_503": sum(1 for a in attempts if a["status"] == 503),
                "invalid_retries": sum(1 for c in self.calls if c["invalid_retry"]),
                "seconds": round(sum(c["seconds"] for c in self.calls), 1),
                "tokens_in": sum(c["tokens_in"] for c in self.calls),
                "tokens_out": sum(c["tokens_out"] for c in self.calls),
                "tokens_thinking": sum(c["tokens_thinking"] for c in self.calls)}


class _GeminiMixin:
    """Replaces the `claude -p` call of the Claude generators (same `command`/`_call` seam)."""

    runner: GeminiRunner
    via = "gemini api"

    def command(self, system: str | None = None, schema: type = CVPlanDraft) -> list[Any]:
        return ["gemini", system or self.system_prompt, schema]  # type: ignore[attr-defined]

    def _call(self, cmd: list[Any], message: str, model: type) -> Any:
        summary_prompt = getattr(self, "summary_prompt", "")
        label = "summary-retry" if summary_prompt and summary_prompt in cmd[1] else "main"
        started = time.monotonic()
        try:
            return self.runner.call(cmd[1], message, model, label)
        finally:
            self.last_duration_ms = int((time.monotonic() - started) * 1000)  # type: ignore[attr-defined]


def runner_for(engine: Engine, model: str, thinking_level: str | None) -> GeminiRunner:
    def terms() -> list[str]:
        from app.services.cv_pool import load_pool

        with Session(engine) as s:
            return private_terms(load_pool(s).profile)

    return GeminiRunner(pool_for(engine, model), model, thinking_level, terms=terms)


class GeminiCVGenerator(_GeminiMixin, ClaudeCVGenerator):
    def __init__(self, runner: GeminiRunner):
        super().__init__(runner.model)
        self.runner = runner
        self.thinking_level = next(iter(runner.thinking.values()))


class GeminiEmailDrafter(_GeminiMixin, ClaudeEmailDrafter):
    def __init__(self, runner: GeminiRunner):
        super().__init__(runner.model)
        self.runner = runner
        self.thinking_level = next(iter(runner.thinking.values()))
