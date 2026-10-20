"""LinkedIn Premium additions: InMail (subject + body, same checks, you send it), InMail credits and
refunds, "viewed my profile" leads with a warm opener that never mentions the visit, and the
Premium end-date reminder. Offline: the mock drafter and the mock verifier, no model."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import engine
from app.models import Application, Company, FitScore, Job, LinkedInLead, LinkedInOutreach
from app.models.base import utcnow
from app.models.enums import LinkedInStatus, Stage
from app.providers.mock import MockLinkedInDrafter
from app.services import linkedin_check as lc
from app.services import linkedin_track as lt
from app.services.dedupe import normalize_company
from tests.test_contacts import make_job
from tests.test_linkedin_track import job_with_people


def person(s: Session, app: Application, name: str = "Maya Rossi", title: str = "Head of Data",
           **kw) -> LinkedInOutreach:
    row = lt.add(s, app, full_name=name, title=title, linkedin_url=None, **kw)
    s.flush()
    return row


def errors(found: list[dict]) -> list[str]:
    return [v["type"] for v in found if v["severity"] == "error"]


def ctx_for(s: Session, row: LinkedInOutreach, kind: str):
    return lt._request(s, row, kind)  # noqa: SLF001


# ------------------------------------------------------------------------------------ InMail


def test_an_inmail_has_a_subject_a_longer_body_and_passes_the_same_checks(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        s.commit()
        rid = row.id
    row = lt.draft_inmail(engine, rid, MockLinkedInDrafter())
    inmail = row.inmail
    assert inmail["subject"].startswith("Interested in the") and len(inmail["text"]) >= 250
    assert inmail["max_chars"] == 1000 and inmail["via"] == "mock"
    assert not errors(inmail["violations"]), inmail["violations"]
    assert "\n\n" in inmail["text"]  # short paragraphs, not a wall of text
    with Session(engine) as s:  # the connection note keeps its own limit
        _req, note_ctx = ctx_for(s, s.get(LinkedInOutreach, rid), "note")
        assert note_ctx.max_chars == 200 and note_ctx.kind == "note"


def test_the_inmail_limit_is_a_setting_and_the_body_is_checked_against_it(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        _req, ctx = ctx_for(s, row, "inmail")
        assert ctx.max_chars == 1000
        body = ("Hi Maya, " + "I build data products and would value your view. " * 30
                + "Could we talk?")
        found = lc.check(body, ctx)
        assert "length" in errors(found) and "limit is 1000" in found[0]["message"]
        short = lc.check("Hi Maya, could we have a short chat about the team?", ctx)
        assert "short" in [v["type"] for v in short]  # a warning, not an error
        s.rollback()


@pytest.mark.parametrize(("subject", "code"), [
    ("", "subject_empty"),
    ("A" * 90, "subject_length"),
    ("Interested in your data role!", "subject_tone"),
    ("See https://example.test/me for the role", "subject_link"),
    ("I would love to connect about data", "banned"),
    ("Thanks for viewing my profile", "viewed"),
    ("Backend engineer, visa needed", "location"),
])
def test_subject_rules(seeded: None, subject: str, code: str) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        _req, ctx = ctx_for(s, row, "inmail")
        assert code in errors(lc.check_subject(subject, ctx)), subject
        s.rollback()


def test_a_plain_subject_passes(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        _req, ctx = ctx_for(s, row, "inmail")
        assert lc.check_subject("Interested in the data engineer opening", ctx) == []
        s.rollback()


def test_inmail_edits_recheck_subject_and_body_and_verification_covers_both(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        s.commit()
        rid = row.id
    lt.draft_inmail(engine, rid, MockLinkedInDrafter())
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, rid)
        lt.edit(s, row, "inmail", subject="Great news!!")
        assert "subject_tone" in errors(row.inmail["violations"]) and row.inmail["edited"]
        before = lc.inmail_text(row.inmail)
        lt.edit(s, row, "inmail", text="Hi Maya, could we talk?")
        assert lc.inmail_text(row.inmail) != before and row.inmail["subject"] == "Great news!!"
        s.rollback()


# ------------------------------------------------------ never mention that they viewed you

BAD = ["I saw that you viewed my profile", "Thanks for checking out my LinkedIn profile",
       "I noticed you looked at my profile last week", "I appreciate your visit",
       "profile views are up this week", "J'ai vu que vous avez consulté mon profil",
       "Merci pour la visite de mon profil", "thanks for looking at my profile"]
FINE = ["I'd value your view on the team", "I saw the data engineer opening on your careers page",
        "Could we have a short chat about how the team works?", "I noticed the opening at Acme",
        "You can see my profile if useful"]


@pytest.mark.parametrize("kind", ["note", "followup", "inmail"])
def test_no_message_may_mention_a_profile_visit_in_any_group(seeded: None, kind: str) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        _req, ctx = ctx_for(s, row, kind)
        for text in BAD:
            assert "viewed" in errors(lc.check(f"Hi Maya, {text}. Could we talk?", ctx)), text
        for text in FINE:
            assert "viewed" not in errors(lc.check(f"Hi Maya, {text}. Could we talk?", ctx)), text
        s.rollback()


def test_a_viewer_lead_gets_a_warm_opener_and_the_model_never_sees_the_reason(
        seeded: None) -> None:
    with Session(engine) as s:
        app, company = job_with_people(s)
        company.name = "Acme Data"
        company.normalized_name = normalize_company("Acme Data")
        s.flush()
        result = lt.add_viewer(s, full_name="Maya Rossi", title="Talent Acquisition Partner",
                               company="Acme Data", linkedin_url=None, viewed_on=date(2026, 10, 20))
        s.commit()
        rid = result["row_id"]
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, rid)
        assert row.source == "viewed_profile" and row.reason == "viewed my profile on 20 Oct"
        request, ctx = ctx_for(s, row, "inmail")
        assert ctx.warm and request.person["warm_opener"] is True
        payload = json.dumps(request.model_dump(), default=str).lower()
        assert "viewed" not in payload and "reason" not in payload  # the reason stays with you
        # a draft that starts cold gets a warning; the mock's warm draft passes
        assert "warm" in [v["type"] for v in lc.check("Interested in the role. Could I send "
                                                       "you my CV?", ctx)]
    row = lt.draft_inmail(engine, rid, MockLinkedInDrafter())
    assert row.inmail["text"].startswith("Hello Maya") and not errors(row.inmail["violations"])
    assert "warm" not in [v["type"] for v in row.inmail["violations"]]


# --------------------------------------------------------------------------------- credits


def sent_inmail(s: Session, row: LinkedInOutreach) -> LinkedInOutreach:
    row.inmail = {"subject": "Interested in the role", "text": "Hi Maya, could we talk? " * 12}
    lt.send_inmail(s, row)
    s.flush()
    return row


def test_sending_an_inmail_uses_a_credit_and_counts_as_messaged(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = person(s, app)
        assert lt.credits(s)["allowance"] == 5 and lt.credits(s)["left"] == 5
        sent_inmail(s, row)
        c = lt.credits(s)
        assert (c["used"], c["refunded"], c["left"]) == (1, 0, 4)
        assert row.status == LinkedInStatus.messaged and row.messaged_at and row.sent_at is None
        assert lt.requests_today(s) == 0  # an InMail is not a connection request
        assert c["recent"][0]["person"] == "Maya Rossi"
        with pytest.raises(lt.LinkedInError, match="already marked sent"):
            lt.send_inmail(s, row)
        s.rollback()


def test_a_reply_within_90_days_gives_the_credit_back_and_undo_takes_it_away(
        seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = sent_inmail(s, person(s, app))
        lt.set_status(s, row, LinkedInStatus.replied)
        c = lt.credits(s)
        assert row.inmail_refunded_at and (c["used"], c["refunded"], c["left"]) == (1, 1, 5)
        lt.set_status(s, row, LinkedInStatus.messaged)  # "they replied" was a mistake
        assert row.inmail_refunded_at is None and lt.credits(s)["left"] == 4
        s.rollback()


def test_a_reply_after_90_days_is_not_refunded(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = sent_inmail(s, person(s, app))
        row.inmail_sent_at = utcnow() - timedelta(days=100)
        lt.set_status(s, row, LinkedInStatus.replied)
        assert row.inmail_refunded_at is None
        s.rollback()


def test_unsending_returns_the_credit_and_the_person_goes_back(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = sent_inmail(s, person(s, app))
        lt.unsend_inmail(s, row)
        assert lt.credits(s)["left"] == 5 and row.status == LinkedInStatus.to_contact
        assert row.messaged_at is None and row.inmail  # the draft is kept
        with pytest.raises(lt.LinkedInError):
            lt.unsend_inmail(s, row)
        s.rollback()


def test_credits_count_by_month_and_a_refund_lands_in_the_month_of_the_reply(
        seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        old = sent_inmail(s, person(s, app, "Old Contact"))
        old.inmail_sent_at = utcnow() - timedelta(days=40)  # an earlier month
        fresh = sent_inmail(s, person(s, app, "Fresh Contact"))
        assert lt.credits(s)["used"] == 1  # last month's InMail is not this month's use
        lt.set_status(s, old, LinkedInStatus.replied)  # reply this month, sent 40 days ago
        c = lt.credits(s)
        assert (c["used"], c["refunded"], c["left"]) == (1, 1, 5)  # the credit came back now
        assert fresh.inmail_refunded_at is None
        s.rollback()


def test_the_allowance_is_a_setting(seeded: None, client: TestClient) -> None:
    cfg = client.get("/api/settings").json()["values"]["linkedin"]
    client.put("/api/settings/linkedin", json={"value": {**cfg, "inmail_monthly_credits": 15}})
    with Session(engine) as s:
        assert lt.credits(s)["allowance"] == 15 and lt.credits(s)["left"] == 15
    bad = client.put("/api/settings/linkedin", json={"value": {**cfg, "inmail_max_chars": 5000}})
    assert bad.status_code == 422
    client.put("/api/settings/linkedin", json={"value": cfg})


# ------------------------------------------------------------------------ Premium reminder


def test_the_premium_reminder_counts_down_and_lists_what_you_got_out_of_it(
        seeded: None, client: TestClient) -> None:
    cfg = client.get("/api/settings").json()["values"]["linkedin"]
    with Session(engine) as s:
        assert lt.premium(s) is None  # no date set: nothing to remind
    today = utcnow().astimezone().date()
    for days, remind, ended in ((40, False, False), (10, True, False), (0, True, False),
                                (-3, True, True)):
        end = (today + timedelta(days=days)).isoformat()
        client.put("/api/settings/linkedin", json={"value": {**cfg, "premium_end_date": end}})
        with Session(engine) as s:
            p = lt.premium(s)
            assert (p["days_left"], p["remind"], p["ended"]) == (days, remind, ended)
            if remind and not ended:
                assert "decide whether to keep it" in p["message"] and "InMail" in p["message"]
            if ended:
                assert "ended" in p["message"]
    assert client.put("/api/settings/linkedin", json={"value": {
        **cfg, "premium_end_date": "next month"}}).status_code == 422
    client.put("/api/settings/linkedin", json={"value": cfg})


# ------------------------------------------------------------------- viewed my profile


def company_with_jobs(s: Session, name: str, scores: list[int | None]) -> tuple[Company, list]:
    company = Company(name=name, normalized_name=normalize_company(name))
    s.add(company)
    s.flush()
    return company, [make_job(s, company, stage=Stage.shortlisted, score=sc) for sc in scores]


def test_a_viewer_is_linked_to_your_best_open_job_at_their_company(seeded: None) -> None:
    with Session(engine) as s:
        company, apps = company_with_jobs(s, "Zephyrine Analytics", [55, 88, 70])
        closed = make_job(s, company, stage=Stage.closed, score=99)
        r = lt.add_viewer(s, full_name="Léa Martin", title="Engineering Manager",
                          company="Zephyrine Analytics S.A.", linkedin_url=None,
                          viewed_on=date(2026, 10, 18))
        assert r["linked"] and r["reason"] == "viewed my profile on 18 Oct"
        assert r["job"]["application_id"] == apps[1].id  # the 88, not the closed 99
        assert [j["application_id"] for j in r["other_jobs"]] == [apps[2].id, apps[0].id]
        row = s.get(LinkedInOutreach, r["row_id"])
        assert row.application_id == apps[1].id and row.source == "viewed_profile"
        assert row.group == "lead"
        assert closed.id not in {j["application_id"] for j in r["other_jobs"]}
        s.rollback()


def test_a_close_company_name_matches_only_when_it_is_unambiguous(seeded: None) -> None:
    with Session(engine) as s:
        company_with_jobs(s, "Delivery Hero", [80])
        r = lt.add_viewer(s, full_name="Sam Ortiz", title="Recruiter",
                          company="Delivery Hero (talabat)", linkedin_url=None)
        assert r["linked"]  # one name contains the other
        company_with_jobs(s, "Delivery Hero Labs", [60])
        again = lt.add_viewer(s, full_name="Kim Bell", title="Recruiter",
                              company="Delivery Hero", linkedin_url=None)
        assert again["linked"]  # exact normalized name wins
        vague = lt.add_viewer(s, full_name="Lee Park", title="Recruiter", company="Delivery",
                              linkedin_url=None)
        assert not vague["linked"]  # "Delivery" fits two companies: held as a lead
        s.rollback()


def test_no_job_at_the_company_keeps_a_lead_that_links_itself_later(seeded: None) -> None:
    with Session(engine) as s:
        r = lt.add_viewer(s, full_name="Ana Silva", title="Talent Partner", company="Brightwave",
                          linkedin_url="https://www.linkedin.com/in/ana-silva/",
                          viewed_on=date(2026, 10, 19))
        assert not r["linked"] and r["lead_id"] and r["row_id"] is None
        assert [x["full_name"] for x in lt.leads(s)] == ["Ana Silva"]
        company, apps = company_with_jobs(s, "Brightwave", [72])  # a job there appears
        assert lt.leads(s) == []  # linked on the next look
        lead = s.get(LinkedInLead, r["lead_id"])
        row = s.get(LinkedInOutreach, lead.linked_outreach_id)
        assert row.application_id == apps[0].id and row.reason == "viewed my profile on 19 Oct"
        s.rollback()


def test_viewer_needs_a_name_and_a_company(seeded: None) -> None:
    with Session(engine) as s:
        with pytest.raises(lt.LinkedInError, match="name"):
            lt.add_viewer(s, full_name=" ", title=None, company="Acme", linkedin_url=None)
        with pytest.raises(lt.LinkedInError, match="company"):
            lt.add_viewer(s, full_name="Max Lee", title=None, company=" ", linkedin_url=None)
        s.rollback()


# -------------------------------------------------------------------------------------- API


def test_api_inmail_flow_gate_credits_and_viewers(seeded: None, client: TestClient) -> None:
    with Session(engine) as s:
        company, apps = company_with_jobs(s, "Quartz Systems", [90])
        s.commit()
        app_id, job_id = apps[0].id, apps[0].job_id
    added = client.post("/api/linkedin/viewers", json={
        "full_name": "Eva Stone", "title": "Head of Data", "company": "Quartz Systems",
        "linkedin_url": "https://www.linkedin.com/in/eva-stone/", "viewed_on": "2026-10-17"}).json()
    assert added["linked"] and added["job"]["job_id"] == job_id
    rid = added["row_id"]
    panel = client.get(f"/api/applications/{app_id}/linkedin").json()
    person_ = next(p for p in panel["people"] if p["id"] == rid)
    assert person_["reason"] == "viewed my profile on 17 Oct"
    assert person_["source"] == "viewed_profile"
    assert panel["credits"]["left"] == 5 and panel["inmail_max_chars"] == 1000
    # draft → can't be marked sent before every claim is verified
    drafted = client.post(f"/api/linkedin/people/{rid}/inmail").json()
    assert drafted["inmail"]["subject"] and drafted["inmail_verification_state"] == "none"
    assert client.post(f"/api/linkedin/people/{rid}/inmail/sent").status_code == 409
    verified = client.post(f"/api/linkedin/people/{rid}/verify", params={"kind": "inmail"}).json()
    assert verified["inmail_verification_state"] == "passed"
    sent = client.post(f"/api/linkedin/people/{rid}/inmail/sent").json()
    assert sent["inmail_sent_at"] and sent["status"] == "messaged"
    assert client.get("/api/linkedin/credits").json()["credits"]["left"] == 4
    # editing after verification makes it stale again (subject is part of what was verified)
    edited = client.patch(f"/api/linkedin/people/{rid}", json={"inmail_subject": "A new subject"})
    assert edited.json()["inmail_verification_state"] == "stale"
    replied = client.post(f"/api/linkedin/people/{rid}/status", json={"status": "replied"}).json()
    assert replied["inmail_refunded_at"]
    assert client.get("/api/linkedin/credits").json()["credits"]["left"] == 5
    undone = client.post(f"/api/linkedin/people/{rid}/inmail/unsent")
    assert undone.status_code == 200 and undone.json()["inmail_sent_at"] is None
    # a lead for a company with no job, then the summary shows it
    lead = client.post("/api/linkedin/viewers", json={
        "full_name": "Zed Park", "company": "Nowhere Labs"}).json()
    assert not lead["linked"]
    assert [x["full_name"] for x in client.get("/api/linkedin/leads").json()] == ["Zed Park"]
    assert client.get("/api/linkedin/summary").json()["leads"][0]["company"] == "Nowhere Labs"
    assert client.delete(f"/api/linkedin/leads/{lead['lead_id']}").status_code == 204
    assert client.post("/api/linkedin/viewers", json={"full_name": "X", "company": "Y"}
                       ).status_code == 422
    job = Session(engine).get(Job, job_id)
    assert job is not None and FitScore  # (keeps the imports honest)
