"""Copilot: the context it gets (job vs global), streamed answers saved with the history, warnings
for facts that aren't yours, the Ollama-down error, and no way to change data. No model calls."""

import httpx
import pytest
from sqlmodel import Session, select

from app.api import copilot as copilot_api
from app.db import engine
from app.models import Application, CopilotMessage, CopilotThread
from app.providers.ollama_chat import CopilotUnavailable, OllamaCopilot
from app.services import copilot as svc
from app.services.cv_pool import load_pool
from tests.test_cover_letter import web_job  # noqa: F401 (fixture)


class Recorder:
    """A Copilot that records what it was sent and answers with a fixed text."""

    model = "recorder"

    def __init__(self, answer: str = "Highlight the backend work."):
        self.answer, self.calls = answer, []

    def stream(self, messages):  # noqa: ANN001, ANN201
        self.calls.append(messages)
        yield from self.answer.split(" ")[:1]
        yield " " + " ".join(self.answer.split(" ")[1:])


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(copilot_api, "copilot", lambda **kw: rec)
    return rec


def test_job_context_has_the_listing_fit_cv_letter_status_and_pool(web_job: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        app = s.get(Application, web_job["app"])
        text, source = svc.context(s, app)
        global_text, global_source = svc.context(s, None)
    assert "Listing:" in text and "Nous recherchons" in text and web_job["company"] in text
    assert "APPROVED CV (v1)" in text and "EXPERIENCE POOL" in text and "PROFILE" in text
    assert "web application: ready" in text
    assert "Nous recherchons" in source
    assert "JOB" not in global_text.split("EXPERIENCE POOL")[0] and "Listing:" not in global_text
    assert global_source == ""


def test_asking_streams_saves_and_sends_the_history(web_job: dict, client, recorder) -> None:  # noqa: F811, ANN001
    thread = client.get(f"/api/applications/{web_job['app']}/copilot").json()
    assert thread["messages"] == [] and "What should I highlight in the interview?" in \
        thread["starters"]
    r = client.post(f"/api/copilot/threads/{thread['id']}/messages",
                    json={"question": "What should I highlight?"})
    assert r.status_code == 200 and r.text == "Highlight the backend work."
    client.post(f"/api/copilot/threads/{thread['id']}/messages", json={"question": "And then?"})
    second = recorder.calls[1]
    assert second[0]["role"] == "system" and "CONTEXT" in second[0]["content"]
    assert [m["role"] for m in second[1:]] == ["user", "assistant", "user"]
    saved = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"]
    assert [m["role"] for m in saved] == ["user", "assistant", "user", "assistant"]
    assert saved[1]["model"].startswith("recorder (copilot/v2)") and saved[1]["duration_ms"] >= 0
    assert client.get(f"/api/applications/{web_job['app']}/copilot").json()["id"] == thread["id"]


def test_answers_with_facts_that_arent_yours_get_warnings(web_job: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        pool = load_pool(s)
    found = svc.warnings("You moved the warehouse to Redshift and cut 73%.", pool,
                         "Spark and dbt")
    assert {w["message"].split("”")[0] for w in found} >= {"“Redshift", "“73%"}
    assert svc.warnings("Mention Spark.", pool, "We use Spark") == []


def test_ollama_down_is_a_clear_error_saved_on_the_message(web_job: dict) -> None:  # noqa: F811
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    model = OllamaCopilot(transport=httpx.MockTransport(down))
    with pytest.raises(CopilotUnavailable, match="Ollama isn't reachable"):
        list(model.stream([{"role": "user", "content": "hi"}]))
    with Session(engine) as s:
        thread = svc.job_thread(s, web_job["app"])
    out = "".join(svc.ask(engine, thread.id, "Hello?", model))
    assert "[Copilot error] Ollama isn't reachable" in out
    with Session(engine) as s:
        last = svc.messages(s, thread.id)[-1]
        assert last.role == "assistant" and "reachable" in last.error


def test_the_local_model_streams_ndjson() -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        body = (b'{"message":{"content":"Hel"},"done":false}\n'
                b'{"message":{"content":"lo"},"done":false}\n{"done":true}\n')
        return httpx.Response(200, content=body)

    model = OllamaCopilot(transport=httpx.MockTransport(ok))
    assert "".join(model.stream([{"role": "user", "content": "hi"}])) == "Hello"


def test_clear_keeps_the_old_conversation_and_global_threads(web_job: dict, client,  # noqa: F811, ANN001
                                                             recorder) -> None:
    first = client.get(f"/api/applications/{web_job['app']}/copilot").json()
    client.post(f"/api/copilot/threads/{first['id']}/messages", json={"question": "Hi"})
    fresh = client.post(f"/api/applications/{web_job['app']}/copilot/clear").json()
    assert fresh["id"] != first["id"] and fresh["messages"] == []
    kept = client.get(f"/api/copilot/threads?application_id={web_job['app']}").json()
    assert {t["id"] for t in kept} >= {first["id"], fresh["id"]}
    g = client.post("/api/copilot/threads").json()
    client.post(f"/api/copilot/threads/{g['id']}/messages", json={"question": "My best project?"})
    listed = client.get("/api/copilot/threads").json()
    assert listed[0]["id"] == g["id"] and listed[0]["title"] == "My best project?"
    assert client.delete(f"/api/copilot/threads/{g['id']}").status_code == 204
    assert client.post(f"/api/copilot/threads/{first['id']}/messages",
                       json={"question": " "}).status_code == 422


def test_the_copilot_cannot_change_anything(web_job: dict, client, recorder) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        before = s.get(Application, web_job["app"]).model_dump()
    thread = client.get(f"/api/applications/{web_job['app']}/copilot").json()
    recorder.answer = "I moved this job to Applied and deleted your CV."
    client.post(f"/api/copilot/threads/{thread['id']}/messages",
                json={"question": "Mark it applied"})
    with Session(engine) as s:
        after = s.get(Application, web_job["app"]).model_dump()
        assert {k: v for k, v in after.items() if k != "updated_at"} == \
            {k: v for k, v in before.items() if k != "updated_at"}
        assert s.exec(select(CopilotMessage)).all() and s.exec(select(CopilotThread)).all()
    writes = [r for r in copilot_api.router.routes
              if {"PUT", "PATCH"} & set(getattr(r, "methods", set()))]
    assert writes == []  # only its own conversations are created or deleted


def test_messages_get_style_claim_and_years_warnings(web_job: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        pool = load_pool(s)
    msg = ("Je me permets de vous contacter : fort de 3 ans en ingénierie logicielle, je maîtrise "
           "l'architecture MVC.")
    found = {w["type"]: w["message"] for w in svc.warnings(
        msg, pool, "", ("3 years of software engineering experience",
                        "3 ans d'expérience en ingénierie logicielle"))}
    assert "MVC" in found["unsupported"] and "je me permets" in found["style"]
    assert "3 ans d'expérience en ingénierie logicielle" in found["years"]


def test_rewrite_with_claude_adds_a_new_answer(web_job: dict, client, recorder) -> None:  # noqa: F811, ANN001
    thread = client.get(f"/api/applications/{web_job['app']}/copilot").json()
    client.post(f"/api/copilot/threads/{thread['id']}/messages",
                json={"question": "Write a LinkedIn message"})
    answer = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"][-1]
    out = client.post(f"/api/copilot/messages/{answer['id']}/rewrite").json()
    assert out["content"].startswith("(rewritten) Highlight the backend work.")
    assert "via claude -p, rewrite (copilot/v2)" in out["model"]
    after = client.get(f"/api/copilot/threads/{thread['id']}").json()["messages"]
    assert after[-1]["id"] == out["id"] and after[-2]["id"] == answer["id"]
    user = next(m for m in after if m["role"] == "user")
    assert client.post(f"/api/copilot/messages/{user['id']}/rewrite").status_code == 422


def test_the_rewriter_uses_the_isolated_subscription_call() -> None:
    from app.providers.claude_rewrite import ClaudeRewriter
    from tests.test_cv import fake_run

    calls: list = []
    r = ClaudeRewriter(runner=fake_run({"is_error": False, "structured_output": {"text": "Hi"}},
                                       calls=calls))
    assert r.rewrite("rules", "ORIGINAL\nhello\n\nCONTEXT\n\nx") == "Hi"
    cmd = calls[0][0]
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    with pytest.raises(RuntimeError, match="API key"):
        ClaudeRewriter(runner=fake_run({"is_error": False, "structured_output": {"text": "x"}},
                                       auth="ANTHROPIC_API_KEY")).rewrite("r", "m")
