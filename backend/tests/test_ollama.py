import json

import httpx
import pytest

from app.providers.base import FitAssessment, JobSnapshot, ScoringFailed
from app.providers.ollama import OllamaFitScorer

JOB = JobSnapshot(title="Data Engineer", company="Acme")


def valid_payload(**overrides) -> dict:
    sub = {"score": 7, "reason": "ok", "evidence": "Python and SQL"}
    data = {
        "role_match": sub, "skills_match": sub, "seniority_fit": sub,
        "location_eligibility": sub, "language_requirements": sub,
        "red_flags": [], "strengths": ["Python"], "gaps": [], "summary": "Decent fit.",
    }
    data.update(overrides)
    return data


def scorer_with(responses: list, calls: list | None = None) -> OllamaFitScorer:
    queue = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(json.loads(request.content) if request.content else request.url.path)
        item = next(queue)
        if isinstance(item, Exception):
            raise item
        return item

    return OllamaFitScorer("qwen2.5:7b", transport=httpx.MockTransport(handler))


def chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def test_valid_structured_output() -> None:
    calls: list = []
    scorer = scorer_with([chat(json.dumps(valid_payload()))], calls)
    result = scorer.assess("sys", "user", JOB)
    assert isinstance(result, FitAssessment) and result.role_match.score == 7
    body = calls[0]
    assert body["format"]["type"] == "object"  # JSON schema passed as `format`
    assert body["options"]["temperature"] == 0 and body["options"]["num_ctx"] == 8192
    assert scorer.last_duration_ms is not None


def test_local_model_uses_structured_output_without_thinking() -> None:
    calls: list = []
    scorer = scorer_with([chat(json.dumps(valid_payload()))], calls)
    scorer.assess("sys", "user", JOB)
    body = calls[0]
    assert body["think"] is False
    assert body["format"]["type"] == "object"
    assert body["messages"][0]["content"] == "sys"  # schema enforced by `format`, not the prompt
    assert scorer.stats == {"calls": 1, "invalid": 0, "valid_first_try": 1,
                            "valid_after_retry": 0, "failed_invalid": 0}


def test_cloud_model_gets_schema_in_prompt_and_fence_is_stripped() -> None:
    """Cloud models ignore `format`: the schema goes in the prompt, fences are stripped."""
    calls: list = []
    fenced = "```json\n" + json.dumps(valid_payload()) + "\n```"
    queue = iter([chat(fenced)])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return next(queue)

    scorer = OllamaFitScorer("gemma4:31b-cloud", transport=httpx.MockTransport(handler))
    assert scorer.assess("sys", "user", JOB).skills_match.score == 7
    system = calls[0]["messages"][0]["content"]
    assert system.startswith("sys") and '"role_match"' in system and "no code fence" in system


def test_rate_limit_waits_and_retries() -> None:
    waits: list[float] = []
    busy = httpx.Response(429, json={"error": "too many concurrent requests"})
    queue = iter([busy, busy, chat(json.dumps(valid_payload()))])
    scorer = OllamaFitScorer(
        "gemma4:31b-cloud", transport=httpx.MockTransport(lambda r: next(queue)),
        sleep=waits.append,
    )
    assert scorer.assess("sys", "user", JOB).role_match.score == 7
    assert waits == [2.0, 5.0]


def test_rate_limit_that_never_clears_fails_visibly() -> None:
    busy = httpx.Response(429, json={"error": "too many concurrent requests"})
    scorer = OllamaFitScorer(
        "gemma4:31b-cloud", transport=httpx.MockTransport(lambda r: busy), sleep=lambda _: None
    )
    with pytest.raises(ScoringFailed, match="429"):
        scorer.assess("sys", "user", JOB)


def test_invalid_output_is_retried_once_with_the_error() -> None:
    calls: list = []
    bad = valid_payload(role_match={"score": 42, "reason": "x", "evidence": ""})  # out of range
    scorer = scorer_with([chat(json.dumps(bad)), chat(json.dumps(valid_payload()))], calls)
    assert scorer.assess("sys", "user", JOB).role_match.score == 7
    feedback = calls[1]["messages"][-1]["content"]
    assert "invalid" in feedback and "role_match" in feedback
    assert scorer.stats["invalid"] == 1 and scorer.stats["valid_after_retry"] == 1


def test_invalid_twice_fails_with_visible_error() -> None:
    scorer = scorer_with([chat("not json"), chat('{"summary": "missing fields"}')])
    with pytest.raises(ScoringFailed, match="Invalid model output after a retry"):
        scorer.assess("sys", "user", JOB)


def test_missing_model_gives_pull_command() -> None:
    scorer = scorer_with([httpx.Response(404, json={"error": "model not found"})])
    with pytest.raises(ScoringFailed, match="ollama pull qwen2.5:7b"):
        scorer.assess("sys", "user", JOB)


def test_ollama_down_and_timeout() -> None:
    with pytest.raises(ScoringFailed, match="isn't reachable"):
        scorer_with([httpx.ConnectError("refused")]).assess("s", "u", JOB)
    with pytest.raises(ScoringFailed, match="Timed out"):
        scorer_with([httpx.ReadTimeout("slow")]).assess("s", "u", JOB)


def test_health() -> None:
    tags = {"models": [{"name": "qwen2.5:0.5b"}]}
    missing = scorer_with([httpx.Response(200, json=tags)]).health()
    assert missing.reachable and not missing.model_present
    assert "ollama pull qwen2.5:7b" in missing.message
    tags["models"].append({"name": "qwen2.5:7b"})
    assert scorer_with([httpx.Response(200, json=tags)]).health().ok
    down = scorer_with([httpx.ConnectError("refused")]).health()
    assert not down.reachable and "isn't reachable" in down.message
