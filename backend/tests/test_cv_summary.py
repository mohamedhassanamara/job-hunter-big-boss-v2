"""Summary workflow in CV Studio: feedback regeneration on the CV model from Settings, history,
summary checks that only inform (never block approval), and bullet errors that still block."""

import shutil
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.providers.base import CVRequest, SummaryDraft
from app.providers.mock import MockCVGenerator

pytestmark = pytest.mark.skipif(shutil.which("latexmk") is None, reason="needs latexmk")


def _draft(client: TestClient) -> dict[str, Any]:
    items = client.get("/api/jobs?stage=all").json()["items"]
    job = next(i for i in items if i["title"] == "LLM Engineer")
    app_id = job["application"]["id"]
    profile = client.get("/api/settings").json()["values"]["profile"]
    client.put("/api/settings/profile", json={"value": {**profile, "full_name": "Test Person"}})
    created = client.post(f"/api/applications/{app_id}/cv/generate", json={})
    assert created.status_code == 200, created.text
    return created.json()


def test_a_typed_summary_with_check_errors_still_lets_me_approve(client: TestClient) -> None:
    v = _draft(client)
    typed = ("I am a passionate engineer with 73% better results and 12 years of experience "
             "in Cobol.")
    edited = client.patch(f"/api/cv/{v['id']}", json={"text": {"summary": typed}}).json()
    assert edited["content"]["summary"] == typed  # never replaced by a fallback
    shown = [x for x in edited["violations"] if x["where"] == "summary"]
    assert shown and {x["severity"] for x in shown} == {"warning"}
    assert all(x["rule"] and "phrase" in x for x in shown)
    assert any(x["phrase"] == "passionate" for x in shown)

    # The live check gives the same kind of warnings without saving anything.
    live = client.post(f"/api/cv/{v['id']}/summary/check", json={"text": typed}).json()
    assert live["warnings"] and all(w["severity"] == "warning" for w in live["warnings"])
    assert client.post(f"/api/cv/{v['id']}/summary/check", json={"text": ""}).json() == {
        "warnings": []}

    approved = client.post(f"/api/cv/{v['id']}/approve")
    assert approved.status_code == 200, approved.text
    version = approved.json()["version"]
    assert version["status"] == "approved"
    assert version["approved_summary_warnings"]  # "approved with summary warnings"
    assert any(w["phrase"] == "passionate" for w in version["approved_summary_warnings"])


def test_a_bullet_error_still_blocks_approval(client: TestClient) -> None:
    from app.db import engine
    from app.models import CVVersion

    v = _draft(client)
    with Session(engine) as s:
        row = s.get(CVVersion, v["id"])
        row.violations = [*row.violations, {"type": "number", "severity": "error",
                                            "where": "role:1:0",
                                            "message": "“73%” isn't anywhere in your experience"}]
        s.commit()
    blocked = client.post(f"/api/cv/{v['id']}/approve")
    assert blocked.status_code == 409 and "73%" in blocked.json()["detail"]


class Recorder(MockCVGenerator):
    model = "gemini-test-model"

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def generate_summary(self, request: CVRequest, feedback: str, current: str = "",
                         user_feedback: str = "") -> SummaryDraft:
        self.calls.append({"feedback": feedback, "current": current,
                           "user_feedback": user_feedback})
        return super().generate_summary(request, feedback, current, user_feedback)


def test_feedback_regeneration_uses_the_cv_model_and_keeps_a_history(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import cv as cv_api
    from app.services import model_choice

    v = _draft(client)
    recorder, built = Recorder(), []

    def fake_generator(**kwargs: Any) -> Recorder:
        built.append(kwargs)
        return recorder

    monkeypatch.setattr(cv_api, "cv_generator", fake_generator)
    before = v["content"]["summary"]
    out = client.post(f"/api/cv/{v['id']}/summary", json={"feedback": "shorter, less jargon"})
    assert out.status_code == 200, out.text
    # The model comes from Settings → Models (cv), not Claude.
    from app.db import engine

    with Session(engine) as s:
        pick = model_choice.choice(s, "cv", None)
    assert built and built[0]["model"] == pick["model"] != "claude-sonnet-5"
    first = recorder.calls[0]
    assert first["user_feedback"] == "shorter, less jargon" and first["current"] == before

    usage = client.get(f"/api/applications/{v['application_id']}/cv").json()["usage"]["summary"]
    assert usage["feedback"] == "shorter, less jargon"
    assert [h["text"] for h in usage["history"]] == [before]

    # Typing then regenerating keeps the typed text in the history and drops its override.
    client.patch(f"/api/cv/{v['id']}", json={"text": {"summary": "My own summary text."}})
    again = client.post(f"/api/cv/{v['id']}/summary", json={}).json()
    assert again["content"]["summary"] != "My own summary text."
    usage = client.get(f"/api/applications/{v['application_id']}/cv").json()["usage"]["summary"]
    texts = [h["text"] for h in usage["history"]]
    assert "My own summary text." in texts and before in texts
    assert next(h for h in usage["history"] if h["text"] == before)["feedback"] is None

    # Going back to the first one.
    back = client.post(f"/api/cv/{v['id']}/summary/restore",
                       json={"index": texts.index(before)}).json()
    assert back["content"]["summary"] == before
