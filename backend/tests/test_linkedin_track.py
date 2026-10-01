"""The LinkedIn messages track: who to message (with code-built links), notes and follow-ups
(mock drafter, real checks), statuses, the email gap rule, reminders. Offline, no model."""

from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    ApplicationResponse,
    Company,
    Contact,
    Job,
    LinkedInOutreach,
    OutreachDraft,
    ResearchRun,
)
from app.models.base import utcnow
from app.models.enums import DraftStatus, LinkedInGroup, LinkedInStatus, Stage
from app.providers.mock import MockLinkedInDrafter
from app.services import linkedin_check as lc
from app.services import linkedin_track as lt
from app.services import research, tracks
from app.services.cv_pool import load_pool
from tests.test_contacts import make_company, make_job


def job_with_people(s: Session, slug: str | None = "acme-data") -> tuple[Application, Company]:
    company = make_company(s)
    company.linkedin_url = f"https://www.linkedin.com/company/{slug}/" if slug else None
    company.domain = "acme.test"
    app = make_job(s, company, stage=Stage.shortlisted)
    s.get(Job, app.job_id).description = "We build data pipelines with Spark for insurers."
    s.flush()
    return app, company


def test_groups_in_order_with_links_and_the_school_from_your_pool(seeded: None) -> None:
    with Session(engine) as s:
        app, company = job_with_people(s)
        groups = lt.suggestions(s, app)
        assert [g["group"] for g in groups] == [LinkedInGroup.hiring_team, LinkedInGroup.alumni,
                                                LinkedInGroup.lead, LinkedInGroup.recruiter]
        short, full = lt.school(load_pool(s))
        assert short and short in groups[1]["label"] and full
        assert groups[1]["search"].startswith(
            "https://www.linkedin.com/company/acme-data/people/?keywords=")
        company.linkedin_url = None  # no slug: a people search with the company name
        assert "search/results/people/?keywords=" in lt.suggestions(s, app)[2]["search"]
        s.rollback()


def test_the_school_short_name_comes_from_brackets() -> None:
    assert lc.school_short("National Institute of Applied Sciences and Technologies (INSAT)") \
        == "INSAT"
    assert lc.school_short("Universidad Politécnica") == "Universidad Politécnica"


