"""Research costs model calls and time: it may start ONLY at the email draft step
(services/outreach.py) or from the Research now button (api/research.py). This fails if anything
else calls it, and checks that the usual flows create no research runs."""

import re
from pathlib import Path

from sqlmodel import Session, func, select

from app.db import engine
from app.models import Application, AppSetting, ResearchRun
from app.models.enums import Source

APP = Path(__file__).resolve().parents[1] / "app"
ALLOWED = {"services/outreach.py", "api/research.py", "services/research.py",
           "services/linkedin_track.py"}  # the email and LinkedIn follow-up draft steps
CALL = re.compile(r"\b(?:research|rs|research_service)\.(?:ensure|_run)\(|"
                  r"from app\.services\.research import[^\n]*\b(?:ensure|_run)\b")


def test_research_is_only_started_by_the_draft_step_or_the_button() -> None:
    offenders = []
    for path in APP.rglob("*.py"):
        rel = str(path.relative_to(APP))
        if rel in ALLOWED:
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if CALL.search(line):
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, "Research started from outside the draft step:\n" + "\n".join(offenders)


def runs() -> int:
    with Session(engine) as s:
        return s.exec(select(func.count()).select_from(ResearchRun)).one()


def test_discovery_scoring_triage_matching_and_cvs_never_research(seeded: None, client,  # noqa: ANN001
                                                                  monkeypatch) -> None:  # noqa: ANN001
    from app.providers.mock import MockCVGenerator, MockJobSource
    from app.services import contacts, cv_build, cv_service
    from app.services.discovery import run_discovery
    from app.services.scoring import recompute_all
    from tests.test_cv import fake_compiler

    before = runs()
    run_discovery(engine, {Source.remotive: MockJobSource(Source.remotive)})
    recompute_all(engine)
    with Session(engine) as s:
        contacts.match_all(s)
        s.commit()
        app_id = s.exec(select(Application.id).where(Application.stage == "new")).first()
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
        row.value = {**row.value, "full_name": "Ada"}
        s.add(row)
        s.commit()
    client.patch(f"/api/applications/{app_id}", json={"stage": "shortlisted"})
    monkeypatch.setattr(cv_build, "compile_tex", fake_compiler(capacity=60, calls=[]))
    cv_service.generate(engine, app_id, MockCVGenerator())
    assert runs() == before
