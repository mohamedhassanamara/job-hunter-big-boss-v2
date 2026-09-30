"""Cover letters: language detection, the Claude call (isolated, subscription only), grounding and
letter checks in English and French, the retry, editing, approval, locking at Mark applied, and
the template (same header as the CV, one page). No model or network calls."""

import re
import shutil
from datetime import date
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    AppSetting,
    Company,
    CoverLetter,
    CVVersion,
    ExperienceItem,
    Job,
)
from app.models.enums import ApplyMethod, CVStatus, Route, Stage
from app.providers.base import (
    AnswersRequest,
    CoverLetterPlan,
    CVPlan,
    DraftFailed,
    EmailSentence,
    LetterRequest,
    PlanEntry,
    PlanProject,
)
from app.providers.claude_letter import ClaudeLetterDrafter
from app.services import cover_letter as cl
from app.services import letter_check as lc
from app.services import tracking
from app.services.cv_pool import load_pool
from app.services.cv_render import (
    CompileResult,
    CVProfile,
    LetterDocument,
    load_template,
    render_letter_tex,
    render_tex,
)
from app.services.text import detect_language
from tests.test_cv import fake_run

_n = count(1)
needs_latex = pytest.mark.skipif(shutil.which("latexmk") is None, reason="needs TeX Live")


def test_language_follows_the_listing() -> None:
    assert detect_language("Nous recherchons un Data Engineer pour rejoindre notre équipe à "
                           "Paris. Vous serez en charge des pipelines de données.") == "fr"
    assert detect_language("We are looking for a Data Engineer to join our team in Berlin. "
                           "You will own the data pipelines.") == "en"
    assert detect_language("") == "en"


# ------------------------------------------------------------------------------ Claude call

LETTER = {"paragraphs": [{"sentences": [{"text": "Acme is hiring.", "about_job": True}]}],
          "ask": "Could we meet?"}


def test_letter_drafter_uses_the_isolated_subscription_call() -> None:
    calls: list = []
    d = ClaudeLetterDrafter(runner=fake_run({"is_error": False, "structured_output": LETTER},
                                            calls=calls))
    out = d.draft_letter(LetterRequest(job={}, candidate={}, pool={}), feedback="- too short")
    assert out.ask == "Could we meet?" and d.prompt_version == "cover_letter/v4"
    cmd, kw = calls[0]
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    system = cmd[cmd.index("--system-prompt") + 1]
    assert "cover letter" in system and "rejected by the automatic checks" in system
    assert "REJECTED PROBLEMS" in kw["input"] and "EXPERIENCE POOL" in kw["input"]

    answers = ClaudeLetterDrafter(runner=fake_run(
        {"is_error": False, "structured_output": {"answers": []}}, calls=calls))
    answers.answer(AnswersRequest(job={}, candidate={}, pool={}, questions=[]))
    system = calls[1][0][calls[1][0].index("--system-prompt") + 1]
    assert "application form" in system and "QUESTIONS" in calls[1][1]["input"]
    with pytest.raises(DraftFailed, match="API key"):
        ClaudeLetterDrafter(runner=fake_run({"is_error": False, "structured_output": LETTER},
                                            auth="ANTHROPIC_API_KEY")).draft_letter(
            LetterRequest(job={}, candidate={}, pool={}))


# ----------------------------------------------------------------------------------- checks


@pytest.fixture
def ctx(seeded: None) -> lc.Context:
    with Session(engine) as s:
        pool = load_pool(s)
    return lc.Context(pool=pool, allowed_years={3}, company="Acme", min_words=20, max_words=200,
                      job_text="Data Engineer\nWe build pipelines with Spark and Kafka for 2M "
                               "users.",
                      banned=lc.DEFAULT_BANNED["en"], other_companies=["Globex"])


def role(ctx: lc.Context) -> ExperienceItem:
    return next(i for i in ctx.pool.items.values() if i.kind == "job" and len(i.bullets) >= 2)


def other_item(ctx: lc.Context, *not_ids: int) -> ExperienceItem:
    return next(i for i in ctx.pool.items.values()
                if i.kind in ("job", "project") and i.bullets and i.id not in not_ids)


