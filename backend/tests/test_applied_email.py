"""The job-linked email (prompt v17, mode "applied"): the portal-first follow-up. Code builds the
subject, greeting, opening (from the application record), ask and signature; the model writes
only the proof. Facts, names, years, links, apologies and attachment wording block; length and
style warn. The research-based introduction stays as the "speculative" mode. Offline: the mock
drafter, no model."""

from datetime import date

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Application, EmailExample, Job
from app.providers.base import AppliedEmailPlan, EmailSentence
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
        opening=ac.opening_line("Data Engineer", "company_site", date(2026, 10, 20),
                                date(2026, 10, 26), "en"),
        experience=[
            EmailSentence(text=f"At {job_ready['org']}, I built data pipelines with "
                               f"{job_ready['tag']}, from the first design to production, for "
                               "a small team.", citations=[job_ready["role"]]),
            EmailSentence(text="I like keeping them reliable as the volume grows.",
                          citations=[job_ready["role"]])],
        ask=ac.cta_line("en"))
    return AppliedEmailPlan(**{**base, **kw})


def good_body(job_ready: dict) -> str:  # noqa: F811
    return ac.body(plan(job_ready))


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


def test_the_subject_is_role_application_and_company_without_your_name() -> None:
    assert ac.subject_line("Mobile Developer", "en", "Acme") \
        == "Mobile Developer application - Acme"
    assert ac.subject_line("Développeur mobile", "fr", "Acme") \
        == "Candidature Développeur mobile - Acme"
    assert ac.subject_line("Mobile Developer", "en") == "Mobile Developer application"
    assert ac.speculative_subject("Data Engineer (m/w/d) – Berlin", "Voxa", "en") \
        == "Quick intro | Data Engineer at Voxa"
    assert ac.plain_role("Mobile Engineer (m/w/d) – Flutter, Enterprise-App") == "Mobile Engineer"
    assert ac.plain_role("Senior Backend Engineer – Platform") == "Senior Backend Engineer"
    assert ac.plain_role("Full-Stack Developer") == "Full-Stack Developer"


# ---------------------------------------------------------------------------------- generate


def test_generate_writes_the_application_follow_up_without_researching(
        job_ready: dict) -> None:  # noqa: F811
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter(), researcher=NoResearch(),
                          hook_checker=NoResearch())
    assert d.plan["format"] == "applied" and d.plan["mode"] == "applied"
    assert d.subject.startswith("Data Engineer application - ")
    parts = d.body.split("\n\n")
    assert parts[0] == "Hi Ana," and "applied" in parts[1] and "Data Engineer" in parts[1]
    assert parts[-1].endswith("?") and "roadmap" not in parts[-1]  # the ask is built by code
    assert not errors(d.violations), d.violations
    assert d.plan["application"]["applied"] is True  # portal first: the gate needs it
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
        plan(job_ready, ask="Would you be open to a quick call?"),
        ctx_for(job_ready, job_text=f"Data Engineer\n{RESIDENCY} We build data pipelines."))
    assert errors(found) == set(), found
    assert "length" not in warnings(found)  # well under 110 words


def test_attachment_wording_is_allowed_because_the_cv_is_attached(job_ready: dict) -> None:  # noqa: F811
    found = ac.check_text("S - Alex Doe",
                          good_body(job_ready) + " I have attached my CV for quick review.",
                          ctx_for(job_ready))
    assert "attachment" not in errors(found), found


def test_visa_and_sponsorship_mentions_are_strictly_banned_errors(job_ready: dict) -> None:  # noqa: F811
    found = ac.check_text("S - Alex Doe", good_body(job_ready) + " I would need visa "
                          "sponsorship.", ctx_for(job_ready))
    assert "visa_disclaimer_banned" in errors(found)

    say_exp = plan(job_ready, experience=[EmailSentence(
        text="I built systems and need sponsorship.", citations=[job_ready["role"]])])
    found_exp = ac.check_plan(say_exp, ctx_for(job_ready))
    assert "visa_disclaimer_banned" in errors(found_exp)


def test_body_assembly_excludes_constraints(job_ready: dict) -> None:  # noqa: F811
    body_text = ac.body(plan(job_ready))
    assert "visa" not in body_text.lower()
    assert "sponsorship" not in body_text.lower()
    assert "relocation" not in body_text.lower()


