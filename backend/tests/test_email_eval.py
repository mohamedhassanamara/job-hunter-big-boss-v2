"""The email regression set: approvals and rejections are recorded with their inputs, reference
examples import once, and eval-emails writes each case again side by side. No model calls."""

import json
from pathlib import Path

from sqlmodel import Session, select

from app.db import engine
from app.eval import emails as ev
from app.models import EmailExample
from app.providers.mock import MockEmailDrafter
from app.services import outreach, research
from tests.test_intro_email import Site
from tests.test_outreach import job_ready  # noqa: F401 (fixture)


def test_approving_and_rejecting_record_cases(job_ready: dict, client) -> None:  # noqa: F811, ANN001
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter(),
                          researcher=research.MockResearcher(), fetcher=Site(),
                          mode="speculative")
    client.post(f"/api/outreach/drafts/{d.id}/reject")
    with Session(engine) as s:
        row = s.exec(select(EmailExample).where(EmailExample.draft_id == d.id)).one()
        assert row.kind == "rejected" and row.inputs["request"]["rules"]["signals"]
    d2 = outreach.generate(engine, job_ready["app"], MockEmailDrafter(),
                           researcher=research.MockResearcher(), fetcher=Site(),
                           mode="speculative")
    assert client.post(f"/api/outreach/drafts/{d2.id}/approve").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(EmailExample).where(EmailExample.draft_id == d2.id)).one().kind \
            == "approved"


def test_examples_import_once(seeded: None, tmp_path: Path) -> None:
    path = tmp_path / "examples.json"
    path.write_text(json.dumps([{"kind": "reference_good", "language": "en", "subject": "S",
                                 "body": "Hi Ana,\n\nA body.", "company": "Acme"}]))
    assert ev.import_examples(engine, path) == 1
    assert ev.import_examples(engine, path) == 0


def test_eval_writes_old_and_new_side_by_side(job_ready: dict, client, tmp_path: Path) -> None:  # noqa: F811, ANN001
    d = outreach.generate(engine, job_ready["app"], MockEmailDrafter(),
                          researcher=research.MockResearcher(), fetcher=Site(),
                          mode="speculative")
    client.post(f"/api/outreach/drafts/{d.id}/reject")
    with Session(engine) as s:
        case = s.exec(select(EmailExample).where(EmailExample.draft_id == d.id)).one().id
    path, results = ev.run_eval(engine, MockEmailDrafter(), case=case, out_dir=tmp_path)
    text = path.read_text()
    assert "| Old | New |" in text and f"## Case {case}" in text
    assert results[0]["new"]["body"].startswith("Hi Ana,") and "errors" in results[0]
    assert path.with_suffix(".json").exists()


def test_the_current_email_prompt_was_run_against_the_regression_set() -> None:
    """A change to app/prompts/outreach.md is adopted only after `make eval-emails`: record the
    report in app/prompts/eval_log.json under the new version."""
    root = Path(__file__).resolve().parents[1] / "app" / "prompts"
    versions = json.loads((root / "versions.json").read_text())["outreach"]
    latest = str(max(map(int, versions)))
    log = json.loads((root / "eval_log.json").read_text()).get("outreach", {})
    assert latest in log, (f"outreach v{latest} has no eval: run `make eval-emails` and record "
                           "the report in app/prompts/eval_log.json")
    assert log[latest]["errors"] == 0 or log[latest].get("note")
