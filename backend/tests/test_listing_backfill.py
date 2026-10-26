"""Migration 0033's backfill: keys keep the country, duplicate rows are folded into their main
listing (kept, hidden, with their own text), the fullest description wins by the 1,500-character
rule, and a changed description only marks the score stale."""

import json
import uuid

from sqlalchemy import text
from sqlmodel import Session

from app.db import engine
from app.models import Company, FitScore, Job
from app.models.enums import Source
from app.services import listing_merge
from app.services.dedupe import dedupe_key

FULL = "The full listing text. " * 100  # ~2,300 chars


def _job(s: Session, company: Company, source: Source, title: str, country: str, text_: str,
         **kw) -> Job:  # noqa: ANN003
    j = Job(source=source, external_id=f"bf-{uuid.uuid4().hex[:10]}", url=f"https://x/{source}",
            title=title, company_id=company.id, country=country, description=text_,
            dedupe_key="old|format", **kw)
    s.add(j)
    s.flush()
    return j


def test_backfill_folds_duplicates_keeps_countries_apart_and_marks_stale() -> None:
    tag = uuid.uuid4().hex[:6]
    with Session(engine) as s:
        co = Company(name=f"Initech {tag} Solutions", normalized_name=f"initech {tag} solutions")
        s.add(co)
        s.flush()
        snippet = _job(s, co, Source.adzuna, f"Data Engineer {tag}", "DE", "short snippet")
        dup = _job(s, co, Source.wttj, f"Data Engineer {tag}", "DE", FULL,
                   duplicate_of_id=snippet.id)
        own = _job(s, co, Source.adzuna, f"ML Engineer {tag}", "DE", "Own text. " * 40)
        longer_dup = _job(s, co, Source.wttj, f"ML Engineer {tag}", "DE", "Own text. " * 60,
                          duplicate_of_id=own.id)  # longer, but the main is not a snippet
        dubai = _job(s, co, Source.adzuna, f"Data Engineer {tag}", "AE", "Dubai text")
        s.add(FitScore(job_id=snippet.id, score=60, prompt_version="v7", experience_version="e1"))
        s.commit()
        ids = {"snippet": snippet.id, "dup": dup.id, "own": own.id, "longer": longer_dup.id,
               "dubai": dubai.id}

    conn = engine.connect()
    trans = conn.begin()
    try:
        dry = listing_merge.backfill(conn, apply=False)
        assert dry.counts["descriptions_changed"] >= 1
        assert conn.execute(text("SELECT dedupe_key FROM job WHERE id = :i"),
                            {"i": ids["snippet"]}).scalar() == "old|format"  # nothing written
        rep = listing_merge.backfill(conn, apply=True)
        assert rep.counts["scores_marked_stale"] >= 1
        row = lambda i: conn.execute(text(  # noqa: E731
            "SELECT dedupe_key, description, sources, source_urls, duplicate_of_id FROM job "
            "WHERE id = :i"), {"i": i}).one()
        main = row(ids["snippet"])
        assert main[0] == dedupe_key(f"Initech {tag} Solutions", f"Data Engineer {tag}", "DE")
        assert main[0].endswith("::de") and "solutions" in main[0]
        assert main[1] == FULL  # a snippet takes the duplicate's full listing
        assert json.loads(main[2]) == ["adzuna", "wttj"] and "wttj" in json.loads(main[3])
        d = row(ids["dup"])
        assert d[1] == FULL and d[4] == ids["snippet"] and json.loads(d[2]) == ["wttj"]  # kept
        assert row(ids["own"])[1] == "Own text. " * 40  # not a snippet: keeps its own
        assert row(ids["longer"])[1] == "Own text. " * 60  # the duplicate keeps its own text
        assert row(ids["dubai"])[0].endswith("::ae")
        assert row(ids["dubai"])[0] != main[0]  # the same title in another country: another job
        stale = conn.execute(text("SELECT experience_version FROM fit_score WHERE job_id = :i"),
                             {"i": ids["snippet"]}).scalar()
        assert stale == listing_merge.STALE_MARK
        assert conn.execute(text("SELECT count(*) FROM scoring_task WHERE job_id = :i"),
                            {"i": ids["snippet"]}).scalar() == 0  # nothing rescored
    finally:
        trans.rollback()
        conn.close()
