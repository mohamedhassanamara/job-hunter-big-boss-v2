# ruff: noqa: E402
"""Data changes and test drafts for the outreach v17 rewrite. Touches the REAL database.

    .venv/bin/python scripts/manual_outreach_v17.py <step> [args] --live

Steps (each backs the DB up first when it writes):
  link                       set Settings → Candidate links → portfolio (PORTFOLIO below)
  retire                     old applied-mode examples become kind "retired" (history)
  draft <app_id> [--claude]  write ONE draft for a job (never approved, never queued)
  example <draft_id>         save that draft's structure as the approved example (the draft itself
                             stays a draft: nothing is approved)
  report <draft_id> [--claude-verify]   the v17 checks on one real draft
  copy-test [--claude]       DB copy in the scratchpad: Backend + Data/AI + Mobile jobs marked
                             applied with a verified contact, one draft each (mock models unless
                             --claude), then the same report. The real database is not touched.
Nothing here sends anything.
"""

import sys

if "--live" not in sys.argv:  # manual script: never run by accident (or as a test)
    sys.exit("manual_outreach_v17.py opens the REAL database. Re-run it with --live.")
sys.argv.remove("--live")

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, col, select

from app.db import engine
from app.models import AppSetting, EmailExample, OutreachDraft
from app.services.contacts_import import backup_db

PORTFOLIO = "https://mohamedhassenamara.dev"


def link() -> None:
    print("backup:", backup_db(engine, "portfolio-link"))
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
        value = dict(row.value)
        links = [dict(x) for x in value.get("links") or []]
        old = [x.get("url") for x in links if x.get("type") == "portfolio"]
        for x in links:
            if x.get("type") == "portfolio":
                x["url"] = PORTFOLIO
        if not old:
            links.append({"type": "portfolio", "label": "", "url": PORTFOLIO})
        row.value = {**value, "links": links}
        s.add(row)
        s.commit()
    print(f"portfolio: {old or 'none'} -> {PORTFOLIO}")


def retire() -> None:
    print("backup:", backup_db(engine, "retire-applied-examples"))
    with Session(engine) as s:
        rows = [e for e in s.exec(select(EmailExample).where(
            col(EmailExample.kind).in_(["approved", "style_reference"]))).all()
            if (e.inputs or {}).get("mode") == "applied"]
        for e in rows:
            e.note = ((e.note or "") + f" [retired: was {e.kind}, applied mode before v17]").strip()
            e.kind = "retired"
            s.add(e)
        s.commit()
    print(f"retired {len(rows)} applied-mode example(s)")


def draft(app_id: int, claude: bool) -> None:
    from app.providers.registry import email_drafter
    from app.services import model_choice, outreach

    with Session(engine) as s:
        pick = model_choice.choice(s, "email", "claude" if claude else None)
    drafter = email_drafter(model=pick["model"], engine=engine,
                            thinking_level=pick["thinking_level"])
    d = outreach.generate_applied(engine, app_id, drafter)
    print(f"draft {d.id} ({drafter.model}, {d.prompt_version}), status {d.status}")
    print(f"Subject: {d.subject}\n\n{d.body}")
    print("violations:", [(v['severity'], v['type'], v['message']) for v in d.violations])


def example(draft_id: int) -> None:
    from app.eval.emails import record

    print("backup:", backup_db(engine, "v17-example"))
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft_id)
        row = record(s, d, "approved")
        row.note = "v17 structure (portal-first follow-up, plain text); from an unapproved draft"
        row.inputs = {**row.inputs, "structure": 17}
        s.commit()
        print("saved example", row.id)