@pytest.mark.parametrize(("change", "expected"), [
    ({"experience": [EmailSentence(text="I built it with Kafka and Terraform at scale.",
                                   citations=[0])]}, "grounding"),
    ({"experience": [EmailSentence(text="I have 12 years of experience building pipelines.",
                                   citations=[0])]}, "years"),
    ({"greeting": "Hi Bob,"}, "name"),
    ({"experience": [EmailSentence(text="I built pipelines at Zeta.", citations=[0])]},
     "company"),
    ({"experience": []}, "experience"),
])
def test_only_facts_names_and_years_block(job_ready: dict, change: dict, expected: str) -> None:  # noqa: F811
    found = ac.check_plan(plan(job_ready, **change), ctx_for(job_ready))
    assert expected in errors(found), found


def test_style_is_only_a_warning(job_ready: dict) -> None:  # noqa: F811
    found = ac.check_text("S - Alex Doe", good_body(job_ready) + " Let's synergize!",
                          ctx_for(job_ready, banned=["synergize"]))
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


def test_an_edited_email_keeps_the_fact_checks_and_only_warns_about_style(
        job_ready: dict) -> None:  # noqa: F811
    ctx = ctx_for(job_ready)
    ok = "Hi Ana,\n\nI applied for the Data Engineer role at Voxa.\n\nI built pipelines."
    assert errors(ac.check_text("Data Engineer application - Voxa", ok, ctx)) == set()
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
    assert "Application: the candidate applied for this job on" in facts


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
    found = ac.check_text("S - Alex Doe", good_body(job_ready) + " I cut costs by 40%, load "
                          "times by 30% and errors by 15%.", ctx_for(job_ready))
    assert "numbers" in warnings(found)
    assert "numbers" not in warnings(ac.check_plan(plan(job_ready), ctx_for(job_ready)))


def test_backticks_and_addresses_never_reach_the_email() -> None:
    text = 'I built the app for "Lovester" (`lovester.net`) and a site (https://x.example/y).'
    assert ac.clean(text) == 'I built the app for "Lovester" and a site.'


def test_a_language_requirement_does_not_allow_mentioning_your_visa(
        job_ready: dict) -> None:  # noqa: F811
    only_language = ctx_for(job_ready, job_text="Data Engineer\nBusiness fluent in English "
                            "required. We are based in Berlin.")
    found = ac.check_text("Role", good_body(job_ready) + " I would need visa sponsorship.",
                          only_language)
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
        in_proof = plan(job_ready, experience=[EmailSentence(
            text=f"I built pipelines. {words}.", citations=[job_ready["role"]])])
        assert "visa_disclaimer_banned" in errors(ac.check_plan(in_proof, ctx_for(job_ready)))
        edited = good_body(job_ready) + f" {words}."
        assert "visa_disclaimer_banned" in errors(ac.check_text("S", edited, ctx_for(job_ready)))


def test_a_company_fact_paragraph_may_use_the_words(job_ready: dict) -> None:  # noqa: F811
    fact = "Voxa sponsors a data conference every year"
    ctx = ctx_for(job_ready, signals={7: fact})
    text = good_body(job_ready) + f"\n\n{fact}."
    assert "visa_disclaimer_banned" not in {v["type"] for v in ac.check_text("Role", text, ctx)}
    edited = text.replace("this week?", "this week? I need a visa.")
    assert "visa_disclaimer_banned" in errors(ac.check_text("Role", edited, ctx))


# ------------------------------------------------------------------ v17: built by code


TODAY = date(2026, 10, 26)


def test_the_opening_says_how_and_when_from_the_application_record() -> None:
    today = ac.opening_line("Mobile Engineer", "company_site", TODAY, TODAY, "en")
    assert today == "I applied for the Mobile Engineer role through your careers page today."
    assert "yesterday" in ac.opening_line("X", "linkedin", date(2026, 10, 25), TODAY, "en")
    assert "on Thursday" in ac.opening_line("X", "company_site", date(2026, 10, 22), TODAY, "en")
    assert "on 12 October" in ac.opening_line("X", "company_site", date(2026, 10, 12), TODAY,
                                              "en")
    for variant in range(ac.VARIANTS):  # never the old filler, never "earlier today"
        line = ac.opening_line("X", "company_site", date(2026, 10, 25), TODAY, "en", variant)
        assert "introduce myself" not in line and "earlier today" not in line


