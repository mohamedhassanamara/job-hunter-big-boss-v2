"""Both routes, the rest: who to contact (by company size), the fixed "I also applied" sentence
in the email, stats per route group, the Today "Also email" list, and the email drafter being
Claude (claude -p), never the local model."""

from datetime import UTC, date, datetime

from sqlmodel import Session

from app.db import engine
from app.models import Application, Company, Job
from app.models.enums import ApplyMethod
from app.services import contacts, outreach, tracking
from tests.test_outreach import Script, good_plan, job_ready  # noqa: F401 (fixture)


def company(**kw) -> Company:  # noqa: ANN003
    return Company(name="Acme", normalized_name="acme", **kw)


def test_who_to_contact_small_company_writes_to_the_cto_or_founder(seeded: None) -> None:
    with Session(engine) as s:
        job = Job(title="Data role", matched_track="Data/AI", company_id=0, url="", source="x",
                  external_id="x", dedupe_key="x")
        w = contacts.who_to_contact(s, job, company(employees_max=50))
    assert w["small"] and w["roles"][0]["label"] == "CTO"
    assert "small (under 50 employees)" in w["reason"] and "CTO" in w["reason"]
    assert '"CTO"' in w["linkedin_query"] and w["linkedin_query"].endswith('"Acme"')
    assert w["linkedin_url"].startswith("https://www.linkedin.com/search/results/people/")
    assert w["apollo"]["company"] == "Acme" and "c_suite" in w["apollo"]["seniority"]


def test_who_to_contact_large_or_unknown_is_the_hiring_team_then_talent(seeded: None) -> None:
    with Session(engine) as s:
        job = Job(title="Data role", matched_track="Data/AI", company_id=0, url="", source="x",
                  external_id="x", dedupe_key="x")
        large = contacts.who_to_contact(s, job, company(employees=5000))
        unknown = contacts.who_to_contact(s, job, company())
    labels = [r["label"] for r in large["roles"]]
    assert labels[0] == "Head of the Data/AI team" and "Head of Data" in large["roles"][0]["titles"]
    assert labels[1] == "Engineering Manager" and labels[-1] == "HR / Talent"
    assert "large (5000 employees)" in large["reason"] and "talent acquisition" in large["reason"]
    assert "size is unknown" in unknown["reason"]


def applied_on_web(app_id: int, day: date = date(2026, 9, 29)) -> None:
    with Session(engine) as s:
        app = s.get(Application, app_id)
        tracking.mark_applied(s, app, applied_on=day, method=ApplyMethod.company_site)
        s.commit()


def test_the_email_mentions_the_web_application_once_applied(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    applied_on_web(job_ready["app"])
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    sentence = "I have also applied through your careers page on 29 September."
    assert sentence in draft.body and draft.plan["application_mention"] == sentence
    assert draft.body.rstrip().endswith("?")  # the ask stays last
    assert not [v for v in draft.violations if v["severity"] == "error"], draft.violations
    out = client.post(f"/api/outreach/drafts/{draft.id}/mention-application",
                      json={"include": False}).json()
    assert sentence not in out["body"] and out["mention_included"] is False
    out = client.post(f"/api/outreach/drafts/{draft.id}/mention-application",
                      json={"include": True}).json()
    assert out["body"].count(sentence) == 1 and out["mention_included"]


def test_no_mention_before_applying(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    assert "careers page" not in draft.body
    r = client.post(f"/api/outreach/drafts/{draft.id}/mention-application", json={"include": True})
    assert r.status_code == 409


def test_the_step_suggests_who_to_contact_without_a_contact(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        app.contact_id = None
        s.add(app)
        s.commit()
    step = client.get(f"/api/applications/{job_ready['app']}/outreach").json()
    assert step["step"] == "contact" and step["who_to_contact"]["roles"]


def test_stats_count_both_routes_and_rates_per_route(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    applied_on_web(job_ready["app"])
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    client.post(f"/api/outreach/drafts/{draft.id}/approve")
    client.post(f"/api/applications/{job_ready['app']}/sent-manually", json={})
    stats = client.get("/api/stats").json()
    assert stats["both_routes"] >= 1
    groups = {g["group"]: g for g in stats["by_route"]}
    assert set(groups) == {"web", "email", "both"} and groups["both"]["applied"] >= 1
    assert "count" in groups["both"]["response"]


def test_today_lists_applied_jobs_nobody_was_emailed_about(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        app.contact_id = None
        s.add(app)
        s.commit()
    applied_on_web(job_ready["app"])
    today = client.get("/api/today").json()
    assert job_ready["app"] in [c["application_id"] for c in today["also_email"]]


def test_emails_are_drafted_by_claude_code_not_the_local_model() -> None:
    from app.providers.claude_email import ClaudeEmailDrafter
    from app.providers.registry import email_drafter

    drafter = email_drafter(mock=False, model="claude-sonnet-5")
    assert isinstance(drafter, ClaudeEmailDrafter) and drafter.via == "claude -p"
    assert "ollama" not in type(drafter).__module__
    assert drafter.command("x")[:2][1] == "-p"


def test_drafts_record_how_they_were_generated(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    draft = outreach.generate(engine, job_ready["app"], Script(good_plan(job_ready)))
    out = next(d for d in client.get("/api/outreach/drafts?status=draft").json()
               if d["id"] == draft.id)
    assert out["model"] == "script" and out["generated_via"] in ("mock", "claude -p")
    assert datetime.now(UTC) >= datetime.fromisoformat(out["created_at"].replace("Z", "+00:00"))
