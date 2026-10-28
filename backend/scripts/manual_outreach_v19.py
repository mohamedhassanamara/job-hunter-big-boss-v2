# ruff: noqa: E402
"""Test drafts for the outreach v19 (persona-aware, gap-resilient) follow-ups. Reads the REAL
database, writes only to a COPY.

    .venv/bin/python scripts/manual_outreach_v19.py [--claude] --live

Backs the real DB up (data/backups), copies it to a temp folder, picks five applications from the
copy (engineering manager + years gap, CTO + stack pivot, staff engineer + direct match,
recruiter, Data/AI), marks them applied with a verified test contact whose title sets the persona,
writes one draft each (mock models unless --claude) and prints the text, the word count, the code
checks and the verifier's verdicts. Nothing is approved, queued or sent; the real DB is not
changed.
"""

import sys

if "--live" not in sys.argv:  # manual script: never run by accident (or as a test)
    sys.exit("manual_outreach_v19.py opens the REAL database. Re-run it with --live.")
sys.argv.remove("--live")

import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, col, select

from app.db import engine, make_engine
from app.models import Application, Contact, Job, OutreachDraft
from app.models.base import utcnow
from app.models.enums import ApplyMethod
from app.services import applied_check as ac
from app.services import contacts, honesty, outreach, verifier
from app.services.contacts_import import backup_db
from app.services.cv_pool import load_pool, years_facts

# (label, contact title, wanted scenario, projects track?, apply method, days ago)
CASES = [
    ("EM + years gap", "Engineering Manager", "years_gap", False, ApplyMethod.company_site, 0),
    ("CTO + stack pivot", "Co-Founder & CTO", "stack_pivot", False, ApplyMethod.linkedin, 1),
    ("Staff + direct match", "Staff Software Engineer", "direct", False,
     ApplyMethod.company_site, 4),
    ("Recruiter", "Senior Technical Recruiter", None, False, ApplyMethod.job_board, 1),
    ("Data/AI", "Head of Data", None, True, ApplyMethod.company_site, 0),
]


def candidates(s: Session) -> list[dict]:
    """Every application with a usable source CV, its scenario and whether its track is a
    projects track."""
    from app.services.cv_service import _tracks

    pool = load_pool(s)
    have = max((int(f["years"]) for f in years_facts(pool, _tracks(s))), default=None)
    projects = {t.name for t in honesty.rules(s).projects}
    text = pool.all_text()
    out = []
    for app in s.exec(select(Application).order_by(col(Application.id).desc())).all():
        job = s.get(Job, app.job_id)
        if job is None or len(job.description or "") < ac.SNIPPET_CHARS:
            continue
        if outreach.source_cv(s, app) is None:
            continue
        out.append({"app": app.id, "job": job.title, "track": job.matched_track,
                    "projects": job.matched_track in projects,
                    **ac.scenario_for(job.title, job.description, text, have)})
    return out


def pick(found: list[dict], want: str | None, projects: bool, used: set[int]) -> dict | None:
    for c in found:
        if c["app"] in used or c["projects"] != projects:
            continue
        if want is None or c["scenario"] == want:
            return c
    return None


def synthesize_pivot(copy, found: list[dict], used: set[int]) -> dict | None:
    """No real listing names a stack your pool lacks: retitle a direct-match mobile job in the
    COPY to "React Native Engineer" so the stack-pivot path is exercised."""
    with Session(copy) as s:
        text = load_pool(s).all_text()
        for c in found:
            if c["app"] in used or c["projects"] or c["scenario"] != "direct":
                continue
            job = s.get(Job, s.get(Application, c["app"]).job_id)
            if ac.scenario_for("React Native Engineer", job.description, text, None)[
                    "scenario"] != "stack_pivot":
                continue
            job.title = "React Native Engineer"
            s.add(job)
            s.commit()
            print(f"(copy only) app {c['app']} retitled “React Native Engineer” for the pivot case")
            return c
    return None


