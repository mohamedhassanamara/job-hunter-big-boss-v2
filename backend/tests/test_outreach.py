"""Cold emails: the Claude call (isolated, subscription only), grounding and lint checks, the
retry, approval, test send, and the send queue (timing, caps, failures, restart recovery, CV
lock, tracking). No real email is ever sent: the mailer is the mock."""

from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    Company,
    Contact,
    CVVersion,
    ExperienceItem,
    Job,
    OutreachDraft,
    SendLog,
    SendQueue,
    SendQueueItem,
)
from app.models.base import utcnow
from app.models.enums import CVStatus, DraftStatus, QueueItemStatus, QueueStatus, Stage
from app.providers.base import (
    CVPlan,
    DraftFailed,
    EmailDraftPlan,
    EmailRequest,
    EmailSentence,
    PlanEntry,
    SendFailed,
)
from app.providers.claude_email import ClaudeEmailDrafter
from app.providers.mock import MockMailer
from app.services import cv_service, outreach, send_queue
from app.services import outreach_check as oc
from app.services.cv_pool import load_pool
from tests.test_cv import fake_run

_n = count(1)
NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)


# ------------------------------------------------------------------------------ Claude call


def plan(**kw) -> EmailDraftPlan:  # noqa: ANN003
    base = {"subject": "Data Engineer at Acme", "greeting": "Hi Ana,",
            "sentences": [{"text": "I saw that Acme is hiring a Data Engineer.",
                           "about_job": True}],
            "ask": "Would you be open to a 15-minute call next week?"}
    return EmailDraftPlan.model_validate({**base, **kw})


REQUEST = EmailRequest(job={"title": "Data Engineer", "company": "Acme"},
                       contact={"first_name": "Ana"}, candidate={}, pool={"roles": []})


def test_email_drafter_uses_the_isolated_subscription_call() -> None:
    calls: list = []
    d = ClaudeEmailDrafter(runner=fake_run({"is_error": False,
                                            "structured_output": plan().model_dump()},
                                           calls=calls))
    out = d.draft(REQUEST, feedback="- too long")
    assert out.greeting == "Hi Ana," and d.prompt_version == "outreach/v10"
    cmd, kw = calls[0]
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    assert "REJECTED DRAFT PROBLEMS" in kw["input"] and "EXPERIENCE POOL" in kw["input"]
    system = cmd[cmd.index("--system-prompt") + 1]
    assert "cold email" in system and "rejected by the automatic checks" in system
    with pytest.raises(DraftFailed, match="API key"):
        ClaudeEmailDrafter(runner=fake_run({"is_error": False, "structured_output": {}},
                                           auth="ANTHROPIC_API_KEY")).draft(REQUEST)


# ----------------------------------------------------------------------------------- checks


@pytest.fixture
def ctx(seeded: None) -> oc.Context:
    with Session(engine) as s:
        pool = load_pool(s)
    return oc.Context(pool=pool, allowed_years={3}, company="Acme", first_name="Ana",
                      job_text="Data Engineer\nWe build pipelines with Spark and Kafka for 2M "
                               "users.",
                      other_companies=["Globex"],
                      others=[(9, "Bob (Globex)", "I saw that Globex is hiring a Data Engineer and "
                               "I built pipelines with Spark for years at my last company. Would "
                               "you be open to a 15-minute call next week?")])


def kinds(violations: list[dict]) -> set[str]:
    return {v["type"] for v in violations if v["severity"] == "error"}


def test_a_clean_draft_passes(ctx: oc.Context) -> None:
    role = next(i for i in ctx.pool.items.values() if i.kind == "job" and i.bullets)
    p = plan(sentences=[
        {"text": "I saw that Acme is hiring a Data Engineer for 2M users.", "about_job": True},
        {"text": f"At {role.org}, I built work with {role.tags[0]} that is close to yours.",
         "citations": [role.id]}])
    assert kinds(oc.check_plan(p, ctx)) == set()


