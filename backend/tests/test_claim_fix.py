"""Suggested fixes for flagged claims (services/claim_fix.py): grounded in the sources, checked in
code (a failing one becomes "remove this sentence"), deterministic repairs without a model, and
Apply = edit + re-verify only the changed sentences. Offline: scripted verifiers."""

from types import SimpleNamespace

from sqlmodel import Session

from app.db import engine
from app.models import ApplicationAnswer
from app.providers.base import VerifyClaim, VerifyPlan
from app.services import claim_fix, verifier
from tests.test_outreach import job_ready  # noqa: F401 (fixture)
from tests.test_verifier import Scripted

SOURCES = {"pool:1": "- Led the refactor to Riverpod, mentoring a junior developer",
           "facts": "Name: Alex Sample\nYears wording (English): 3 years of software engineering "
                    "experience",
           "recipient": "Company: Acme\nJob title: Data Engineer\nContact: Ana Test, CTO"}


def flagged(sentence: str, **kw) -> VerifyClaim:  # noqa: ANN003
    return VerifyClaim(sentence=sentence, claim=sentence, about="candidate",
                       verdict=kw.pop("verdict", "exaggerated"), source_id="pool:1",
                       source_quote="mentoring a junior developer", reason="One person", **kw)


def run(claim: VerifyClaim, text: str, ctx: object = None) -> dict:
    return verifier.run(Scripted(VerifyPlan(claims=[claim])), "email", text, SOURCES,
                        fixer=claim_fix.Fixer(SOURCES, ctx))


def stated(text: str = "I mentored other developers.") -> dict:
    claim = flagged(text, suggestion="I mentored a junior developer.",
                    suggestion_source_id="pool:1", suggestion_quote="mentoring a junior developer")
    return run(claim, text)["claims"][0]["fix"]


# ------------------------------------------------------------------ grounded suggestions


def test_a_flagged_claim_gets_a_suggestion_grounded_in_its_source() -> None:
    fix = stated()
    assert fix["kind"] == "replace" and fix["text"] == "I mentored a junior developer."
    assert fix["source_id"] == "pool:1" and fix["source_quote"] == "mentoring a junior developer"
    assert fix["origin"] == "claude"


def test_nothing_supporting_it_means_remove_the_sentence() -> None:
    row = run(flagged("I led a team of eight."), "I led a team of eight.")["claims"][0]
    assert row["fix"]["kind"] == "remove" and "suggestion" not in row  # raw fields are dropped


def test_supported_claims_get_no_fix() -> None:
    ok = flagged("I mentored a junior developer.", verdict="supported")
    assert "fix" not in run(ok, "I mentored a junior developer.")["claims"][0]


# ------------------------------------------------------------- a failing suggestion → remove


def test_a_suggestion_with_a_made_up_quote_is_replaced_by_remove() -> None:
    claim = flagged("I led a team.", suggestion="I mentored a junior developer.",
                    suggestion_source_id="pool:1", suggestion_quote="mentored ten developers")
    assert run(claim, "I led a team.")["claims"][0]["fix"]["kind"] == "remove"


def test_a_suggestion_that_fails_the_code_checks_is_replaced_by_remove() -> None:
    for bad in ("I mentored 12 junior developers using Kubernetes.",  # number and tool
                "I mentored a junior developer, a world-class one."):  # banned phrase
        ctx = SimpleNamespace(banned=["world-class"], years_statement=None, years_statement_fr=None,
                              language="en", allowed_years=set(), honesty=None)
        claim = flagged("I led a team.", suggestion=bad, suggestion_source_id="pool:1",
                        suggestion_quote="mentoring a junior developer")
        fix = run(claim, "I led a team.", ctx)["claims"][0]["fix"]
        assert fix["kind"] == "remove" and fix["origin"] == "checks", bad


# -------------------------------------------------------------- deterministic, no model


def _ctx(**kw) -> SimpleNamespace:  # noqa: ANN003
    base = dict(banned=[], years_statement="3 years of software engineering experience",
                years_statement_fr=None, language="en", allowed_years={3}, honesty=None)
    return SimpleNamespace(**(base | kw))


def test_wrong_years_wording_becomes_the_approved_wording() -> None:
    text = "I bring 5+ years to this role."
    fix = run(flagged(text), text, _ctx())["claims"][0]["fix"]
    assert fix["kind"] == "replace" and fix["origin"] == "code"
    assert fix["text"] == "I bring 3 years of software engineering experience to this role."


def test_a_wrong_number_becomes_the_one_in_the_source() -> None:
    sources = SOURCES | {"pool:2": "- Cut costs by 37% with a nightly job"}
    row = flagged("I cut costs by 73% with a nightly job.")
    row.source_id, row.source_quote = "pool:2", "Cut costs by 37% with a nightly job"
    out = verifier.run(Scripted(VerifyPlan(claims=[row])), "email", row.sentence, sources,
                       fixer=claim_fix.Fixer(sources))
    assert out["claims"][0]["fix"]["text"] == "I cut costs by 37% with a nightly job."


