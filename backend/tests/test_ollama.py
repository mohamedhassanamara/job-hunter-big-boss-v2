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


def test_invalid_output_is_retried_once_with_the_error() -> None:
    calls: list = []
    bad = valid_payload(role_match={"score": 42, "reason": "x", "evidence": ""})  # out of range
    scorer = scorer_with([chat(json.dumps(bad)), chat(json.dumps(valid_payload()))], calls)
    assert scorer.assess("sys", "user", JOB).role_match.score == 7
    feedback = calls[1]["messages"][-1]["content"]
    assert "invalid" in feedback and "role_match" in feedback


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
