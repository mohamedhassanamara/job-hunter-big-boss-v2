"""Copilot, research, hook check, letters, email/LinkedIn drafting and the reviewer run on APInex
(no real calls)."""

import json

import httpx
import pytest

from app.providers import registry
from app.providers.apinex_client import APInexClient, APInexStructured
from app.providers.base import CoverLetterPlan
from app.providers.gemini_generate import GeminiLinkedInDrafter
from app.providers.ollama_chat import APInexCopilot, CopilotUnavailable, OllamaCopilot
from app.services.hook_check import HookReview, OllamaHookChecker
from app.services.research import OllamaResearcher

M = "free/minimax-m3.1-flash"


def client(content: str, seen: list[dict] | None = None) -> APInexClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return APInexClient(model=M, api_key="k", transport=httpx.MockTransport(handler),
                        sleep_fn=lambda _s: None)


def test_copilot_sends_the_conversation_as_plain_text() -> None:
    seen: list[dict] = []
    copilot = APInexCopilot(M, client("Hello there, " * 10, seen))
    out = "".join(copilot.stream([{"role": "system", "content": "ctx"},
                                  {"role": "user", "content": "hi?"}]))
    assert out.startswith("Hello there")
    assert seen[0]["messages"][1]["content"] == "hi?"
    assert "response_format" not in seen[0]


def test_copilot_without_a_key_says_so() -> None:
    c = APInexClient(model=M, api_key="")
    c.api_key = ""
    with pytest.raises(CopilotUnavailable, match="APINEX_API_KEY"):
        list(APInexCopilot(M, c).stream([{"role": "user", "content": "x"}]))


def test_registry_defaults_are_apinex_with_ollama_still_selectable() -> None:
    assert isinstance(registry.copilot(mock=False), APInexCopilot)
    assert isinstance(registry.copilot(mock=False, model="gemma4:12b"), OllamaCopilot)
    assert isinstance(registry.researcher(mock=False), OllamaResearcher)
    assert registry.researcher(mock=False).model == M
    assert isinstance(registry.hook_checker(mock=False), OllamaHookChecker)
    assert registry.hook_checker(mock=False).model == M


def test_structured_validates_and_retries_once() -> None:
    answers = iter(['{"nope": 1}', '{"claims": []}'])

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": next(answers)}}]})

    c = APInexClient(model=M, api_key="k", transport=httpx.MockTransport(handler),
                     sleep_fn=lambda _s: None)
    out, meta = APInexStructured(M, c).call("sys", "user", HookReview)
    assert out.claims == [] and meta["calls"] == 2


def test_letters_and_answers_use_apinex_and_validate() -> None:
    from app.providers.apinex_letter import APInexLetterDrafter

    drafter = registry.letter_drafter(mock=False)
    assert isinstance(drafter, APInexLetterDrafter)
    plan = CoverLetterPlan(paragraphs=[], ask="").model_dump()
    drafter.client = client(json.dumps(plan))
    assert drafter._call(drafter.command("sys", CoverLetterPlan), "msg", CoverLetterPlan)
    drafter.client = client('{"bad": 1}')
    from app.providers.base import CVGenerationFailed

    with pytest.raises(CVGenerationFailed):
        drafter._call(drafter.command("sys", CoverLetterPlan), "msg", CoverLetterPlan)


def test_linkedin_defaults_to_the_apinex_gemini_and_google_ids_still_work() -> None:
    from app.providers.apinex_outreach import APInexLinkedInDrafter

    assert isinstance(registry.linkedin_drafter(mock=False), APInexLinkedInDrafter)
    assert isinstance(registry.linkedin_drafter(mock=False, model="gemini-3.5-flash-lite"),
                      GeminiLinkedInDrafter)