def example(item: ExperienceItem) -> dict:
    """A v3 example: what the work was, in plain words (not the CV bullet), cited."""
    tool = f" with {item.tags[0]}" if item.tags else ""
    return {"text": f"At {item.org or item.title}, I built this kind of system{tool}, which is "
                    "close to what your team does.", "citations": [item.id]}


def paragraphs(ctx: lc.Context, opening: str = "Acme builds pipelines for millions of users, "
               "which is the work I want to do.") -> list[dict]:
    r = role(ctx)
    return [{"sentences": [{"text": opening, "about_job": True},
                           {"text": "My experience matches that closely.", "citations": [r.id]}]},
            {"sentences": [example(r), example(other_item(ctx, r.id))]}]


def kinds(violations: list[dict]) -> set[str]:
    return {v["type"] for v in violations if v["severity"] == "error"}


ASK = "I would welcome an interview to discuss the role."


def test_a_clean_letter_passes(ctx: lc.Context) -> None:
    assert kinds(lc.check_letter("Dear Hiring Manager,", paragraphs(ctx), ASK, ctx)) == set()


@pytest.mark.parametrize(("change", "expected"), [
    (lambda p: p[1]["sentences"].append({"text": "I ran Kubernetes for 40 teams.",
                                          "citations": [p[1]["sentences"][0]["citations"][0]]}),
     "grounding"),
    (lambda p: p[0]["sentences"].append({"text": "Acme serves 9M users with Snowflake.",
                                          "about_job": True}), "grounding"),
    (lambda p: p.pop(), "structure"),
    (lambda p: p[0]["sentences"].__setitem__(0, {
        "text": "Acme: we build pipelines with Spark and Kafka for 2M users.",
        "about_job": True}), "restates"),
    (lambda p: p[1]["sentences"].append({"text": "Idempotent loads handled schema drift.",
                                          "citations": p[1]["sentences"][0]["citations"]}),
     "jargon"),
    (lambda p: p[1]["sentences"].append({"text": "We passed 10/10 tests.",
                                          "citations": p[1]["sentences"][0]["citations"]}),
     "jargon"),
    (lambda p: p.__setitem__(0, {"sentences": [{"text": "The role builds pipelines.",
                                                "about_job": True}]}), "opening"),
    (lambda p: p[0]["sentences"].append({"text": "Is Acme hiring a Data Engineer?",
                                          "about_job": True}), "ask"),
    (lambda p: p[0]["sentences"].append({"text": "Like Globex, Acme is hiring.",
                                          "about_job": True}), "company"),
    (lambda p: p[0]["sentences"].append({"text": "I am passionate about Acme.",
                                          "about_job": True}), "banned"),
    (lambda p: p[0]["sentences"].append({"text": "Acme is hiring. " + "word " * 200,
                                          "about_job": True}), "length"),
])
def test_each_letter_rule_is_enforced(ctx: lc.Context, change, expected: str) -> None:  # noqa: ANN001
    p = paragraphs(ctx)
    change(p)
    assert expected in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))


def test_the_letter_ends_with_one_clear_ask(ctx: lc.Context) -> None:
    assert "ask" in kinds(lc.check_letter("Dear Hiring Manager,", paragraphs(ctx),
                                          "Thank you.", ctx))
    assert "ask" not in kinds(lc.check_letter("Dear Hiring Manager,", paragraphs(ctx),
                                              "Could we talk next week?", ctx))


def test_opening_must_come_from_the_listing(ctx: lc.Context) -> None:
    p = paragraphs(ctx)
    p[0] = {"sentences": [{**p[1]["sentences"][0], "text": "Acme matters to me. "
                           + p[1]["sentences"][0]["text"]}]}
    assert "opening" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))


def test_at_most_two_examples_of_one_or_two_sentences(ctx: lc.Context) -> None:
    r = role(ctx)
    other = other_item(ctx, r.id)
    third = other_item(ctx, r.id, other.id)
    p = paragraphs(ctx)
    p[1]["sentences"].append(example(third))
    assert "builds" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    p = paragraphs(ctx)
    p[1]["sentences"] += [example(r), example(r)]  # r now runs 3 sentences
    found = lc.check_letter("Dear Hiring Manager,", p, ASK, ctx)
    assert any("runs 3 sentences" in v["message"] for v in found)


