# ruff: noqa: E402
"""Data changes and test drafts for the outreach v17 rewrite. Touches the REAL database.

    .venv/bin/python scripts/manual_outreach_v17.py <step> [args] --live

Steps (each backs the DB up first when it writes):
  link                       set Settings → Candidate links → portfolio (PORTFOLIO below)
  retire                     old applied-mode examples become kind "retired" (history)
  draft <app_id> [--claude]  write ONE draft for a job (never approved, never queued)
  example <draft_id>         save that draft's structure as the approved example (the draft itself
                             stays a draft: nothing is approved)
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
    else:
        sys.exit(__doc__)
