"""Fit before/after (gemma on the tailored CV, stored apart; lexical evidence) and Critique
(issues only, never a rewrite). Mock scorer and critic: no model, no network."""

import time

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, CVFit, CVVersion, FitScore, OutreachDraft
from app.providers.mock import MockCritic
from app.services import critique, cv_fit, fit_lexical
from app.services.cv_pool import load_pool
from tests.test_outreach import job_ready  # noqa: F401 (fixture)


def test_lexical_terms_skip_soft_skills_places_and_the_company(seeded: None) -> None:
    vocab = {"python", "spark"}
    assert fit_lexical.salient_terms("Strong communication and proactive mindset", vocab) == []
    terms = fit_lexical.salient_terms("Experience with Python, Spark and PostgreSQL in Paris",
                                      vocab, fit_lexical.ignored("Acme", "Data Engineer", ""))
    assert terms == ["python", "spark", "postgresql"]
    assert fit_lexical._has("We use LLMs daily", "llm")
    assert fit_lexical.years_note("At least 5+ years of Python", 3) == \
        "The listing asks for 5+ years; you have 3"


def test_compare_counts_shown_dropped_and_unbacked(seeded: None) -> None:
    with Session(engine) as s:
        pool = load_pool(s)
    tag = next(t for i in pool.items.values() for t in (i.tags or []) if len(t) > 2)
    description = (f"You will build pipelines with {tag}.\nYou know Haskell and Rust well.\n"
                   "Great communication and a proactive attitude.")
    after = {"summary": "Engineer.", "skills": [{"category": "x", "items": ["Rust"]}],
             "roles": []}
    r = fit_lexical.compare(pool, description, after)
    assert r["checkable"] == 2 and r["evidenced"] >= 1
    assert tag.lower() in r["dropped"]  # backed by your experience, missing from the CV
    assert "rust" in r["unbacked"] and "haskell" in r["gaps"]


def test_fit_after_is_stored_apart_and_the_jobs_fit_is_untouched(job_ready: dict) -> None:  # noqa: F811
    with Session(engine) as s:
        cv = s.get(CVVersion, job_ready["cv"])
        cv.content = {"summary": "Data engineer.", "roles": [], "skills": []}
        app = s.get(Application, job_ready["app"])
        s.commit()
        before = len(s.exec(select(FitScore).where(FitScore.job_id == app.job_id)).all())
    row = cv_fit.run(engine, job_ready["cv"], mock=True, sleep=lambda _: None)
    assert row.status == "ok" and row.score is not None and row.lexical["checkable"] >= 0
    with Session(engine) as s:
        app = s.get(Application, job_ready["app"])
        assert len(s.exec(select(FitScore).where(FitScore.job_id == app.job_id)).all()) == before


def test_approving_a_cv_starts_fit_before_after(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    with Session(engine) as s:
        cv = s.get(CVVersion, job_ready["cv"])
        cv.status, cv.page_count = "draft", 1
        cv.content = {"summary": "Data engineer.", "roles": [], "skills": []}
        s.commit()
    assert client.post(f"/api/cv/{job_ready['cv']}/approve").status_code == 200
    for _ in range(100):
        out = client.get(f"/api/cv/{job_ready['cv']}/fit").json()
        if out and out["status"] != "pending":
            break
        time.sleep(0.05)
    assert out["status"] == "ok" and "lexical" in out
    with Session(engine) as s:
        assert s.exec(select(CVFit).where(CVFit.cv_version_id == job_ready["cv"])).one()


def test_critique_lists_issues_and_never_rewrites(job_ready: dict, client) -> None:  # noqa: ANN001, F811
    with Session(engine) as s:
        d = OutreachDraft(application_id=job_ready["app"], subject="Pipelines", body="Hi Ana, …")
        s.add(d)
        s.commit()
        draft_id = d.id
        result = critique.critique(s, "email", draft_id, MockCritic())
        s.commit()
        assert result["issues"] and result["issues"][0]["where"] == "opening"
        d = s.get(OutreachDraft, draft_id)
        assert d.body == "Hi Ana, …" and d.plan["critique"]["model"] == "mock-critic"
    r = client.post("/api/critique", json={"kind": "cv", "id": job_ready["cv"]})
    assert r.status_code == 200 and r.json()["issues"]
    assert client.post("/api/critique", json={"kind": "nope", "id": 1}).status_code == 422