def test_cv_bullets_are_not_pasted_or_listing_repeated(ctx: lc.Context) -> None:
    r = role(ctx)
    p = paragraphs(ctx)
    p[1]["sentences"][0] = {"text": r.bullets[0], "citations": [r.id]}
    assert "cv_copy" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    p = paragraphs(ctx)
    p[1]["sentences"].insert(0, {"text": "Acme also ships pipelines.", "about_job": True})
    assert "listing" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))


def test_the_current_role_is_used_when_it_matches(ctx: lc.Context) -> None:
    r = role(ctx)
    unused = other_item(ctx, r.id, other_item(ctx, r.id).id)
    ctx.current_role_id, ctx.current_role_org = unused.id, unused.org or unused.title
    found = lc.check_letter("Dear Hiring Manager,", paragraphs(ctx), ASK, ctx)
    assert "current_role" in kinds(found)
    edited = [{"text": "Why Acme."}, {"text": f"At {ctx.current_role_org} I did this work."}]
    assert "current_role" not in kinds(lc.check_letter("Dear Hiring Manager,", edited, ASK, ctx))
    ctx.current_role_id = None


def test_fit_sentences_state_only_the_profile(ctx: lc.Context) -> None:
    ctx.facts_text = "Tunis, Tunisia needs visa sponsorship to work"
    p = paragraphs(ctx)
    p[1]["sentences"].append({"text": "I am based in Tunis and need visa sponsorship.",
                              "about_candidate": True})
    assert "grounding" not in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    p[1]["sentences"][-1] = {"text": "I am based in Tunis and ready to relocate to Paris.",
                             "about_candidate": True}
    found = lc.check_letter("Dear Hiring Manager,", p, ASK, ctx)
    assert any("relocating" in v["message"] for v in found if v["type"] == "grounding")
    ctx.facts_text = ""


def test_current_role_is_picked_by_tags_or_a_title_theme() -> None:
    from datetime import date as d

    from app.services.cv_pool import Pool

    role = ExperienceItem(id=1, kind="job", title="Software Engineer", org="Sportco",
                          start_date=d(2025, 9, 1), tags=["spring-boot", "java", "flutter"],
                          bullets=["Built backend endpoints for the app",
                                   "Integrated backend services with data-driven screens"])
    pool = Pool(items={1: role}, profile={}, by_kind={"job": [role]})
    assert cl.current_role(pool, "Développeur Backend\nPython et PostgreSQL") is role
    assert cl.current_role(pool, "Java Engineer\nJava and Spring Boot") is role
    assert cl.current_role(pool, "Data Engineer\nSpark and dbt") is None  # "data" too broad


def test_the_ask_is_its_own_short_paragraph(ctx: lc.Context) -> None:
    long = "I would welcome an interview " + "to talk about it " * 10 + "soon."
    assert "ask" in kinds(lc.check_letter("Dear Hiring Manager,", paragraphs(ctx), long, ctx))


def test_form_text_has_no_letter_furniture_and_a_hard_limit(ctx: lc.Context) -> None:
    ctx.format, ctx.char_limit = "form", 200
    p = paragraphs(ctx)
    assert "form" not in kinds(lc.check_letter("", p, "", ctx))
    assert "form" in kinds(lc.check_letter("Madame, Monsieur,", p, "", ctx))
    p[1]["sentences"].append({"text": "Kind regards, Alex.", "citations": [role(ctx).id]})
    assert "form" in kinds(lc.check_letter("", p, "", ctx))
    long = paragraphs(ctx)
    long[1]["sentences"][0]["text"] += " It helped." * 30
    found = lc.check_letter("", long, "", ctx)
    assert any(v["type"] == "length" and v["message"].endswith("/200 characters") for v in found)
    ctx.format, ctx.char_limit = "pdf", None


