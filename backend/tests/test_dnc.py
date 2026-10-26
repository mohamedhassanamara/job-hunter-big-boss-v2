"""Do-not-contact: the list, the flag, and every place that must refuse (imports, drafting,
approval, the queue, LinkedIn, the finders). Offline."""

from itertools import count

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    Company,
    Contact,
    DoNotContactRule,
    Job,
    LinkedInOutreach,
    OutreachDraft,
    SendQueueItem,
)
from app.models.enums import ContactSource, DraftStatus, QueueItemStatus, ResponseKind
from app.providers.mock import MockEmailDrafter, MockMailer
from app.services import (
    contact_waterfall,
    contacts,
    dnc,
    get_contact,
    linkedin_track,
    outreach,
    send_queue,
    tracking,
)
from app.services.contact_waterfall import Candidate
from app.services.contacts import DEFAULT_ROLE_RANKING
from tests.test_contacts import company_contacts, csv_bytes, do_import
from tests.test_email_step_v2 import sent_gate_setup
from tests.test_outreach import NOW, fresh_queue, job_ready  # noqa: F401 (fixtures)
from tests.test_tracking import applied_app

_n = count(1)


def _contact(app_id: int) -> Contact:
    with Session(engine) as s:
        return s.get(Contact, s.get(Application, app_id).contact_id)


# ------------------------------------------------------------------------------------ parsing


def test_pasted_emails_and_domains_are_split_and_cleaned() -> None:
    rules, bad = dnc.parse("Ana@Acme.io, https://www.beta.com/jobs\n@gamma.de; mailto:x@y.fr  ???")
    assert rules == [("email", "ana@acme.io"), ("domain", "beta.com"), ("domain", "gamma.de"),
                     ("email", "x@y.fr")]
    assert bad == ["???"]


def test_a_domain_rule_covers_subdomains_and_an_email_rule_only_that_address(
        seeded: None) -> None:
    with Session(engine) as s:
        out = dnc.add_rules(s, "blocked-co.test, one@single.test", "asked by phone")
        assert out["added"] == 2 and out["already_listed"] == 0
        assert dnc.add_rules(s, "blocked-co.test", "")["already_listed"] == 1
        rules = dnc.rules(s)
        assert dnc.rule_for("a@blocked-co.test", rules)
        assert dnc.rule_for("a@mail.blocked-co.test", rules)
        assert dnc.rule_for("a@notblocked-co.test", rules) is None
        assert dnc.rule_for("one@single.test", rules)
        assert dnc.rule_for("two@single.test", rules) is None
        with pytest.raises(dnc.DncError):
            dnc.add_rules(s, "   ")
        s.rollback()


def test_a_new_rule_flags_the_contacts_it_covers_and_removing_it_keeps_the_flag(
        seeded: None) -> None:
    with Session(engine) as s:
        company = Company(name=f"Flag Co {next(_n)}", normalized_name=f"flag co {next(_n)}")
        s.add(company)
        s.flush()
        c = Contact(company_id=company.id, full_name="Pat Flag", normalized_name="pat flag",
                    email="pat@flagged-domain.test", email_normalized="pat@flagged-domain.test")
        s.add(c)
        s.flush()
        dnc.add_rules(s, "flagged-domain.test", "legal request")
        s.flush()
        assert c.do_not_contact and "legal request" in (c.dnc_reason or "")
        rule = s.exec(select(DoNotContactRule).where(
            DoNotContactRule.value == "flagged-domain.test")).one()
        dnc.remove_rule(s, rule)
        s.flush()
        assert c.do_not_contact  # lifted only by you, from the card
        s.rollback()


# ------------------------------------------------------------------------------------- imports


def test_import_skips_a_listed_address_and_domain_and_never_touches_a_flagged_or_left_contact(
        seeded: None) -> None:
    co = f"Skip Co {next(_n)}"
    with Session(engine) as s:
        dnc.add_rules(s, "nope@skip-list.test, banned-domain.test", "")
        s.commit()
    do_import(csv_bytes(f"Old,Flagged,,{co},flagged@skip-list2.test",
                        f"Old,Left,,{co},left@skip-list2.test"))
    with Session(engine) as s:
        for c in s.exec(select(Contact).where(Contact.email_normalized.in_(  # type: ignore[attr-defined]
                ["flagged@skip-list2.test", "left@skip-list2.test"]))).all():
            if c.full_name == "Old Flagged":
                dnc.flag(s, c, "asked")
            else:
                from app.models.base import utcnow
                c.left_at, c.left_reason = utcnow(), "left"
                s.add(c)
        s.commit()
    run = do_import(csv_bytes(
        f"No,Pe,CTO,{co},nope@skip-list.test",  # the address is listed
        f"Ba,Nned,CTO,{co},anyone@banned-domain.test",  # the domain is listed
        f"Old,Flagged,CTO,{co},flagged@skip-list2.test",  # flagged: not filled in
        f"Old,Left,CTO,{co},left@skip-list2.test",  # left: not filled in
        f"Ok,Person,CTO,{co},ok@fine-domain.test"), name="second.csv")
    assert run.created == 1
    assert run.skipped_reasons == {"do_not_contact": 3, "left": 1}
    titles = {c.full_name: c.title for c in company_contacts(co)}
    assert titles["Old Flagged"] is None and titles["Old Left"] is None
    assert "No Pe" not in titles and "Ba Nned" not in titles


# ------------------------------------------------------------------- drafting and approval