def report(engine_, draft_id: int, verifier_: object | None = None) -> None:
    """The v17 checks on one draft: plain text with no attachment, the opening against the
    application record, no URL in the body, the portfolio link in the signature, under 110
    words, and the verifier's verdicts."""
    import re

    from app.models import Application, Job
    from app.providers import smtp_mailer
    from app.services import applied_check as ac
    from app.services import outreach, verifier

    with Session(engine_) as s:
        d = s.get(OutreachDraft, draft_id)
        app = s.get(Application, d.application_id)
        job = s.get(Job, app.job_id)
        full = outreach.full_body(s, d)
        email = outreach.outgoing(s, engine_, d)
        msg = smtp_mailer.plain_message(email, "sender@example.invalid")
        facts = outreach.application_facts(app)
        portfolio = next((x["url"] for x in AppProfile(s) if x.get("type") == "portfolio"), "")
        shown = re.sub(r"^https?://(www\.)?", "", portfolio)
        opening = d.body.split("\n\n")[1]
        want_via = ac.method_phrase(facts["method"], (d.plan or {}).get("language") or "en")
        when = facts["date"]
        words = len(d.body.split())
        record = verifier.verify_email(s, d, verifier_) if verifier_ else d.verification
        s.commit()
        claims = (record or {}).get("claims") or []
        verdicts: dict[str, int] = {}
        for c in claims:
            verdicts[c.get("verdict", "?")] = verdicts.get(c.get("verdict", "?"), 0) + 1
        print(f"\n=== draft {d.id} · app {app.id} · {job.matched_track} · {job.title[:50]} · "
              f"{d.model} ===")
        print(f"Subject: {d.subject}\n\n{full}\n")

        def line(ok: bool, text: str) -> None:
            print(f"  [{'PASS' if ok else 'FAIL'}] {text}")

        line(not list(msg.iter_attachments()) and msg.get_content_type() == "text/plain"
             and smtp_mailer.email_problem(email) is None,
             f"zero attachments, text/plain only (content type {msg.get_content_type()}, "
             f"multipart={msg.is_multipart()})")
        line(want_via in opening, f"opening matches the record: method {facts['method']}, "
             f"applied {when}: “{opening}”")
        line(not ac._DOMAIN.search(d.body), "zero URLs or domains in the body")
        line(bool(shown) and shown in full.split("\n\n")[-1] or shown in full.splitlines()[-1],
             f"signature carries the portfolio link ({shown})")
        line(words <= 110, f"{words} words (greeting to ask)")
        errs = [v for v in d.violations or [] if v.get("severity") == "error"]
        line(not errs, f"no blocking check errors {[v['message'] for v in errs]}")
        status = (record or {}).get("status", "not run")
        print(f"  verifier: {status} · verdicts {verdicts or 'none'} · "
              f"via {(record or {}).get('model', '')}")
        for c in claims:
            if c.get("verdict") not in ("supported", "not_a_claim"):
                print(f"    - {c['verdict']}: {c.get('claim')} ({(c.get('reason') or '')[:160]})")
        print("  warnings:", [v["type"] for v in d.violations or []
                              if v.get("severity") != "error"])
        if job.matched_track == "Data/AI":
            body = d.body.lower()
            line(any(w in body for w in ("project", "projet", "internship", "stage", "graduation",
                                         "personal", "personnel", "fin d")),
                 "the Data/AI draft describes the work as projects (not professional experience)")


def AppProfile(s: Session) -> list[dict]:  # noqa: N802
    row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).one()
    return list(row.value.get("links") or [])


def copy_test(claude: bool) -> None:
    import tempfile
    from datetime import timedelta

    from app.db import make_engine
    from app.models import Application, Contact, Job
    from app.models.base import utcnow
    from app.models.enums import ApplyMethod
    from app.providers.mock import MockEmailDrafter, MockVerifier
    from app.services import model_choice, outreach, verifier

    folder = Path(tempfile.mkdtemp(prefix="v17-copy-"))
    path = backup_db(engine, "v17-copy", folder)
    print("copy:", path)
    copy = make_engine(f"sqlite:///{path}")
    now = utcnow()
    with Session(copy) as s:
        # Backend: LinkedIn, yesterday, a new verified contact; Data/AI: a job board, today.
        backend = s.get(Application, 3938)
        data = s.get(Application, 1073)
        for app, method, when in ((backend, ApplyMethod.linkedin, now - timedelta(days=1)),
                                  (data, ApplyMethod.job_board, now)):
            app.web_method, app.web_applied_at = method, when
            s.add(app)
        job = s.get(Job, backend.job_id)
        contact = Contact(company_id=job.company_id, full_name="Test Contact", first_name="Test",
                          title="Engineering Manager", email="test.contact@example.invalid",
                          normalized_name="test contact", role_rank=0, verified_at=now,
                          verified_how="still_there")
        s.add(contact)
        s.flush()
        backend.contact_id = contact.id
        dc = s.get(Contact, data.contact_id)
        dc.verified_at, dc.verified_how = now, "still_there"
        s.add(dc)
        s.commit()
    if claude:
        from app.providers.registry import email_drafter

        with Session(copy) as s:
            pick = model_choice.choice(s, "email", "claude")
        drafter = email_drafter(model=pick["model"], engine=copy,
                                thinking_level=pick["thinking_level"])
        with Session(copy) as s:
            check = verifier.for_workspace(s, "real")  # Claude, as approval would use
    else:
        drafter, check = MockEmailDrafter(), MockVerifier()
    for app_id in (4736, 3938, 1073):
        d = outreach.generate_applied(copy, app_id, drafter)
        report(copy, d.id, check)


if __name__ == "__main__":
    args = sys.argv[1:]
    step = args[0] if args else ""
    if step == "link":
        link()
    elif step == "retire":
        retire()
    elif step == "draft":
        draft(int(args[1]), "--claude" in args)
    elif step == "example":
        example(int(args[1]))
    elif step == "report":
        from app.services import verifier as _v

        verifier_ = None
        if "--claude-verify" in args:
            with Session(engine) as _s:
                verifier_ = _v.for_workspace(_s, "real")
        report(engine, int(args[1]), verifier_)
    elif step == "copy-test":
        copy_test("--claude" in args)
    else:
        sys.exit(__doc__)