def test_french_letters_use_french_banned_phrases_and_the_french_years_wording(
        ctx: lc.Context) -> None:
    ctx.language, ctx.banned = "fr", lc.DEFAULT_BANNED["fr"]
    ctx.years_statement = "3 years of software engineering experience"
    ctx.years_statement_fr = lc.french_statement(ctx.years_statement)
    assert ctx.years_statement_fr == "3 ans d'expérience en ingénierie logicielle"
    ok = paragraphs(ctx, "Acme recrute un Data Engineer, et j’apporte 3 ans d’expérience en "
                         "ingénierie logicielle.")
    assert kinds(lc.check_letter("Madame, Monsieur,", ok, "Seriez-vous disponible pour un "
                                 "entretien ?", ctx)) == set()
    short = paragraphs(ctx, "Acme recrute ; ingénieur logiciel, j'ai 3 ans d'expérience.")
    assert "years" not in kinds(lc.check_letter("Madame, Monsieur,", short, ASK, ctx))
    for bad in ("Acme recrute et j'ai plus de 3 ans en data.", "Acme recrute ; 3 years in data."):
        assert "years" in kinds(lc.check_letter("Madame, Monsieur,", paragraphs(ctx, bad), ASK,
                                                ctx))
    cliché = paragraphs(ctx, "Je me permets de postuler chez Acme.")
    assert "banned" in kinds(lc.check_letter("Madame, Monsieur,", cliché, ASK, ctx))


def test_french_thousands_and_the_years_sentence_dont_confuse_the_checks(ctx: lc.Context) -> None:
    r = role(ctx)
    item = ctx.pool.get(r.id)
    fact = next((b for b in item.bullets if re.search(r"\d,\d{3}", b)), None)
    p = paragraphs(ctx)
    if fact:  # "2,000" in the pool, "2 000" in a French letter
        french = re.sub(r"(\d),(\d{3})", "\\1\u00a0\\2", fact)
        p[1]["sentences"].append({"text": french, "citations": [r.id]})
    assert lc._ungroup("environ 2 000 et 2,000 puis 1 234 567") == \
        "environ 2000 et 2000 puis 1234567"
    # The close backs the years with roles: that isn't a fourth build.
    others = [i.id for i in ctx.pool.items.values() if i.kind == "job" and i.id != r.id][:2]
    p.append({"sentences": [{"text": "I bring 3 years of experience.", "citations": others}]})
    found = lc.check_letter("Dear Hiring Manager,", p, ASK, ctx)
    assert "builds" not in kinds(found)
    assert "grounding" not in kinds(found)


def test_edited_paragraphs_are_checked_against_experience_and_listing(ctx: lc.Context) -> None:
    p = paragraphs(ctx)
    p[1] = {"text": "I cut costs by 73% with Snowflake at my last company."}
    assert "grounding" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    p[1] = {"text": "I built pipelines with Spark, the stack Acme uses."}
    assert "grounding" not in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))


def test_answers_respect_the_character_limit_without_cutting(ctx: lc.Context) -> None:
    text = "I built pipelines with Spark. " * 5
    found = lc.check_answer(None, text, 60, ctx)
    assert f"{len(text)}/60 characters" in {v["message"] for v in found}
    assert lc.check_answer(None, "I built pipelines with Spark.", 60, ctx) == []


# ------------------------------------------------------------------------------ generation


