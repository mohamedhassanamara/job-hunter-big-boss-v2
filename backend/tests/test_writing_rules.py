"""Phase 7 follow-ups: work authorization only when allowed and asked, your reason for the
company in the opening (rephrased), no task lists, concrete examples, and the same rules on
emails, which follow the listing's language."""

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, AppSetting
from app.services import cover_letter as cl
from app.services import letter_check as lc
from app.services import outreach
from tests.test_cover_letter import ASK, ctx, example, kinds, paragraphs, role  # noqa: F401
from tests.test_outreach import Script, good_plan, job_ready  # noqa: F401 (fixture)


def test_work_authorization_is_never_mentioned_by_default(ctx: lc.Context) -> None:  # noqa: F811
    p = paragraphs(ctx)
    p[1]["sentences"].append({"text": "I am based in Tunis and would need visa sponsorship.",
                              "about_candidate": True})
    assert "authorization" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    ctx.mention_authorization = True
    assert "authorization" not in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    ctx.mention_authorization = False


def test_only_if_the_listing_asks(seeded: None) -> None:
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "writing")).first() \
            or AppSetting(key="writing", value={})
        row.value = {"work_authorization": "if_asked"}
        s.add(row)
        s.commit()
        assert cl.mention_authorization(s, "Candidates must have the right to work in the EU")
        assert not cl.mention_authorization(s, "We build pipelines with Spark")
        row.value = {"work_authorization": "never"}
        s.add(row)
        s.commit()
        assert not cl.mention_authorization(s, "Visa sponsorship available")


def test_the_opening_uses_your_reason_rephrased(ctx: lc.Context) -> None:  # noqa: F811
    ctx.company_reason = "I use their route planning software for my own deliveries"
    p = paragraphs(ctx)
    assert "reason" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    p[0]["sentences"][0] = {"text": "Having relied on Acme's route planning for my own "
                            "deliveries, I know what the software changes.",
                            "about_candidate": True}
    assert "reason" not in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    p[0]["sentences"][0] = {"text": "I use their route planning software for my own deliveries.",
                            "about_candidate": True}
    found = lc.check_letter("Dear Hiring Manager,", p, ASK, ctx)
    assert any("word for word" in v["message"] for v in found)
    ctx.company_reason = ""


def test_no_task_list_and_no_vague_examples(ctx: lc.Context) -> None:  # noqa: F811
    ctx.job_text = "Backend role\nPython, Spark and Kafka in an agile team building APIs."
    p = paragraphs(ctx)
    p[0]["sentences"][0] = {"text": "Acme wants Python, Spark and Kafka in an agile team.",
                            "about_job": True}
    assert "task_list" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    p = paragraphs(ctx)
    r = role(ctx)
    p[1]["sentences"][0] = {"text": f"At {r.org}, I worked on a project close to yours.",
                            "citations": [r.id]}
    assert "vague" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))


def test_emails_follow_the_writing_rules_and_the_listing_language(job_ready: dict,  # noqa: F811
                                                                  client) -> None:  # noqa: ANN001
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        job = app.job_id
    from app.models import Job

    with Session(engine) as s:
        j = s.get(Job, job)
        j.description = "Nous recherchons un ingénieur pour notre équipe de données à Paris."
        s.add(j)
        s.commit()
    pasted = good_plan(job_ready)
    pasted.sentences[1].text = f"At {job_ready['org']}, I {job_ready['fact']}"
    drafter = Script(pasted, good_plan(job_ready))
    draft = outreach.generate(engine, job_ready["app"], drafter)
    assert "reads like a CV bullet" in drafter.feedback[1]
    assert draft.plan["language"] == "fr"
    body = client.get("/api/outreach/drafts?status=draft").json()
    full = next(d for d in body if d["id"] == draft.id)["full_body"]
    # French sign-off, and the email ends with your name (no default last line).
    assert "Bien cordialement," in full and full.rstrip().endswith("Alex Sample")


def test_the_reason_is_saved_on_the_job(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    r = client.patch(f"/api/applications/{job_ready['app']}",
                     json={"company_reason": "  Their product saved my team a week  "})
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.get(Application, job_ready["app"]).company_reason == \
            "Their product saved my team a week"
    assert client.patch(f"/api/applications/{job_ready['app']}",
                        json={"company_reason": "x" * 400}).status_code == 422
    assert client.put("/api/settings/writing",
                      json={"value": {"work_authorization": "maybe"}}).status_code == 422


def test_copied_listing_wording_and_the_years_fact(ctx: lc.Context) -> None:  # noqa: F811
    ctx.job_text = ("AI role\nVous participerez à l’industrialisation de nos solutions d’IA "
                    "générative, conversationnelle et agentique.")
    p = paragraphs(ctx)
    p[0]["sentences"][0] = {"text": "Acme mise sur des solutions d'IA générative, "
                            "conversationnelle et agentique, ce qui me motive.", "about_job": True}
    assert "restates" in kinds(lc.check_letter("Dear Hiring Manager,", p, ASK, ctx))
    ctx.years_statement = "3 years of software engineering experience"
    ctx.years_statement_fr = "3 ans d'expérience en ingénierie logicielle"
    assert lc._candidate_fact_problems("J'ai 3 ans d'expérience en ingénierie logicielle.",
                                       ctx) == []
    ctx.years_statement = ctx.years_statement_fr = None