def test_the_opening_capitalizes_a_leading_date() -> None:
    line = ac.opening_line("Mobile Engineer", "linkedin", date(2026, 10, 22), TODAY, "en", 2)
    assert line == "On Thursday, I applied for the Mobile Engineer role on LinkedIn."
    assert ac.opening_line("Mobile Engineer", "linkedin", None, TODAY, "en", 2) == (
        "I applied for the Mobile Engineer role on LinkedIn.")


@pytest.mark.parametrize("variant", range(ac.VARIANTS))
def test_a_linkedin_or_board_application_never_says_careers_page(variant: int) -> None:
    linkedin = ac.opening_line("Engineer", "linkedin", TODAY, TODAY, "en", variant)
    board = ac.opening_line("Engineer", "job_board", TODAY, TODAY, "en", variant)
    assert "LinkedIn" in linkedin and "careers" not in linkedin
    assert "a job board" in board and "careers" not in board  # no board is ever named
    assert "Engineer" in board


def test_the_wordings_rotate_and_french_is_built_too() -> None:
    lines = {ac.opening_line("E", "company_site", TODAY, TODAY, "en", v)
             for v in range(ac.VARIANTS)}
    assert len(lines) == ac.VARIANTS
    fr = ac.opening_line("Ingénieur", "company_site", date(2026, 10, 25), TODAY, "fr")
    assert fr.startswith("J'ai postulé au poste de Ingénieur via votre site carrières hier")


def test_the_closing_has_three_wordings_a_call_for_recruiters_and_never_next_week() -> None:
    for recruiter in (False, True):
        for lang in ("en", "fr"):
            for v in range(ac.CTA_VARIANTS):
                for weekday in range(7):
                    line = ac.cta_line(lang, recruiter, v, weekday)
                    assert "next week" not in line and "prochaine" not in line
    cv = "I have attached my CV for quick review. "
    assert "brief 10-minute introductory call in the next few days" in ac.cta_line(
        "en", False, 0, 4)
    assert ac.cta_line("en", True, 0, 0) == cv + (
        "If my background aligns with what you're screening for, I'd welcome a brief "
        "10-minute introductory call this week.")
    assert ac.cta_line("en", False, 0, 0) == cv + (
        "Would you be open to a brief 10-minute introductory call this week?")
    assert ac.cta_line("en", False, 1, 0) == cv + (
        "Do you have 10 minutes for a brief technical call this week?")
    assert ac.cta_line("en", False, 2, 0) == cv + (
        "Happy to hop on a 10-minute call this week if you'd like to connect.")
    assert ac.cta_line("en", True, 0, 4).endswith("introductory call in the next few days.")
    assert ac.cta_line("en", True, 1, 0) == ac.cta_line("en", True, 2, 0)
    assert ac.is_recruiter("Senior Technical Recruiter") and ac.is_recruiter("Head of People")
    assert not ac.is_recruiter("CTO", "Engineering leader")


@pytest.mark.parametrize("variant", [1, 2])
def test_wordings_b_and_c_say_this_week_only_monday_to_wednesday(variant: int) -> None:
    for weekday in (0, 1, 2):
        assert "this week" in ac.cta_line("en", False, variant, weekday)
        assert "cette semaine" in ac.cta_line("fr", False, variant, weekday)
    for weekday in (3, 4, 5, 6):
        line = ac.cta_line("en", False, variant, weekday)
        assert "this week" not in line and "in the next few days" in line


def test_the_closing_never_repeats_the_previous_emails_wording_to_the_company() -> None:
    for previous in range(ac.CTA_VARIANTS):
        picked = {ac.cta_variant(previous, seed) for seed in range(12)}
        assert previous not in picked and len(picked) == ac.CTA_VARIANTS - 1  # still rotates
    assert {ac.cta_variant(None, seed) for seed in range(3)} == {0, 1, 2}


