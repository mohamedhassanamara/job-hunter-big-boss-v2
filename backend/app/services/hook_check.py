"""Hook faithfulness: the email's company claims against the signals they cite.

The code checks catch numbers and names that aren't in the signals, but not a claim that links
two true facts ("sovereign models, which let a mutual insurer automate 37%"). A model
(gemma4:31b-cloud, local gemma4:12b as the fallback, research's error policy) splits the hook
into claims and judges each against the cited signals; code turns every claim that isn't
"stated" into an error. Runs at the draft step (each attempt) and on approve when you edited the
hook. Tests and the sandbox use MockHookChecker.
"""

import hashlib
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.services.cv_check import violation
from app.services.research import OllamaStructured, ResearchError

Verdict = Literal["stated", "causal", "combined", "not_stated"]
_LABEL = {"causal": "links the facts by cause or effect", "combined": "merges two signals into "
          "one fact", "not_stated": "isn't in the signals"}


class HookClaim(BaseModel):
    claim: str = Field(description="One claim about the company, quoted or closely paraphrased "
                                   "from the hook")
    signal_ids: list[int] = Field(description="The ids of the signals it relies on")
    verdict: Verdict
    why: str = Field(description="One short sentence (empty when stated)")


class HookReview(BaseModel):
    claims: list[HookClaim]


class HookChecker(Protocol):
    model: str

    def review(self, hook: str, signals: dict[int, str],
               log: Any) -> HookReview: ...


def prompt() -> tuple[str, str]:
    from app.services.prompt import PROMPTS_DIR

    text = (PROMPTS_DIR / "hook_check.md").read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    return f"hook_check/v{version.group(1) if version else '0'}", \
        text.split("## system", 1)[1].strip()


def user_message(hook: str, signals: dict[int, str]) -> str:
    lines = [f"SIGNAL {i}: {fact}" for i, fact in signals.items()]
    return "SIGNALS:\n" + "\n".join(lines) + f"\n\nHOOK:\n{hook}"


class OllamaHookChecker(OllamaStructured):
    def review(self, hook: str, signals: dict[int, str], log: Any) -> HookReview:
        version, system = prompt()
        return self.ask(version, system, user_message(hook, signals), HookReview, log)


_LINK = re.compile(
    r"\b(?:which (?:let|lets|enabled|allowed|helped)|thanks to|leading to|enabling|allowing|"
    r"ayant permis|permettant|grâce à|ce qui a permis|qui a permis|qui permet)\b", re.I)


class MockHookChecker:
    """Tests and the sandbox: a hook that cites two signals and links them ("which enabled",
    "ayant permis", "grâce à") is causal; everything else is stated. No model."""

    model = "mock-hook-check"

    def review(self, hook: str, signals: dict[int, str], log: Any) -> HookReview:
        log({"model": self.model, "prompt_version": "hook_check/mock", "outcome": "ok",
             "duration_ms": 0})
        ids = list(signals)
        link = _LINK.search(hook)
        if len(ids) >= 2 and link:
            return HookReview(claims=[HookClaim(
                claim=hook[max(0, link.start() - 60):link.end() + 60].strip(), signal_ids=ids,
                verdict="causal", why=f"“{link.group(0)}” links two separate signals")])
        return HookReview(claims=[HookClaim(claim=hook, signal_ids=ids, verdict="stated",
                                            why="")])


def fingerprint(hook: str) -> str:
    return hashlib.sha256(" ".join(hook.split()).encode()).hexdigest()[:16]


def check(checker: HookChecker | None, hook: str, signals: dict[int, str]) -> dict[str, Any]:
    """The review as stored on the draft (plan["hook_check"]): never raises. A model that can't
    be reached gives status "unchecked" (a warning, not an error)."""
    calls: list[dict[str, Any]] = []
    base = {"hash": fingerprint(hook), "calls": calls,
            "model": getattr(checker, "model", None)}
    if checker is None or not hook.strip() or not signals:
        return {**base, "status": "skipped", "claims": []}
    try:
        found = checker.review(hook, signals, calls.append)
    except ResearchError as exc:
        return {**base, "status": "unchecked", "error": str(exc)[:300], "claims": []}
    return {**base, "status": "ok", "model": getattr(checker, "model", None),
            "claims": [c.model_dump() for c in found.claims]}


def violations(result: dict[str, Any] | None) -> list[dict[str, str]]:
    if not result:
        return []
    if result.get("status") == "unchecked":
        return [violation("hook_unchecked", "The hook's claims couldn't be checked against the "
                          f"signals ({result.get('error')}): read it against them yourself",
                          "hook")]
    return [violation("hook_faithful", f"The hook says “{c['claim']}”: it {_LABEL[c['verdict']]}"
                      + (f" ({c['why'].rstrip('.')})" if c.get("why") else "")
                      + ". Keep each signal as its own fact, as the signal states it", "hook",
                      "error")
            for c in result.get("claims") or [] if c.get("verdict") in _LABEL]
