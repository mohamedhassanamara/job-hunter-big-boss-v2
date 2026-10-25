from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Job
from app.models.enums import DescriptionLevel, RemoteType, Source
from app.providers.base import RawJob
from app.services.dedupe import dedupe_fingerprint, normalize_company, normalize_title
from app.services.ingest import ingest


def test_dedupe_fingerprint_normalization() -> None:
    # Legal suffixes stripped
    assert normalize_company("Acme Gmbh & Co. KG") == "acme"
    assert normalize_company("Stripe Inc.") == "stripe"
    assert normalize_company("Doctolib S.A.S.") == "doctolib"
    assert normalize_company("Spotify AB") == "spotify"

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
            "Python, Spark, Kafka, AWS, Snowflake, dbt, and full team expectations."
        )
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

        # Verify description was upgraded to the richer version
        assert job.description == longer_desc
        assert job.description_level == DescriptionLevel.full

        # Verify exactly one application exists for this job
        apps = session.exec(select(Application).where(Application.job_id == job.id)).all()
        assert len(apps) == 1
