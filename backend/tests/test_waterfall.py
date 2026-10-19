"""The contact waterfall: order, stop at the first verified email, cache = zero credits, quotas,
refused keys, the pattern step, and that only one click endpoint can start it. No network."""

import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import (
    Application,
    AppSetting,
    CompanyProviderRun,
    Contact,
    ProviderCall,
    ProviderKeyState,
    ProviderUsage,
)
from app.providers.contact_finders import Candidate, Cost, KeyRefused, OutOfCredits, Search
from app.providers.contact_finders.mock import MockFinder
from app.services import contact_waterfall as wf
from app.services import provider_quota as quota
from tests.test_contacts import make_company, make_job

DOMAIN = "waterfall.test"


def finders(calls: list[str], **finds: bool) -> dict:
    return {"hunter": MockFinder("hunter", finds=finds.get("hunter", False), calls=calls),
            "prospeo": MockFinder("prospeo", needs_reveal=True, finds=finds.get("prospeo", False),
                                  calls=calls),
            "apollo": MockFinder("apollo", needs_reveal=True, finds=finds.get("apollo", False),
                                 calls=calls),
            "apify": MockFinder("apify", "usd", finds=finds.get("apify", False), calls=calls)}


def setting(s: Session, key: str, value: dict) -> None:
    row = s.exec(select(AppSetting).where(AppSetting.key == key)).first()
    if row:
        row.value = value
    else:
        s.add(AppSetting(key=key, value=value))
    s.flush()


@pytest.fixture()
def world(seeded: None):  # noqa: ANN201
    with Session(engine) as s:
        for model in (CompanyProviderRun, ProviderCall, ProviderKeyState, ProviderUsage):
            for row in s.exec(select(model)).all():
                s.delete(row)
        company = make_company(s)
        company.domain = DOMAIN
        app = make_job(s, company)
        s.flush()
        yield s, company, app
        s.rollback()


def test_stops_at_the_first_verified_email(world) -> None:  # noqa: ANN001
    s, company, app = world
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, hunter=True, prospeo=True))
    assert out.found_by == "hunter"
    assert [c.split(".")[0] for c in calls] == ["hunter"]  # nothing after the first success
    assert out.candidates and out.candidates[0]["verified"]
    assert out.candidates[0]["provider"] == "hunter"
    stored = s.exec(select(Contact).where(Contact.found_by_provider == "hunter")).first()
    assert stored and stored.verification_status == "valid" and stored.verified_at is None
    assert company.email_pattern == "{first}.{last}"  # Hunter's pattern is cached


def test_waterfall_order_and_reveal(world) -> None:  # noqa: ANN001
    s, _, app = world
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, prospeo=True))
    assert out.found_by == "prospeo"
    assert calls[0] == "hunter.search:" + DOMAIN and calls[1].startswith("prospeo.search")
    assert any(c.startswith("prospeo.reveal") for c in calls)
    assert out.credits == 3.0 and out.usd == 0  # hunter search + prospeo search + reveal
    assert [st.provider for st in out.steps][:3] == ["cache", "hunter", "prospeo"]


def test_second_job_at_a_cached_company_costs_nothing(world) -> None:  # noqa: ANN001
    s, company, app = world
    calls: list[str] = []
    fs = finders(calls, prospeo=True)
    first = wf.run(s, app, mock=True, finders=fs)
    assert first.credits > 0
    n = len(calls)
    other = make_job(s, company)
    again = wf.run(s, other, mock=True, finders=fs)
    assert again.from_cache and again.credits == 0 and again.usd == 0
    assert len(calls) == n  # no provider was called
    assert again.candidates[0]["contact_id"] == first.candidates[0]["contact_id"]


def test_providers_already_queried_are_skipped_until_stale_or_requery(world) -> None:  # noqa: ANN001
    s, _, app = world
    calls: list[str] = []
    fs = finders(calls)  # nobody finds anything
    wf.run(s, app, mock=True, finders=fs)
    first = len(calls)
    assert first >= 4
    again = wf.run(s, app, mock=True, finders=fs)
    assert len(calls) == first and {st.status for st in again.steps if st.provider in
                                   wf.WATERFALL} == {"cached"}
    wf.run(s, app, mock=True, finders=fs, requery=True)
    assert len(calls) == first * 2
    for run in s.exec(select(CompanyProviderRun)).all():  # older than max_age_days
        run.queried_at = run.queried_at.replace(year=run.queried_at.year - 1)
        s.add(run)
    s.flush()
    wf.run(s, app, mock=True, finders=fs)
    assert len(calls) == first * 3


def test_a_key_out_of_credits_is_skipped_and_never_exceeded(world) -> None:  # noqa: ANN001
    s, _, app = world
    setting(s, "providers", {"limits": {"hunter": 0.5}})
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, prospeo=True))
    assert not any(c.startswith("hunter.search") for c in calls)
    assert next(st for st in out.steps if st.provider == "hunter").status == "exhausted"
    assert out.found_by == "prospeo"
    for u in s.exec(select(ProviderUsage)).all():
        assert quota.used_of(u, u.provider) <= quota.limit_of(s, u.provider, u.key_label) + 1e-9


class Refusing(MockFinder):
    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 10) -> Search:
        self.calls.append("hunter.search")
        raise KeyRefused("Hunter: HTTP 401 invalid key")