def test_the_weekday_is_read_in_your_timezone(job_ready: dict) -> None:  # noqa: F811
    from datetime import UTC, datetime

    from app.models import AppSetting

    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "motivation")).first()
        if row is None:
            row = AppSetting(key="motivation", value={})
        row.value = {**row.value, "timezone": "Africa/Tunis"}
        s.add(row)
        s.commit()
        # Wednesday 23:30 UTC is already Thursday 00:30 in Tunis (UTC+1, no DST).
        assert outreach.local_weekday(s, datetime(2026, 10, 28, 23, 30, tzinfo=UTC)) == 3
        assert outreach.local_weekday(s, datetime(2026, 10, 28, 22, 30, tzinfo=UTC)) == 2


def test_a_generated_email_avoids_the_previous_closing_to_the_same_company(
        job_ready: dict) -> None:  # noqa: F811
    first = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter())
    second = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter())
    assert first.plan["cta_variant"] != second.plan["cta_variant"]
    assert first.body.split("\n\n")[-1] != second.body.split("\n\n")[-1]
    assert "next week" not in second.body


def test_next_week_in_the_closing_is_a_warning_not_an_error(job_ready: dict) -> None:  # noqa: F811
    text = good_body(job_ready).rsplit("\n\n", 1)[0] + "\n\nCould we talk next week?"
    found = ac.check_text("S - Alex Doe", text, ctx_for(job_ready))
    assert "closing" in warnings(found) and "closing" not in errors(found)
    assert "closing" not in warnings(ac.check_text("S - Alex Doe", good_body(job_ready),
                                                   ctx_for(job_ready)))


@pytest.mark.parametrize(("text", "kind"), [
    ("See https://portfolio.example/work for details.", "url"),
    ("More on mysite.dev please.", "url"),
    ("Even though I'm based in Tunis, I can work remotely.", "apology"),
    ("I know you receive many emails.", "apology"),
    ("Sorry to bother you.", "apology"),
    ("Are you hiring right now?", "bypass"),
    ("I'm writing instead of the portal because it is faster.", "bypass"),
])
def test_links_apologies_and_bypass_wording_block(job_ready: dict, text: str, kind: str) -> None:  # noqa: F811
    found = ac.check_text("S - Alex Doe", good_body(job_ready) + " " + text, ctx_for(job_ready))
    assert kind in errors(found), found


def test_more_than_110_words_is_an_error(job_ready: dict) -> None:  # noqa: F811
    wordy = good_body(job_ready) + " " + "I enjoy this work a lot. " * 12
    found = ac.check_text("S - Alex Doe", wordy, ctx_for(job_ready))
    assert "length" in errors(found)
    assert "length" not in errors(ac.check_text("S - Alex Doe", good_body(job_ready),
                                                ctx_for(job_ready)))


def test_the_duplicate_check_looks_at_the_proof_only(job_ready: dict) -> None:  # noqa: F811
    mine = good_body(job_ready)
    same_proof = mine.replace("Hi Ana,", "Hi Bob,").replace("Data Engineer position", "Role")
    other = (1, "Bob", same_proof)
    assert "duplicate" in warnings(ac.check_text("S", mine, ctx_for(job_ready, others=[other])))
    other_opening = mine.split("\n\n")
    other_opening[2] = "I run the on-call rota for the payments platform."
    different = (2, "Cy", "\n\n".join(other_opening))
    assert "duplicate" not in warnings(ac.check_text("S", mine, ctx_for(
        job_ready, others=[different])))


def test_a_generated_email_is_built_from_the_record_with_links_in_the_signature(
        job_ready: dict) -> None:  # noqa: F811
    from app.models import AppSetting

    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).first()
        profile = dict(row.value)
        profile["links"] = [{"type": "portfolio", "label": "", "url": "https://me.example.dev"},
                            {"type": "github", "label": "", "url": "https://github.com/alex"},
                            {"type": "linkedin", "label": "", "url": "https://www.linkedin.com/in/alex"}]
        row.value = profile
        s.add(row)
        s.commit()
    try:
        d = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter())
        parts = d.body.split("\n\n")
        assert len(parts) == 4 and parts[1].startswith(
            ("I applied", "I submitted", "Today, I applied", "My application"))
        assert "Data Engineer" in parts[1]
        assert "https://" not in d.body and "me.example.dev" not in d.body  # links: signature only
        assert len(d.body.split()) <= 110 and not errors(d.violations), d.violations
        with Session(engine) as s:
            full = outreach.full_body(s, d)
        tail = full.split("\n\n")[-1].split("\n")
        assert tail[0] == "Best regards," and tail[-1] == (
            "me.example.dev · github.com/alex · linkedin.com/in/alex")
    finally:
        with Session(engine) as s:
            row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).first()
            row.value = {**row.value, "links": []}
            s.add(row)
            s.commit()


