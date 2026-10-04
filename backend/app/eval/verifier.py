"""The claim verifier's regression set (`make eval-verifier`; ARGS="--mock", "--case 5").

Must pass: your approved examples (email_example kind reference_good / approved, emails and
LinkedIn notes). Must fail: the "must_fail" rows (added here once if missing): "mentoring other
developers" (your experience says one junior developer) and "3 years of experience building
data pipelines" (your years are professional mobile and backend; data is project-based).

Each case runs the real verifier (Claude via `claude -p`, Opus by default, never an API key)
on the text exactly as the reader sees it, with the same sources as in the app. The report in
data/eval/verifier/ lists every claim with its verdict, source quote and reason, and the time
each verification took.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.config import DATA_DIR
from app.models import Application, EmailExample, Job
from app.services import verifier
from app.services.cv_pool import load_pool

OUT_DIR = DATA_DIR / "eval" / "verifier"
MUST_PASS = ("reference_good", "approved")
BASE_NOTE = 5  # your approved LinkedIn note: each must-fail case changes one claim of it

# Each must-fail case swaps one fragment of the approved note (no names in source code).
MUST_FAIL = [
    {"case": "mentoring",
     "replace": ("with dbt and Airflow projects", "and I've been mentoring other developers"),
     "note": "Must fail: your experience says you mentored one junior developer, not "
             "'other developers'."},
    {"case": "years_data_pipelines",
     "replace": ("a software engineer (3 years, mobile and backend) moving into data, with dbt "
                 "and Airflow projects", "a software engineer with 3 years of experience "
                 "building data pipelines"),
     "note": "Must fail: your 3 years are professional mobile and backend; data pipelines are "
             "projects."},
]


def ensure_must_fail(s: Session) -> int:
    """Add the must-fail cases once (on the context of your approved LinkedIn note)."""
    base = s.get(EmailExample, BASE_NOTE)
    have = {(e.inputs or {}).get("case") for e in s.exec(
        select(EmailExample).where(EmailExample.kind == "must_fail")).all()}
    added = 0
    for case in MUST_FAIL:
        old, new = case["replace"]
        if case["case"] in have or base is None or old not in base.body:
            continue
        s.add(EmailExample(kind="must_fail", language="en", company=base.company,
                           body=base.body.replace(old, new), note=case["note"],
                           inputs={**(base.inputs or {}), "case": case["case"],
                                   "expect": "fail", "track": None}))
        added += 1
    s.commit()
    return added


def cases(s: Session, only: int | None = None) -> list[EmailExample]:
    stmt = select(EmailExample).where(col(EmailExample.kind).in_([*MUST_PASS, "must_fail"]))
    if only is not None:
        stmt = stmt.where(EmailExample.id == only)
    return list(s.exec(stmt.order_by(col(EmailExample.id))).all())


def text_and_sources(s: Session, ex: EmailExample) -> tuple[str, str, dict[str, str]]:
    """The text as the reader sees it, and the sources the app would give the verifier."""
    inputs = ex.inputs or {}
    app = s.get(Application, inputs.get("application_id") or -1)
    if app is None:
        raise ValueError("no application_id in the example's inputs")
    job = s.get(Job, app.job_id)
    sources = verifier.candidate_sources(s, load_pool(s), verifier._approved_cv(s, app.id)) \
        | verifier.signal_sources(s, job.company_id)
    from app.eval.emails import case_contact  # the job's contact, or the one its draft had

    contact = case_contact(s, ex, app)
    sources |= verifier.recipient_source(s, job, contact.id if contact else None)
    if inputs.get("channel") == "linkedin":
        sources["listing"] = f"{job.title}\n{job.description or ''}"
        return "LinkedIn connection note", ex.body, sources
    return "cold email (with its subject)", f"Subject: {ex.subject}\n\n{ex.body}", sources


def run_eval(engine: Engine, v: Any, only: int | None = None,
             out_dir: Path = OUT_DIR) -> tuple[Path, list[dict[str, Any]]]:
    rows = []
    with Session(engine) as s:
        ensure_must_fail(s)
        for ex in cases(s, only):
            expect = "fail" if ex.kind == "must_fail" else "pass"
            row: dict[str, Any] = {"id": ex.id, "kind": ex.kind, "expect": expect,
                                   "company": ex.company, "note": ex.note,
                                   "channel": (ex.inputs or {}).get("channel") or "email"}
            try:
                kind, text, sources = text_and_sources(s, ex)
            except ValueError as exc:
                rows.append({**row, "skipped": str(exc)})
                continue
            record = verifier.run(v, kind, text, sources)
            got = "pass" if record["status"] == "passed" else (
                "fail" if record["status"] == "failed" else "error")
            rows.append({**row, "text": text, "status": record["status"], "got": got,
                         "as_expected": got == expect, "duration_ms": record["duration_ms"],
                         "model": record.get("model"), "error": record.get("error"),
                         "claims": record.get("claims") or []})
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}_{getattr(v, 'prompt_version', 'verify').replace('/', '_')}.md"
    path.write_text(render_md(rows, v))
    path.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    return path, rows


def render_md(rows: list[dict[str, Any]], v: Any) -> str:
    done = [r for r in rows if "got" in r]
    ok = sum(r["as_expected"] for r in done)
    times = [r["duration_ms"] for r in done]
    lines = [f"# Claim verifier · {getattr(v, 'prompt_version', '?')} · "
             f"{getattr(v, 'model', '?')} · {datetime.now(UTC):%Y-%m-%d %H:%M} UTC", "",
             f"{ok}/{len(done)} as expected"
             + (f" · {sum(times) / len(times) / 1000:.1f} s per verification on average "
                f"({min(times) / 1000:.1f}-{max(times) / 1000:.1f} s)" if times else ""), "",
             "| # | Kind | Expected | Got | Time | Blocking claims |", "|---|---|---|---|---|---|"]
    for r in rows:
        if "got" not in r:
            lines.append(f"| {r['id']} | {r['kind']} | {r['expect']} | skipped | | "
                         f"{r['skipped']} |")
            continue
        bad = [c for c in r["claims"] if c["verdict"] in verifier.BLOCKING]
        mark = "" if r["as_expected"] else " ✗"
        lines.append(f"| {r['id']} | {r['kind']} ({r['channel']}) | {r['expect']} | "
                     f"{r['got']}{mark} | {r['duration_ms'] / 1000:.1f} s | {len(bad)} |")
    for r in done:
        lines += ["", f"## #{r['id']} · {r['kind']} · {r['company']} · expected {r['expect']},"
                      f" got {r['got']}", ""]
        if r.get("note"):
            lines += [f"_{r['note']}_", ""]
        lines += ["```", r["text"], "```", ""]
        if r.get("error"):
            lines += [f"Error: {r['error']}", ""]
        lines += ["| Verdict | Claim | Source | Quote | Reason |", "|---|---|---|---|---|"]
        for c in r["claims"]:
            def cell(x: Any) -> str:
                return str(x or "").replace("|", "/").replace("\n", " ")
            lines.append(f"| {c['verdict']} | {cell(c['claim'])} | {cell(c['source_id'])} | "
                         f"{cell(c['source_quote'])} | {cell(c['reason'])} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    from app.db import engine
    from app.providers.registry import verifier as make_verifier

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="the mock verifier (no Claude)")
    parser.add_argument("--case", type=int)
    parser.add_argument("--model", default=verifier.DEFAULT_MODEL)
    args = parser.parse_args()
    v = make_verifier(mock=args.mock, model=args.model)
    path, rows = run_eval(engine, v, args.case)
    print(f"{len(rows)} case(s) with {getattr(v, 'model', '?')}: {path}")
    for r in rows:
        if "got" in r:
            print(f"  #{r['id']} {r['kind']}: expected {r['expect']}, got {r['got']}"
                  f"{'' if r['as_expected'] else '  ✗'} ({r['duration_ms'] / 1000:.1f} s)"
                  + (f"  {r['error']}" if r.get("error") else ""))
        else:
            print(f"  #{r['id']} {r['kind']}: skipped ({r['skipped']})")


if __name__ == "__main__":
    main()