def report(copy, draft_id: int, label: str, check: object) -> None:
    with Session(copy) as s:
        d = s.get(OutreachDraft, draft_id)
        app = s.get(Application, d.application_id)
        job = s.get(Job, app.job_id)
        full = outreach.full_body(s, d)
        record = verifier.verify_email(s, d, check)
        s.commit()
        claims = record.get("claims") or []
        verdicts: dict[str, int] = {}
        for c in claims:
            verdicts[c.get("verdict", "?")] = verdicts.get(c.get("verdict", "?"), 0) + 1
        g = (d.plan or {}).get("guidance") or {}
        words = len(d.body.split())
        print(f"\n=== {label} · draft {d.id} · app {app.id} · {job.matched_track} · "
              f"{job.title[:50]} · {d.model} ===")
        print(f"persona {g.get('persona')} ({g.get('persona_source')}) · scenario "
              f"{g.get('scenario')} {g.get('scenario_detail') or ''}")
        print(f"Subject: {d.subject}\n\n{full}\n")
        print(f"  words (greeting to ask): {words} ({'OK' if words < 110 else 'OVER 110'})")
        errs = [v["message"] for v in d.violations or [] if v.get("severity") == "error"]
        warns = [v["type"] for v in d.violations or [] if v.get("severity") != "error"]
        print(f"  code errors: {errs or 'none'} · warnings: {warns or 'none'}")
        print(f"  verifier: {record.get('status')} · verdicts {verdicts or 'none'} · "
              f"via {record.get('model', '')}")
        for c in claims:
            if c.get("verdict") not in ("supported", "not_a_claim"):
                print(f"    - {c['verdict']}: {c.get('claim')} ({(c.get('reason') or '')[:160]})")


def main(claude: bool) -> None:
    real_backup = backup_db(engine, "outreach-v19")
    print("real DB backed up to:", real_backup)
    folder = Path(tempfile.mkdtemp(prefix="v19-copy-"))
    path = backup_db(engine, "v19-copy", folder)
    print("working copy:", path)
    copy = make_engine(f"sqlite:///{path}")
    with Session(copy) as s:
        found = candidates(s)
    print(f"{len(found)} application(s) with a source CV and a full listing; scenarios: "
          f"{ {k: sum(1 for c in found if c['scenario'] == k) for k in ac.SCENARIOS} }")
    now = utcnow()
    chosen, used = [], set()
    for label, title, want, projects, method, days in CASES:
        c = pick(found, want, projects, used)
        if c is None and want == "stack_pivot":
            c = synthesize_pivot(copy, found, used)  # no real listing pivots: retitle one (copy)
        if c is None:
            print(f"!! no application for “{label}” (scenario {want}, projects={projects})")
            continue
        used.add(c["app"])
        chosen.append((label, title, method, days, c))
    with Session(copy) as s:
        for _label, title, method, days, c in chosen:
            app = s.get(Application, c["app"])
            app.web_method, app.web_applied_at = method, now - timedelta(days=days)
            job = s.get(Job, app.job_id)
            contact = Contact(company_id=job.company_id, full_name="Test Contact",
                              first_name="Test", title=title, email="test@example.invalid",
                              normalized_name=f"test contact {app.id}",
                              role_rank=contacts.rank(title, contacts.role_ranking(s))[0],
                              verified_at=now, verified_how="still_there")
            s.add(contact)
            s.flush()
            app.contact_id = contact.id
            s.add(app)
        s.commit()
    if claude:
        from app.providers.registry import email_drafter
        from app.services import model_choice

        with Session(copy) as s:
            pick_ = model_choice.choice(s, "email", "claude")
            check = verifier.for_workspace(s, "real")  # Claude, as approval would use
        drafter = email_drafter(model=pick_["model"], engine=copy,
                                thinking_level=pick_["thinking_level"])
    else:
        from app.providers.mock import MockEmailDrafter, MockVerifier

        drafter, check = MockEmailDrafter(), MockVerifier()
    for label, _title, _method, _days, c in chosen:
        d = outreach.generate_applied(copy, c["app"], drafter)
        report(copy, d.id, label, check)


if __name__ == "__main__":
    main("--claude" in sys.argv[1:])
