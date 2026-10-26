from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Job
from app.models.enums import DescriptionLevel, RemoteType, Source
from app.providers.base import RawJob
from app.services.dedupe import dedupe_fingerprint, normalize_company, normalize_title
from app.services.ingest import ingest


def test_dedupe_fingerprint_normalization() -> None:
    # Real legal forms stripped; descriptive words are part of the name
    assert normalize_company("Acme Gmbh") == "acme"
    assert normalize_company("Stripe Inc.") == "stripe"
    assert normalize_company("Doctolib S.A.S.") == "doctolib"
    for name in ("Acme Solutions", "Acme Technologies", "Acme Holding"):
        assert normalize_company(name) == name.lower()
    assert normalize_company("Acme Solutions") != normalize_company("Acme Technologies")

    # Noise & filler tags stripped from titles
    assert normalize_title("Data Engineer (m/w/d) - Hybrid") == "data engineer"
    assert normalize_title("Flutter Developer (all genders)") == "flutter developer"
    assert (
        normalize_title("Senior Backend Engineer (f/m/d) 100% Remote")
        == "senior backend engineer"
    )
    assert normalize_title("AI Specialist [m/f/x]") == "ai specialist"

    # Fingerprints match across sources despite formatting differences
    fp1 = dedupe_fingerprint("Doctolib France S.A.S.", "Senior Data Engineer (m/w/d) - Hybrid")
    fp2 = dedupe_fingerprint("Doctolib France", "Senior Data Engineer")
    assert fp1 == fp2


def test_cross_source_ingest_merging() -> None:
    with Session(engine) as session:
        # Ingest Job from Source 1: Adzuna (snippet level)
        raw_adzuna = RawJob(
            source=Source.adzuna,
            external_id="adz-123",
            url="https://adzuna.com/jobs/123",
            title="Senior Data Engineer (m/w/d)",
            company="Globex Corp GmbH",
            location="Berlin, Germany",
            country="DE",
            remote_type=RemoteType.hybrid,
            description="Brief 200-char summary of the data engineering role at Globex.",
            description_level=DescriptionLevel.snippet,
        )
        stats1 = ingest(session, [raw_adzuna], source_run_id=None, profile_id=None)
        session.commit()

        assert stats1.new == 1
        assert stats1.duplicates == 0

        # Ingest same Job from Source 2: WTTJ (full level with longer text)
        longer_desc = (
            "Detailed multi-paragraph description from WTTJ covering all tech stack: "
            "Python, Spark, Kafka, AWS, Snowflake, dbt, and full team expectations. "
        ) * 12  # a full listing (over 1,500 characters)
        raw_wttj = RawJob(
            source=Source.wttj,
            external_id="wttj-456",
            url="https://welcometothejungle.com/jobs/456",
            title="Senior Data Engineer",
            company="Globex Corp",
            location="Berlin",
            country="DE",
            remote_type=RemoteType.hybrid,
            description=longer_desc,
            description_level=DescriptionLevel.full,
        )
        stats2 = ingest(session, [raw_wttj], source_run_id=None, profile_id=None)
        session.commit()

        assert stats2.new == 0
        assert stats2.duplicates == 1

        # Verify only 1 canonical Job exists for Globex Senior Data Engineer
        jobs = session.exec(select(Job).where(Job.external_id == "adz-123")).all()
        assert len(jobs) == 1
        job = jobs[0]

        # Verify sources and URLs merged
        assert "adzuna" in job.sources
        assert "wttj" in job.sources
        assert job.source_urls.get("adzuna") == "https://adzuna.com/jobs/123"
        assert job.source_urls.get("wttj") == "https://welcometothejungle.com/jobs/456"

        # The main one was a snippet and this is the full listing: it takes the full text
        assert job.description == longer_desc
        assert job.description_level == DescriptionLevel.full

        # Verify exactly one application exists for this job
        apps = session.exec(select(Application).where(Application.job_id == job.id)).all()
        assert len(apps) == 1


def _raw(source: Source, ext: str, desc: str, country: str = "DE", **kw) -> RawJob:  # noqa: ANN003
    # the session DB is shared: a test's jobs get a title of their own (the ext without its
    # last part, so a pair of sources shares it)
    return RawJob(source=source, external_id=ext, url=f"https://x.test/{ext}",
                  title=f"Platform Engineer {ext.rsplit('-', 1)[0]}",
                  company="Initech Phase13 GmbH", country=country,
                  location="x", remote_type=RemoteType.unknown, description=desc,
                  description_level=DescriptionLevel.full, **kw)


def test_the_main_listing_keeps_its_own_text_unless_it_is_a_snippet() -> None:
    own = "Our own listing text. " * 40  # ~900 chars: not full, but not clearly shorter either
    with Session(engine) as session:
        ingest(session, [_raw(Source.adzuna, "p13x-a", own)], source_run_id=None, profile_id=None)
        ingest(session, [_raw(Source.wttj, "p13x-b", own + "A little more. " * 5)],
               source_run_id=None, profile_id=None)  # slightly longer, still under 1,500
        session.commit()
        main = session.exec(select(Job).where(Job.external_id == "p13x-a")).one()
        assert main.description == own and set(main.sources) == {"adzuna", "wttj"}


def test_a_changed_description_marks_the_score_stale_and_rescores_nothing() -> None:
    from app.models import FitScore, ScoringTask

    with Session(engine) as session:
        ingest(session, [_raw(Source.adzuna, "p13y-c", "short snippet")], source_run_id=None,
               profile_id=None)
        session.commit()
        main = session.exec(select(Job).where(Job.external_id == "p13y-c")).one()
        session.add(FitScore(job_id=main.id, score=70, prompt_version="v7",
                             experience_version="exp-1"))
        session.commit()
        tasks_before = len(session.exec(select(ScoringTask)).all())
        ingest(session, [_raw(Source.wttj, "p13y-d", "The full listing. " * 120)],
               source_run_id=None, profile_id=None)
        session.commit()
        row = session.exec(select(FitScore).where(FitScore.job_id == main.id)).one()
        assert row.experience_version == "stale:description-changed" and row.score == 70
        assert len(session.exec(select(ScoringTask)).all()) == tasks_before  # nothing queued


def test_the_same_job_in_two_countries_stays_two_jobs() -> None:
    with Session(engine) as session:
        stats = ingest(session, [_raw(Source.adzuna, "p13z-e", "A. " * 30, country="DE"),
                                 _raw(Source.wttj, "p13z-f", "A. " * 30, country="AE")],
                       source_run_id=None, profile_id=None)
        assert stats.new == 2 and stats.duplicates == 0
        session.commit()
