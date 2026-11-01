"""Studio "Generate CV": a general CV per track / all-purpose, never stored."""

import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import AppSetting, CVVersion, SearchProfile
from app.providers.base import CVRequest
from app.providers.mock import MockCVGenerator
from app.services import cv_build, cv_service, cv_track
from app.services.cv_pool import load_pool
from tests.test_cv import fake_compiler


class Spy(MockCVGenerator):
    requests: list[CVRequest]

    def __init__(self) -> None:
        super().__init__()
        self.requests = []

    def generate(self, request: CVRequest):  # noqa: ANN201
        self.requests.append(request)
        return super().generate(request)


@pytest.fixture()
def ready(seeded: None, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    def compiler(tex: str, out_dir: Path, name: str = "cv"):  # noqa: ANN202
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{name}.pdf").write_bytes(b"%PDF-1.4 fake")
        return fake_compiler(capacity=80, calls=[])(tex, out_dir, name)

    monkeypatch.setattr(cv_build, "compile_tex", compiler)
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
        row.value = {**row.value, "full_name": "Ada Lovelace"}
        s.add(row)
        s.commit()


def track_names() -> list[str]:
    with Session(engine) as s:
        return [t["name"] for t in s.exec(select(SearchProfile)).first().tracks]


def test_options_start_with_all_purpose_then_registered_tracks(ready: None) -> None:
    opts = cv_track.options(engine)
    assert opts[0]["value"] == "all_purpose"
    assert [o["value"] for o in opts[1:]] == track_names()


def test_all_purpose_and_track_cv_get_their_own_framing(ready: None) -> None:
    track = track_names()[0]
    spy = Spy()
    a = cv_track.start(engine, "all_purpose", spy, wait=True)
    b = cv_track.start(engine, track, spy, wait=True)
    assert a.status == b.status == "ready", (a.error, b.error)
    assert spy.requests[0].job["matched_track"] == "(none)"
    assert spy.requests[1].job["matched_track"] == track
    assert track in spy.requests[1].job["description"]
    assert a.skills and b.skills and a.pdf_path.exists() and a.page_count == 1
    assert a.filename.endswith("All_Purpose.pdf") and track in b.filename


def test_unknown_track_is_rejected(ready: None) -> None:
    with pytest.raises(ValueError):
        cv_track.start(engine, "astronaut", Spy())


def test_nothing_is_stored_and_download_deletes_it(ready: None, client) -> None:  # noqa: ANN001
    with Session(engine) as s:
        before = len(s.exec(select(CVVersion)).all())
    r = client.post("/api/cv/generate", json={"track": "all_purpose"})
    assert r.status_code == 202
    job_id = r.json()["id"]
    for _ in range(100):
        body = client.get(f"/api/cv/generate/{job_id}").json()
        if body["status"] != "running":
            break
        time.sleep(0.05)
    assert body["status"] == "ready", body
    assert client.get(f"/api/cv/generate/{job_id}/pdf").status_code == 200  # preview keeps it
    assert client.get(f"/api/cv/generate/{job_id}/pdf?download=true").status_code == 200
    assert client.get(f"/api/cv/generate/{job_id}").status_code == 404  # gone after download
    with Session(engine) as s:
        assert len(s.exec(select(CVVersion)).all()) == before


def test_api_rejects_unknown_track_and_lists_options(ready: None, client) -> None:  # noqa: ANN001
    assert client.post("/api/cv/generate", json={"track": "nope"}).status_code == 422
    assert client.get("/api/cv/tracks").json()[0]["value"] == "all_purpose"


def test_with_a_job_it_is_saved_like_any_cv(ready: None, client) -> None:  # noqa: ANN001
    from app.models import Application

    with Session(engine) as s:
        job_id = s.exec(select(Application.job_id)).first()
    r = client.post("/api/cv/generate", json={"track": "all_purpose", "target_job_id": job_id})
    assert r.status_code == 202 and r.json()["cv_id"]
    with Session(engine) as s:
        assert s.get(CVVersion, r.json()["cv_id"]) is not None


def test_service_import_smoke() -> None:
    assert cv_service.build_track_request and load_pool
