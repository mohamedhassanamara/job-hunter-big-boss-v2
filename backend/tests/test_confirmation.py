"""Ask Claude: a second opinion stored next to the main score. Claude's CLI is faked, the Gemini
API is faked; nothing here calls a model or the network."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.models import FitConfirmation, FitScore, Job
from app.providers import registry
from app.providers.base import (
    ConfirmationAnswer,
    CoreRequirement,
    CVGenerationFailed,
    SubScore,
    Verdict,
)
from app.providers.claude_confirm import ClaudeConfirmer
from app.providers.mock import MockConfirmer
from app.services import confirmation


def answer(core: list[CoreRequirement] | None = None, advice: str = "apply") -> ConfirmationAnswer:
    sub = SubScore(score=8, reason="fits", evidence="")
    return ConfirmationAnswer(
        role_match=sub, skills_match=sub, seniority_fit=sub, location_eligibility=sub,
        language_requirements=sub, strengths=["Python"], gaps=[], summary="A good match.",
        core_requirements=core or [],
        verdict=Verdict(advice=advice, why="The skills match and the level is right.",
                        seniority="Right level.", skills="Core stack matches.",
                        location_visa="Sponsorship not mentioned.", language="English is enough."))


def fake_run(payload: dict, auth: str = "none", calls: list | None = None):
    def run(cmd, **kw):  # noqa: ANN001, ANN202
        if calls is not None:
            calls.append((cmd, kw))
        init = json.dumps({"type": "system", "subtype": "init", "apiKeySource": auth})
        body = json.dumps({"type": "result", "is_error": False, "structured_output": payload})
        return SimpleNamespace(stdout=f"{init}\n{body}\n", stderr="", returncode=0)
    return run


class Works:
    model, via = "gemma-4-31b-it", "gemini api"

    def __init__(self, ans: ConfirmationAnswer | None = None):
        self.ans, self.calls = ans or answer(), []

    def confirm(self, system: str, user: str) -> ConfirmationAnswer:
        self.calls.append((system, user))
        return self.ans


class Fails:
    model, via = "claude-sonnet-5-5", "claude -p"

    def confirm(self, system: str, user: str) -> ConfirmationAnswer:
        raise CVGenerationFailed("Claude timed out after 240s")


def first_job_id() -> int:
    with Session(engine) as s:
        return s.exec(select(Job.id)).first()


def main_scores(job_id: int) -> list[tuple[int, int | None]]:
    with Session(engine) as s:
        return [(r.id, r.score) for r in s.exec(select(FitScore).where(FitScore.job_id == job_id))]


# ------------------------------------------------------------------------------ the CLI call


def test_claude_is_called_isolated_with_the_scoring_schema_plus_verdict() -> None:
    calls: list = []
    conf = ClaudeConfirmer(runner=fake_run(answer().model_dump(mode="json"), calls=calls))
    result = conf.confirm("SYSTEM TEXT", "USER TEXT")
    assert result.verdict.advice == "apply"
    cmd, kw = calls[0]
    assert cmd[cmd.index("--system-prompt") + 1] == "SYSTEM TEXT" and kw["input"] == "USER TEXT"
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert "verdict" in schema["required"] and "core_requirements" in schema["required"]
    assert "ANTHROPIC_API_KEY" not in kw["env"]


def test_an_api_key_login_is_refused_before_anything_is_billed() -> None:
    conf = ClaudeConfirmer(runner=fake_run(answer().model_dump(mode="json"), auth="env"))
    with pytest.raises(CVGenerationFailed, match="API key"):
        conf.confirm("s", "u")


# ----------------------------------------------------------------------------------- the API


def test_ask_stores_a_separate_confirmation_and_never_touches_the_main_score(
        client: TestClient) -> None:
    job_id = first_job_id()
    before = main_scores(job_id)
    assert client.get(f"/api/jobs/{job_id}/confirmation").json() is None
    res = client.post(f"/api/jobs/{job_id}/confirm")
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "mock" and body["verdict"]["advice"] in ("apply", "maybe", "skip")
    assert body["score"] is not None and body["model"] == "mock-confirmer"
    assert main_scores(job_id) == before  # the main score is exactly as it was
    assert client.get(f"/api/jobs/{job_id}/confirmation").json()["id"] == body["id"]
    again = client.post(f"/api/jobs/{job_id}/confirm").json()
    assert again["id"] != body["id"]  # history is kept; the newest is shown
    assert client.get(f"/api/jobs/{job_id}/confirmation").json()["id"] == again["id"]


def test_the_fallback_chain_notes_what_was_skipped(client: TestClient,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    gemma = Works()
    monkeypatch.setattr(registry, "confirmers",
                        lambda **kw: [("claude", Fails()), ("gemma", gemma)])
    job_id = first_job_id()
    body = client.post(f"/api/jobs/{job_id}/confirm").json()
    assert body["source"] == "gemma" and body["model"] == "gemma-4-31b-it"
    assert "Skipped" in body["notes"] and "timed out" in body["notes"]
    assert "comes from gemma-4-31b-it" in body["notes"]
    system, user = gemma.calls[0]
    assert "VERDICT" in system and "Title:" in user  # scoring prompt + addendum, same user prompt


def test_when_every_step_fails_the_manual_flow_is_offered(client: TestClient,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "confirmers",
                        lambda **kw: [("claude", Fails()), ("gemma", Fails())])
    job_id = first_job_id()
    res = client.post(f"/api/jobs/{job_id}/confirm")
    assert res.status_code == 503 and "Gemini Pro app" in res.json()["detail"]
    prompt = client.get(f"/api/jobs/{job_id}/confirmation/prompt").json()["prompt"]
    assert "VERDICT" in prompt and "Answer with the JSON object only" in prompt
    assert '"verdict"' in prompt and "Title:" in prompt
    pasted = "```json\n" + answer(advice="skip").model_dump_json() + "\n```"
    stored = client.post(f"/api/jobs/{job_id}/confirmation/paste", json={"text": pasted})
    assert stored.status_code == 200
    assert stored.json()["source"] == "manual" and stored.json()["verdict"]["advice"] == "skip"
    bad = client.post(f"/api/jobs/{job_id}/confirmation/paste", json={"text": "I think it fits"})
    assert bad.status_code == 422 and "JSON" in bad.json()["detail"]


def test_a_second_ask_while_one_runs_is_refused(client: TestClient) -> None:
    job_id = first_job_id()
    confirmation._running.add(job_id)  # noqa: SLF001
    try:
        assert client.post(f"/api/jobs/{job_id}/confirm").status_code == 409
    finally:
        confirmation._running.discard(job_id)  # noqa: SLF001


def test_the_confirmation_has_the_same_caps_and_follows_the_settings(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = first_job_id()
    with Session(engine) as s:
        job = s.get(Job, job_id)
        quote = " ".join(job.description.split()[:6])
    cobol = CoreRequirement(requirement="Cobol", evidence=quote, missing=True)
    monkeypatch.setattr(registry, "confirmers",
                        lambda **kw: [("gemma", Works(answer(core=[cobol])))])
    body = client.post(f"/api/jobs/{job_id}/confirm").json()
    assert body["score"] == 60 and body["capped_by"] == "missing_core"
    assert body["missing_core"] == "Cobol"
    cfg = client.get("/api/settings").json()["values"]["scoring"]
    client.put("/api/settings/scoring", json={"value": {**cfg, "missing_core_cap": 100}})
    assert client.get(f"/api/jobs/{job_id}/confirmation").json()["score"] == 80  # recomputed
    client.put("/api/settings/scoring", json={"value": cfg})


def test_the_registry_chain_is_claude_then_gemma_and_the_mock_in_the_sandbox() -> None:
    real = registry.confirmers(mock=False)
    assert [name for name, _ in real] == ["claude", "gemma"]
    assert real[0][1].via == "claude -p" and real[1][1].model == "gemma-4-31b-it"
    assert real[1][1].native is False  # Gemma rejects the native schema: it goes in the prompt
    assert [name for name, _ in registry.confirmers(mock=True)] == ["mock"]
    assert isinstance(registry.confirmers(mock=True)[0][1], MockConfirmer)


def test_confirmations_are_a_separate_table() -> None:
    assert FitConfirmation.__tablename__ == "fit_confirmation" != FitScore.__tablename__