def test_a_projects_track_proof_cannot_cite_a_job(job_ready: dict) -> None:  # noqa: F811
    from app.services import honesty

    rules = honesty.Rules(projects=[honesty.Track("Data/AI", ["data"], ["data engineer"],
                                                  "personal projects")])
    ctx = ctx_for(job_ready, track="Data/AI", honesty=rules)
    found = ac.check_plan(plan(job_ready), ctx)  # cites the fixture's job
    assert "projects_track" in errors(found), found
    # the same proof on a professional track is fine
    assert "projects_track" not in errors(ac.check_plan(plan(job_ready), ctx_for(job_ready)))
    # an internship is allowed on a projects track
    with Session(engine) as s:
        pool = load_pool(s)
        item = pool.items[job_ready["role"]]
        item.title = "Data Engineering Intern"
    ok = ac.check_plan(plan(job_ready), ctx_for(job_ready, pool=pool, track="Data/AI",
                                                honesty=rules))
    assert "projects_track" not in errors(ok)


# ------------------------------------------------------------ v19: persona, scenario, banlist


@pytest.mark.parametrize("title,group,expected", [
    ("Engineering Manager", "Engineering Manager", "engineering_manager"),
    ("Head of Data", None, "engineering_manager"),
    ("VP Engineering", None, "engineering_manager"),
    ("Co-Founder & CEO", "Founder / CEO", "founder_cto"),
    ("CTO", None, "founder_cto"),
    ("Staff Engineer", None, "tech_lead"),
    ("Senior Software Developer", None, "tech_lead"),
    ("Tech Lead", None, "tech_lead"),
    ("Senior Technical Recruiter", None, "recruiter"),
    ("Talent Acquisition Partner", "HR / Talent", "recruiter"),
    ("Office Coordinator", None, "other"),
    (None, None, "other")])
def test_persona_comes_from_the_contacts_title(title: str | None, group: str | None,
                                               expected: str) -> None:
    assert ac.persona_for(title, group) == expected


def test_the_years_a_listing_asks_for_are_read_near_the_word_experience() -> None:
    assert ac.required_years("We need 5+ years of experience with Flutter") == 5
    assert ac.required_years("Experience: at least 4 years in mobile") == 4
    assert ac.required_years("Founded 12 years ago. A friendly team.") is None
    assert ac.required_years("3 years of experience, ideally 6 years total experience") == 6


def test_a_years_gap_needs_two_more_years_than_you_have() -> None:
    gap = ac.scenario_for("Senior Developer", "5+ years of experience", "I built apps", 3)
    assert gap == {"scenario": "years_gap", "required_years": 5, "have_years": 3}
    near = ac.scenario_for("Developer", "4 years of experience", "I built apps", 3)
    assert near["scenario"] == "direct"
    assert ac.scenario_for("Developer", "5 years of experience", "x", None)["scenario"] == "direct"


def test_a_stack_pivot_is_a_title_stack_your_pool_lacks_in_a_family_it_has() -> None:
    pivot = ac.scenario_for("React Native Engineer", "Build apps", "Shipped Flutter apps", 3)
    assert pivot["scenario"] == "stack_pivot" and pivot["target_stack"] == "react native"
    assert pivot["pool_stack"] == ["flutter"]
    same = ac.scenario_for("Flutter Engineer", "Build apps", "Shipped Flutter apps", 3)
    assert same["scenario"] == "direct"
    nothing = ac.scenario_for("React Native Engineer", "Build apps", "Wrote SQL pipelines", 3)
    assert nothing["scenario"] == "direct"  # no mobile stack in the pool: not a pivot
    assert ac.scenario_for("Java Developer", "javascript, typescript", "Python APIs", 3)[
        "target_stack"] == "java"  # java is not javascript


def test_a_pivot_outranks_a_years_gap() -> None:
    both = ac.scenario_for("React Native Engineer", "6 years of experience", "Flutter", 3)
    assert both["scenario"] == "stack_pivot" and both["required_years"] == 6


