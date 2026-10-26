"""Claim verification in the background: verify after a draft, one regeneration with the failing
claims as feedback (then stop), and re-verify only when the text or the sources changed."""

from datetime import timedelta

from sqlmodel import Session, select

from app.db import engine
from app.models import AppSetting, OutreachDraft
from app.models.base import utcnow
from app.models.enums import DraftStatus
from app.providers.base import VerifyClaim, VerifyPlan
from app.providers.mock import MockEmailDrafter
from app.services import auto_verify, outreach, verifier
from tests.test_applied_email import plan
from tests.test_outreach import job_ready  # noqa: F401 (fixture)


class Judge:
    """A verifier that judges every sentence: all fine, or its first sentence unsupported."""

    model, prompt_version, via, auth_source = "judge", "verify/test", "test", "none"

    def __init__(self, verdicts: list[str]):
        self.verdicts, self.calls = list(verdicts), []

    def verify(self, request: dict) -> VerifyPlan:
        self.calls.append(request)
        verdict = self.verdicts.pop(0) if self.verdicts else "pass"
        claims = []
        for i, sentence in enumerate(verifier.sentences(request["text"])):
            bad = verdict == "fail" and i == 0
            claims.append(VerifyClaim(
                sentence=sentence, claim=sentence, about="candidate" if bad else "other",
                verdict="unsupported" if bad else "not_a_claim",
                reason="Not in the sources" if bad else "No factual content"))
        return VerifyPlan(claims=claims)


def drafter_for(job_ready: dict, seen: list[str]):  # noqa: F811, ANN201
    class Drafter(MockEmailDrafter):
        def draft_applied(self, request, feedback: str = ""):  # noqa: ANN001, ANN202
            seen.append(feedback or (request.rules.get("revision") or {}).get("feedback", ""))
            return plan(job_ready)

    return Drafter()


def first_draft(job_ready: dict, drafter) -> int:  # noqa: F811, ANN001
    return outreach.generate_applied(engine, job_ready["app"], drafter).id


def test_a_passing_draft_is_verified_once_and_not_regenerated(
        job_ready: dict, monkeypatch) -> None:  # noqa: F811, ANN001
    judge, seen = Judge(["pass"]), []
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: judge)
    drafter = drafter_for(job_ready, seen)
    draft_id = first_draft(job_ready, drafter)
    final, info = auto_verify.verify_after_draft(engine, draft_id, drafter=drafter)
    assert final == draft_id and len(judge.calls) == 1 and len(seen) == 1
    assert info["verify"] == "passed" and info["verify_attempts"] == 1
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        assert verifier.state(d.verification, verifier.email_text(s, d), verifier.pool_stamp(s)) \
            == "passed"


def test_a_failed_draft_is_regenerated_once_with_its_verdicts_then_left_alone(
        job_ready: dict, monkeypatch) -> None:  # noqa: F811, ANN001
    judge, seen = Judge(["fail", "fail", "fail"]), []
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: judge)
    drafter = drafter_for(job_ready, seen)
    draft_id = first_draft(job_ready, drafter)
    final, info = auto_verify.verify_after_draft(engine, draft_id, drafter=drafter)
    assert final != draft_id
    assert len(seen) == 2 and "don't support" in seen[1] and "Not in the sources" in seen[1]
    assert len(judge.calls) == 2  # exactly one regeneration, verified once: never a third call
    assert info["verify_attempts"] == 2 and info["verify"] == "failed"
    with Session(engine) as s:
        old, new = s.get(OutreachDraft, draft_id), s.get(OutreachDraft, final)
        assert old.status == DraftStatus.rejected and new.status == DraftStatus.draft
        assert new.parent_id == draft_id and new.verification["status"] == "failed"


def test_a_failed_draft_whose_revision_passes_is_left_verified(
        job_ready: dict, monkeypatch) -> None:  # noqa: F811, ANN001
    judge, seen = Judge(["fail", "pass"]), []
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: judge)
    drafter = drafter_for(job_ready, seen)
    final, info = auto_verify.verify_after_draft(
        engine, first_draft(job_ready, drafter), drafter=drafter)
    assert info["verify"] == "passed"
    with Session(engine) as s:
        assert s.get(OutreachDraft, final).verification["status"] == "passed"


def test_a_verifier_that_cannot_run_never_triggers_a_rewrite(
        job_ready: dict, monkeypatch) -> None:  # noqa: F811, ANN001
    from app.providers.base import DraftFailed

    class Down(Judge):
        def verify(self, request: dict) -> VerifyPlan:
            raise DraftFailed("claude is not installed")

    seen: list[str] = []
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: Down([]))
    drafter = drafter_for(job_ready, seen)
    draft_id = first_draft(job_ready, drafter)
    final, info = auto_verify.verify_after_draft(engine, draft_id, drafter=drafter)
    assert final == draft_id and len(seen) == 1 and info["verify"] == "error"


def test_code_check_errors_come_first_and_claude_is_not_called(
        job_ready: dict, monkeypatch) -> None:  # noqa: F811, ANN001
    judge, seen = Judge([]), []
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: judge)
    drafter = drafter_for(job_ready, seen)
    draft_id = first_draft(job_ready, drafter)
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        d.violations = [{"type": "x", "severity": "error", "message": "m", "where": "body"}]
        s.add(d)
        s.commit()
    final, info = auto_verify.verify_after_draft(engine, draft_id, drafter=drafter)
    assert final == draft_id and judge.calls == [] and info["verify"].startswith("skipped")


def test_an_edit_or_a_changed_pool_makes_it_stale_and_it_is_verified_again_once(
        job_ready: dict, monkeypatch) -> None:  # noqa: F811, ANN001
    judge, seen = Judge([]), []
    monkeypatch.setattr(verifier, "for_workspace", lambda s, w: judge)
    drafter = drafter_for(job_ready, seen)
    draft_id = first_draft(job_ready, drafter)
    auto_verify.verify_after_draft(engine, draft_id, drafter=drafter)
    with Session(engine) as s:
        assert auto_verify.stale_drafts(s) == []  # nothing changed: nothing to do
    assert auto_verify.stale_tick(engine) is False and len(judge.calls) == 1

    with Session(engine) as s:  # you edit the text
        d = s.get(OutreachDraft, draft_id)
        d.body = d.body + " Thanks for reading."
        d.edited = True
        s.add(d)
        s.commit()
        assert auto_verify.stale_drafts(s) == []  # still within the quiet minute: typing
        d.updated_at = utcnow() - timedelta(minutes=5)
        s.add(d)
        s.commit()
        assert [x.id for x in auto_verify.stale_drafts(s)] == [draft_id]
    assert auto_verify.stale_tick(engine) is True and len(judge.calls) == 2
    assert auto_verify.stale_tick(engine) is False  # once per change

    with Session(engine) as s:  # your profile (a source of the claims) changes
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
        row.value = {**row.value, "location": "somewhere else"}
        row.updated_at = utcnow() + timedelta(seconds=5)
        s.add(row)
        s.commit()
        d = s.get(OutreachDraft, draft_id)
        assert verifier.state(d.verification, verifier.email_text(s, d),
                              verifier.pool_stamp(s)) == "stale"
    assert auto_verify.stale_tick(engine) is True and len(judge.calls) == 3
    assert auto_verify.stale_tick(engine) is False
