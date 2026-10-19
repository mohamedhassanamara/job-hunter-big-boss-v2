"""Listing red flags, in code: no pay range, hype wording, a posting older than 90 days. They are
hints on the job (never a score or a filter) and only read what the listing says."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Job
from app.models.enums import DescriptionLevel
from app.services import listing_flags as lf

NOW = datetime(2026, 10, 19, tzinfo=UTC)
BODY = ("We build data pipelines for logistics customers across Europe. You will own the "
        "ingestion layer, work with analysts and ship weekly. " * 4)


def job(description: str = BODY, **kw) -> Job:  # noqa: ANN003
    return Job(source="adzuna", external_id="x", url="https://x.test", title=kw.pop(
        "title", "Data Engineer"), company_id=1, dedupe_key="x", description=description,
        description_level=kw.pop("description_level", DescriptionLevel.full), **kw)


def kinds(j: Job) -> list[str]:
    return [f.kind for f in lf.scan(j, NOW)]


def test_no_salary_is_flagged_on_a_full_listing_only() -> None:
    assert kinds(job()) == ["no_salary"]
    assert kinds(job(description_level=DescriptionLevel.snippet)) == []  # can't prove it
    assert kinds(job("Short ad")) == []  # too little text to say anything
    assert kinds(job(salary_text="45-55k EUR")) == []


@pytest.mark.parametrize("pay", [
    "Salary: €60,000 per year", "Rémunération : 55 000 € brut annuel", "$120k plus equity",
    "45-55k depending on experience", "AED 25,000 monthly", "60k€ fixe", "45 à 55k selon profil",
    "Gehalt 70.000 EUR", "80k per year"])
def test_a_pay_range_in_the_text_counts(pay: str) -> None:
    assert kinds(job(f"{BODY}\n{pay}")) == []


@pytest.mark.parametrize("vague", [
    "We offer a competitive salary and 25 days of holiday.", "Great benefits, 3 days remote.",
    "Join our team of 120 people in 4 offices."])
def test_vague_pay_talk_and_other_numbers_are_not_pay(vague: str) -> None:
    assert kinds(job(f"{BODY}\n{vague}")) == ["no_salary"]


@pytest.mark.parametrize(("text", "found"), [
    ("We want a rockstar developer", ["rockstar"]), ("Ninja and guru wanted", ["ninja", "guru"]),
    ("Work hard, play hard culture", ["work hard, play hard"]), ("10x engineers only", ["10x"]),
    ("We are like a family", ["like a family"])])
def test_hype_wording_is_named(text: str, found: list[str]) -> None:
    assert lf.hype_words(job(f"{BODY} {text}", salary_text="x")) == found


def test_hype_matches_whole_words_only() -> None:
    assert lf.hype_words(job(f"{BODY} Ninjago, wizardry, 110x, gurus", salary_text="x")) == []
    assert lf.hype_words(job("No hype here", title="Data Rockstar")) == ["rockstar"]  # the title


def test_a_posting_older_than_90_days_is_flagged() -> None:
    assert kinds(job(salary_text="x", posted_at=NOW - timedelta(days=91))) == ["stale"]
    assert kinds(job(salary_text="x", posted_at=NOW - timedelta(days=89))) == []
    assert kinds(job(salary_text="x", posted_at=None)) == []
    flag = lf.scan(job(salary_text="x", posted_at=NOW - timedelta(days=120)), NOW)[0]
    assert "120 days" in flag.text and lf.is_stale(job(posted_at=NOW - timedelta(days=120)), NOW)


def test_job_detail_carries_the_flags(seeded: None, client) -> None:  # noqa: ANN001
    from sqlmodel import Session

    from app.db import engine
    from app.models import Application

    with Session(engine) as s:
        app = s.query(Application).first()
        j = s.get(Job, app.job_id)
        j.description, j.salary_text = f"{BODY} We need a rockstar.", None
        j.description_level, j.posted_at = DescriptionLevel.full, NOW - timedelta(days=200)
        s.add(j)
        s.commit()
        job_id = j.id
    body = client.get(f"/api/jobs/{job_id}").json()
    assert [f["kind"] for f in body["listing_flags"]] == ["no_salary", "hype", "stale"]
    assert all(f["text"] for f in body["listing_flags"])
