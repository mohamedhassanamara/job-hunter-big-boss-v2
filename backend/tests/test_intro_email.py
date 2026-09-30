"""The cold email as a personal introduction (prompt v4): research first (reused while fresh),
then hook · intro (code) · value · ask, with its checks. No model or network calls."""

import time

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, ResearchRun
from app.providers.base import EmailSentence, HookSentence, IntroEmailPlan
from app.providers.mock import MockEmailDrafter
from app.services import intro_check as ic
from app.services import outreach, research
from app.services.cv_pool import load_pool
from tests.test_outreach import job_ready  # noqa: F401 (fixture)


class Site:
    """A company site with one verifiable customer result."""

    def __init__(self, text: str = "A mutual insurer automated 37% of its incoming requests "
                                   "with us."):
        self.text, self.calls = text, 0

    def site(self, home, max_pages, progress):  # noqa: ANN001, ANN201
        self.calls += 1
        return [research.Source(f"{home}/clients", "customers", "Clients", self.text)], []

    def news(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
        return [], []


def test_the_intro_line_is_built_from_your_profile() -> None:
    en = ic.intro_line("Alex", "backend, mobile and AI systems", "en",
                       "3 years of software engineering experience", None)
    assert en == ("I'm Alex, a software engineer with 3 years of experience in backend, mobile "
                  "and AI systems.")
    fr = ic.intro_line("Alex", "systèmes backend, mobiles et IA", "fr",
                       "3 years of software engineering experience",
                       "3 ans d'expérience en ingénierie logicielle")
    assert fr == ("Je suis Alex, ingénieur logiciel avec 3 ans d'expérience en ingénierie "
                  "logicielle, sur des systèmes backend, mobiles et IA.")


def draft(job_ready: dict, site: Site | None = None):  # noqa: F811, ANN201
    return outreach.generate(engine, job_ready["app"], MockEmailDrafter(),
                             researcher=research.MockResearcher(), fetcher=site or Site())


def test_research_then_draft_with_the_signal_cited(job_ready: dict) -> None:  # noqa: F811
    d = draft(job_ready)
    assert d.plan["format"] == "intro" and d.plan["signal_ids"]
    parts = d.body.split("\n\n")
    assert parts[0] == "Hi Ana," and "37%" in parts[1] and parts[2] == d.plan["intro_line"]
    assert parts[-1].endswith("?")
    assert not [v for v in d.violations if v["severity"] == "error"], d.violations
    assert d.plan["signals"][0]["fact"].startswith("A mutual insurer")


def test_fresh_signals_are_reused_without_fetching(job_ready: dict) -> None:  # noqa: F811
    site = Site()
    draft(job_ready, site)
    draft(job_ready, site)
    assert site.calls == 1
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        company_id = s.exec(select(ResearchRun.company_id)).all()
        statuses = [r.status for r in s.exec(select(ResearchRun).where(
            ResearchRun.company_id.in_(company_id))).all()]
    assert "cached" in statuses and app is not None


def test_without_a_signal_the_draft_needs_one_and_cant_be_approved(job_ready: dict,  # noqa: F811
                                                                   client) -> None:  # noqa: ANN001
    d = draft(job_ready, Site("Welcome."))
    assert any(v["type"] == "needs_signal" for v in d.violations)
    assert client.post(f"/api/outreach/drafts/{d.id}/approve").status_code == 409


def ctx_for(job_ready: dict, **kw) -> ic.Context:  # noqa: F811, ANN003
    with Session(engine) as s:
        pool = load_pool(s)
    base = dict(pool=pool, allowed_years={3}, job_title="Data Platform Lead",
                job_text="Data Platform Lead\nWe build pipelines with Spark for insurers.",
                company="Voxa", first_name="Ana",
                signals={7: "A mutual insurer automated 37% of its incoming requests"},
                intro_line="I'm Alex, a software engineer with 3 years of experience in data "
                           "systems.", places=["Tunis", "Tunisia", "tunisie"])
    return ic.Context(**{**base, **kw})


def plan(job_ready: dict, **kw) -> IntroEmailPlan:  # noqa: F811, ANN003
    base = dict(
        subject="Pipelines that stay reliable as volume grows",
        greeting="Hi Ana,",
        hook=HookSentence(text="I came across Voxa while looking at companies building voice "
                               "tools for insurers, and one thing stood out: a mutual insurer "
                               "automated 37% of its incoming requests with you.",
                          signal_ids=[7]),
        intro_focus="data systems",
        problem="Keeping every integration reliable while the number of customers keeps "
                "growing is the kind of problem I like working on, and it is hard to get right.",
        proofs=[EmailSentence(text=f"At {job_ready['org']}, I built this kind of pipeline with "
                                   f"{job_ready['tag']}, from the first design to production, "
                                   "for a small team.", citations=[job_ready["role"]])],
        ask="Do you currently have an opening where this would be useful?")
    return IntroEmailPlan(**{**base, **kw})


def kinds(found: list[dict]) -> set[str]:
    return {v["type"] for v in found if v["severity"] == "error"}


def test_a_good_introduction_passes(job_ready: dict) -> None:  # noqa: F811
    assert kinds(ic.check_plan(plan(job_ready), ctx_for(job_ready))) == set()


@pytest.mark.parametrize(("change", "expected"), [
    ({"problem": "The role you posted needs someone to keep pipelines reliable as volume grows "
                 "every week."}, "listing"),
    ({"problem": "From Tunis, I can help keep your pipelines reliable as the volume grows every "
                 "week for insurers."}, "location"),
    ({"subject": "Data Platform Lead role at Voxa"}, "subject"),
    ({"subject": "Re: your pipelines"}, "subject"),
    ({"ask": "I would welcome a chat."}, "ask"),
    ({"hook": HookSentence(text="Voxa grew 45% last year.", signal_ids=[7])}, "hook"),
    ({"hook": HookSentence(text="", signal_ids=[])}, "needs_signal"),
    ({"proofs": []}, "proofs"),
])
def test_each_introduction_rule(job_ready: dict, change: dict, expected: str) -> None:  # noqa: F811
    assert expected in kinds(ic.check_plan(plan(job_ready, **change), ctx_for(job_ready)))


def test_too_many_tools_and_copying_an_example(job_ready: dict) -> None:  # noqa: F811
    p = plan(job_ready)
    p.problem = "You run Spark, Kafka, Airflow and Snowflake together, which is hard to keep " \
                "reliable as the number of customers grows."
    assert "tools" in kinds(ic.check_plan(p, ctx_for(job_ready)))
    good = plan(job_ready)
    copy = ic.body(good, ctx_for(job_ready).intro_line)
    found = ic.check_plan(good, ctx_for(job_ready, examples=[("reference_good #1", copy)]))
    assert "example_copy" in kinds(found)


def test_the_draft_step_runs_in_the_background_with_progress(job_ready: dict,  # noqa: F811
                                                             client) -> None:  # noqa: ANN001
    r = client.post(f"/api/applications/{job_ready['app']}/draft/generate")
    assert r.status_code == 202 and r.json()["status"] == "running"
    for _ in range(100):
        state = client.get(f"/api/applications/{job_ready['app']}/draft/progress").json()
        if state["status"] != "running":
            break
        time.sleep(0.05)
    assert state["status"] in ("done", "failed"), state
