"""The cold email as a personal introduction (prompt v4): research first (reused while fresh),
then hook · intro (code) · value · ask, with its checks. No model or network calls."""

import time
import unicodedata

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Job, ResearchRun
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
    assert fr == ("Je suis Alex, ingénieur logiciel avec 3 ans d'expérience, sur des systèmes "
                  "backend, mobiles et IA.")  # the field isn't said twice


def draft(job_ready: dict, site: Site | None = None):  # noqa: F811, ANN201
    from app.services.hook_check import MockHookChecker

    return outreach.generate(engine, job_ready["app"], MockEmailDrafter(),
                             researcher=research.MockResearcher(), fetcher=site or Site(),
                             hook_checker=MockHookChecker(), mode="speculative")


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
                "growing is the kind of problem I like working on, from the first design to the "
                "last customer.",
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


def test_intro_grammar_and_the_intro_line_isnt_compared_with_examples(job_ready: dict) -> None:  # noqa: F811
    fr = ic.intro_line("Alex", "l'IA conversationnelle et les données", "fr", None,
                       "3 ans d'expérience en ingénierie logicielle")
    assert fr.endswith("sur l'IA conversationnelle et les données.")
    ctx = ctx_for(job_ready)
    example = f"Hi Stéphane,\n\nSomething else entirely here.\n\n{ctx.intro_line}\n\nMore."
    found = ic.check_plan(plan(job_ready), ctx_for(job_ready, examples=[("ref", example)]))
    assert "example_copy" not in kinds(found)


def test_based_on_is_not_a_location_and_long_tool_lists_are_caught(job_ready: dict) -> None:  # noqa: F811
    p = plan(job_ready)
    p.problem = ("Un modèle basé sur des données clients doit rester fiable quand le volume de "
                 "clients grandit chaque mois, et c'est difficile à garantir.")
    assert "location" not in kinds(ic.check_plan(p, ctx_for(job_ready)))
    p.problem = ("Basé à Tunis, je peux aider à garder vos intégrations fiables quand le "
                 "volume grandit.")
    assert "location" in kinds(ic.check_plan(p, ctx_for(job_ready)))
    long = plan(job_ready)
    long.proofs[0].text += " " + "It kept working as the team grew and more customers joined." * 2
    assert "proofs" in kinds(ic.check_plan(long, ctx_for(job_ready)))



def test_roi_is_banned_and_connected_signals_come_first(job_ready: dict) -> None:  # noqa: F811
    p = plan(job_ready)
    p.problem = ("Proving the ROI of every automated call is hard when volumes change every "
                 "month for insurers and their customers.")
    from app.services.outreach_check import DEFAULT_BANNED

    assert "banned" in kinds(ic.check_plan(p, ctx_for(job_ready, banned=DEFAULT_BANNED)))
    with Session(engine) as s:
        pool = load_pool(s)
    assert research.connection("They run sovereign, proprietary models", pool) == \
        ["private or local models"] or "local" not in pool.all_text().lower()


def test_a_hook_that_links_two_signals_is_caught_by_the_hook_check() -> None:
    from app.services import hook_check

    signals = {2: "Zaion relies on proprietary, sovereign models", 4: "A mutual insurer "
               "automated 37% of its incoming requests"}
    linked = ("Zaion relies on sovereign models, ayant permis à une mutuelle d'automatiser 37% "
              "de ses demandes.")
    found = hook_check.violations(hook_check.check(hook_check.MockHookChecker(), linked, signals))
    assert [v["type"] for v in found] == ["hook_faithful"] and found[0]["severity"] == "error"
    apart = ("Deux choses m'ont marqué : vos modèles souverains, et cette mutuelle qui a "
             "automatisé 37% de ses demandes.")
    assert hook_check.violations(hook_check.check(hook_check.MockHookChecker(), apart,
                                                  signals)) == []


def test_an_unreachable_hook_check_is_a_warning_not_a_block() -> None:
    from app.services import hook_check
    from app.services.research import ResearchError

    class Down:
        model = "gemma4:31b-cloud"

        def review(self, *a):  # noqa: ANN002, ANN202
            raise ResearchError("Ollama isn't reachable")

    found = hook_check.violations(hook_check.check(Down(), "A hook.", {1: "A fact."}))
    assert [(v["type"], v["severity"]) for v in found] == [("hook_unchecked", "warning")]


