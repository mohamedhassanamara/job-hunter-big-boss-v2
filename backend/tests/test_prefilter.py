from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import RemoteType, Source
from app.providers.base import ProfileSpec, RawJob
from app.services.prefilter import matches_role, prefilter

NOW = datetime(2026, 9, 26, tzinfo=UTC)
PROFILE = ProfileSpec(
    roles=["Data Engineer", "AI Engineer", "ML Engineer", "Analytics Engineer"],
    excluded_keywords=["intern", "internship", "stage", "alternance", "working student"],
    locations=["ES", "PT", "FR", "IT"],
    remote_policy="remote_ok",
    max_age_days=30,
)


def job(title="Data Engineer", country="ES", remote=RemoteType.hybrid, location="Madrid, Spain",
        days=1, **kw) -> RawJob:
    return RawJob(
        source=Source.adzuna, external_id=kw.pop("eid", title), url="https://x.test/j",
        title=title, company=kw.pop("company", "Acme"), location=location, country=country,
        remote_type=remote, posted_at=NOW - timedelta(days=days), **kw,
    )


@pytest.mark.parametrize(
    "title",
    [
        "Senior Data Engineer (m/f/d)", "Staff Data Engineer", "Data Platform Engineer",
        "Ingeniero de Datos", "Ingénieur Data H/F", "Engenheiro de Dados", "Ingegnere dei dati",
        "Machine Learning Engineer", "MLOps Engineer", "LLM Engineer", "Applied AI Engineer",
        "Ingénieur IA", "GenAI Engineer", "Analytics Engineer II", "Lead Data Engineering",
    ],
)
def test_role_matches(title: str) -> None:
    assert matches_role(title, PROFILE.roles), title


@pytest.mark.parametrize(
    "title",
    [
        "Data Analyst", "Software Engineer", "Account Executive", "Product Manager AI", "Engineer",
        # English titles with the words in reverse order are not the role (real-run noise):
        "Backend Engineer Kotlin & Data", "System Engineer – Data & Cloud Security",
        "Software Engineer Frontend - AI-Powered Store Manager Companion",
        "Staff Backend Engineer (Databases Analytics)",
        # Other trades that share the words (real-run noise, 2026-09-27):
        "Principal Data Center Mechanical Engineer", "Principal Data Center Electrical Engineer",
        "Data Center Operations Engineer (DCOE) Italy", "Data Centre Engineer",
        "Datacenter Engineer",
        "Data Center Chief Engineer - For German Resident Only", "AI Mechanical Engineer",
    ],
)
def test_role_non_matches(title: str) -> None:
    assert matches_role(title, PROFILE.roles) is None, title


def test_reasons() -> None:
    jobs = [
        job("Data Engineer", eid="ok"),
        job("Data Engineer Intern", eid="intern"),
        job("Data Analyst", eid="analyst"),
        job("Data Engineer", eid="old", days=45),
        job("Data Engineer", eid="de", country="DE", location="Berlin"),
        job("Data Engineer", eid="us-remote", country="US", remote=RemoteType.remote,
            location="New York, United States"),
        job("Data Engineer", eid="eu-remote", country=None, remote=RemoteType.remote,
            location="Europe"),
        job("Data Engineer", eid="usa-only", country=None, remote=RemoteType.remote,
            location="USA"),
        job("Data Engineer", eid="de-remote", country="DE", remote=RemoteType.remote,
            location="Berlin"),
        job("", eid="empty"),
    ]
    result = prefilter(jobs, PROFILE, now=NOW)
    kept = {j.external_id for j in result.kept}
    reasons = {d.job.external_id: d.reason for d in result.dropped}
    assert kept == {"ok", "eu-remote", "de-remote"}
    assert reasons == {
        "intern": "title_excluded:intern",
        "analyst": "title_no_role_match",
        "old": "too_old",
        "de": "location_outside:DE",
        "us-remote": "remote_outside:US",
        "usa-only": "remote_outside:US",
        "empty": "incomplete",
    }
    assert result.reason_counts()["title_excluded:intern"] == 1


@pytest.mark.parametrize(
    ("scope", "kept"),
    [
        ("anywhere", {"world", "europe", "nl", "gulf", "unknown"}),
        ("europe", {"world", "europe", "nl", "unknown"}),
        ("targets", {"world", "europe", "gulf", "unknown"}),
    ],
)
def test_remote_scope(scope: str, kept: set[str]) -> None:
    profile = PROFILE.model_copy(update={"locations": ["ES", "FR", "AE"], "remote_scope": scope})
    remote = [
        ("world", "Worldwide"), ("europe", "Europe"), ("nl", "Netherlands"),
        ("gulf", "Dubai, UAE"), ("us", "USA only"), ("unknown", "Remote"),
    ]
    jobs = [job(eid=e, country=None, remote=RemoteType.remote, location=loc) for e, loc in remote]
    result = prefilter(jobs, profile, now=NOW)
    assert {j.external_id for j in result.kept} == kept


def test_onsite_gulf_target_is_kept() -> None:
    profile = PROFILE.model_copy(update={"locations": ["AE", "QA"]})
    jobs = [job(eid="dubai", country="AE", location="Dubai, United Arab Emirates"),
            job(eid="madrid")]
    assert [j.external_id for j in prefilter(jobs, profile, now=NOW).kept] == ["dubai"]


def test_seniority_is_never_filtered_by_default() -> None:
    titles = ["Junior Data Engineer", "Senior ML Engineer", "Principal AI Engineer",
              "Head of Data Engineering", "Lead Analytics Engineer"]
    result = prefilter([job(t, eid=t) for t in titles], PROFILE, now=NOW)
    assert len(result.kept) == len(titles)


def test_remote_only_policy() -> None:
    profile = PROFILE.model_copy(update={"remote_policy": "remote_only"})
    result = prefilter([job(remote=RemoteType.hybrid)], profile, now=NOW)
    assert result.dropped[0].reason == "not_remote"