@pytest.mark.parametrize("phrase", [
    "wanted to introduce myself directly", "I hope this email finds you well",
    "This fits your team's roadmap", "I spearheaded the work", "I am passionate",
    "I was thrilled", "rock-solid releases", "engineering discipline", "UI assembly",
    "I'd love to grab a coffee", "so here is the part that matters",
    "I'd rather say that up front"])
def test_the_v19_banlist_is_blocking(job_ready: dict, phrase: str) -> None:  # noqa: F811
    text = good_body(job_ready) + f"\n\n{phrase}."
    assert "banlist" in errors(ac.check_text("S - Alex Doe", text, ctx_for(job_ready)))


@pytest.mark.parametrize("scenario,phrase", [
    ("years_gap", "Despite my lack of years"), ("years_gap", "even though I only have three"),
    ("years_gap", "rather than ticket-taking"), ("years_gap", "high-velocity teams"),
    ("stack_pivot", "What carries over is work I've done"),
    ("stack_pivot", "I'm productive from day one"),
    ("stack_pivot", "it will transfer immediately")])
def test_scenario_patterns_are_banned_only_in_their_scenario(scenario: str, phrase: str) -> None:
    found = ac.banlist_violations(f"I did it. {phrase}.", scenario)
    assert found and found[0]["severity"] == "error"
    assert not ac.banlist_violations(f"I did it. {phrase}.", "direct")


def test_the_scenarios_one_acknowledgement_may_name_the_postings_years(
        job_ready: dict) -> None:  # noqa: F811
    sentence = (f"While the posting calls for 5 years, my 3 years of software engineering have "
                f"centered on delivery: at {job_ready['org']}, I built data pipelines with "
                f"{job_ready['tag']}.")
    p = plan(job_ready, experience=[EmailSentence(text=sentence, citations=[job_ready["role"]])])
    ctx = ctx_for(job_ready, scenario="years_gap", required_years={5})
    assert "years" not in errors(ac.check_plan(p, ctx)), ac.check_plan(p, ctx)
    plain = ctx_for(job_ready)  # without the scenario, 5 years is still a claim you can't make
    assert "years" in errors(ac.check_plan(p, plain))
    claim = sentence.replace("the posting calls for 5 years", "I have 5 years")
    p2 = plan(job_ready, experience=[EmailSentence(text=claim, citations=[job_ready["role"]])])
    assert "years" in errors(ac.check_plan(p2, ctx))  # only the posting's wording is exempt


def test_the_target_stack_may_be_named_in_a_pivot(job_ready: dict) -> None:  # noqa: F811
    sentence = (f"While my production work is in {job_ready['tag']} rather than React Native, "
                f"at {job_ready['org']} I built data pipelines with {job_ready['tag']}.")
    p = plan(job_ready, experience=[EmailSentence(text=sentence, citations=[job_ready["role"]])])
    ctx = ctx_for(job_ready, scenario="stack_pivot", target_stack="React Native")
    assert "grounding" not in errors(ac.check_plan(p, ctx)), ac.check_plan(p, ctx)


def test_generate_stores_the_persona_and_scenario_and_honors_overrides(
        job_ready: dict) -> None:  # noqa: F811
    d = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter())
    g = d.plan["guidance"]
    assert g["persona_source"] == "auto" and g["persona"] in ac.PERSONAS
    assert g["scenario"] == "direct" and d.plan["request"]["rules"]["persona"] == g["persona"]
    assert d.plan["request"]["rules"]["scenario"]["kind"] == "direct"
    picked = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter(),
                                       persona="founder_cto", base_draft_id=d.id)
    assert picked.plan["guidance"]["persona"] == "founder_cto"
    assert picked.plan["guidance"]["persona_source"] == "manual"
    kept = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter(),
                                     base_draft_id=picked.id)  # a regeneration keeps your pick
    assert kept.plan["guidance"]["persona"] == "founder_cto"
    cleared = outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter(),
                                        persona="auto", base_draft_id=kept.id)
    assert cleared.plan["guidance"]["persona_source"] == "auto"
    with pytest.raises(outreach.OutreachError):
        outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter(), persona="boss")
    with pytest.raises(outreach.OutreachError):  # nothing in the listing to acknowledge
        outreach.generate_applied(engine, job_ready["app"], MockEmailDrafter(),
                                  scenario="stack_pivot")


