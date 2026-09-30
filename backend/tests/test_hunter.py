"""Try Hunter: credits read for free, find / verify mapped from Hunter's JSON, a missing key is
a clear error, and nothing calls Hunter except the Try Hunter endpoints."""

import re
from pathlib import Path

import httpx
import pytest

from app.providers.hunter import HunterClient, HunterError
from tests.test_outreach import job_ready  # noqa: F401 (fixture)

ACCOUNT = {"data": {"plan_name": "Free", "reset_date": "2026-10-15", "requests": {
    "searches": {"used": 3, "available": 25}, "verifications": {"used": 1, "available": 50}}}}
FIND = {"data": {"first_name": "Marie", "last_name": "Dupont", "email": "marie.dupont@zaion.ai",
                 "score": 92, "domain": "zaion.ai", "position": "CEO", "linkedin_url": None,
                 "verification": {"status": "valid"}, "sources": [{"uri": "x"}, {"uri": "y"}]}}
VERIFY = {"data": {"email": "marie.dupont@zaion.ai", "result": "deliverable", "status": "valid",
                   "score": 95}}


def client_with(calls: list[httpx.Request], status: int = 200) -> HunterClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {"account": ACCOUNT, "email-finder": FIND,
                "email-verifier": VERIFY}[request.url.path.rsplit("/", 1)[-1]]
        return httpx.Response(status, json=body if status == 200 else {"errors": []})

    return HunterClient("secret-key", transport=httpx.MockTransport(handler))


def test_credits_find_and_verify() -> None:
    calls: list[httpx.Request] = []
    h = client_with(calls)
    credits = h.account()
    assert (credits.searches_left, credits.verifications_left) == (22, 49)
    found = h.find("zaion.ai", "Marie", "Dupont")
    assert (found.email, found.score, found.status, found.sources) == \
        ("marie.dupont@zaion.ai", 92, "valid", 2)
    assert h.verify("marie.dupont@zaion.ai").result == "deliverable"
    assert all(r.headers["X-API-KEY"] == "secret-key" and "secret" not in str(r.url)
               for r in calls)  # the key never goes in a URL


def test_errors_are_plain_and_paid_calls_are_not_retried() -> None:
    with pytest.raises(HunterError, match="HUNTER_API_KEY"):
        HunterClient("")
    calls: list[httpx.Request] = []
    with pytest.raises(HunterError, match="rejected the API key"):
        client_with(calls, status=401).find("zaion.ai", "Marie", "Dupont")
    calls.clear()
    with pytest.raises(HunterError):
        client_with(calls, status=500).find("zaion.ai", "Marie", "Dupont")
    assert len(calls) == 1  # a retry could spend a second credit


def test_only_the_try_hunter_endpoints_call_hunter() -> None:
    app_dir = Path(__file__).resolve().parents[1] / "app"
    callers = sorted(str(p.relative_to(app_dir)) for p in app_dir.rglob("*.py")
                     if re.search(r"hunter_provider\(|registry\.hunter\(|HunterClient\(",
                                  p.read_text()) and p.name not in ("hunter.py", "registry.py"))
    assert callers == ["api/get_contact.py"]


def test_try_hunter_fills_the_form_and_saves_nothing(job_ready, client) -> None:  # noqa: ANN001, F811
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Application, Company, Contact, Job

    with Session(engine) as s:
        company = s.get(Company, s.get(Job, s.get(Application, job_ready["app"]).job_id)
                        .company_id)
        company.domain = "outco.test"
        s.commit()
        before = len(s.exec(select(Contact)).all())
    credits = client.get("/api/hunter/credits").json()
    assert credits["configured"] and credits["searches_left"] is not None
    r = client.post("/api/hunter/find", json={"application_id": job_ready["app"],
                                              "full_name": "Marie Dupont"})
    assert r.status_code == 200 and r.json()["email"] == "marie.dupont@outco.test"
    assert r.json()["credits"]["searches_left"] == credits["searches_left"] - 1
    assert client.post("/api/hunter/find", json={"application_id": job_ready["app"],
                                                 "full_name": "Gregoire G."}).status_code == 422
    with Session(engine) as s:
        assert len(s.exec(select(Contact)).all()) == before

