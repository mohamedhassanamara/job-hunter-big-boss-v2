"""The Get contact step: states, verification (and its expiry), the gate before drafting and
research, left / wrong person, the queue, and migration 0016. No model calls, no network."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Contact, ContactAlert, Job, ResearchRun
from app.models.base import utcnow
from app.models.enums import ContactSearch, ContactSource, Stage
from app.providers.mock import MockEmailDrafter
from app.services import contacts, get_contact, outreach, research
from tests.test_contacts import make_company, make_job
from tests.test_outreach import job_ready  # noqa: F401 (fixture)


def test_states_get_verify_ready_and_never(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s, ("Carl Cto", "CTO", "apollo_dump"))
        app = make_job(s, company, stage=Stage.shortlisted)
        contacts.resolve(s, app)
        carl = s.get(Contact, app.contact_id)
        assert get_contact.state(s, app) == "verify"  # imported: never confirmed
        carl.verified_at = utcnow() - timedelta(days=10)
        assert get_contact.state(s, app) == "ready"
        carl.verified_at = utcnow() - timedelta(days=31)  # older than verify_days (30)
        assert get_contact.state(s, app) == "verify"
        carl.verified_at, carl.email = utcnow(), None
        assert get_contact.state(s, app) == "verify"  # no email: can't write to them
        empty = make_job(s, make_company(s), stage=Stage.shortlisted)
        contacts.resolve(s, empty)
        assert get_contact.state(s, empty) == "get"
        contacts.set_contact_search(s, s.get(Job, empty.job_id).company_id, ContactSearch.never)
        assert get_contact.state(s, empty) == "never"
        s.rollback()


def test_verify_days_comes_from_settings(client) -> None:  # noqa: ANN001
    value = client.get("/api/settings").json()["values"]["contacts"]
    assert client.put("/api/settings/contacts",
                      json={"value": {**value, "verify_days": 0}}).status_code == 422
    assert client.put("/api/settings/contacts",
                      json={"value": {**value, "verify_days": 7}}).status_code == 200
    with Session(engine) as s:
        assert get_contact.verify_days(s) == 7
    client.put("/api/settings/contacts", json={"value": {**value, "verify_days": 30}})


def test_drafting_and_research_wait_for_a_verified_contact(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        s.get(Contact, app.contact_id).verified_at = None
        company_id = s.get(Job, app.job_id).company_id
        s.commit()
    with pytest.raises(outreach.OutreachError, match="Verify"):
        outreach.generate(engine, job_ready["app"], MockEmailDrafter(),
                          researcher=research.MockResearcher())
    with Session(engine) as s:  # the gate is before research: nothing was fetched or run
        assert s.exec(select(ResearchRun).where(ResearchRun.company_id == company_id)).all() == []
        get_contact.verify(s, s.get(Application, job_ready["app"]), "still_there")
        s.commit()
        assert get_contact.state(s, s.get(Application, job_ready["app"])) == "ready"


def test_approving_needs_a_current_verification(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    with Session(engine) as s:
        contact = s.get(Contact, s.get(Application, job_ready["app"]).contact_id)
        contact.verified_at = utcnow() - timedelta(days=90)
        s.commit()
    r = client.post(f"/api/outreach/drafts/{d.id}/approve")
    assert r.status_code == 409 and "Verify" in r.json()["detail"]


def test_still_there_verifies_and_dismisses_the_left_alert(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    app_id = job_ready["app"]
    with Session(engine) as s:
        app = s.get(Application, app_id)
        contact = s.get(Contact, app.contact_id)
        contact.verified_at = None
        s.add(ContactAlert(contact_id=contact.id, company_id=contact.company_id,
                           key=f"k-{contact.id}", kind="left", reason="“left”",
                           excerpt=f"{contact.full_name} has left.", source_url="https://x"))
        s.commit()
    view = client.get(f"/api/applications/{app_id}/get-contact").json()
    assert view["state"] == "verify" and view["alerts"]
    assert view["provenance"]["kind"] in ("import", "apollo_dump", "manual")
    assert view["links"]["profile"].startswith("https://www.linkedin.com/")
    after = client.post(f"/api/applications/{app_id}/contact/verify",
                        json={"action": "still_there"}).json()
    assert after["state"] == "ready" and after["alerts"] == [] and after["verified_how"] == \
        "still_there"


def test_left_moves_every_job_to_the_next_contact_and_they_are_never_picked_again(
        seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s, ("Carl Cto", "CTO", "apollo_dump"),
                               ("Rita Recruiter", "Recruiter", "apollo_dump"))
        company.employees = 20  # small: the CTO first
        a, b = make_job(s, company, stage=Stage.shortlisted), make_job(s, company)
        contacts.resolve_many(s, [(x, s.get(Job, x.job_id)) for x in (a, b)])
        carl = s.get(Contact, a.contact_id)
        assert carl.full_name == "Carl Cto" and b.contact_id == carl.id
        get_contact.verify(s, a, "left")
        assert carl.left_at is not None and carl.left_reason == "left"
        assert s.get(Contact, a.contact_id).full_name == "Rita Recruiter"
        assert s.get(Contact, b.contact_id).full_name == "Rita Recruiter"
        contacts.resolve_company(s, company.id)  # a later match never brings Carl back
        assert a.contact_id != carl.id
        get_contact.verify(s, a, "wrong_person")
        assert a.contact_id is None and get_contact.state(s, a) == "get"
        s.rollback()


def test_found_updates_a_known_email_and_edit_reverifies(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s, ("Carl Cto", "CTO", "apollo_dump"))
        app = make_job(s, company, stage=Stage.shortlisted)
        carl = s.exec(select(Contact).where(Contact.company_id == company.id)).one()
        carl.email_normalized = carl.email.lower()  # as imports store it
        contacts.set_contact_search(s, company.id, ContactSearch.not_found)
        again = get_contact.found(s, app, full_name="Carl Cto", title="CTO & co-founder",
                                  email=carl.email.upper(), linkedin_url=None)
        assert again.id == carl.id and carl.verified_at is not None  # no duplicate
        assert company.contact_search == ContactSearch.none
        with pytest.raises(get_contact.GetContactError):
            get_contact.found(s, app, full_name="No Email", title=None, email="",
                              linkedin_url=None)
        carl.verified_at = None
        get_contact.edit(s, carl, email="carl.new@co.io")
        assert carl.verified_at is not None and carl.verified_how == "entered"
        s.rollback()


def test_the_to_get_endpoint_and_nav_count(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        s.get(Contact, app.contact_id).verified_at = None
        s.commit()
    queue = client.get("/api/contacts/to-get").json()
    row = next(i for i in queue["items"] if i["application_id"] == job_ready["app"])
    assert row["state"] == "verify" and row["contact_name"]
    assert client.get("/api/nav-counts").json()["contacts_to_get"] >= 1
    today = client.get("/api/today").json()["contacts_to_get"]
    assert today["total"] >= 1 and "daily_limit" in today


def test_a_new_contact_by_hand_counts_as_verified(seeded: None) -> None:
    with Session(engine) as s:
        company = make_company(s)
        c = contacts.add_contact(s, company.id, full_name="Hand Made", title=None,
                                 email="hand@made.io", linkedin_url=None,
                                 source=ContactSource.manual)
        assert c.verified_at is not None and c.verified_how == "entered"
        s.rollback()


def test_migration_0016_moves_the_lookup_queue_to_companies(tmp_path: Path) -> None:
    import sqlite3

    from alembic import command
    from alembic.config import Config

    from tests.conftest import BACKEND

    db = tmp_path / "m.db"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "0015")
    con = sqlite3.connect(db)
    now = "2026-09-01 10:00:00"
    for i, status in enumerate(["never", "not_found", "queued", "skipped"], 1):
        con.execute("INSERT INTO company (id, created_at, updated_at, name, normalized_name, "
                    "aggregator_reviewed) VALUES (?, ?, ?, ?, ?, 0)",
                    (i, now, now, f"Co {i}", f"co {i}"))
        con.execute("INSERT INTO company_lookup (created_at, updated_at, company_id, status, "
                    "priority, queued_at, notes) VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (now, now, i, status, now, f"note {i}"))
    con.execute("INSERT INTO contact (created_at, updated_at, company_id, full_name, source, "
                "normalized_name, role_rank, notes) VALUES (?, ?, 1, 'Lu Look', "
                "'apollo_lookup', 'lu look', 0, '')", (now, now))
    con.commit()
    con.close()
    command.upgrade(cfg, "0016")
    con = sqlite3.connect(db)
    assert con.execute("SELECT id, contact_search, contact_search_notes FROM company "
                       "ORDER BY id").fetchall() == [(1, "never", "note 1"),
                                                     (2, "not_found", "note 2"),
                                                     (3, "none", ""), (4, "none", "")]
    assert con.execute("SELECT source, verified_how FROM contact").fetchall() == \
        [("found", "entered")]
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "company_lookup" not in tables
    con.close()


def test_a_match_report_saved_before_phase_9_still_opens(client) -> None:  # noqa: ANN001
    from app.models import AppSetting

    old = {"totals": {"jobs": 3, "with_contact": 1, "queued": 1, "no_contact": 1},
           "by_track": [{"group": "T", "jobs": 3, "with_contact": 1, "queued": 1,
                         "no_contact": 1}], "by_country": [], "lookup_queue": 7,
           "contacts": 5, "companies_with_contacts": 2, "at": "2026-09-28T10:00:00"}
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "contacts_last_match")).first()
        if row is None:
            row = AppSetting(key="contacts_last_match", value=old)
        row.value = old
        s.add(row)
        s.commit()
    r = client.get("/api/contacts/match/report")
    assert r.status_code == 200
    assert r.json()["contacts_to_get"] == 7 and r.json()["totals"]["to_get"] == 1
