"""The claim verifier (services/verifier.py): code checks the verifier (quotes must be in their
source, every sentence must be judged), blocking verdicts, "can't run" blocks too, the email and
letter approval gates, re-verification after an edit, form answers, and the Claude call's
isolation (only the text and its sources). Offline: scripted verifiers, never a model."""

import json

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import Contact, OutreachDraft
from app.models.base import utcnow
from app.models.enums import DraftStatus
from app.providers.base import DraftFailed, VerifyClaim, VerifyPlan
from app.services import outreach, verifier
from tests.test_outreach import Script, good_plan, job_ready  # noqa: F401 (fixture)

SOURCES = {"pool:1": "- Led the refactor to Riverpod, mentoring a junior developer",
           "signal:7": "Zaion automated 37% of a mutual insurer's requests\nQuote: 37%"}


def claim(sentence: str, verdict: str = "supported", source_id: str = "pool:1",
          quote: str = "mentoring a junior developer", **kw) -> VerifyClaim:  # noqa: ANN003
    return VerifyClaim(sentence=sentence, claim=kw.pop("text", sentence), about="candidate",
                       verdict=verdict, source_id=source_id, source_quote=quote, **kw)


class Scripted:
    model, prompt_version, via, auth_source = "scripted", "verify/test", "test", "none"

    def __init__(self, plan: VerifyPlan | Exception):
        self.plan, self.calls = plan, []

    def verify(self, request: dict) -> VerifyPlan:
        self.calls.append(request)
        if isinstance(self.plan, Exception):
            raise self.plan
        return self.plan


def test_a_supported_verdict_needs_its_quote_in_the_source() -> None:
    text = "I mentored a junior developer."
    honest = verifier.run(Scripted(VerifyPlan(claims=[claim(text)])), "email", text, SOURCES)
    assert honest["status"] == "passed" and honest["blocking"] == 0
    made_up = verifier.run(Scripted(VerifyPlan(claims=[claim(text, quote="mentored ten")])),
                           "email", text, SOURCES)
    assert made_up["status"] == "failed" and made_up["claims"][0]["quote_not_found"]
    wrong_source = verifier.run(Scripted(VerifyPlan(claims=[claim(text, source_id="cv")])),
                                "email", text, SOURCES)
    assert wrong_source["status"] == "failed"


def test_every_sentence_must_be_judged() -> None:
    text = "I mentored a junior developer. I also led a team of eight."
    result = verifier.run(Scripted(VerifyPlan(claims=[claim("I mentored a junior developer.")])),
                          "email", text, SOURCES)
    skipped = [c for c in result["claims"] if c.get("skipped")]
    assert result["status"] == "failed" and skipped[0]["sentence"] == "I also led a team of eight."


@pytest.mark.parametrize("verdict", ["unsupported", "exaggerated", "merged", "causal"])
def test_these_verdicts_block(verdict: str) -> None:
    text = "I mentored other developers."
    result = verifier.run(Scripted(VerifyPlan(claims=[claim(text, verdict, reason="One only")])),
                          "email", text, SOURCES)
    assert result["status"] == "failed" and result["blocking"] == 1
    assert verifier.LABEL[verdict] in verifier.problem(result)


def test_greetings_and_questions_are_not_claims() -> None:
    text = "Hi Alex,\nWould a short call help?"
    plan = VerifyPlan(claims=[claim("Hi Alex,", "not_a_claim", "", ""),
                              claim("Would a short call help?", "not_a_claim", "", "")])
    assert verifier.run(Scripted(plan), "email", text, SOURCES)["status"] == "passed"


def test_a_verifier_that_cannot_run_blocks() -> None:
    result = verifier.run(Scripted(DraftFailed("claude not logged in")), "email", "x y z", SOURCES)
    assert result["status"] == "error" and "couldn't run" in verifier.problem(result)
    assert not verifier.is_current(result, "x y z")


def test_a_verification_is_tied_to_the_exact_text() -> None:
    text = "I mentored a junior developer."
    record = verifier.run(Scripted(VerifyPlan(claims=[claim(text)])), "email", text, SOURCES)
    assert verifier.is_current(record, text) and verifier.state(record, text) == "passed"
    assert verifier.state(record, text + " ") == "stale"
    assert verifier.state(None, text) == "none"


# --------------------------------------------------------------------- approval gates


def _ready_draft(info: dict) -> int:
    draft = outreach.generate(engine, info["app"], Script(good_plan(info)))
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft.id)
        contact = s.get(Contact, d.contact_id)
        contact.verified_at = utcnow()  # the Get contact step is done
        s.add(contact)
        s.commit()
    return draft.id


