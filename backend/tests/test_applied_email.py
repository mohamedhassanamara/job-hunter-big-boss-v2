"""The job-linked email (prompt v11, mode "applied"): an honest application follow-up. Only facts
block (pool, listing and signals, names, years, honesty); style is a warning; the old research-
based introduction stays as the "speculative" mode. Offline: the mock drafter, no model."""

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, EmailExample, Job
from app.providers.base import AppliedEmailPlan, EmailSentence, HookSentence
from app.providers.mock import MockEmailDrafter
from app.services import applied_check as ac
from app.services import intro_check as ic
from app.services import outreach, verifier
from app.services.cv_pool import load_pool
from tests.test_outreach import job_ready  # noqa: F401 (fixture)

RESIDENCY = "You live in Germany (German residency required)."


class NoResearch:
    """The job-linked email never starts research: any call fails the test."""

    def __getattr__(self, name: str):  # noqa: ANN204
        raise AssertionError(f"research started ({name})")


def errors(found: list[dict]) -> set[str]:
    return {v["type"] for v in found if v["severity"] == "error"}


def warnings(found: list[dict]) -> set[str]:
    return {v["type"] for v in found if v["severity"] != "error"}


def ctx_for(job_ready: dict, job_text: str = "Data Engineer\nWe build data pipelines.",  # noqa: F811
            **kw) -> ic.Context:  # noqa: ANN003
    with Session(engine) as s:
        pool = load_pool(s)
    base = dict(pool=pool, allowed_years={3}, job_title="Data Engineer", job_text=job_text,
                company="Voxa", first_name="Ana", signals={7: "A mutual insurer automated 37%"},
                intro_line="", places=["Tunis", "Tunisia"], min_words=ac.MIN_WORDS,
                max_words=ac.MAX_WORDS, other_companies=["Zeta"], candidate_name="Alex Doe")
    return ic.Context(**{**base, **kw})


def plan(job_ready: dict, **kw) -> AppliedEmailPlan:  # noqa: F811, ANN003
    base = dict(
        role="Data Engineer", greeting="Hi Ana,",
        opening="I've just applied for the Data Engineer role at Voxa and wanted to reach out "
                "to you directly.",
        experience=[
            EmailSentence(text=f"At {job_ready['org']}, I built data pipelines with "
                               f"{job_ready['tag']}, from the first design to production, for "
                               "a small team.", citations=[job_ready["role"]]),
            EmailSentence(text="I like keeping them reliable as the volume grows.",
                          citations=[job_ready["role"]])],
        ask="Would you take a look at my CV? It's attached.")
    return AppliedEmailPlan(**{**base, **kw})


# ------------------------------------------------------------------------------------ mode


def test_a_job_with_a_posting_is_applied_and_one_without_is_speculative() -> None:
    posted = Job(source="adzuna", external_id="a", url="u", title="T", company_id=1,
                 dedupe_key="a", description="We build things.")
    bare = Job(source="adzuna", external_id="b", url="", title="T", company_id=1, dedupe_key="b")
    assert outreach.email_mode(posted) == "applied"
    assert outreach.email_mode(bare) == "speculative"
    assert outreach.email_mode(posted, "speculative") == "speculative"
    assert outreach.email_mode(bare, "applied") == "applied"
    assert outreach.email_mode(posted, "nonsense") == "applied"


def test_the_subject_is_role_application_and_your_name() -> None:
    assert ac.subject_line("Mobile Developer", "Mohamed Hassen Amara", "en") \
        == "Mobile Developer application – Mohamed Hassen Amara"
    assert ac.subject_line("Développeur mobile", "Alex Doe", "fr") \
        == "Candidature Développeur mobile – Alex Doe"
    assert ac.plain_role("Mobile Engineer (m/w/d) – Flutter, Enterprise-App") == "Mobile Engineer"
    assert ac.plain_role("Senior Backend Engineer – Platform") == "Senior Backend Engineer"
    assert ac.plain_role("Full-Stack Developer") == "Full-Stack Developer"


# ---------------------------------------------------------------------------------- generate