def test_drafting_and_approval_are_refused_for_a_contact_who_asked_not_to_be_contacted(
        job_ready: dict, client) -> None:  # noqa: ANN001, F811
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    with Session(engine) as s:
        dnc.flag(s, _contact_in(s, job_ready["app"]), "asked by email")
        s.commit()
    r = client.post(f"/api/outreach/drafts/{d.id}/approve")
    assert r.status_code == 409 and "asked not to be contacted" in r.json()["detail"]
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        assert get_contact.state(s, app) == "blocked"
        with pytest.raises(get_contact.GetContactError, match="Do not contact"):
            get_contact.require_ready(s, app)
    with pytest.raises(outreach.OutreachError, match="Do not contact"):
        outreach.generate(engine, job_ready["app"], MockEmailDrafter())


def _contact_in(s: Session, app_id: int) -> Contact:
    return s.get(Contact, s.get(Application, app_id).contact_id)


def test_marking_a_contact_moves_their_jobs_to_the_next_contact(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        company_id = s.get(Contact, app.contact_id).company_id
        backup = Contact(company_id=company_id, full_name="Bea Backup",
                         normalized_name="bea backup",
                         title="Engineering Manager", email="bea@outco-backup.test",
                         email_normalized="bea@outco-backup.test",
                         role_rank=contacts.rank("Engineering Manager", DEFAULT_ROLE_RANKING)[0])
        s.add(backup)
        s.flush()
        get_contact.do_not_contact(s, _contact_in(s, job_ready["app"]), "asked")
        s.flush()
        assert app.contact_id == backup.id  # never the flagged one again
        s.rollback()


def test_entering_a_listed_address_is_refused(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        dnc.add_rules(s, "refused-domain.test", "")
        app = s.get(Application, job_ready["app"])
        company_id = s.get(Contact, app.contact_id).company_id
        with pytest.raises(contacts.ContactError, match="Do not contact"):
            contacts.add_contact(s, company_id, full_name="Zed", title="CTO",
                                 email="zed@refused-domain.test", linkedin_url=None,
                                 source=ContactSource.manual)
        with pytest.raises(get_contact.GetContactError, match="Do not contact"):
            get_contact.found(s, app, full_name="Zed", title="CTO", email="zed@refused-domain.test",
                              linkedin_url=None)
        s.rollback()


# -------------------------------------------------------------------------------- the send gate


def test_a_queued_email_to_a_contact_who_asked_not_to_be_contacted_is_pulled_back(
        job_ready: dict, client, fresh_queue: None) -> None:  # noqa: ANN001, F811
    draft_id = sent_gate_setup(job_ready, client)
    with Session(engine) as s:  # asked not to be contacted AFTER the email was queued
        dnc.flag(s, _contact_in(s, job_ready["app"]), "replied: please stop")
        s.commit()
    mailer = MockMailer()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "blocked"
    assert mailer.sent == []
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        item = s.exec(select(SendQueueItem).where(SendQueueItem.draft_id == draft_id)).one()
        assert d.status == DraftStatus.draft and item.status == QueueItemStatus.cancelled
        assert "do not contact" in item.error and "please stop" in item.error
        assert any(v["type"] == "send_gate" and "please stop" in v["message"]
                   for v in d.violations)


def test_a_listed_domain_also_stops_a_queued_email_and_cant_be_queued_again(
        job_ready: dict, client, fresh_queue: None) -> None:  # noqa: ANN001, F811
    draft_id = sent_gate_setup(job_ready, client)
    with Session(engine) as s:
        dnc.add_rules(s, "outco.test", "company asked")  # also flags the contact
        s.commit()
    mailer = MockMailer()
    assert send_queue.tick(engine, lambda s: mailer, NOW) == "blocked" and mailer.sent == []
    assert client.post(f"/api/outreach/drafts/{draft_id}/queue").status_code == 409


# ---------------------------------------------------------------------------------- a logged reply


def test_logging_asked_not_to_be_contacted_flags_the_contact_and_changes_no_stage(
        seeded: None) -> None:
    with Session(engine) as s:
        app = applied_app(s)
        job_company = s.get(Company, s.get(Job, app.job_id).company_id)
        person = Contact(company_id=job_company.id, full_name="Re Plier",
                         normalized_name="re plier", email="re@plier.test",
                         email_normalized="re@plier.test")
        s.add(person)
        s.flush()
        app.contact_id = person.id
        stage = app.stage
        tracking.log_response(s, app, kind=ResponseKind.do_not_contact, received_on=None)
        assert person.do_not_contact and "asked not to be contacted" in person.dnc_reason
        assert app.stage == stage
        s.rollback()


# ------------------------------------------------------------------------------ LinkedIn, finders


def test_a_linkedin_message_is_not_drafted_for_a_flagged_contact(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        row = LinkedInOutreach(application_id=app.id, contact_id=app.contact_id)
        s.add(row)
        dnc.flag(s, _contact_in(s, app.id), "asked")
        s.commit()
        row_id = row.id

    class Never:
        def draft(self, *a, **k):  # noqa: ANN002, ANN003, ANN202
            raise AssertionError("a model must not be called")

    for fn in (linkedin_track.draft_note, linkedin_track.draft_inmail):
        with pytest.raises(linkedin_track.LinkedInError, match="Do not contact"):
            fn(engine, row_id, Never())


def test_the_finders_never_save_a_listed_address(seeded: None) -> None:
    with Session(engine) as s:
        company = Company(name=f"Find Co {next(_n)}", normalized_name=f"find co {next(_n)}")
        s.add(company)
        s.flush()
        dnc.add_rules(s, "finder-blocked.test", "")
        cand = Candidate(full_name="Fi Nder", title="CTO", email="fi@finder-blocked.test",
                         email_status="valid", provider="hunter")
        ranking = contacts.ranking_settings(s)
        assert contact_waterfall._persist(s, company, cand, ContactSource.hunter, ranking) is None
        s.rollback()