def test_notes_fit_the_limit_and_only_alumni_get_the_school(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        alum = lt.add(s, app, full_name="Lea Alum", title="Data Engineer", linkedin_url=None,
                      group=LinkedInGroup.alumni)
        lead = lt.add(s, app, full_name="Max Lead", title="Head of Data",
                      linkedin_url="https://www.linkedin.com/in/max-lead?x=1",
                      group=LinkedInGroup.lead)
        s.commit()
        ids = (alum.id, lead.id)
        short = lt.school(load_pool(s))[0]
    a = lt.draft_note(engine, ids[0], MockLinkedInDrafter())
    b = lt.draft_note(engine, ids[1], MockLinkedInDrafter())
    assert len(a.note["text"]) <= 200 and short in a.note["text"]
    assert short not in b.note["text"]
    assert not [v for v in a.note["violations"] if v["severity"] == "error"], a.note
    with Session(engine) as s:
        assert s.get(Contact, b.contact_id).linkedin_url == "https://www.linkedin.com/in/max-lead/"


def ctx(**kw) -> lc.Context:  # noqa: ANN003
    with Session(engine) as s:
        pool = load_pool(s)
    base = dict(pool=pool, allowed_years={3}, job_text="Data Engineer\nSpark pipelines",
                company="Acme", kind="note", max_chars=200, alumni=False, school="INSAT",
                school_full="National Institute of Applied Sciences and Technologies (INSAT)",
                first_name="Lea", places=["Tunis", "Tunisia"])
    return lc.Context(**{**base, **kw})


@pytest.mark.parametrize(("text", "kind", "alumni"), [
    ("Hi Lea, fellow INSAT graduate here. Could I ask how your team works?", None, True),
    ("Hi Lea, fellow INSAT graduate here. Could I ask how your team works?", "school", False),
    ("Hi Lea, I'm based in Tunis and work on data. Could I ask how your team works?",
     "location", False),
    ("Hi Lea, I would love to connect. How does your team work?", "banned", False),
    ("Hi Lea, see https://example.com. How does your team work?", "link", False),
    ("Hi Lea, I build data pipelines. " + "Really. " * 30 + "Could we talk?", "length", False),
    ("Hi Lea, I work on data pipelines at scale.", "ask", False),
])
def test_linkedin_checks(seeded: None, text: str, kind: str | None, alumni: bool) -> None:
    errors = {v["type"] for v in lc.check(text, ctx(alumni=alumni)) if v["severity"] == "error"}
    assert (kind in errors) if kind else not errors, errors


def test_statuses_dates_counter_replies_and_undo(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = lt.add(s, app, full_name="Ann Hire", title="Head of Data", linkedin_url=None,
                     group=LinkedInGroup.hiring_team)
        before = lt.requests_today(s)
        lt.set_status(s, row, LinkedInStatus.sent)
        assert row.sent_at is not None and lt.requests_today(s) == before + 1
        assert tracks.for_app(s, app).linkedin == "sent"
        lt.set_status(s, row, LinkedInStatus.replied)
        replies = s.exec(select(ApplicationResponse).where(
            ApplicationResponse.application_id == app.id)).all()
        assert [r.channel for r in replies] == ["linkedin"]
        lt.set_status(s, row, LinkedInStatus.accepted)  # undo the reply
        assert row.replied_at is None and s.exec(select(ApplicationResponse).where(
            ApplicationResponse.application_id == app.id)).all() == []
        s.rollback()


def test_no_email_and_request_to_the_same_person_within_the_gap(seeded: None) -> None:
    with Session(engine) as s:
        app, company = job_with_people(s)
        person = Contact(company_id=company.id, full_name="Gap Person", normalized_name="gap "
                         "person", email="gap@acme.test", email_normalized="gap@acme.test")
        s.add(person)
        s.flush()
        s.add(OutreachDraft(application_id=app.id, contact_id=person.id, subject="s", body="b",
                            status=DraftStatus.sent, sent_at=utcnow() - timedelta(days=1)))
        row = lt.add(s, app, full_name="Gap Person", title=None, linkedin_url=None,
                     group=LinkedInGroup.lead)
        s.flush()
        assert row.contact_id == person.id  # the same person across tracks
        hint = lt.gap_hint(s, person.id)
        assert hint and hint.startswith("Emailed on")
        assert row.id not in [x["row_id"] for x in lt.to_send(s)]
        s.rollback()


def test_reminders_for_no_answer_and_accepted_waiting(seeded: None) -> None:
    with Session(engine) as s:
        app, _ = job_with_people(s)
        a = lt.add(s, app, full_name="Old Request", title=None, linkedin_url=None,
                   group=LinkedInGroup.recruiter)
        b = lt.add(s, app, full_name="Said Yes", title=None, linkedin_url=None,
                   group=LinkedInGroup.lead)
        a.status, a.sent_at = LinkedInStatus.sent, utcnow() - timedelta(days=6)
        b.status, b.accepted_at = LinkedInStatus.accepted, utcnow()
        s.flush()
        kinds = {r.row_id: r.kind for r in lt.reminders(s)}
        assert kinds[a.id] == "no_answer" and kinds[b.id] == "write_followup"
        s.rollback()


class Site:
    calls = 0

    def site(self, home, max_pages, progress):  # noqa: ANN001, ANN201
        Site.calls += 1
        return [research.Source(f"{home}/clients", "customers", "Clients",
                                "A mutual insurer automated 37% of its requests with us.")], []

    def news(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
        return [], []


def test_followup_after_accept_researches_only_then(seeded: None) -> None:
    with Session(engine) as s:
        app, company = job_with_people(s)
        row = lt.add(s, app, full_name="Ok Accepted", title="Head of Data", linkedin_url=None,
                     group=LinkedInGroup.lead)
        s.commit()
        row_id, company_id = row.id, company.id
    with pytest.raises(lt.LinkedInError, match="accepted"):
        lt.draft_followup(engine, row_id, MockLinkedInDrafter())
    with Session(engine) as s:
        assert s.exec(select(ResearchRun).where(ResearchRun.company_id == company_id)).all() == []
        lt.set_status(s, s.get(LinkedInOutreach, row_id), LinkedInStatus.accepted)
        s.commit()
    done = lt.draft_followup(engine, row_id, MockLinkedInDrafter(),
                             researcher=research.MockResearcher(), fetcher=Site())
    assert done.followup["text"].endswith("?") and Site.calls == 1
    with Session(engine) as s:
        runs = s.exec(select(ResearchRun).where(ResearchRun.company_id == company_id)).all()
        assert [r.trigger for r in runs] == ["linkedin"]


def test_the_panel_endpoint(seeded: None, client) -> None:  # noqa: ANN001
    with Session(engine) as s:
        app, _ = job_with_people(s)
        s.commit()
        app_id = app.id
    added = client.post(f"/api/applications/{app_id}/linkedin/people",
                        json={"full_name": "Pat Recruit", "title": "Recruiter",
                              "group": "recruiter"}).json()
    assert added["people"][0]["full_name"] == "Pat Recruit" and added["max_chars"] == 200
    assert [g["group"] for g in added["groups"]][0] == "hiring_team"
    row_id = added["people"][0]["id"]
    noted = client.post(f"/api/linkedin/people/{row_id}/note").json()
    assert noted["note"]["text"] and noted["note"]["prompt_version"] == "linkedin/mock"
    edited = client.patch(f"/api/linkedin/people/{row_id}",
                          json={"note": "Hi Pat, I'd love to connect!"}).json()
    assert {v["type"] for v in edited["note"]["violations"]} >= {"banned", "ask"}
    sent = client.post(f"/api/linkedin/people/{row_id}/status", json={"status": "sent"}).json()
    assert sent["status"] == "sent" and sent["sent_at"]


def test_stats_per_channel_group_and_source(seeded: None, client) -> None:  # noqa: ANN001
    with Session(engine) as s:
        app, _ = job_with_people(s)
        row = lt.add(s, app, full_name="Al Umni", title="Engineer", linkedin_url=None,
                     group=LinkedInGroup.alumni)
        lt.set_status(s, row, LinkedInStatus.sent)
        lt.set_status(s, row, LinkedInStatus.replied)
        s.commit()
    out = client.get("/api/stats").json()
    linkedin_row = next(c for c in out["by_channel"] if c["group"] == "linkedin")
    assert linkedin_row["reached"] >= 1 and linkedin_row["count"] >= 1
    alumni = next(g for g in out["linkedin_groups"] if g["group"] == "alumni")
    assert alumni["sent"] >= 1 and alumni["replied"]["count"] >= 1
    assert {o["group"] for o in out["by_origin"]} == {"linkedin_import", "discovery"}
