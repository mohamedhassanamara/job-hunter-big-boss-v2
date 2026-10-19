"""Your pool text is yours: only the Experience screen (and Undo / the explicit master import)
may change it. These tests fail if any other code path writes it."""

import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import ExperienceHistory, ExperienceItem
from app.services import experience_write
from app.services.experience_write import PoolWriteError

APP = Path(__file__).resolve().parents[1] / "app"
# Modules allowed to create/modify/delete ExperienceItem rows directly.
WRITERS = {"services/experience_write.py", "seed/seed.py", "seed/test_cv.py",
           "models/experience.py"}


def first_job(s: Session) -> ExperienceItem:
    return s.exec(select(ExperienceItem).where(ExperienceItem.kind == "job")).first()


def test_direct_text_edit_is_refused(seeded: None) -> None:
    with Session(engine) as s:
        item = first_job(s)
        item.bullets = [*item.bullets, "sneaky"]
        s.add(item)
        with pytest.raises(PoolWriteError):
            s.commit()
    with Session(engine) as s:
        assert "sneaky" not in first_job(s).bullets


@pytest.mark.parametrize("field,value", [("title", "X"), ("tags", ["x"]), ("is_active", False),
                                         ("summary", "x"), ("date_label", "2020")])
def test_every_text_field_is_guarded(seeded: None, field: str, value: object) -> None:
    with Session(engine) as s:
        item = first_job(s)
        setattr(item, field, value)
        s.add(item)
        with pytest.raises(PoolWriteError):
            s.commit()


def test_delete_is_refused_but_reordering_is_not(seeded: None) -> None:
    with Session(engine) as s:
        item = first_job(s)
        item.position = 99  # layout, not text
        s.add(item)
        s.commit()
        s.delete(item)
        with pytest.raises(PoolWriteError):
            s.commit()


def test_gateway_edits_are_logged_and_undoable(seeded: None) -> None:
    with Session(engine) as s:
        item = first_job(s)
        old = list(item.bullets)
        experience_write.update(s, item, {"bullets": ["new text"]})
        s.commit()
        rows = experience_write.history(s, item.id)
        assert rows[0].action == "edited" and rows[0].before["bullets"] == old
        experience_write.update(s, item, {"bullets": ["new text"]})  # no change: not logged
        s.commit()
        assert len(experience_write.history(s, item.id)) == 1
        experience_write.undo(s, rows[0].id)
        s.commit()
        assert item.bullets == old
        assert experience_write.history(s, item.id)[0].action == "undo"


def test_undo_of_delete_and_create(seeded: None) -> None:
    with Session(engine) as s:
        new = experience_write.create(s, {"kind": "project", "title": "P", "bullets": ["b"]})
        s.commit()
        experience_write.undo(s, experience_write.history(s, new.id)[0].id)
        s.commit()
        assert new.is_active is False  # undoing a creation archives it
        item_id, title = new.id, new.title
        experience_write.delete(s, new)
        s.commit()
        assert s.get(ExperienceItem, item_id) is None
        hist = s.exec(select(ExperienceHistory).where(ExperienceHistory.item_id == item_id)
                      .where(ExperienceHistory.action == "deleted")).one()
        back = experience_write.undo(s, hist.id)
        s.commit()
        assert back.id == item_id and back.title == title


def test_api_edit_goes_through_the_gateway(client) -> None:  # noqa: ANN001
    items = client.get("/api/experience").json()
    job = next(i for i in items if i["kind"] == "job")
    r = client.patch(f"/api/experience/{job['id']}", json={"bullets": ["edited by me"]})
    assert r.status_code == 200
    hist = client.get(f"/api/experience/{job['id']}/history").json()
    assert hist[0]["source"] == "user" and hist[0]["before"]["bullets"] == job["bullets"]
    undone = client.post(f"/api/experience/history/{hist[0]['id']}/undo").json()
    assert undone["bullets"] == job["bullets"]


def test_no_module_writes_pool_text_outside_the_gateway() -> None:
    """Static guard: creating, bulk-updating or bulk-deleting ExperienceItem rows is reserved to
    the gateway and the sample-data seeds (which run inside `writing()`)."""
    pattern = re.compile(r"ExperienceItem\(|update\(ExperienceItem|delete\(ExperienceItem|"
                         r"\.bullets\s*(?:\+|=)[^=]|\.bullets\.(?:append|extend|insert|pop|remove)")
    offenders = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel in WRITERS or rel.startswith("eval/"):
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line) and "ExperienceItem" in path.read_text():
                offenders.append(f"{rel}:{n}: {line.strip()}")
    # Pydantic plan models legitimately have `bullets=`; only code touching ExperienceItem counts.
    offenders = [o for o in offenders if "bullets=" not in o]
    assert not offenders, "pool text written outside services/experience_write.py:\n" + \
        "\n".join(offenders)


def test_generation_never_changes_the_pool(seeded: None) -> None:
    """Running the CV generator (mock) leaves every pool row byte-identical."""
    from app.models import Application
    from app.providers.mock import MockCVGenerator
    from app.services import cv_service

    def pool_state() -> list[dict]:
        with Session(engine) as s:
            return [experience_write.snapshot(i) | {"id": i.id}
                    for i in s.exec(select(ExperienceItem).order_by(ExperienceItem.id)).all()]

    before = pool_state()
    with Session(engine) as s:
        app_id = s.exec(select(Application.id)).first()
    cv_service.generate(engine, app_id, MockCVGenerator())
    assert pool_state() == before