@pytest.mark.parametrize(("change", "expected"), [
    ({"sentences": [{"text": "At Acme I ran Kubernetes for 40 teams.", "citations": [1]}]},
     "grounding"),
    ({"sentences": [{"text": "Acme serves 9M users with Snowflake.", "about_job": True}]},
     "grounding"),
    ({"greeting": "Hi Bob,"}, "name"),
    ({"subject": "Hello", "sentences": [{"text": "I saw the role.", "about_job": True}]},
     "company"),
    ({"sentences": [{"text": "Like Globex, Acme is hiring a Data Engineer.",
                     "about_job": True}]}, "company"),
    ({"greeting": "Hi Ana, I hope this email finds you well."}, "banned"),
    ({"sentences": [{"text": "Is Acme hiring a Data Engineer?", "about_job": True}]}, "ask"),
    ({"sentences": [{"text": "Acme is hiring a Data Engineer. " + "word " * 160,
                     "about_job": True}]}, "length"),
])
def test_each_rule_is_enforced(ctx: oc.Context, change: dict, expected: str) -> None:
    assert expected in kinds(oc.check_plan(plan(**change), ctx))


def test_emails_use_only_the_exact_years_statement(ctx: oc.Context) -> None:
    ctx.years_statement = "3 years of software engineering experience"
    ok = plan(sentences=[{"text": "I saw that Acme is hiring a Data Engineer, and I bring 3 "
                                  "years of software engineering experience.", "about_job": True}])
    assert "years" not in kinds(oc.check_plan(ok, ctx))
    bad = plan(sentences=[{"text": "I saw that Acme is hiring, and I have 3+ years in data.",
                           "about_job": True}])
    assert "years" in kinds(oc.check_plan(bad, ctx))
    ctx.years_statement = None


def test_durations_in_the_ask_are_not_claims(ctx: oc.Context) -> None:
    assert "grounding" not in kinds(oc.check_plan(plan(ask="Could we talk for 20 minutes?"), ctx))


def test_near_duplicates_of_other_recipients_are_flagged(ctx: oc.Context) -> None:
    copy = plan(sentences=[{"text": "I saw that Acme is hiring a Data Engineer and I built "
                                    "pipelines with Spark for years at my last company.",
                            "about_job": True}])
    dup = [v for v in oc.check_plan(copy, ctx) if v["type"] == "duplicate"]
    assert dup and dup[0]["severity"] == "warning" and "Bob" in dup[0]["message"]


def test_edited_text_is_rechecked_without_citations(ctx: oc.Context) -> None:
    bad = oc.check_text("Data Engineer at Acme", "Hi Ana,\n\nAt Acme I cut costs by 73% with "
                        "Snowflake.\n\nCould we talk for 15 minutes?", ctx)
    assert {"grounding"} <= kinds(bad)
    ok = oc.check_text("Data Engineer at Acme", "Hi Ana,\n\nI saw that Acme is hiring a Data "
                       "Engineer.\n\nCould we talk for 15 minutes?", ctx)
    assert kinds(ok) == set()


# ------------------------------------------------------------------------------ generation


