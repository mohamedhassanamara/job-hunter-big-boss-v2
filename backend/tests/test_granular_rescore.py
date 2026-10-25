from datetime import timedelta

from sqlmodel import Session

from app.db import engine
from app.models import Application, Company, FitScore, Job
from app.models.base import utcnow
from app.models.enums import FitStatus, Source, Stage
from app.services.scoring import filter_jobs_for_scoring


def _ensure_company(session: Session) -> Company:
    c = session.get(Company, 1)
    if not c:
        c = Company(name="Test Co", normalized_name="test co")
        session.add(c)
        session.flush()
    return c


def test_granular_filter_by_track_and_limit() -> None:
    with Session(engine) as session:
        co = _ensure_company(session)
        now = utcnow()
        # Create jobs with different tracks
        j1 = Job(source=Source.adzuna, external_id="t1", url="http://1", title="Flutter Dev",
                 company_id=co.id, dedupe_key="c::t1", matched_track="Mobile", created_at=now)
        j2 = Job(source=Source.adzuna, external_id="t2", url="http://2", title="iOS Dev",
                 company_id=co.id, dedupe_key="c::t2", matched_track="Mobile", created_at=now)
        j3 = Job(source=Source.adzuna, external_id="t3", url="http://3", title="Backend Dev",
                 company_id=co.id, dedupe_key="c::t3", matched_track="Backend", created_at=now)
        session.add_all([j1, j2, j3])
        session.commit()

        # Filter Mobile case-insensitively
        mobile_ids = filter_jobs_for_scoring(session, track="mobile")
        assert j1.id in mobile_ids and j2.id in mobile_ids
        assert j3.id not in mobile_ids

        # Filter with limit
        limited_ids = filter_jobs_for_scoring(session, track="mobile", limit=1)
        assert len(limited_ids) == 1
        assert limited_ids[0] in {j1.id, j2.id}

        # Filter Backend
        backend_ids = filter_jobs_for_scoring(session, track="backend")
        assert j3.id in backend_ids
        assert j1.id not in backend_ids


def test_granular_filter_by_date_and_dismissed() -> None:
    with Session(engine) as session:
        co = _ensure_company(session)
        now = utcnow()
        old_time = now - timedelta(days=20)
        recent_time = now - timedelta(days=2)

        j_old = Job(
            source=Source.adzuna,
            external_id="old1",
            url="http://old",
            title="Old Job",
            company_id=co.id,
            dedupe_key="c::old",
            matched_track="Mobile",
            created_at=old_time,
        )
        j_recent = Job(
            source=Source.adzuna,
            external_id="rec1",
            url="http://rec",
            title="Recent Job",
            company_id=co.id,
            dedupe_key="c::rec",
            matched_track="Mobile",
            created_at=recent_time,
        )
        j_closed = Job(
            source=Source.adzuna,
            external_id="cls1",
            url="http://cls",
            title="Closed Job",
            company_id=co.id,
            dedupe_key="c::cls",
            matched_track="Mobile",
            created_at=recent_time,
        )
        session.add_all([j_old, j_recent, j_closed])
        session.commit()

        # Close/dismiss j_closed
        app_closed = Application(job_id=j_closed.id, stage=Stage.closed)
        session.add(app_closed)
        session.commit()

        # Filter within 7 days
        recent_ids = filter_jobs_for_scoring(session, track="mobile", since_days=7)
        assert j_recent.id in recent_ids
        assert j_old.id not in recent_ids
        assert j_closed.id not in recent_ids  # dismissed/closed is excluded


def test_granular_filter_only_unscored() -> None:
    with Session(engine) as session:
        co = _ensure_company(session)
        now = utcnow()
        j_unscored = Job(
            source=Source.adzuna,
            external_id="u1",
            url="http://u1",
            title="Unscored",
            company_id=co.id,
            dedupe_key="c::u1",
            matched_track="Mobile",
            created_at=now,
        )
        j_scored = Job(
            source=Source.adzuna,
            external_id="s1",
            url="http://s1",
            title="Scored",
            company_id=co.id,
            dedupe_key="c::s1",
            matched_track="Mobile",
            created_at=now,
        )
        session.add_all([j_unscored, j_scored])
        session.commit()

        score = FitScore(job_id=j_scored.id, status=FitStatus.ok, score=85, model="test")
        session.add(score)
        session.commit()

        # All mobile
        all_mobile = filter_jobs_for_scoring(session, track="mobile")
        assert j_unscored.id in all_mobile and j_scored.id in all_mobile

        # Only unscored
        unscored_only = filter_jobs_for_scoring(session, track="mobile", only_unscored=True)
        assert j_unscored.id in unscored_only
        assert j_scored.id not in unscored_only