def test_a_stray_stack_mention_is_not_a_pivot_and_the_title_beats_the_group() -> None:
    stray = "We use Java daily. Some services are .NET or .NET Core, others Python."
    assert ac.scenario_for("Backend Engineer", stray, "Java Spring Python", 3)[
        "scenario"] == "direct"
    dominant = "React Native React Native React Native React Native, some Swift"
    assert ac.scenario_for("Mobile Engineer", dominant, "Flutter apps", 3)[
        "target_stack"] == "react native"
    assert ac.persona_for("Engineering Manager", "CTO") == "engineering_manager"
    assert ac.persona_for("", "Founder / CEO") == "founder_cto"
    assert ac.persona_for("Partner", "HR / Talent") == "recruiter"


def test_a_model_opening_and_raw_dates_are_dropped_from_the_proof() -> None:
    from types import SimpleNamespace as S
    kept = ac.strip_model_opening([
        S(text="I applied for the Fullstack role through the company's portal on 2026-10-29."),
        S(text="At Reality Sports I shipped the app on 2026-10-29.")])
    assert [k.text for k in kept] == ["At Reality Sports I shipped the app."]


def test_recruiter_proofs_lead_with_years_and_carry_no_metrics_or_libraries() -> None:
    from types import SimpleNamespace as S

    def plan(*texts: str) -> S:
        return S(experience=[S(text=t) for t in texts], greeting="Hi Anna,", opening="x.", ask="y.")

    good = plan("Over the last 3 years of production engineering I bridged iOS and Android "
                "delivery with Spring Boot APIs.")
    assert ac.recruiter_problems(good) == []
    bad = plan("I built 10+ Flutter screens and 15+ RESTful services behind BFF endpoints.")
    kinds = {p["type"] for p in ac.recruiter_problems(bad)}
    assert {"recruiter_years", "recruiter_jargon"} <= kinds


def test_force_approve_overrides_code_errors_but_records_them(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter())
    with Session(engine) as s:
        row = s.get(type(d), d.id)
        row.violations = [{"type": "grounding", "severity": "error", "where": "body",
                           "message": "false positive"}]
        s.add(row)
        s.commit()
    assert client.post(f"/api/outreach/drafts/{d.id}/approve").status_code == 409
    forced = client.post(f"/api/outreach/drafts/{d.id}/approve?force=true")
    assert forced.status_code == 200 and forced.json()["status"] == "approved"
    with Session(engine) as s:
        approval = s.get(type(d), d.id).plan["approval"]
        assert approval["forced_errors"] == [{"type": "grounding", "message": "false positive"}]


def test_the_opening_and_subject_name_the_company_without_its_legal_form() -> None:
    assert ac.display_company("Acme S.r.l.") == "Acme" and ac.display_company("Acme GmbH") == "Acme"
    assert ac.display_company("Reality Sports Inc.") == "Reality Sports"
    assert ac.display_company("Group") == "Group"
    lines = [ac.opening_line("Fullstack Developer", "linkedin", TODAY, TODAY, "en", v, "Acme Corp")
             for v in range(ac.VARIANTS)]
    assert all("at Acme Corp" in line for line in lines)
    assert lines[0] == (
        "I applied for the Fullstack Developer role at Acme Corp through LinkedIn today.")
    assert "chez Acme" in ac.opening_line("Dev", "linkedin", TODAY, TODAY, "fr", 0, "Acme SAS")
    assert ac.subject_line("Fullstack Developer", "en", "Acme Corp") \
        == "Fullstack Developer application - Acme Corp"
    assert ac.subject_line("Dev", "en") == "Dev application"


# ---- v25: clean titles, hook clause, executive-altitude guards