@pytest.fixture
def job_ready(seeded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A job with an approved CV (PDF faked), a contact with an email, in cv_ready."""
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4 approved")
    monkeypatch.setattr(cv_service, "ensure_pdf", lambda engine, v: pdf)
    n = next(_n)
    with Session(engine) as s:
        role = next(i for i in s.exec(select(ExperienceItem)).all()
                    if i.kind == "job" and i.bullets)
        company = Company(name=f"Outco {n}", normalized_name=f"outco {n}")
        s.add(company)
        s.flush()
        contact = Contact(company_id=company.id, full_name=f"Ana Test{n}", first_name="Ana",
                          title="CTO", email=f"ana{n}@outco.test", normalized_name=f"ana test{n}",
                          role_rank=0, verified_at=utcnow(), verified_how="still_there")
        job = Job(source="adzuna", external_id=f"out-{n}", url="https://example.test",
                  title="Data Engineer", company_id=company.id, dedupe_key=f"out-{n}",
                  description="We build data pipelines.")
        s.add_all([contact, job])
        s.flush()
        app = Application(job_id=job.id, stage=Stage.cv_ready, contact_id=contact.id)
        s.add(app)
        s.flush()
        cv = CVVersion(application_id=app.id, version=1, status=CVStatus.approved,
                       plan={"plan": CVPlan(summary="", summary_short="", roles=[
                           PlanEntry(item_id=role.id, relevance=9)]).model_dump()})
        s.add(cv)
        s.commit()
        return {"app": app.id, "cv": cv.id, "company": company.name, "role": role.id,
                "fact": role.bullets[0], "org": role.org, "email": contact.email, "pdf": pdf,
                "tag": role.tags[0] if role.tags else ""}


class Script:
    """A drafter returning scripted plans; records the feedback it gets."""

    model, prompt_version = "script", "outreach/test"

    def __init__(self, *plans: EmailDraftPlan):
        self.plans, self.feedback = list(plans), []

    def draft(self, request: EmailRequest, feedback: str = "") -> EmailDraftPlan:
        self.feedback.append(feedback)
        assert request.pool["roles"], "the CV's items are what the email may cite"
        return self.plans.pop(0)


def good_plan(info: dict) -> EmailDraftPlan:
    return plan(subject=f"Data Engineer at {info['company']}", sentences=[
        EmailSentence(text=f"I saw that {info['company']} is hiring a Data Engineer.",
                      about_job=True),
        EmailSentence(text=f"At {info['org']}, I built data work with {info['tag']} that is "
                           "close to what your team does.", citations=[info["role"]])])


def test_generate_retries_once_with_the_problems_then_stores_the_draft(job_ready: dict) -> None:
    bad = plan(subject="Hi", greeting="Hi Bob,")
    drafter = Script(bad, good_plan(job_ready))
    draft = outreach.generate(engine, job_ready["app"], drafter)
    assert drafter.feedback[0] == "" and "first name" in drafter.feedback[1]
    assert draft.plan["attempts"] == 2 and oc.errors(draft.violations) == []
    assert draft.cv_version_id == job_ready["cv"] and draft.body.startswith("Hi Ana,")
    with Session(engine) as s:
        body = outreach.full_body(s, s.get(OutreachDraft, draft.id))
    assert body.rstrip().endswith("Alex Sample")  # signature added by code; no last line


def test_a_still_failing_draft_is_kept_with_its_problems_and_cant_be_approved(
        job_ready: dict, client) -> None:  # noqa: ANN001
    bad = plan(greeting="Hi Bob,")
    draft = outreach.generate(engine, job_ready["app"], Script(bad, bad))
    assert "name" in kinds(draft.violations)
    r = client.post(f"/api/outreach/drafts/{draft.id}/approve")
    assert r.status_code == 409 and "problem" in r.json()["detail"]


def test_generate_needs_an_approved_cv_and_runs_one_at_a_time(job_ready: dict) -> None:
    with Session(engine) as s:
        cv = s.get(CVVersion, job_ready["cv"])
        cv.status = CVStatus.draft
        s.add(cv)
        s.commit()
    with pytest.raises(outreach.OutreachError, match="Approve the CV"):
        outreach.generate(engine, job_ready["app"], Script())
    assert outreach._one_at_a_time.acquire(blocking=False)
    try:
        with pytest.raises(outreach.OutreachError, match="one at a time"):
            outreach.generate(engine, job_ready["app"], Script())
    finally:
        outreach._one_at_a_time.release()


# ------------------------------------------------------------------------------ sending


def mark_verified(s: Session, d: OutreachDraft) -> None:
    """What a passed approval leaves: a verification of this exact text and CV."""
    from app.services import verifier

    d.verification = {"status": "passed", "claims": [],
                      "hash": verifier.text_hash(verifier.email_text(s, d)),
                      "attachment_sha256": verifier.email_attachment(s, d)}
    s.add(d)


def approved(job_ready: dict) -> int:
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft.id)
        mark_verified(s, d)
        assert send_queue.enqueue(s, d)
        s.commit()
    return draft.id


def test_the_send_gate_returns_changed_or_unverified_emails_to_review(
        job_ready: dict, fresh_queue: None) -> None:
    draft_id = approved(job_ready)
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        d.body = d.body + " Also, I mentored ten developers."  # changed after verification
        s.add(d)
        send_queue.resume(s, NOW)
        s.commit()
    mailer = MockMailer()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "blocked"
    assert mailer.sent == []
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        item = s.exec(select(SendQueueItem).where(SendQueueItem.draft_id == draft_id)).one()
        assert d.status == DraftStatus.draft and item.status == QueueItemStatus.cancelled
        assert "text changed" in item.error and any(
            v["type"] == "send_gate" for v in d.violations)
        assert send_queue.queue(s).next_send_at == NOW  # the next email isn't held up


def test_the_send_gate_checks_the_attached_cv(job_ready: dict, fresh_queue: None) -> None:
    draft_id = approved(job_ready)
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        d.verification = {**d.verification, "attachment_sha256": "0" * 64}
        s.add(d)
        send_queue.resume(s, NOW)
        s.commit()
    mailer = MockMailer()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "blocked" and mailer.sent == []
    with Session(engine) as s:
        item = s.exec(select(SendQueueItem).where(SendQueueItem.draft_id == draft_id)).one()
        assert "attached CV changed" in item.error


@pytest.fixture
def fresh_queue(seeded: None) -> None:
    with Session(engine) as s:
        for item in s.exec(select(SendQueueItem)).all():
            s.delete(item)
        q = send_queue.queue(s)
        q.status, q.next_send_at, q.interval_minutes, q.max_items = QueueStatus.idle, None, 15, 20
        s.add(q)
        s.commit()


def test_test_send_goes_to_you_with_the_cv_and_changes_nothing(job_ready: dict) -> None:
    draft_id = approved(job_ready)
    mailer = MockMailer()
    with Session(engine) as s:
        s.exec(select(SendLog)).all()
    log = outreach.test_send(engine, draft_id, mailer)
    email = mailer.sent[0]
    assert log.status == "sent" and email.subject.startswith("[TEST] ")
    assert email.to != job_ready["email"] and email.attachment_path == str(job_ready["pdf"])
    assert "Best regards," in email.body
    with Session(engine) as s:
        assert s.get(Application, job_ready["app"]).stage == Stage.cv_ready  # not sent
        assert s.get(OutreachDraft, draft_id).test_sent_at is not None


def test_the_queue_needs_a_test_send_first(seeded: None) -> None:
    with Session(engine) as s:
        for row in s.exec(select(SendLog)).all():
            s.delete(row)
        s.flush()
        with pytest.raises(send_queue.QueueError, match="test email"):
            send_queue.resume(s)
        s.rollback()


def test_one_send_per_interval_then_tracking_and_cv_lock(job_ready: dict,
                                                         fresh_queue: None) -> None:
    draft_id = approved(job_ready)
    mailer = MockMailer()
    with Session(engine) as s:
        send_queue.resume(s, NOW)
        s.commit()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "sent"
    assert mailer.sent[0].to == job_ready["email"] and not mailer.sent[0].subject.startswith("[")
    assert send_queue.tick(engine, lambda s: mailer, NOW + timedelta(minutes=14)) in (
        "waiting", "empty")
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        assert (app.stage, app.applied_method) == (Stage.done, "email")
        assert app.applied_cv_version_id == job_ready["cv"]
        assert s.get(CVVersion, job_ready["cv"]).locked_at is not None
        assert s.get(OutreachDraft, draft_id).status == DraftStatus.sent
        assert s.exec(select(SendLog).where(SendLog.draft_id == draft_id,
                                            SendLog.kind == "real")).one().status == "sent"
        assert send_queue.queue(s).next_send_at == NOW + timedelta(minutes=15)


def test_the_queue_holds_at_most_max_items(job_ready: dict, fresh_queue: None) -> None:
    draft_id = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready))).id
    with Session(engine) as s:
        q = send_queue.queue(s)
        q.max_items = 0
        s.add(q)
        assert not send_queue.enqueue(s, s.get(OutreachDraft, draft_id))
        s.rollback()


def test_failures_are_logged_retryable_and_auth_errors_pause(job_ready: dict,
                                                            fresh_queue: None) -> None:
    approved(job_ready)
    mailer = MockMailer()
    mailer.fail = SendFailed("Recipient refused: x")
    with Session(engine) as s:
        send_queue.resume(s, NOW)
        s.commit()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "failed"
    with Session(engine) as s:
        item = s.exec(select(SendQueueItem)).one()
        assert item.status == QueueItemStatus.failed and "refused" in item.error
        assert send_queue.queue(s).status == QueueStatus.running
        assert s.exec(select(SendLog).where(SendLog.status == "failed")).first() is not None
        send_queue.retry(s, item)
        s.commit()
    mailer.fail = SendFailed("Gmail refused the login", fatal=True)
    assert send_queue.tick(engine, lambda s: mailer, NOW + timedelta(minutes=16)) == \
        "failed (queue paused)"
    with Session(engine) as s:
        assert send_queue.queue(s).status == QueueStatus.paused


def test_restart_never_resends_an_email_that_was_being_sent(job_ready: dict,
                                                           fresh_queue: None) -> None:
    approved(job_ready)
    with Session(engine) as s:
        item = s.exec(select(SendQueueItem)).one()
        item.status = QueueItemStatus.sending  # the app stopped mid-send
        s.add(item)
        s.commit()
    assert send_queue.recover(engine) == 1
    mailer = MockMailer()
    with Session(engine) as s:
        send_queue.resume(s, NOW)
        s.commit()
    send_queue.tick(engine, lambda s: mailer, NOW)
    assert mailer.sent == []
    with Session(engine) as s:
        item = s.exec(select(SendQueueItem)).one()
        assert item.status == QueueItemStatus.unknown
        send_queue.mark_sent(s, item, NOW)
        s.commit()
        assert s.get(Application, job_ready["app"]).stage == Stage.done


def test_queue_survives_restarts_because_it_lives_in_the_db(job_ready: dict,
                                                           fresh_queue: None) -> None:
    approved(job_ready)
    with Session(engine) as s:
        send_queue.resume(s, NOW)
        s.commit()
    with Session(engine) as s:  # a "new process": state comes back from the database
        q = s.exec(select(SendQueue)).one()
        assert q.status == QueueStatus.running
        assert s.exec(select(SendQueueItem)).one().status == QueueItemStatus.pending



def test_the_signature_ends_with_the_name_unless_contacts_are_on() -> None:
    cfg = {"sign_off": "Best regards,",
           "signature": {"name": "Alex", "title": "Engineer", "email": "a@x.test",
                         "phone": "+1 555", "linkedin": "https://www.linkedin.com/in/alex/",
                         "show_phone": False}}
    assert outreach.signature_block(cfg) == "Best regards,\nAlex"
    cfg["signature"]["show_contacts"] = True
    block = outreach.signature_block(cfg)
    assert "+1 555" not in block and "linkedin.com/in/alex" in block and "a@x.test" in block
    cfg["signature"]["show_phone"] = True
    assert "+1 555" in outreach.signature_block(cfg)


def test_the_phone_toggle_saves_from_settings(client) -> None:  # noqa: ANN001
    value = client.get("/api/settings").json()["values"]["outreach"]
    value["signature"] = {**value["signature"], "show_phone": True}
    assert client.put("/api/settings/outreach", json={"value": value}).status_code == 200
    value["signature"]["show_phone"] = "yes"
    assert client.put("/api/settings/outreach", json={"value": value}).status_code == 422
    value["signature"]["show_phone"] = False
    assert client.put("/api/settings/outreach", json={"value": value}).status_code == 200


def test_the_subject_says_who_and_which_company() -> None:
    from app.services import intro_check as ic

    assert ic.subject_line("Zaion", "en") == "Software engineer interested in joining Zaion"
    assert ic.subject_line("  Zaion  SAS ", "fr") == "Ingénieur logiciel intéressé par Zaion SAS"
    assert ic.subject_line("", "en") == "Software engineer"