@pytest.fixture
def web_job(seeded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A web-apply job with an approved CV; LaTeX is faked (a 1-page PDF file)."""
    def fake_compile(tex: str, out_dir: Path, name: str = "cv") -> CompileResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf = out_dir / f"{name}.pdf"
        pdf.write_bytes(b"%PDF-1.4 " + tex[-40:].encode())
        return CompileResult(True, pdf, 1, 0.6)

    monkeypatch.setattr(cl, "compile_tex", fake_compile)
    monkeypatch.setattr(cl, "LETTER_DIR", tmp_path / "letters")
    cv_pdf = tmp_path / "cv.pdf"
    cv_pdf.write_bytes(b"%PDF-1.4 cv")
    n = next(_n)
    with Session(engine) as s:
        items = [SimpleNamespace(id=i.id, kind=i.kind, bullets=list(i.bullets),
                                 org=i.org or i.title, tags=list(i.tags))
                 for i in s.exec(select(ExperienceItem)).all()
                 if i.kind in ("job", "project") and i.bullets]
        # Short word ranges: a fixture can't hand-write 220 grounded words; the ranges are
        # checked by their own tests.
        settings = s.exec(select(AppSetting).where(AppSetting.key == "cover_letter")).first() \
            or AppSetting(key="cover_letter", value={})
        settings.value = {**(settings.value or {}), "min_words": 20, "max_words": 320,
                          "form_min_words": 15, "form_max_words": 220}
        s.add(settings)
        company = Company(name=f"Webco {n}", normalized_name=f"webco {n}")
        s.add(company)
        s.flush()
        job = Job(source="adzuna", external_id=f"web-{n}", url="https://example.test",
                  title="Data Engineer", company_id=company.id, dedupe_key=f"web-{n}",
                  description="Nous recherchons un Data Engineer pour notre équipe. Vous "
                              "construirez des pipelines de données avec Spark.")
        s.add(job)
        s.flush()
        app = Application(job_id=job.id, stage=Stage.cv_ready, route=Route.web_apply)
        s.add(app)
        s.flush()
        cv = CVVersion(application_id=app.id, version=1, status=CVStatus.approved,
                       pdf_path=str(cv_pdf), plan={"plan": CVPlan(
                           summary="", summary_short="",
                           roles=[PlanEntry(item_id=i.id, relevance=9) for i in items
                                  if i.kind == "job"],
                           projects=[PlanProject(item_id=i.id, relevance=5) for i in items
                                     if i.kind == "project"]).model_dump()})
        s.add(cv)
        s.commit()
        return {"app": app.id, "cv": cv.id, "company": company.name, "items": items}


class Script:
    """A letter drafter returning scripted plans; records the requests and feedback."""

    model, prompt_version = "script", "cover_letter/test"

    def __init__(self, *plans: CoverLetterPlan):
        self.plans, self.feedback, self.requests = list(plans), [], []

    def draft_letter(self, request: LetterRequest, feedback: str = "") -> CoverLetterPlan:
        self.feedback.append(feedback)
        self.requests.append(request)
        assert request.pool["roles"], "the CV's items are what the letter may cite"
        return self.plans.pop(0)

    draft_form = draft_letter  # same shape; the request's rules say it's a form


def good_plan(info: dict, fr: bool = True, form: bool = False) -> CoverLetterPlan:
    """A v3 letter: why this company (one listing sentence), two examples in plain words."""
    company = info["company"]
    first, second = info["items"][0], info["items"][1]
    if fr:
        opening = f"Chez {company}, les pipelines de données avec Spark me donnent envie de postuler."
        why = "C'est exactement le travail que je veux faire."
        ex = [f"Chez {i.org}, j'ai construit ce type de système, proche de votre besoin."
              for i in (first, second)]
    else:
        opening = f"{company} works on data pipelines, which is why I want to join."
        why = "That is exactly the work I want to do."
        ex = [f"At {i.org}, I built this kind of system, close to what you need."
              for i in (first, second)]
    return CoverLetterPlan(paragraphs=[
        {"sentences": [EmailSentence(text=opening, about_job=True),
                       EmailSentence(text=why, citations=[first.id])]},
        {"sentences": [EmailSentence(text=ex[0], citations=[first.id]),
                       EmailSentence(text=ex[1], citations=[second.id])]}],
        ask="" if form else ("Seriez-vous disponible pour un entretien ?" if fr
                             else "Could we meet for an interview?"))


def test_generate_follows_the_listing_language_retries_once_then_stores(web_job: dict) -> None:
    bad = CoverLetterPlan(paragraphs=[{"sentences": [{"text": "Bonjour.", "about_job": True}]}],
                          ask="Merci.")
    drafter = Script(bad, good_plan(web_job))
    letter = cl.generate(engine, web_job["app"], drafter)
    assert drafter.requests[0].rules["language"] == "fr" and letter.language == "fr"
    assert drafter.feedback[0] == "" and "paragraphs" in drafter.feedback[1]
    assert letter.plan["attempts"] == 2 and lc.errors(letter.violations) == [], letter.violations
    assert letter.version == 1 and letter.status == CVStatus.draft and letter.page_count == 1
    assert letter.content["salutation"] == "Madame, Monsieur,"
    assert letter.text.startswith("Madame, Monsieur,") and "salutations distinguées" in \
        letter.text
    assert "Objet : candidature au poste de Data Engineer" in letter.tex


def test_language_override_and_new_versions_replace_the_draft(web_job: dict) -> None:
    with Session(engine) as s:
        app = s.get(Application, web_job["app"])
        app.letter_language = "en"
        s.add(app)
        s.commit()
    first = cl.generate(engine, web_job["app"], Script(good_plan(web_job, fr=False)))
    second = cl.generate(engine, web_job["app"], Script(good_plan(web_job, fr=False)))
    assert (first.language, second.language, second.version) == ("en", "en", 2)
    with Session(engine) as s:
        assert s.get(CoverLetter, first.id).status == CVStatus.superseded
    assert second.content["salutation"] == "Dear Hiring Manager,"
    assert "Application for the Data Engineer position" in second.tex


def test_generate_needs_an_approved_cv(web_job: dict) -> None:
    with Session(engine) as s:
        s.get(CVVersion, web_job["cv"]).status = CVStatus.draft
        s.commit()
    with pytest.raises(cl.LetterError, match="Approve the CV"):
        cl.generate(engine, web_job["app"], Script())


def test_errors_block_approval_edits_recheck_and_approval_supersedes(web_job: dict) -> None:
    letter = cl.generate(engine, web_job["app"], Script(good_plan(web_job)))
    edited = cl.edit(engine, letter.id, paragraphs=[
        *(cl.paragraph_text(p) for p in letter.content["paragraphs"][:2]),
        "J'ai réduit les coûts de 73 % avec Snowflake."])
    assert edited.id == letter.id and edited.content["paragraphs"][2] == {
        "text": "J'ai réduit les coûts de 73 % avec Snowflake."}
    assert "sentences" in edited.content["paragraphs"][0]  # untouched: citations kept
    assert "grounding" in kinds(edited.violations)
    with pytest.raises(cl.LetterError, match="Fix"):
        cl.approve(engine, letter.id)
    fixed = cl.edit(engine, letter.id, paragraphs=[
        cl.paragraph_text(p) for p in letter.content["paragraphs"]])
    assert lc.errors(fixed.violations) == [], fixed.violations
    assert cl.approve(engine, letter.id).status == CVStatus.approved
    newer = cl.generate(engine, web_job["app"], Script(good_plan(web_job)))
    cl.approve(engine, newer.id)
    with Session(engine) as s:
        assert s.get(CoverLetter, letter.id).status == CVStatus.superseded


def test_mark_applied_locks_the_cv_and_the_letter(web_job: dict) -> None:
    letter = cl.approve(engine, cl.generate(engine, web_job["app"],
                                            Script(good_plan(web_job))).id)
    with Session(engine) as s:
        app = s.get(Application, web_job["app"])
        tracking.mark_applied(s, app, applied_on=date(2026, 9, 30), method=ApplyMethod.company_site,
                              cover_letter_id=letter.id)
        s.commit()
        app = s.get(Application, web_job["app"])
        saved = s.get(CoverLetter, letter.id)
        assert app.applied_cover_letter_id == letter.id and app.stage == Stage.done
        assert saved.locked_at is not None and re.fullmatch(r"[0-9a-f]{64}", saved.pdf_sha256)
        assert s.get(CVVersion, web_job["cv"]).locked_at is not None
    changed = cl.edit(engine, letter.id, salutation="Madame,")
    assert changed.id != letter.id and changed.version == letter.version + 1
    with Session(engine) as s:
        assert s.get(CoverLetter, letter.id).content["salutation"] == "Madame, Monsieur,"


def test_mark_applied_without_a_letter_or_with_a_draft(web_job: dict) -> None:
    draft = cl.generate(engine, web_job["app"], Script(good_plan(web_job)))
    with Session(engine) as s:
        app = s.get(Application, web_job["app"])
        with pytest.raises(tracking.TrackingError, match="approved cover letter"):
            tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.company_site,
                                  cover_letter_id=draft.id)
        s.rollback()
        app = s.get(Application, web_job["app"])
        tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.company_site)
        s.commit()
        assert s.get(Application, web_job["app"]).applied_cover_letter_id is None


QUESTION = "Expliquez-nous pourquoi vous souhaitez nous rejoindre"


def test_form_text_answers_the_question_with_a_hard_limit(web_job: dict) -> None:
    long = good_plan(web_job, form=True)
    long.paragraphs[1].sentences[0].text += " Cela a beaucoup compté pour moi." * 12
    drafter = Script(long, good_plan(web_job, form=True))
    letter = cl.generate(engine, web_job["app"], drafter, fmt="form", question=QUESTION,
                         char_limit=400)
    rules = drafter.requests[0].rules
    assert (rules["format"], rules["question"], rules["char_limit"]) == ("form", QUESTION, 400)
    assert "/400 characters" in drafter.feedback[1]
    assert (letter.format, letter.pdf_path, letter.page_count) == ("form", None, None)
    assert letter.content["salutation"] == "" and lc.errors(letter.violations) == [], \
        letter.violations
    text = letter.text
    assert len(text) <= 400 and "Madame" not in text and "salutations" not in text
    assert "Objet" not in text and cl.ensure_pdf(engine, letter) is None
    # A PDF letter and a form text keep their own versions.
    pdf = cl.generate(engine, web_job["app"], Script(good_plan(web_job)))
    assert (pdf.version, letter.version) == (1, 1)
    with pytest.raises(cl.LetterError, match="question"):
        cl.generate(engine, web_job["app"], Script(), fmt="form")


def test_mark_applied_records_the_form_text_too(web_job: dict) -> None:
    form = cl.approve(engine, cl.generate(engine, web_job["app"],
                                          Script(good_plan(web_job, form=True)), fmt="form",
                                          question=QUESTION).id)
    with Session(engine) as s:
        app = s.get(Application, web_job["app"])
        tracking.mark_applied(s, app, applied_on=None, method=ApplyMethod.company_site,
                              form_letter_id=form.id)
        s.commit()
        assert s.get(CoverLetter, form.id).locked_at is not None
        assert s.get(Application, web_job["app"]).applied_cover_letter_id is None


def test_download_name(web_job: dict) -> None:
    letter = cl.generate(engine, web_job["app"], Script(good_plan(web_job)))
    with Session(engine) as s:
        name = cl.download_name(s, s.get(CoverLetter, letter.id))
    assert name.endswith(f"_Cover_Letter_{web_job['company'].replace(' ', '_')}.pdf")


# -------------------------------------------------------------------------------- template


def header(tex: str) -> str:
    start = tex.index("%----------HEADER----------")
    return tex[start:tex.index(r"\end{center}", start)]


def test_the_letter_template_shares_the_cv_header() -> None:
    from app.services.cv_render import CVDocument, CVLink

    profile = CVProfile(full_name="Alex Sample", location="City", email="alex@example.com",
                        links=[CVLink(type="github", url="https://github.com/example")])
    template = load_template("default")
    letter = render_letter_tex(LetterDocument(language="fr", paragraphs=["Un.", "Deux."]),
                               profile, template)
    assert header(letter) == header(render_tex(CVDocument(), profile, template))
    assert r"\usepackage[french]{babel}" in letter


@needs_latex
def test_the_letter_template_compiles_to_one_page(tmp_path: Path) -> None:
    from app.services.cv_render import compile_tex

    profile = CVProfile(full_name="Alex Sample", location="City", email="alex@example.com")
    body = "J’ai conçu des pipelines de données avec Spark : 40 % de temps gagné. " * 6
    doc = LetterDocument(language="fr", place_date="City, le 30 septembre 2026",
                         company="Acme & Co", subject="Objet : candidature",
                         salutation="Madame, Monsieur,", paragraphs=[body] * 4,
                         closing="Je vous prie d'agréer l'expression de mes salutations.")
    result = compile_tex(render_letter_tex(doc, profile, load_template("default")), tmp_path,
                         "cover_letter")
    assert result.ok and result.pages == 1, result.error


# ------------------------------------------------------------------------------------- API


def test_letter_api_studio_generate_edit_approve_pdf_and_apply(web_job: dict, client) -> None:  # noqa: ANN001
    app_id = web_job["app"]
    studio = client.get(f"/api/applications/{app_id}/letter").json()
    assert (studio["language"], studio["detected_language"], studio["template_ok"]) == (
        "fr", "fr", True)
    assert studio["approved_cv_id"] == web_job["cv"] and studio["letters"] == []
    studio = client.put(f"/api/applications/{app_id}/letter/language",
                        json={"language": "en"}).json()
    assert studio["language"] == "en" and studio["language_setting"] == "en"
    assert client.put(f"/api/applications/{app_id}/letter/language",
                      json={"language": "de"}).status_code == 422

    letter = client.post(f"/api/applications/{app_id}/letter/generate", json={}).json()
    assert letter["language"] == "en" and letter["version"] == 1 and letter["has_pdf"]
    assert letter["download_name"].endswith(".pdf") and letter["word_count"] > 0
    assert all(p["edited"] is False for p in letter["paragraphs"])
    assert set(map(int, letter["sources"])) == {c for p in letter["paragraphs"]
                                                for x in p["sentences"] for c in x["citations"]}

    # Replace the mock's text with a clean scripted letter, then edit through the API.
    clean = cl.generate(engine, app_id, Script(good_plan(web_job, fr=False)))
    texts = [p["text"] for p in client.get(f"/api/applications/{app_id}/letter")
             .json()["letters"][0]["paragraphs"]]
    edited = client.patch(f"/api/letters/{clean.id}",
                          json={"paragraphs": [texts[0], texts[1] + " I love it!"]}).json()
    assert edited["paragraphs"][1]["edited"] and any(
        v["type"] == "tone" for v in edited["violations"])
    client.patch(f"/api/letters/{clean.id}", json={"paragraphs": texts})
    approved = client.post(f"/api/letters/{clean.id}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    pdf = client.get(f"/api/letters/{clean.id}/pdf?download=true")
    assert pdf.status_code == 200 and "no-store" in pdf.headers["cache-control"]
    assert "attachment" in pdf.headers["content-disposition"]
    text = client.get(f"/api/letters/{clean.id}/text").json()["text"]
    assert text.startswith("Dear Hiring Manager,") and "Kind regards,\n" in text

    ready = next(r for r in client.get("/api/applications/ready").json()
                 if r["application_id"] == app_id)
    assert (ready["letter_id"], ready["letter_status"]) == (clean.id, "approved")
    r = client.post(f"/api/applications/{app_id}/applied",
                    json={"method": "company_site", "cover_letter_id": clean.id})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/letters/{letter['id']}/approve").status_code == 409  # superseded


def test_cover_letter_settings_are_validated(client) -> None:  # noqa: ANN001
    values = client.get("/api/settings").json()["values"]["cover_letter"]
    assert values["filename_pattern"] == "{full_name}_Cover_Letter_{company}.pdf"
    assert "je me permets de" in values["banned_phrases"]["fr"]
    ok = client.put("/api/settings/cover_letter", json={"value": {**values, "min_words": 200}})
    assert ok.status_code == 200
    assert ok.json()["values"]["cover_letter"]["min_words"] == 200
    for bad in ({"min_words": 400, "max_words": 300}, {"filename_pattern": "{nope}.pdf"},
                {"closing": {"de": "Grüße"}}, {"language": "es"}):
        assert client.put("/api/settings/cover_letter",
                          json={"value": {**values, **bad}}).status_code == 422
    client.put("/api/settings/cover_letter", json={"value": values})


def test_the_sandbox_has_a_letter_and_answers_for_the_tours(seeded: None, client) -> None:  # noqa: ANN001
    ready = client.get("/api/applications/ready").json()
    with_letter = [r for r in ready if r["letter_status"] != "none"]
    assert len(with_letter) == 1
    answers = client.get(f"/api/applications/{with_letter[0]['application_id']}/answers").json()
    assert len(answers) == 2 and all(a["sentences"] for a in answers)