def test_approval_runs_the_verifier_and_blocks_on_a_bad_claim(job_ready: dict, client,  # noqa: F811, ANN001
                                                              monkeypatch) -> None:  # noqa: ANN001
    draft_id = _ready_draft(job_ready)
    bad = Scripted(VerifyPlan(claims=[claim("Subject", "exaggerated", reason="one junior only")]))
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: bad)
    r = client.post(f"/api/outreach/drafts/{draft_id}/approve")
    assert r.status_code == 409 and "don't hold" in r.json()["detail"]
    shown = client.get(f"/api/outreach/drafts/{draft_id}").json()
    assert shown["verification_state"] == "failed" and shown["status"] == "draft"
    assert shown["verification"]["claims"][0]["verdict"] == "exaggerated"
    # Only the final text and its sources reach the verifier: never the drafting prompt.
    request = bad.calls[0]
    assert set(request) == {"kind", "text", "sources"}
    assert request["text"].startswith("Subject: ") and "Best regards," in request["text"]
    assert any(k.startswith("pool:") for k in request["sources"]) and "facts" in \
        request["sources"]


def test_approval_passes_then_an_edit_makes_it_verify_again(job_ready: dict, client,  # noqa: F811, ANN001
                                                            monkeypatch) -> None:  # noqa: ANN001
    draft_id = _ready_draft(job_ready)

    class AllGood(Scripted):
        def verify(self, request: dict) -> VerifyPlan:
            self.calls.append(request)
            return VerifyPlan(claims=[VerifyClaim(sentence=x, claim=x, about="other",
                                                  verdict="not_a_claim")
                                      for x in verifier.sentences(request["text"])])

    good = AllGood(VerifyPlan())
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: good)
    checked = client.post(f"/api/outreach/drafts/{draft_id}/verify").json()
    assert checked["verification_state"] == "passed" and len(good.calls) == 1
    client.patch(f"/api/outreach/drafts/{draft_id}", json={"subject": "A new subject"})
    assert client.get(f"/api/outreach/drafts/{draft_id}").json()["verification_state"] == "stale"
    approved = client.post(f"/api/outreach/drafts/{draft_id}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert len(good.calls) == 2  # the edited text was verified again at approval
    with Session(engine) as s:
        assert s.get(OutreachDraft, draft_id).status == DraftStatus.approved


def test_a_verifier_error_blocks_approval(job_ready: dict, client, monkeypatch) -> None:  # noqa: F811, ANN001
    draft_id = _ready_draft(job_ready)
    monkeypatch.setattr(verifier, "for_workspace",
                        lambda s, w: Scripted(DraftFailed("Claude is authenticated with an API "
                                                          "key")))
    r = client.post(f"/api/outreach/drafts/{draft_id}/approve")
    assert r.status_code == 409 and "couldn't run" in r.json()["detail"]


def test_the_claude_call_is_isolated_and_gets_only_text_and_sources() -> None:
    from app.providers.claude_verify import ClaudeVerifier, message

    v = ClaudeVerifier("claude-opus-5-5", binary="claude")
    cmd = v.command(v.system, VerifyPlan)
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    assert "zero tolerance" in cmd[cmd.index("--system-prompt") + 1]
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert "claims" in json.dumps(schema)
    text = message({"kind": "cold email", "text": "Hi.", "sources": {"pool:1": "fact"}})
    assert text.startswith("KIND: cold email") and "SOURCE pool:1\nfact" in text


def test_form_answers_are_verified_on_demand(job_ready: dict, client, monkeypatch) -> None:  # noqa: F811, ANN001
    from app.models import ApplicationAnswer

    with Session(engine) as s:
        a = ApplicationAnswer(application_id=job_ready["app"], question="Why us?",
                              answer="I mentored other developers.")
        s.add(a)
        s.commit()
        answer_id = a.id
    bad = Scripted(VerifyPlan(claims=[claim("I mentored other developers.", "exaggerated")]))
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: bad)
    out = client.post(f"/api/answers/{answer_id}/verify").json()
    assert out["verification_state"] == "failed"
    assert "listing" in bad.calls[0]["sources"]  # answers may use the listing
    edited = client.patch(f"/api/answers/{answer_id}",
                          json={"answer": "I mentored a junior developer."}).json()
    assert edited["verification_state"] == "stale"  # Copy stays locked until verified again


def test_a_cover_letter_is_verified_before_approval(monkeypatch) -> None:
    from app.models import CoverLetter

    class Fails(Scripted):
        pass

    bad = Fails(VerifyPlan(claims=[claim("x", "causal")]))
    with Session(engine) as s:
        letter = s.query(CoverLetter).first() if hasattr(s, "query") else None
        if letter is None:
            pytest.skip("no letter in the test workspace")
        with pytest.raises(verifier.VerifyError, match="don't hold"):
            letter.verification = {}
            verifier.require_letter(s, letter, bad)
        assert letter.verification["status"] == "failed"
        s.rollback()
