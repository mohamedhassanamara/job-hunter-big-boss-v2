"""The email step's four additions: the writing-language rule (German listing → English), regenerate
with feedback and a draft history (emails, LinkedIn, letters), approval without verification, and
"copy for another AI" with a pasted draft brought back through the checks. Offline: scripted
drafters and verifiers, never a model."""

from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    AppSetting,
    Company,
    Contact,
    EmailExample,
    Job,
    OutreachDraft,
    SendQueueItem,
)
from app.models.enums import DraftStatus, QueueItemStatus
from app.providers.base import AppliedEmailPlan, EmailSentence, VerifyClaim, VerifyPlan
from app.providers.claude_email import ClaudeEmailDrafter
from app.providers.mock import MockEmailDrafter, MockMailer
from app.services import external_ai, language, outreach, send_queue, verifier
from app.services.cv_pool import load_pool
from app.services.text import detect_language
from tests.test_outreach import NOW, fake_run, fresh_queue, job_ready  # noqa: F401 (fixtures)

GERMAN = ("Das erwartet dich: Wir entwickeln mobile Apps für Patient:innen. Du bist Teil eines "
          "Teams, das die App mit Flutter weiterentwickelt und du kümmerst dich um die "
          "Schnittstellen zum Backend. Wir bieten dir flexible Arbeitszeiten und ein starkes "
          "Team. Was du mitbringst: Erfahrung mit Flutter und die Lust, neue Dinge zu lernen.")
FRENCH = ("Nous recherchons un développeur pour notre équipe. Vous travaillerez avec les "
          "équipes produit sur une application mobile, et vous participerez à la mise en "
          "production. Votre expérience avec Flutter est un vrai plus pour ce poste, chez nous.")
ENGLISH = ("We are looking for an engineer to join our team. You will work with the product "
           "team on a mobile app, and you will take part in the release process for our users.")
PROFILE = {"languages": [{"language": "Arabic", "level": "Native"},
                         {"language": "English", "level": "Full professional"},
                         {"language": "French", "level": "Full professional"},
                         {"language": "Spanish", "level": "Limited working"}]}


# ================================================================== 1. the language rule


def test_a_german_listing_is_no_longer_read_as_french() -> None:
    """The old detector voted between French and English only: the German "du" and "des" (also
    French words) beat the English ones. German is now detected as German."""
    assert language.detect(GERMAN)[0] == "de"
    assert detect_language(GERMAN) == "en"  # letters and notes: French only when really French
    assert detect_language(FRENCH) == "fr" and detect_language(ENGLISH) == "en"


def test_a_german_listing_gets_an_english_email_because_german_isnt_a_working_language() -> None:
    choice = language.choose(GERMAN, PROFILE)
    assert (choice.language, choice.detected, choice.source) == ("en", "de", "auto")
    assert "German" in choice.reason and "isn't a working language" in choice.reason


def test_a_french_listing_gets_french_when_you_speak_it_and_english_when_you_dont() -> None:
    assert language.choose(FRENCH, PROFILE).language == "fr"
    no_french = {"languages": [{"language": "English", "level": "Native"}]}
    choice = language.choose(FRENCH, no_french)
    assert choice.language == "en" and choice.detected == "fr"
    limited = {"languages": [{"language": "French", "level": "Limited working"}]}
    assert language.choose(FRENCH, limited).language == "en"


def test_a_short_english_snippet_with_a_german_body_is_german_so_the_email_is_english() -> None:
    snippet = "Mobile Engineer (m/w/d) – Flutter\nRemote, Köln\n\n" + GERMAN[:170]
    choice = language.choose(snippet, PROFILE)
    assert choice.detected == "de" and choice.language == "en"
    # and a listing with nothing to go on stays English, never French by accident
    assert language.choose("Flutter Engineer", PROFILE).language == "en"


def test_a_language_you_speak_but_the_app_cant_write_falls_back_to_english_and_says_so() -> None:
    arabic = "نبحث عن مهندس تطبيقات الجوال للانضمام إلى فريقنا في الرياض " * 3
    choice = language.choose(arabic, PROFILE)
    assert choice.detected == "ar" and choice.language == "en"
    assert "English or French only" in choice.reason


