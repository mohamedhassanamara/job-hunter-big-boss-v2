"""CV generator on Claude Code headless mode (`claude -p`), structured output only.

The CLI runs in an empty temp directory with our own system prompt, no tools, no settings or
MCP servers, so it's a plain "JSON in, JSON out" call. `--json-schema` makes the CLI validate
the answer and return it as `structured_output`; we validate it again with Pydantic.

Subscription only: API-key variables are removed from the child environment, and the CLI's own
auth report (`apiKeySource` in the stream's init event) must be "none", i.e. the user's Claude
login. Anything else stops before any usage is billed to an API key.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.providers.base import (
    CVGenerationFailed,
    CVPlan,
    CVPlanDraft,
    CVRequest,
    SummaryDraft,
    plan_from_draft,
)

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "cv_generate.md"
_API_KEY_VARS = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE"}
TIMEOUT = 240


def load_prompts() -> tuple[str, str, str]:
    """(version id, system prompt, summary-retry instructions) from app/prompts/cv_generate.md."""
    version, system, summary, _ = load_all_prompts()
    return version, system, summary


def load_all_prompts() -> tuple[str, str, str, str]:
    """(version id, system, summary-retry, summary-revise instructions)."""
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    body = text.split("## system", 1)[1]
    system, _, rest = body.partition("## summary")
    summary, _, revise = rest.partition("## revise")
    return (f"cv_generate/v{version.group(1) if version else '0'}", system.strip(),
            summary.strip(), revise.strip())


def load_system_prompt() -> tuple[str, str]:
    version, system, _ = load_prompts()
    return version, system


def plan_schema(model: type = CVPlanDraft) -> dict[str, Any]:
    """The draft's JSON schema with $refs inlined and descriptions kept (they guide the model)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def user_message(request: CVRequest, feedback: str = "", current: str = "",
                 user_feedback: str = "") -> str:
    revision = (
        (f"CURRENT SUMMARY\n{current}\n\n" if current else "")
        + (f"FEEDBACK (what should change)\n{user_feedback}\n\n" if user_feedback else "")
        + (f"CHECK PROBLEMS\n{feedback}\n\n" if feedback and current else ""))
    return (
        revision
        + (f"REJECTED SENTENCES\n{feedback}\n\n" if feedback and not current else "")
        + (f"WRITING GUIDE (follow it)\n{request.guide}\n\n" if request.guide else "")
        + ("STYLE EXEMPLAR (tone, summary length and bullet length only; its content is already "
           "in the pool)\n" + json.dumps(request.style, ensure_ascii=False, indent=1) + "\n\n"
           if request.style else "")
        + ("LAYOUT (what code will show; rank facts with this in mind)\n"
           + json.dumps(request.layout, ensure_ascii=False) + "\n\n" if request.layout else "")
        + "FACTS (the only years claims allowed)\n"
        + json.dumps(request.facts or {}, ensure_ascii=False) + "\n\n"
        + "JOB\n" + json.dumps(request.job, ensure_ascii=False, indent=1)
        + "\n\nEMPHASIS FOR THIS TRACK\n" + json.dumps(request.emphasis or {}, ensure_ascii=False)
        + "\n\nEXPERIENCE POOL\n" + json.dumps(request.pool, ensure_ascii=False, indent=1)
    )


class ClaudeCVGenerator:
    def __init__(self, model: str = "claude-sonnet-5", *, binary: str | None = None,
                 runner: Any = subprocess.run, timeout: int = TIMEOUT):
        self.model = model
        self.binary = binary or shutil.which("claude") or "claude"
        self.runner = runner
        self.timeout = timeout
        (self.prompt_version, self.system_prompt, self.summary_prompt,
         self.revise_prompt) = load_all_prompts()
        self.last_cost_usd: float | None = None  # notional for subscriptions; not billed
        self.auth_source: str | None = None
        self.last_duration_ms: int | None = None

    def command(self, system: str | None = None, schema: type = CVPlanDraft) -> list[str]:
        return [
            self.binary, "-p", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence",
            "--model", self.model, "--system-prompt", system or self.system_prompt,
            "--tools", "", "--setting-sources", "", "--strict-mcp-config",
            "--json-schema", json.dumps(plan_schema(schema)),
        ]

    @staticmethod
    def child_env() -> dict[str, str]:
        """The backend's environment minus API keys (force the subscription login) and minus
        Claude Code session variables (a dev server started from a Claude Code session must not
        make this CLI think it runs nested inside it)."""
        return {k: v for k, v in os.environ.items()
                if k not in _API_KEY_VARS and k != "CLAUDECODE"
                and not k.startswith("CLAUDE_CODE_") and k not in ("CLAUDE_PID", "CLAUDE_EFFORT")}

    def generate(self, request: CVRequest) -> CVPlan:
        draft = self._call(self.command(), user_message(request), CVPlanDraft)
        return plan_from_draft(draft)

    def generate_summary(self, request: CVRequest, feedback: str, current: str = "",
                         user_feedback: str = "") -> SummaryDraft:
        """Only the summary again. `feedback` = what the automatic checks found; with `current`
        (and the user's `user_feedback`) the model edits that summary instead of rewriting."""
        revise = bool(current or user_feedback)
        system = f"{self.system_prompt}\n\n{self.revise_prompt if revise else self.summary_prompt}"
        return self._call(self.command(system, SummaryDraft),
                          user_message(request, feedback, current, user_feedback), SummaryDraft)

    def _call(self, cmd: list[str], message: str, model: type) -> Any:
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="jh-claude-") as tmp:
            try:
                proc = self.runner(cmd, input=message, cwd=tmp,
                                   capture_output=True, text=True, timeout=self.timeout,
                                   env=self.child_env())
            except FileNotFoundError as exc:
                raise CVGenerationFailed(
                    "The `claude` CLI isn't installed or not on PATH (Claude Code).") from exc
            except subprocess.TimeoutExpired as exc:
                raise CVGenerationFailed(f"Claude timed out after {self.timeout}s") from exc
        self.last_duration_ms = int((time.monotonic() - started) * 1000)
        events = []
        for line in (proc.stdout or "").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        init = next((e for e in events if e.get("type") == "system"
                     and e.get("subtype") == "init"), None)
        out = next((e for e in reversed(events) if e.get("type") == "result"), None)
        if out is None:
            detail = (proc.stderr or proc.stdout or "").strip()[:300]
            raise CVGenerationFailed(f"Claude returned no JSON: {detail}")
        self.auth_source = (init or {}).get("apiKeySource")
        if init is not None and self.auth_source not in (None, "none"):
            raise CVGenerationFailed(
                f"Claude is authenticated with an API key ({self.auth_source}), not your Claude "
                "subscription. Remove the key (and sign in with `claude`) before generating.")
        self.last_cost_usd = out.get("total_cost_usd")
        if proc.returncode != 0 or out.get("is_error"):
            message = str(out.get("result") or proc.stderr or "unknown error").strip()[:300]
            if "login" in message.lower():
                message += " (run `claude` once in a terminal to sign in)"
            raise CVGenerationFailed(f"Claude failed: {message}")
        data = out.get("structured_output")
        if data is None:
            try:
                data = json.loads(out.get("result") or "")
            except ValueError as exc:
                raise CVGenerationFailed("Claude's answer wasn't valid JSON") from exc
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise CVGenerationFailed(f"Claude's plan didn't match the schema: {where}: "
                                     f"{first['msg']}") from exc