def test_generate_writes_the_application_follow_up_without_researching(
        job_ready: dict) -> None:  # noqa: F811
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter(), researcher=NoResearch(),
                          hook_checker=NoResearch())
    assert d.plan["format"] == "applied" and d.plan["mode"] == "applied"
    assert d.subject.startswith("Data Engineer application – ")
    parts = d.body.split("\n\n")
    assert parts[0] == "Hi Ana," and "applying" in parts[1] and "Data Engineer" in parts[1]
    assert parts[-1].endswith("CV? It's attached.")  # a natural ask, not a forced question
    assert not errors(d.violations), d.violations
    assert d.plan["application"]["applied"] is False
    assert "snippet" in warnings(d.violations)  # the fixture's listing is one short line


def test_the_speculative_mode_is_still_there(job_ready: dict) -> None:  # noqa: F811
    from tests.test_intro_email import Site, research

    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter(), mode="speculative",
                          researcher=research.MockResearcher(), fetcher=Site())
    assert d.plan["format"] == "intro" and d.body.split("\n\n")[2] == d.plan["intro_line"]


def test_the_api_takes_a_mode_and_refuses_a_wrong_one(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    assert client.post(f"/api/applications/{job_ready['app']}/draft/generate?mode=x") \
        .status_code == 422


def test_an_applied_draft_cant_get_the_careers_page_sentence(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    r = client.post(f"/api/outreach/drafts/{d.id}/mention-application", json={"include": True})
    assert r.status_code == 409


# --------------------------------------------------------------------- facts block, style warns


def test_a_good_follow_up_passes(job_ready: dict) -> None:  # noqa: F811
    assert errors(ac.check_plan(plan(job_ready), ctx_for(job_ready))) == set()


def test_what_the_old_rules_blocked_is_now_allowed(job_ready: dict) -> None:  # noqa: F811
    """The listing, the role, a closing that isn't a question and a short email: none of them
    is an error any more."""
    found = ac.check_plan(
        plan(job_ready, ask="I've attached my CV."),
        ctx_for(job_ready, job_text=f"Data Engineer\n{RESIDENCY} We build data pipelines."))
    assert errors(found) == set(), found
    assert "length" in warnings(found)  # the 90-170 range is a warning, never a block


def test_visa_and_sponsorship_mentions_are_strictly_banned_errors(job_ready: dict) -> None:  # noqa: F811
    say = plan(job_ready, opening="I've just applied for Data Engineer at Voxa, though I "
                                  "would need visa sponsorship.")
    found = ac.check_plan(say, ctx_for(job_ready))
    assert "visa_disclaimer_banned" in errors(found)

    say_exp = plan(job_ready, experience=[EmailSentence(
        text="I built systems and need sponsorship.", citations=[job_ready["role"]])])
    found_exp = ac.check_plan(say_exp, ctx_for(job_ready))
    assert "visa_disclaimer_banned" in errors(found_exp)


def test_body_assembly_excludes_constraints(job_ready: dict) -> None:  # noqa: F811
    p = plan(job_ready, ask="Would you look at my CV?")
    body_text = ac.body(p)
    assert "visa" not in body_text.lower()
    assert "sponsorship" not in body_text.lower()
    assert "relocation" not in body_text.lower()


@pytest.mark.parametrize(("change", "expected"), [
    ({"experience": [EmailSentence(text="I built it with Kafka and Terraform at scale.",
                                   citations=[0])]}, "grounding"),
    ({"opening": "I applied for the Data Engineer role at Voxa with 12 years behind me."},
     "years"),
    ({"greeting": "Hi Bob,"}, "name"),
    ({"opening": "I applied for the Data Engineer role at Zeta and wanted to reach out."},
     "company"),
    ({"signal": HookSentence(text="Voxa grew 45% last year.", signal_ids=[7])}, "signal"),
    ({"signal": HookSentence(text="Voxa helps insurers.", signal_ids=[])}, "signal"),
    ({"experience": []}, "experience"),
    ({"opening": ""}, "opening"),
])
def test_only_facts_names_and_years_block(job_ready: dict, change: dict, expected: str) -> None:  # noqa: F811
    p = plan(job_ready, **change)
    if expected == "name":
        p.greeting = "Hi Bob,"
    found = ac.check_plan(p, ctx_for(job_ready))
    assert expected in errors(found), found


def test_style_is_only_a_warning(job_ready: dict) -> None:  # noqa: F811
    found = ac.check_plan(
        plan(job_ready, ask="Let's synergize!", opening="I applied for the Data Engineer role at "
             "Voxa. I am passionate about it!"), ctx_for(job_ready, banned=["synergize"]))
    assert errors(found) == set(), found
    assert {"banned", "tone"} <= warnings(found)


def test_a_short_listing_warns_that_requirements_cant_be_seen_and_a_full_one_does_not(
        job_ready: dict) -> None:  # noqa: F811
    short = ac.check_plan(plan(job_ready), ctx_for(job_ready))
    assert "snippet" in warnings(short) and errors(short) == set()
    full = ac.check_plan(plan(job_ready), ctx_for(
        job_ready, job_text="Data Engineer\n" + "We build data pipelines for insurers. " * 60))
    assert "snippet" not in warnings(full)


@pytest.mark.parametrize("text", [
    "* German and English, both written and spoken",
    "Fluent German required", "Deutschkenntnisse erforderlich", "Wohnsitz in Deutschland",
    "You live in Germany (German residency required)", "English and French, written and spoken",
    "## Applicant location requirements\n\nDE"])
def test_the_listing_requirements_the_detector_recognises(text: str) -> None:
    assert ac.listing_states_constraint(text)
    assert not ac.listing_states_constraint("Flutter, Riverpod, Remote, Cologne, 30 days off")


def test_two_proofs_one_sentence_each(job_ready: dict) -> None:  # noqa: F811
    three = plan(job_ready, experience=[
        EmailSentence(text="I built pipelines.", citations=[job_ready["role"]])] * 3)
    assert "experience" in warnings(ac.check_plan(three, ctx_for(job_ready)))
    long = "I built data pipelines " + "with great care and many steps " * 8 + "for a small team."
    found = ac.check_plan(plan(job_ready, experience=[
        EmailSentence(text=long, citations=[job_ready["role"]])]), ctx_for(job_ready))
    assert "proof_length" in warnings(found)


def test_the_step_offers_the_default_mode_and_the_snippet_state(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    step = client.get(f"/api/applications/{job_ready['app']}/outreach").json()
    assert step["email_mode"] == "applied" and step["listing_short"] is True
    assert step["can_fetch_listing"] is True and step["listing_chars"] < ac.SNIPPET_CHARS


def test_a_linkedin_job_is_never_fetched(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        job = s.get(Job, s.get(Application, job_ready["app"]).job_id)
        job.url = "https://www.linkedin.com/jobs/view/123"
        s.add(job)
        s.commit()
        job_id = job.id
    r = client.post(f"/api/jobs/{job_id}/fetch-full").json()
    assert r["ok"] is False and r["can_paste"] is True and "LinkedIn" in r["message"]
    step = client.get(f"/api/applications/{job_ready['app']}/outreach").json()
    assert step["can_fetch_listing"] is False


def test_saving_the_full_listing_keeps_it_and_queues_a_rescore(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    with Session(engine) as s:
        job_id = s.get(Application, job_ready["app"]).job_id
    text = "Data Engineer\n" + "We build data pipelines for insurers. " * 60
    r = client.put(f"/api/jobs/{job_id}/description", json={"description": text}).json()
    assert r["ok"] and r["characters"] >= ac.SNIPPET_CHARS
    step = client.get(f"/api/applications/{job_ready['app']}/outreach").json()
    assert step["listing_short"] is False


def test_your_languages_are_facts_the_verifier_can_use(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        pool = load_pool(s)
        pool.profile["languages"] = [{"language": "English", "level": "Full professional"},
                                     {"language": "French", "level": "Native"}]
        facts = verifier.candidate_sources(s, pool, None)["facts"]
    assert outreach.logistics(pool)["languages"] == "English (Full professional), French (Native)"
    assert "English (Full professional), French (Native) (no other language is claimed)" in facts


def test_a_long_opening_that_argues_a_fit_is_warned(job_ready: dict) -> None:  # noqa: F811
    found = ac.check_plan(plan(job_ready, opening=(
        "I've just applied for the Data Engineer role at Voxa and wanted to reach out directly, "
        "since your insurance automation work is close to everything I have been building lately "
        "in my own projects, and I would love to bring that same energy and care to your team "
        "this year.")), ctx_for(job_ready))
    assert errors(found) == set() and "opening" in warnings(found)


def test_a_signal_is_optional_and_never_recited(job_ready: dict) -> None:  # noqa: F811
    ok = ac.check_plan(plan(job_ready, signal=HookSentence(
        text="The 37% automation a mutual insurer reached with you is what drew me in.",
        signal_ids=[7])), ctx_for(job_ready))
    assert errors(ok) == set()
    recited = ac.check_plan(plan(job_ready, signal=HookSentence(
        text="A mutual insurer automated 37% of its incoming requests with you.",
        signal_ids=[7])), ctx_for(job_ready, signals={
            7: "A mutual insurer automated 37% of its incoming requests with you."}))
    assert errors(recited) == set() and "signal" in warnings(recited)


def test_a_signal_that_guesses_what_it_shows_is_warned(job_ready: dict) -> None:  # noqa: F811
    found = ac.check_plan(plan(job_ready, signal=HookSentence(
        text="A mutual insurer reached 37% automation, which says a lot about how you work.",
        signal_ids=[7])), ctx_for(job_ready))
    assert errors(found) == set() and "signal" in warnings(found)


def test_an_edited_email_keeps_the_fact_checks_and_only_warns_about_style(
        job_ready: dict) -> None:  # noqa: F811
    ctx = ctx_for(job_ready)
    ok = "Hi Ana,\n\nI applied for the Data Engineer role at Voxa.\n\nI built pipelines."
    assert errors(ac.check_text("Data Engineer application – Alex Doe", ok, ctx)) == set()
    bad = ok + " I also run Kubernetes clusters with 99% uptime."
    assert "grounding" in errors(ac.check_text("S", bad, ctx))
    assert "subject" in errors(ac.check_text("", ok, ctx))


# ------------------------------------------------------------------- approval and verification


def test_the_applied_verifier_gets_the_listing_your_situation_and_the_application_status(
        job_ready: dict) -> None:  # noqa: F811
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter())

    class Spy:
        model, prompt_version, via, auth_source = "spy", "verify/test", "test", "none"
        seen: dict = {}

        def verify(self, request: dict):  # noqa: ANN202
            from app.providers.base import VerifyPlan

            self.seen = request
            return VerifyPlan(claims=[])

    spy = Spy()
    with Session(engine) as s:
        draft = s.get(type(d), d.id)
        verifier.verify_email(s, draft, spy)
    assert "listing" in spy.seen["sources"] and "email about a job application" \
        in spy.seen["kind"]
    facts = spy.seen["sources"]["facts"]
    assert "Application: the candidate is applying" in facts


def test_approving_an_applied_email_records_an_applied_example(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    assert client.post(f"/api/outreach/drafts/{d.id}/approve").status_code == 200
    with Session(engine) as s:
        row = s.exec(select(EmailExample).where(EmailExample.draft_id == d.id)).one()
        assert row.kind == "approved" and row.inputs["mode"] == "applied"
        assert s.get(Application, job_ready["app"]) is not None


# -------------------------------------------------- v14: summarize, don't import the bullets


def test_eight_words_in_a_row_from_a_bullet_is_a_copy_and_a_paraphrase_is_not(
        job_ready: dict) -> None:  # noqa: F811
    words = job_ready["fact"].split()
    assert len(words) >= 9
    copied = f"At {job_ready['org']} I " + " ".join(words[:9]) + "."
    found = ac.check_plan(plan(job_ready, experience=[
        EmailSentence(text=copied, citations=[job_ready["role"]])]), ctx_for(job_ready))
    copy = next(v for v in found if v["type"] == "cv_copy")
    assert copy["severity"] == "warning" and "summarize in your own words" in copy["message"]
    assert ac.copies(found)
    paraphrase = f"At {job_ready['org']} I work on {job_ready['tag']} day to day."
    again = ac.check_plan(plan(job_ready, experience=[
        EmailSentence(text=paraphrase, citations=[job_ready["role"]])]), ctx_for(job_ready))
    assert not ac.copies(again)


def test_a_style_reference_is_part_of_the_copy_check(job_ready: dict) -> None:  # noqa: F811
    reference = "I build mobile screens and connect them to the REST backend every single week"
    sentence = "I build mobile screens and connect them to the REST backend for the team."
    found = ac.check_plan(
        plan(job_ready, experience=[EmailSentence(text=sentence, citations=[job_ready["role"]])]),
        ctx_for(job_ready, references=[reference]))
    assert any(v["type"] == "cv_copy" and "style reference" in v["message"] for v in found)


def test_experience_is_written_with_i_not_as_a_fragment(job_ready: dict) -> None:  # noqa: F811
    fragment = f"Shipped data pipelines with {job_ready['tag']} to production."
    found = ac.check_plan(plan(job_ready, experience=[
        EmailSentence(text=fragment, citations=[job_ready["role"]])]), ctx_for(job_ready))
    assert "fragment" in warnings(found)
    assert "fragment" not in warnings(ac.check_plan(plan(job_ready), ctx_for(job_ready)))
    fr = ac.check_plan(plan(job_ready, experience=[EmailSentence(
        text=f"Chez {job_ready['org']}, je construis des pipelines avec {job_ready['tag']}.",
        citations=[job_ready["role"]])]), ctx_for(job_ready, language="fr"))
    assert "fragment" not in warnings(fr)


def test_numbers_and_tools_are_counted_over_the_whole_email(job_ready: dict) -> None:  # noqa: F811
    busy = plan(job_ready, ask="I cut costs by 40%, load times by 30% and errors by 15%: "
                               "would you look at my CV?")
    found = ac.check_plan(busy, ctx_for(job_ready))
    assert "numbers" in warnings(found)
    assert "numbers" not in warnings(ac.check_plan(plan(job_ready), ctx_for(job_ready)))


def test_backticks_and_addresses_never_reach_the_email() -> None:
    text = 'I built the app for "Lovester" (`lovester.net`) and a site (https://x.example/y).'
    assert ac.clean(text) == 'I built the app for "Lovester" and a site.'


def test_a_language_requirement_does_not_allow_mentioning_your_visa(
        job_ready: dict) -> None:  # noqa: F811
    only_language = ctx_for(job_ready, job_text="Data Engineer\nBusiness fluent in English "
                            "required. We are based in Berlin.")
    say = plan(job_ready, opening="I applied for Data Engineer at Voxa and would need visa "
                                  "sponsorship.")
    found = ac.check_plan(say, only_language)
    assert "visa_disclaimer_banned" in errors(found)


def test_a_copying_draft_is_regenerated_once_and_the_better_one_kept(
        job_ready: dict) -> None:  # noqa: F811
    copied = f"At {job_ready['org']} I " + " ".join(job_ready["fact"].split()[:9]) + "."
    fresh = f"At {job_ready['org']} I work on {job_ready['tag']} every day."
    seen: list[str] = []

    class Drafter(MockEmailDrafter):
        def draft_applied(self, request, feedback: str = ""):  # noqa: ANN001, ANN202
            seen.append(feedback)
            text = fresh if feedback else copied
            return plan(job_ready, experience=[
                EmailSentence(text=text, citations=[job_ready["role"]])])

    d = outreach.generate_applied(engine, job_ready["app"], Drafter())
    assert d.plan["attempts"] == 2 and "own words" in seen[1]
    assert not any(v["type"] == "cv_copy" for v in d.violations)
    # still copying after the retry: kept, as a warning only
    class Stubborn(Drafter):
        def draft_applied(self, request, feedback: str = ""):  # noqa: ANN001, ANN202
            return plan(job_ready, experience=[
                EmailSentence(text=copied, citations=[job_ready["role"]])])

    d2 = outreach.generate_applied(engine, job_ready["app"], Stubborn())
    assert d2.plan["attempts"] == 2
    assert [v["severity"] for v in d2.violations if v["type"] == "cv_copy"] == ["warning"]


def test_the_style_reference_has_its_own_kind(
        job_ready: dict) -> None:  # noqa: F811
    from app.providers.base import EmailRequest
    from app.providers.claude_email import applied_message

    with Session(engine) as s:
        s.add(EmailExample(kind="style_reference", language="en", subject="", body="REF-APPLIED",
                           inputs={"mode": "applied"}))
        s.add(EmailExample(kind="reference_good", language="en", subject="x", body="REF-INTRO",
                           inputs={"mode": "applied"}))  # an approved example is not a reference
        s.commit()
        refs = outreach.applied_references(s)
    assert refs == ["REF-APPLIED"]
    request = EmailRequest(job={}, contact={}, candidate={}, pool={},
                           rules={"style_reference": refs, "language": "en"})
    message = applied_message(request)
    assert "STYLE REFERENCE" in message and "REF-APPLIED" in message
    assert '"style_reference"' not in message  # a block of its own, not inside RULES


def test_the_companys_own_name_is_not_a_tool(job_ready: dict) -> None:  # noqa: F811
    assert ac._is_company_word("GmbH", "Healy World GmbH")
    assert ac._is_company_word("SaltRock", "SaltRock")
    assert ac._is_company_word("ElevenLabs", "ElevenLabs")
    assert not ac._is_company_word("Flutter", "Healy World GmbH")
    ctx = ctx_for(job_ready, company="Healy World GmbH")
    found = ac.text_rules("S", "Hi Ana,\n\nI work with Flutter and REST at Healy World GmbH.", ctx)
    assert not any(v["type"] == "tools" for v in found)


def test_a_years_only_sentence_needs_no_citation(job_ready: dict) -> None:  # noqa: F811
    ctx = ctx_for(job_ready, years_statement="3 years of software engineering experience")
    p = plan(job_ready, experience=[
        EmailSentence(text="I have 3 years of software engineering experience.", citations=[]),
        EmailSentence(text=f"At {job_ready['org']} I work on {job_ready['tag']} every day.",
                      citations=[job_ready["role"]])])
    found = ac.check_plan(p, ctx)
    assert not any(v["type"] == "grounding" and "no citations" in v["message"] for v in found)


def test_the_visa_ban_covers_the_ask_and_german_and_french_terms(job_ready: dict) -> None:  # noqa: F811
    for words in ("Ich brauche eine Arbeitserlaubnis", "Mein Aufenthalt ist befristet",
                  "J'ai besoin d'un titre de séjour", "une question de parrainage",
                  "an Umzug wäre nötig"):
        in_opening = plan(job_ready, opening=f"I've just applied for the role at Voxa. {words}.")
        assert "visa_disclaimer_banned" in errors(ac.check_plan(in_opening, ctx_for(job_ready)))
    in_ask = plan(job_ready, ask="Could we talk about visa sponsorship?")
    assert "visa_disclaimer_banned" in errors(ac.check_plan(in_ask, ctx_for(job_ready)))


def test_a_signal_or_company_fact_may_use_the_words(job_ready: dict) -> None:  # noqa: F811
    fact = "Voxa sponsors a data conference every year"
    ctx = ctx_for(job_ready, signals={7: fact})
    say = plan(job_ready, signal=HookSentence(text=fact + ".", signal_ids=[7]))
    found = ac.check_plan(say, ctx)
    assert "visa_disclaimer_banned" not in {v["type"] for v in found}, found
    # an edited email: the paragraph that carries the company fact is left alone, the rest is not
    text = ac.body(say)
    assert "visa_disclaimer_banned" not in {v["type"] for v in ac.check_text("Role", text, ctx)}
    edited = text.replace("It's attached.", "It's attached. I need a visa.")
    assert "visa_disclaimer_banned" in errors(ac.check_text("Role", edited, ctx))