def test_an_explicit_choice_always_wins_and_the_reason_says_so() -> None:
    assert language.choose(GERMAN, PROFILE, override="fr").language == "fr"
    assert language.choose(GERMAN, PROFILE, job_setting="fr").source == "job"
    assert language.choose(GERMAN, PROFILE, setting="fr").source == "setting"
    picked = language.choose(ENGLISH, PROFILE, override="fr")
    assert picked.source == "override" and "your choice for this draft" in picked.reason


def test_the_draft_stores_the_language_and_why_and_a_picked_language_sticks(
        job_ready: dict, client) -> None:  # noqa: ANN001, F811
    with Session(engine) as s:
        job = s.get(Job, s.get(Application, job_ready["app"]).job_id)
        job.description = GERMAN
        s.add(job)
        s.commit()
    first = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    choice = first.plan["language_choice"]
    assert first.plan["language"] == "en" and choice["detected"] == "de"
    out = client.get(f"/api/outreach/drafts/{first.id}").json()
    assert out["language"] == "en" and out["language_detected"] == "de"
    assert "German" in out["language_reason"] and out["language_source"] == "auto"
    # the dropdown: regenerate in French; the choice stays for the next regeneration …
    second = outreach.generate(engine, job_ready["app"], MockEmailDrafter(), language="fr")
    assert second.plan["language"] == "fr" and second.plan["language_choice"]["source"] == \
        "override"
    third = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    assert third.plan["language"] == "fr"
    # … until you pick Automatic again
    fourth = outreach.generate(engine, job_ready["app"], MockEmailDrafter(), language="auto")
    assert fourth.plan["language"] == "en" and fourth.plan["language_choice"]["source"] == "auto"