def test_a_refused_key_is_disabled_and_not_retried(world) -> None:  # noqa: ANN001
    s, _, app = world
    calls: list[str] = []
    fs = finders(calls, prospeo=True)
    fs["hunter"] = Refusing("hunter", calls=calls)
    out = wf.run(s, app, mock=True, finders=fs)
    assert calls.count("hunter.search") == 1 and out.found_by == "prospeo"
    state = s.exec(select(ProviderKeyState).where(ProviderKeyState.key_label == "hunter#1")).one()
    assert state.disabled_at is not None and "refused" in (state.disabled_reason or "")
    wf.run(s, app, mock=True, finders=fs, requery=True)
    assert calls.count("hunter.search") == 1  # disabled: never tried again
    quota.enable(s, "hunter", "hunter#1")
    wf.run(s, app, mock=True, finders=fs, requery=True)
    assert calls.count("hunter.search") == 2


class Broke(MockFinder):
    def search(self, key: str, domain: str, titles: list[str], *, limit: int = 10) -> Search:
        raise OutOfCredits("Prospeo: INSUFFICIENT_CREDITS")


def test_out_of_credits_parks_the_key_for_the_month(world) -> None:  # noqa: ANN001
    s, _, app = world
    calls: list[str] = []
    fs = finders(calls, apollo=True)
    fs["prospeo"] = Broke("prospeo", calls=calls)
    out = wf.run(s, app, mock=True, finders=fs)
    assert out.found_by == "apollo"
    assert quota.remaining(s, "prospeo", "prospeo#1") == 0


def test_pattern_step_verifies_before_using_a_guess(world) -> None:  # noqa: ANN001
    s, company, app = world
    setting(s, "providers", {"max_reveals": 0})  # providers list people but reveal nothing
    from app.models.enums import ContactSource
    s.add(Contact(company_id=company.id, full_name="Ana Diaz", email=f"ana.diaz@{DOMAIN}",
                  email_normalized=f"ana.diaz@{DOMAIN}", normalized_name="ana diaz",
                  source=ContactSource.apollo_dump))
    s.flush()
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, prospeo=True))
    assert out.found_by == "pattern"
    assert any(c.startswith("hunter.verify") for c in calls)
    assert company.email_pattern == "{first}.{last}"
    top = out.candidates[0]
    assert top["rank_label"] == "HR / Talent"  # unknown size: the large-company order
    assert top["verified"] and top["email"] == f"lena.rossi@{DOMAIN}"


class CatchAll(MockFinder):
    def verify(self, key: str, email: str) -> tuple[str, Cost]:
        self.calls.append("hunter.verify")
        return "accept_all", Cost(credits=0.5)


def test_catch_all_and_unverified_guesses_are_never_used(world) -> None:  # noqa: ANN001
    s, company, app = world
    setting(s, "providers", {"max_reveals": 0})
    s.add(Contact(company_id=company.id, full_name="Ana Diaz", email=f"ana.diaz@{DOMAIN}",
                  email_normalized=f"ana.diaz@{DOMAIN}", normalized_name="ana diaz"))
    s.flush()
    calls: list[str] = []
    fs = finders(calls, prospeo=True)
    fs["hunter"] = CatchAll("hunter", calls=calls)
    out = wf.run(s, app, mock=True, finders=fs)
    assert out.found_by is None and not any(c["verified"] for c in out.candidates)
    assert out.steps[-1].provider == "manual"  # the Apollo extension is the last resort
    assert all(c["contact_id"] is None for c in out.candidates)
    assert not s.exec(select(Contact).where(Contact.found_by_provider == "pattern")).all()


def test_no_domain_goes_straight_to_manual(world) -> None:  # noqa: ANN001
    s, company, app = world
    company.domain = None
    s.flush()
    calls: list[str] = []
    out = wf.run(s, app, mock=True, finders=finders(calls, hunter=True))
    assert calls == [] and out.steps[-1].provider == "manual"


def test_find_and_use_endpoints(client, world) -> None:  # noqa: ANN001
    s, _, app = world
    s.commit()
    r = client.post(f"/api/applications/{app.id}/contact/find", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found_by"] == "prospeo" and body["candidates"][0]["verified"]
    cid = body["candidates"][0]["contact_id"]
    used = client.post(f"/api/applications/{app.id}/contact/use", json={"contact_id": cid})
    assert used.status_code == 200
    again = client.post(f"/api/applications/{app.id}/contact/find", json={}).json()
    assert again["from_cache"] and again["credits"] == 0
    status = client.get("/api/providers/status").json()
    assert any(k["provider"] == "prospeo" and k["used"] > 0 for k in status["keys"]) or \
        status["keys"] == []  # mock workspaces have no .env keys listed
    with Session(engine) as s2:
        assert s2.get(Application, app.id).contact_id == cid


def test_only_one_endpoint_starts_the_waterfall() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    callers = sorted(str(p.relative_to(app_dir)) for p in app_dir.rglob("*.py")
                     if re.search(r"contact_waterfall\.run\(|registry\.contact_finders\(",
                                  p.read_text()) and p.name != "registry.py")
    assert callers == ["api/get_contact.py", "services/contact_waterfall.py"]


def test_candidate_roundtrip() -> None:
    c = Candidate("A B", "CTO", "a@b.c", "valid", "hunter")
    assert Candidate.load(c.as_dict()) == c and c.verified
    assert not Candidate("A B", email="a@b.c", email_status="accept_all").verified
