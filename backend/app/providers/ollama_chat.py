"""The Copilot's model: a local Ollama chat (gemma4:12b by default), streamed. It gets text only
(no tools, no functions): it can't read or change anything the app doesn't hand it."""

import json
from collections.abc import Iterator
from typing import Any

import httpx

from app.providers.ollama import DEFAULT_URL


class CopilotUnavailable(RuntimeError):
    """Ollama isn't running or the model isn't pulled; the message says what to do."""


class OllamaCopilot:
    def __init__(self, model: str = "gemma4:12b", *, base_url: str = DEFAULT_URL,
                 timeout: float = 300.0, num_ctx: int = 16384,
                 transport: httpx.BaseTransport | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._transport = transport

    def _not_running(self) -> str:
        return (f"Ollama isn't reachable at {self.base_url}. Start it (open the Ollama app or run "
                "`ollama serve`).")

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Text chunks of the answer, as they come."""
        body = {"model": self.model, "messages": messages, "stream": True, "think": False,
                "options": {"temperature": 0.3, "num_ctx": self.num_ctx}}
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client, \
                    client.stream("POST", f"{self.base_url}/api/chat", json=body) as res:
                if res.status_code == 404:
                    raise CopilotUnavailable(
                        f"Model {self.model} isn't pulled. Run: ollama pull {self.model}")
                if res.status_code >= 400:
                    res.read()
                    raise CopilotUnavailable(f"Ollama error {res.status_code}: {res.text[:200]}")
                for line in res.iter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if event.get("error"):
                        raise CopilotUnavailable(f"Ollama: {event['error']}")
                    chunk = (event.get("message") or {}).get("content") or ""
                    if chunk:
                        yield chunk
                    if event.get("done"):
                        break
        except httpx.TimeoutException as exc:
            raise CopilotUnavailable(f"The local model timed out after {self.timeout:g}s") from exc
        except httpx.TransportError as exc:
            raise CopilotUnavailable(self._not_running()) from exc


class APInexCopilot:
    """The Copilot on APInex (`free/minimax-m3.1-flash`). The gateway call isn't streamed: the
    answer arrives whole and is yielded in small pieces so the page still fills in. Text only,
    no tools. A quota or gateway failure is a `CopilotUnavailable` with the reason."""

    def __init__(self, model: str = "free/minimax-m3.1-flash", client: Any = None):
        from app.providers.apinex_client import APInexClient

        self.model = model
        self.client = client or APInexClient(model=model)

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        from app.providers.base import QuotaExceeded, ScoringFailed

        if not self.client.api_key:
            raise CopilotUnavailable("No APInex API key (APINEX_API_KEY in .env).")
        try:
            text = self.client.text_sync("", "", model=self.model, messages=messages)
        except QuotaExceeded as exc:
            raise CopilotUnavailable(f"APInex: {exc}") from exc
        except (ScoringFailed, ValueError) as exc:
            raise CopilotUnavailable(f"APInex failed: {exc}") from exc
        for i in range(0, len(text), 40):
            yield text[i:i + 40]


class MockCopilot:
    """Sandbox and tests: a deterministic answer built from the context (no model)."""

    model = "mock-copilot"

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        question = messages[-1]["content"]
        context = messages[0]["content"]
        job = next((ln.split(":", 1)[1].strip() for ln in context.splitlines()
                    if ln.startswith("Job:")), "your job search")
        yield f"About {job}: "
        yield f"here is a short answer to “{question[:80]}”, from the context I was given."