def test_clean_job_title_strips_scraper_tags() -> None:
    assert ac.clean_job_title("Développeur/Développeuse Flutter (H/F)") == "Développeur Flutter"
    assert ac.clean_job_title("Ingénieur logiciel (F/H) - Paris") == "Ingénieur logiciel"
    assert ac.clean_job_title("Data Engineer (m/w/d)") == "Data Engineer"
    assert ac.clean_job_title("Backend Developer (M/F/D) - Remote") == "Backend Developer"
    assert ac.clean_job_title("Software Engineer (All Genders)") == "Software Engineer"
    assert ac.clean_job_title("Développeur/euse mobile") == "Développeur mobile"
    # not twins: left alone
    assert ac.clean_job_title("Frontend/Backend Engineer") == "Frontend/Backend Engineer"
    assert ac.clean_job_title("Product/Service Owner") == "Product/Service Owner"
    assert "(H/F)" not in ac.subject_line("Développeur Flutter (H/F)", "fr", "Acme")


def test_the_opening_ends_with_the_hook_clause_in_both_languages() -> None:
    hook = "building fast, reliable mobile apps aligns closely with my background"
    en = ac.opening_line("Flutter Developer", "company_site", TODAY, TODAY, "en", 0, "Acme",
                         hook + ".")
    assert en == ("I applied for the Flutter Developer role at Acme through your careers page "
                  f"today, as {hook}.")
    fr = ac.opening_line("Développeur Flutter (H/F)", "company_site", TODAY, TODAY, "fr", 0,
                         "Acme", "un poste centré sur le mobile correspond à mon parcours")
    assert fr == ("J'ai postulé au poste de Développeur Flutter chez Acme via votre site "
                  "carrières aujourd'hui, un poste centré sur le mobile correspond à mon parcours.")
    assert ac.opening_line("X", "linkedin", TODAY, TODAY, "en", 2, "", "as a clause").endswith(
        "on LinkedIn, as a clause.")  # a leading "as" is not doubled
    assert ac.opening_line("X", "linkedin", TODAY, TODAY, "en").endswith("today.")  # no hook


def test_run_on_dashes_and_then_glue_are_blocking() -> None:
    long = " ".join(["word"] * 29) + "."
    assert [v["type"] for v in ac.run_on_violations(long)] == ["run_on"]
    assert ac.run_on_violations(" ".join(["word"] * 28) + ". Short one.") == []
    for bad in ("I built it — then shipped it.", "I built it – fast.",
                "I built it, then shipped it."):
        assert any(v["severity"] == "error" for v in ac.banlist_violations(bad)), bad
    for bad in ("Moreover, I led it.", "I also led it.", "Furthermore it ran.",
                "It ran seamlessly.", "I successfully shipped it.", "Additionally, I led it."):
        assert ac.banlist_violations(bad), bad
    assert ac.banlist_violations("I built it and shipped it.") == []
    assert ac.scraped_title_violations("Dev (H/F) application - Acme", "")
    assert ac.scraped_title_violations("x", "Développeur/Développeuse Flutter")
    assert ac.scraped_title_violations("(m/w/d) x", "")
    assert ac.scraped_title_violations("Dev application - Acme", "I applied for the Dev role") == []


@pytest.mark.parametrize("company", ["Accurat.ai", "Lodgify.io", "Acme.AI Inc.", "Nextlane.io GmbH",
                                     "Zaion.ai"])
def test_a_company_name_that_looks_like_a_domain_is_not_a_link(company: str) -> None:
    short = ac.display_company(company)
    text = (f"I applied for the Data Engineer role at {company} this week. "
            f"What {short} builds with data is close to my work. {short}'s team came up too.")
    assert ac.v17_violations(text, company) == []


@pytest.mark.parametrize("text", [
    "I applied at Accurat.ai. Details on https://accurat.ai/careers",  # a real URL
    "I applied at Accurat.ai. See www.accurat.ai",
    "I applied at Accurat.ai. My site is portfolio.dev",  # a different domain
    "I applied at Accurat.ai. Write to jobs@accurat.ai",  # the company's own address
    "I applied at Accurat.ai. See accurat.ai/careers",
    "I applied at Accurat.ai. See careers.accurat.ai",
])
def test_real_links_and_other_domains_still_fail_next_to_the_company_name(text: str) -> None:
    found = ac.v17_violations(text, "Accurat.ai")
    assert [v["type"] for v in found] == ["url"] and found[0]["severity"] == "error"


def test_without_a_company_the_rule_is_unchanged() -> None:
    assert ac.v17_violations("I applied at Accurat.ai.")  # no company given: still flagged