def test_a_banned_phrase_is_removed_and_a_greeting_gets_the_contact_name() -> None:
    text = "I mentored a junior developer, passionate about data."
    fix = run(flagged(text), text, _ctx(banned=["passionate about data"]))["claims"][0]["fix"]
    assert fix["kind"] == "replace" and fix["origin"] == "code"
    assert "passionate" not in fix["text"] and fix["text"].startswith("I mentored a junior")
    greeting = run(flagged("Hi,", verdict="unsupported"), "Hi,")["claims"][0]["fix"]
    assert greeting["kind"] == "replace" and greeting["text"] == "Hi Ana,"


# ------------------------------------------------------------------------ apply


class Judge:
    """Flags the answer's sentence once (with a suggestion from a real source bullet), then
    supports whatever it is asked about: records every request."""

    model, prompt_version, via, auth_source = "scripted", "verify/test", "test", "none"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.bullet = ""

    def verify(self, request: dict) -> VerifyPlan:
        self.calls.append(request)
        source_id, body = next((k, v) for k, v in request["sources"].items()
                               if k.startswith("pool:") and "\n- " in v)
        self.bullet = body.split("\n- ", 1)[1].splitlines()[0]
        claims = []
        for sentence in verifier.sentences(request["text"]):
            if sentence == "I mentored other developers.":
                claims.append(VerifyClaim(
                    sentence=sentence, claim=sentence, about="candidate", verdict="exaggerated",
                    reason="Not in the sources", suggestion=self.bullet,
                    suggestion_source_id=source_id, suggestion_quote=self.bullet))
            else:
                claims.append(VerifyClaim(sentence=sentence, claim=sentence, about="candidate",
                                          verdict="supported", source_id=source_id,
                                          source_quote=self.bullet))
        return VerifyPlan(claims=claims)


def test_apply_updates_the_text_and_reverifies_only_the_changed_sentence(
        job_ready: dict, client, monkeypatch) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        a = ApplicationAnswer(application_id=job_ready["app"], question="Why us?",
                              answer=f"I mentored other developers. {job_ready['company']} "
                                     "builds data pipelines.")
        s.add(a)
        s.commit()
        answer_id = a.id
    judge = Judge()
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: judge)
    checked = client.post(f"/api/answers/{answer_id}/verify").json()
    assert checked["verification_state"] == "failed"
    flag = next(c for c in checked["verification"]["claims"] if c["verdict"] == "exaggerated")
    assert flag["fix"]["kind"] == "replace" and flag["fix"]["text"] == judge.bullet

    applied = client.post("/api/claim-fixes/apply", json={
        "kind": "answer", "id": answer_id,
        "fixes": [{"sentence": flag["sentence"], "replacement": flag["fix"]["text"]}]})
    assert applied.status_code == 200 and applied.json()["verification_state"] == "passed"
    assert judge.calls[-1]["text"] == judge.bullet  # only the changed sentence was re-verified
    with Session(engine) as s:
        a = s.get(ApplicationAnswer, answer_id)
        assert a.answer.startswith(judge.bullet) and "mentored other" not in a.answer
        assert verifier.state(a.verification, a.answer) == "passed"  # not stale, Copy unlocks


def test_apply_remove_drops_the_sentence_and_a_stale_check_is_refused(
        job_ready: dict, client, monkeypatch) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        a = ApplicationAnswer(application_id=job_ready["app"], question="Why us?",
                              answer="I mentored other developers. Thanks for reading.")
        s.add(a)
        s.commit()
        answer_id = a.id
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: Judge())
    client.post(f"/api/answers/{answer_id}/verify")
    body = {"kind": "answer", "id": answer_id,
            "fixes": [{"sentence": "I mentored other developers.", "replacement": ""}]}
    assert client.post("/api/claim-fixes/apply", json=body).status_code == 200
    with Session(engine) as s:
        assert s.get(ApplicationAnswer, answer_id).answer == "Thanks for reading."
    client.patch(f"/api/answers/{answer_id}", json={"answer": "Something else entirely."})
    again = client.post("/api/claim-fixes/apply", json=body)
    assert again.status_code == 409 and "check the claims again" in again.json()["detail"]


def test_apply_on_an_email_edits_its_body_and_reverifies_the_sentence(
        job_ready: dict, client, monkeypatch) -> None:  # noqa: F811, ANN001
    from app.models import OutreachDraft
    from app.services import outreach
    from tests.test_outreach import Script, good_plan

    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    sentence = f"I saw that {job_ready['company']} is hiring a Data Engineer."

    class OneBad(Judge):
        def verify(self, request: dict) -> VerifyPlan:
            plan = super().verify(request)
            for c in plan.claims:
                if c.sentence == sentence:
                    c.verdict, c.suggestion = "unsupported", ""
                elif c.verdict == "supported" and not c.sentence.startswith("Subject"):
                    c.verdict = "not_a_claim"
            return plan

    judge = OneBad()
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: judge)
    out = client.post(f"/api/outreach/drafts/{draft.id}/verify").json()
    flag = next(c for c in out["verification"]["claims"] if c["verdict"] == "unsupported")
    assert flag["sentence"] == sentence and flag["fix"]["kind"] == "remove"
    applied = client.post("/api/claim-fixes/apply", json={
        "kind": "email", "id": draft.id, "fixes": [{"sentence": sentence, "replacement": ""}]})
    assert applied.status_code == 200, applied.text
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft.id)
        assert sentence not in d.body and d.edited
        assert verifier.state(d.verification, verifier.email_text(s, d)) in ("passed", "failed")