def test_the_api_takes_a_language_and_refuses_others(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    r = client.post(f"/api/applications/{job_ready['app']}/draft/generate",
                    json={"language": "de"})
    assert r.status_code == 422


def test_the_job_language_setting_still_applies_to_emails(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        app.letter_language = "fr"
        s.add(app)
        job = s.get(Job, app.job_id)
        job.description = ENGLISH
        s.add(job)
        s.commit()
        assert outreach.language_choice(s, job, app).source == "job"
        assert outreach.email_language(s, job, app) == "fr"


# ============================================================= 2. regenerate with feedback


class Spy:
    """A drafter that records each request and returns the next scripted plan."""

    model, prompt_version, via = "spy", "outreach/test", "test"

    def __init__(self, *plans: AppliedEmailPlan):
        self.plans, self.requests = list(plans), []

    def draft_applied(self, request, feedback: str = ""):  # noqa: ANN001, ANN201
        self.requests.append(request)
        return self.plans.pop(0)


def applied_plan(info: dict, **kw) -> AppliedEmailPlan:  # noqa: ANN003
    base = dict(
        role="Data Engineer", greeting="Hi Ana,",
        opening="I'm applying for the Data Engineer role and wanted to reach out directly.",
        experience=[EmailSentence(
            text=f"At {info['org']}, I built data pipelines with {info['tag']}, from the first "
                 "design to production, for a small team.", citations=[info["role"]])],
        ask="Would you take a look at my CV? It's attached.")
    return AppliedEmailPlan(**{**base, **kw})


def test_regenerating_with_feedback_edits_the_previous_draft_and_keeps_every_version(
        job_ready: dict) -> None:  # noqa: F811
    spy = Spy(applied_plan(job_ready), applied_plan(job_ready, ask="A short call, perhaps?"))
    first = outreach.generate(engine, job_ready["app"], spy)
    second = outreach.generate(engine, job_ready["app"], spy, feedback="Make the ask a call")
    assert "revision" not in spy.requests[0].rules
    rev = spy.requests[1].rules["revision"]
    assert rev["previous_body"] == first.body and rev["feedback"] == "Make the ask a call"
    assert spy.requests[1].pool and spy.requests[1].candidate  # the normal sources stay
    assert (second.parent_id, second.feedback) == (first.id, "Make the ask a call")
    with Session(engine) as s:
        assert s.get(OutreachDraft, first.id).status == DraftStatus.rejected  # kept, not deleted
        history = outreach.draft_history(s, job_ready["app"])
    assert [h["version"] for h in history] == [2, 1]
    assert history[0]["feedback"] == "Make the ask a call" and history[0]["parent_id"] == first.id
    assert history[0]["current"] and not history[1]["current"]


def test_the_facts_checks_still_apply_to_a_revision(job_ready: dict) -> None:  # noqa: F811
    spy = Spy(applied_plan(job_ready), applied_plan(job_ready, experience=[EmailSentence(
        text="I built it with Kafka and Terraform at scale.", citations=[job_ready["role"]])]),
        applied_plan(job_ready, experience=[EmailSentence(
            text="I built it with Kafka and Terraform at scale.",
            citations=[job_ready["role"]])]))
    outreach.generate(engine, job_ready["app"], spy)
    revised = outreach.generate(engine, job_ready["app"], spy, feedback="Mention Kafka")
    assert any(v["type"] == "grounding" and v["severity"] == "error" for v in revised.violations)


def test_going_back_restores_an_older_version(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    spy = Spy(applied_plan(job_ready), applied_plan(job_ready, ask="Call me?"))
    first = outreach.generate(engine, job_ready["app"], spy)
    second = outreach.generate(engine, job_ready["app"], spy, feedback="Ask for a call")
    r = client.post(f"/api/outreach/drafts/{first.id}/restore")
    assert r.status_code == 200 and r.json()["status"] == "draft"
    with Session(engine) as s:
        assert s.get(OutreachDraft, second.id).status == DraftStatus.rejected  # one under review
    hist = client.get(f"/api/applications/{job_ready['app']}/draft/history").json()
    assert [(h["version"], h["current"]) for h in hist] == [(2, False), (1, True)]


def test_the_claude_drafter_sends_the_previous_draft_and_the_feedback_with_the_revise_rules(
        job_ready: dict) -> None:  # noqa: F811
    calls: list = []
    spy = Spy(applied_plan(job_ready))
    spy_plan = applied_plan(job_ready)
    drafter = ClaudeEmailDrafter(runner=fake_run({"is_error": False,
                                                  "structured_output": spy_plan.model_dump()},
                                                 calls=calls))
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        job = s.get(Job, app.job_id)
        cv = outreach.approved_cv(s, app)
        contact = s.get(Contact, app.contact_id)
        request = outreach.applied_request(s, app, job, s.get(Company, job.company_id), contact,
                                           cv, load_pool(s), "en")
    outreach.add_revision(request, OutreachDraft(subject="S", body="Hi Ana,\n\nOld body."),
                          "shorter please")
    drafter.draft_applied(request)
    cmd, kw = calls[0]
    system = cmd[cmd.index("--system-prompt") + 1]
    assert "PREVIOUS DRAFT (edit this)" in kw["input"] and "Old body." in kw["input"]
    assert "WHAT THE USER WANTS CHANGED\nshorter please" in kw["input"]
    assert "Edit the previous draft toward that feedback" in system
    assert "revision" not in kw["input"].split("PREVIOUS DRAFT")[0]  # not leaked into RULES
    assert spy.requests == []


def test_linkedin_feedback_edits_the_message_and_every_version_can_be_restored(
        seeded: None) -> None:
    from app.providers.mock import MockLinkedInDrafter
    from app.services import linkedin_track as lt
    from tests.test_linkedin_inmail import job_with_people, person

    seen: list = []

    class Drafter(MockLinkedInDrafter):
        def draft(self, request, feedback: str = ""):  # noqa: ANN001, ANN201
            seen.append(request.rules.get("revision"))
            return super().draft(request, feedback)

    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        s.commit()
        rid = row.id
    first = lt.draft_note(engine, rid, Drafter())
    second = lt.draft_note(engine, rid, Drafter(), feedback="warmer")
    assert seen[0] is None and seen[1]["feedback"] == "warmer"
    assert seen[1]["previous_text"] == first.note["text"] or second.note["history"]
    assert second.note["feedback"] == "warmer"
    assert len(second.note["history"]) == 1
    with Session(engine) as s:
        row = s.get(type(second), rid)
        lt.restore_version(s, row, "note", 0)
        s.commit()
        assert row.note["feedback"] == "" and row.note["text"] == first.note["text"]
        assert row.note["history"][0]["feedback"] == "warmer"  # the other one is kept
        assert "verification" not in row.note  # the restored text is verified again


# =========================================================== 3. approval without verification


def draft_with_errors(job_ready: dict) -> int:  # noqa: F811
    bad = applied_plan(job_ready, experience=[EmailSentence(
        text="I built it with Kafka and Terraform at scale.", citations=[job_ready["role"]])])
    return outreach.generate(engine, job_ready["app"], Spy(bad, bad)).id


def test_approving_without_verification_needs_a_confirmation_and_skips_the_verifier(
        job_ready: dict, client) -> None:  # noqa: ANN001, F811
    draft_id = draft_with_errors(job_ready)  # a draft with a blocking error
    assert client.post(f"/api/outreach/drafts/{draft_id}/approve").status_code == 409
    assert client.post(f"/api/outreach/drafts/{draft_id}/approve-unverified",
                       json={"confirm": False}).status_code == 422
    r = client.post(f"/api/outreach/drafts/{draft_id}/approve-unverified",
                    json={"confirm": True})
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "approved" and out["verification"] in ({}, None)
    approval = out["unverified_approval"]
    assert approval["at"] and approval["verification_state"] == "none"
    types = {i["type"] for i in approval["ignored"]}
    assert {"grounding", "verification"} <= types  # the error and the skipped verifier are listed
    severities = {i["severity"] for i in approval["ignored"] if i["type"] == "grounding"}
    assert severities == {"error"}


def test_it_is_marked_on_the_draft_in_the_queue_and_on_the_job_step(
        job_ready: dict, client, fresh_queue: None) -> None:  # noqa: ANN001, F811
    draft_id = draft_with_errors(job_ready)
    client.post(f"/api/outreach/drafts/{draft_id}/approve-unverified", json={"confirm": True})
    assert client.post(f"/api/outreach/drafts/{draft_id}/queue").status_code == 200
    queue = client.get("/api/queue").json()
    assert [i["unverified"] for i in queue["items"]] == [True]
    step = client.get(f"/api/applications/{job_ready['app']}/outreach").json()
    assert step["draft"]["unverified_approval"]["ignored"]


def test_a_normal_approval_is_not_marked(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    out = client.post(f"/api/outreach/drafts/{d.id}/approve").json()
    assert out["status"] == "approved" and out["unverified_approval"] is None


def sent_gate_setup(job_ready: dict, client) -> int:  # noqa: ANN001, F811
    draft_id = draft_with_errors(job_ready)
    client.post(f"/api/outreach/drafts/{draft_id}/approve-unverified", json={"confirm": True})
    assert client.post(f"/api/outreach/drafts/{draft_id}/queue").status_code == 200
    with Session(engine) as s:
        send_queue.resume(s, NOW)
        s.commit()
    return draft_id


def test_the_send_gate_lets_an_unverified_approval_go_when_nothing_changed(
        job_ready: dict, client, fresh_queue: None) -> None:  # noqa: ANN001, F811
    sent_gate_setup(job_ready, client)
    mailer = MockMailer()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "sent"
    assert mailer.sent and mailer.sent[0].to == job_ready["email"]


@pytest.mark.parametrize("change", ["text", "attachment", "contact", "cv_version"])
def test_the_send_gate_still_holds_text_attachment_contact_and_cv_version(
        job_ready: dict, client, fresh_queue: None, change: str) -> None:  # noqa: ANN001, F811
    draft_id = sent_gate_setup(job_ready, client)
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        approval = dict(d.unverified_approval)
        if change == "text":
            d.body += " I also mentored ten developers."
        elif change == "attachment":
            approval["attachment_sha256"] = "0" * 64
        elif change == "contact":
            approval["recipient"] = "someone.else@outco.test"
        else:
            approval["cv_version_id"] = (d.cv_version_id or 0) + 999
        d.unverified_approval = approval
        s.add(d)
        s.commit()
    mailer = MockMailer()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "blocked" and mailer.sent == []
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        item = s.exec(select(SendQueueItem).where(SendQueueItem.draft_id == draft_id)).one()
        assert d.status == DraftStatus.draft and item.status == QueueItemStatus.cancelled
        assert not d.unverified_approval  # approving again is a new decision
        assert any(v["type"] == "send_gate" for v in d.violations)


def test_an_unverified_approval_never_joins_the_regression_set(job_ready: dict,  # noqa: F811
                                                               client) -> None:  # noqa: ANN001
    draft_id = draft_with_errors(job_ready)
    client.post(f"/api/outreach/drafts/{draft_id}/approve-unverified", json={"confirm": True})
    with Session(engine) as s:
        assert s.exec(select(EmailExample).where(EmailExample.draft_id == draft_id)).first() \
            is None


# ================================================================ 4. copy for another AI


def with_profile(extra: dict) -> None:
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).first()
        row.value = {**row.value, **extra}
        s.add(row)
        s.commit()


def test_the_prompt_is_self_contained_and_leaves_private_data_out(job_ready: dict) -> None:  # noqa: F811
    with_profile({"phone": "+216 99 888 777", "email": "me.private@example.com"})
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        job = s.get(Job, app.job_id)
        job.description = "We build data pipelines with Spark for insurers. " * 40
        s.add(job)
        s.add(Contact(company_id=job.company_id, full_name="Other Person", first_name="Other",
                      email="other.person@outco.test", normalized_name="other person"))
        s.commit()
        out = external_ai.build_prompt(s, job_ready["app"], mode="applied")
        company = s.get(Company, job.company_id)
        contact = s.get(Contact, app.contact_id)
    prompt = out["prompt"]
    assert job.description.strip() in prompt  # the full listing
    assert company.name in prompt and contact.full_name in prompt and contact.title in prompt
    assert job_ready["org"] in prompt and job_ready["fact"] in prompt  # the relevant experience
    for private in ("+216", "me.private@example.com", contact.email, "other.person@outco.test",
                    "Other Person"):
        assert private not in prompt
    assert "Write the whole email in English" in prompt and out["language"]["language"] == "en"
    assert "never add a tool" in prompt.lower() or "Never add a tool" in prompt
    assert "at most two proofs" in prompt.lower()
    assert "Only paste it into AI tools you trust" in out["note"]
    assert out["items"] and out["mode"] == "applied"


def test_the_mode_changes_the_structure_and_the_language_rule_is_in_the_prompt(
        job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        job = s.get(Job, s.get(Application, job_ready["app"]).job_id)
        job.description = GERMAN
        s.add(job)
        s.commit()
        applied = external_ai.build_prompt(s, job_ready["app"], mode="applied")
        speculative = external_ai.build_prompt(s, job_ready["app"], mode="speculative")
        french = external_ai.build_prompt(s, job_ready["app"], mode="applied", language="fr")
    assert "application follow-up" in applied["prompt"]
    assert "speculative introduction" in speculative["prompt"]
    assert "application follow-up" not in speculative["prompt"]
    assert applied["language"]["detected"] == "de" and "Write the whole email in English" \
        in applied["prompt"] and "German" in applied["prompt"]
    assert "Write the whole email in French" in french["prompt"]
    assert "Never mention the candidate's location" in speculative["prompt"]


def test_an_approved_example_is_included_for_tone_only(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        s.add(EmailExample(kind="approved", language="en", subject="Role application – Alex",
                           body="Hi Dana,\n\nA sample body for tone.", inputs={"mode": "applied"}))
        s.commit()
        text = external_ai.build_prompt(s, job_ready["app"], mode="applied")["prompt"]
    assert "A sample body for tone." in text and "tone and structure only" in text


def test_the_api_returns_the_prompt(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    r = client.post(f"/api/applications/{job_ready['app']}/external-prompt",
                    json={"mode": "speculative"})
    assert r.status_code == 200 and r.json()["mode"] == "speculative"
    bad = client.post(f"/api/applications/{job_ready['app']}/external-prompt",
                      json={"mode": "x"})
    assert bad.status_code == 422


def test_a_pasted_draft_is_split_into_subject_and_body_without_the_other_ais_sign_off() -> None:
    subject, body = external_ai.split_pasted(
        "**Subject:** Data Engineer application – Alex Sample\n\nHi Ana,\n\nBody here.\n\n"
        "Best regards,\nAlex Sample", "Alex Sample")
    assert subject == "Data Engineer application – Alex Sample"
    assert body == "Hi Ana,\n\nBody here."
    assert external_ai.split_pasted("Hi Ana,\n\nNo subject line.", "Alex Sample") == \
        ("", "Hi Ana,\n\nNo subject line.")


class Judge:
    """A scripted claim verifier: marks every sentence containing "Kafka" unsupported."""

    model, prompt_version, via, auth_source = "judge", "verify/test", "test", "none"

    def verify(self, request: dict) -> VerifyPlan:
        claims = []
        for sentence in verifier.sentences(request["text"]):
            bad = "Kafka" in sentence
            claims.append(VerifyClaim(
                sentence=sentence, claim=sentence, about="candidate",
                verdict="unsupported" if bad else "not_a_claim",
                reason="No source mentions it" if bad else "No factual content"))
        return VerifyPlan(claims=claims)


def test_a_pasted_draft_shows_each_claim_with_its_verdict_and_the_code_checks(
        job_ready: dict) -> None:  # noqa: F811
    pasted = ("Subject: Data Engineer application – Alex Sample\n\nHi Ana,\n\n"
              "I'm applying for the Data Engineer role at Outco.\n\n"
              f"At {job_ready['org']} I ran Kafka clusters with 99.9% uptime.\n\n"
              "Would you take a look at my CV?")
    with Session(engine) as s:
        before = len(s.exec(select(OutreachDraft)).all())
        out = external_ai.check_pasted(s, job_ready["app"], pasted, mode="applied",
                                       verifier_=Judge())
        assert len(s.exec(select(OutreachDraft)).all()) == before  # a check stores nothing
    verdicts = {c["claim"]: c["verdict"] for c in out["verification"]["claims"]}
    assert any(v == "unsupported" for v in verdicts.values())
    assert out["verification"]["status"] == "failed"
    assert any(v["type"] == "grounding" for v in out["violations"])  # code checks run too
    assert out["subject"].startswith("Data Engineer application")


def test_a_checked_draft_can_be_saved_as_a_normal_draft_and_discarding_stores_nothing(
        job_ready: dict, client) -> None:  # noqa: ANN001, F811
    pasted = ("Subject: Data Engineer application – Alex Sample\n\nHi Ana,\n\n"
              "I'm applying for the Data Engineer role at Outco.\n\n"
              f"At {job_ready['org']}, I built data pipelines with {job_ready['tag']}.\n\n"
              "Would you take a look at my CV? It's attached.")
    with Session(engine) as s:
        before = len(s.exec(select(OutreachDraft)).all())
    r = client.post(f"/api/applications/{job_ready['app']}/external-draft/check",
                    json={"text": pasted, "mode": "applied"})
    assert r.status_code == 200 and r.json()["verification"]["status"] in ("passed", "failed")
    with Session(engine) as s:  # a check alone leaves nothing behind
        assert len(s.exec(select(OutreachDraft)).all()) == before
    saved = client.post(f"/api/applications/{job_ready['app']}/external-draft",
                        json={"text": pasted, "mode": "applied"})
    assert saved.status_code == 200
    d = saved.json()
    assert d["source"] == "external" and d["status"] == "draft" and d["mode"] == "applied"
    assert d["body"].startswith("Hi Ana,") and "Best regards" not in d["body"]
    assert d["verification"]  # kept: approval reuses it while the text is unchanged
    edited = client.patch(f"/api/outreach/drafts/{d['id']}",
                          json={"body": d["body"] + " Extra."}).json()
    assert edited["verification_state"] == "stale"


def test_the_check_needs_a_contact_and_some_text(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    assert client.post(f"/api/applications/{job_ready['app']}/external-draft/check",
                       json={"text": "  "}).status_code == 409
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        app.contact_id = None
        s.add(app)
        s.commit()
    r = client.post(f"/api/applications/{job_ready['app']}/external-draft/check",
                    json={"text": "Hi,\n\nSomething long enough to check."})
    assert r.status_code == 409 and "contact" in r.json()["detail"]
    _ = timedelta
