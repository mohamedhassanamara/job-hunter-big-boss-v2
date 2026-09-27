"""CV generator on Claude Code headless mode (`claude -p`), structured output only.

The CLI runs in an empty temp directory with our own system prompt, no tools, no settings or
MCP servers, so it's a plain "JSON in, JSON out" call. `--json-schema` makes the CLI validate
the answer and return it as `structured_output`; we validate it again with Pydantic.
"""

import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.providers.base import CVGenerationFailed, CVPlan, CVRequest

PROMPT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "cv_generate.md"
TIMEOUT = 240


def load_system_prompt() -> tuple[str, str]:
    """(version id, system prompt) from app/prompts/cv_generate.md."""
    text = PROMPT_FILE.read_text()
    version = re.search(r"^version:\s*(\S+)", text, re.M)
    body = text.split("## system", 1)[1].strip()
    return f"cv_generate/v{version.group(1) if version else '0'}", body


def plan_schema() -> dict[str, Any]:
    """CVPlan's JSON schema with $refs inlined and descriptions kept (they guide the model)."""
    schema = CVPlan.model_json_schema()
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


def user_message(request: CVRequest) -> str:
    return (
        "JOB\n" + json.dumps(request.job, ensure_ascii=False, indent=1)
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
        self.prompt_version, self.system_prompt = load_system_prompt()
        self.last_cost_usd: float | None = None
        self.last_duration_ms: int | None = None

    def command(self) -> list[str]:
        return [
            self.binary, "-p", "--output-format", "json", "--no-session-persistence",
            "--model", self.model, "--system-prompt", self.system_prompt,
            "--tools", "", "--setting-sources", "", "--strict-mcp-config",
            "--json-schema", json.dumps(plan_schema()),
        ]

    def generate(self, request: CVRequest) -> CVPlan:
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="jh-claude-") as tmp:
            try:
                proc = self.runner(self.command(), input=user_message(request), cwd=tmp,
                                   capture_output=True, text=True, timeout=self.timeout)
            except FileNotFoundError as exc:
                raise CVGenerationFailed(
                    "The `claude` CLI isn't installed or not on PATH (Claude Code).") from exc
            except subprocess.TimeoutExpired as exc:
                raise CVGenerationFailed(f"Claude timed out after {self.timeout}s") from exc
        self.last_duration_ms = int((time.monotonic() - started) * 1000)
        try:
            out = json.loads(proc.stdout or "{}")
        except ValueError as exc:
            detail = (proc.stderr or proc.stdout or "").strip()[:300]
            raise CVGenerationFailed(f"Claude returned no JSON: {detail}") from exc
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
            return CVPlan.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise CVGenerationFailed(f"Claude's plan didn't match the schema: {where}: "
                                     f"{first['msg']}") from exc