def test_the_ollama_hook_check_reads_the_models_verdicts() -> None:
    import json

    import httpx

    from app.services import hook_check

    answer = {"claims": [{"claim": "sovereign models enabled the 37%", "signal_ids": [2, 4],
                          "verdict": "causal", "why": "No signal says the models caused it"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "SIGNAL 2:" in body["messages"][1]["content"]
        return httpx.Response(200, json={"message": {"content": json.dumps(answer)},
                                         "prompt_eval_count": 10, "eval_count": 5})

    checker = hook_check.OllamaHookChecker(transport=httpx.MockTransport(handler))
    result = hook_check.check(checker, "A hook.", {2: "models", 4: "37%"})
    assert result["status"] == "ok" and result["calls"][0]["prompt_version"] == "hook_check/v1"
    assert "cause or effect" in hook_check.violations(result)[0]["message"]


@pytest.mark.parametrize(("problem", "ok"), [
    ("Garder des agents fiables sur chaque canal reste un vrai défi pour une équipe qui grandit "
     "vite.", False),
    ("Keeping every channel reliable as customers grow is hard for any team.", False),
    ("Garder des agents fiables sur chaque canal, c'est le genre de problème qui me plaît.", True),
    ("Keeping every channel reliable as customers grow is the kind of problem I enjoy.", True),
])
def test_the_problem_is_what_you_like_working_on_not_a_general_truth(
        job_ready: dict, problem: str, ok: bool) -> None:  # noqa: F811
    found = kinds(ic.check_plan(plan(job_ready, problem=problem), ctx_for(job_ready)))
    assert ("problem_frame" in found) is not ok


def test_the_greeting_spells_the_name_as_the_companys_pages_do(job_ready: dict) -> None:  # noqa: F811
    from app.models import Company, CompanyPage, Contact

    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        contact = s.get(Contact, app.contact_id)
        company_id = s.get(Job, app.job_id).company_id
        first, last = contact.first_name or contact.full_name.split()[0], \
            contact.full_name.split()[-1]
        accented = unicodedata.normalize("NFC", first + "\u0301")  # Ana → Aná
        s.add(CompanyPage(company_id=company_id, url="https://example.com/team", kind="page",
                          title="Team", text=f"Our CEO {accented.upper()} {last.upper()} and "
                                             f"{accented} {last} founded the company."))
        s.commit()
        found = outreach.email_first_name(s, company_id, contact)
        assert found[0] == accented and found[1]["url"] == "https://example.com/team"
        ctx = outreach.intro_context(s, app, s.get(Job, app.job_id), s.get(Company, company_id),
                                     contact, load_pool(s), language="en", intro="")
        assert ctx.first_name == accented
        for page in s.exec(select(CompanyPage).where(CompanyPage.url == "https://example.com/team")):
            s.delete(page)
        s.commit()


def test_an_edited_hook_is_checked_again_on_approve(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    d = draft(job_ready)
    assert d.plan["hook_check"]["status"] == "ok"
    hook = ic.hook_paragraph(d.body, d.plan["intro_line"])
    edited = d.body.replace(hook, hook.rstrip(".") + ", thanks to its sovereign models.")
    r = client.patch(f"/api/outreach/drafts/{d.id}", json={"body": edited}).json()
    assert "hook_edited" in {v["type"] for v in r["violations"]}
    with Session(engine) as s:  # a second selected signal, so the mock sees two facts linked
        research.add_manual(s, s.get(Job, s.get(Application, job_ready["app"]).job_id).company_id,
                            "They run sovereign models", "https://example.com")
    r = client.post(f"/api/outreach/drafts/{d.id}/approve")
    assert r.status_code == 409 and "hook says" in r.json()["detail"]
    after = client.get(f"/api/applications/{job_ready['app']}/outreach").json()
    assert after["draft"]["hook_check"]["status"] == "ok"


def test_the_greeting_is_in_the_emails_language(job_ready: dict) -> None:  # noqa: F811
    found = kinds(ic.check_plan(plan(job_ready, greeting="Bonjour Ana,"), ctx_for(job_ready)))
    assert "greeting" in found
    assert "greeting" not in kinds(ic.check_plan(plan(job_ready), ctx_for(job_ready)))


def test_quoting_the_same_signal_as_an_example_isnt_copying_it(job_ready: dict) -> None:  # noqa: F811
    fact = "Voxa runs proprietary sovereign models tailored to each channel and use case"
    good = plan(job_ready, hook=HookSentence(
        text=f"I follow voice tools for insurers, and noticed that {fact.replace('Voxa ', '')}.",
        signal_ids=[7]))
    example = ("Hi Sam,\n\nSomething about Voxa: it runs proprietary sovereign models tailored to "
               "each channel and use case, which stood out.\n\nAn unrelated body here.")
    ctx = ctx_for(job_ready, signals={7: fact}, examples=[("ref", example)])
    assert "example_copy" not in kinds(ic.check_plan(good, ctx))
