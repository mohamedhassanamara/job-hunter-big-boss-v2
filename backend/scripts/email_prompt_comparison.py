# ruff: noqa: E501, B023
"""Email prompt v14: the same jobs written by Gemini (Settings default) and by Claude, side by side.

Runs the production code (`outreach.generate_applied`: prompt, checks, one retry, the Claude claim
verifier) on a SCRATCH COPY of the real DB: nothing real is written, nothing is approved or sent.
Where a job has no approved CV or verified contact in the real data, the scratch copy gets them
(a Gemini CV marked approved there; an existing contact of the company, else a placeholder) and
the report says so. The email never contains the placeholder's data beyond a first name.

    .venv/bin/python scripts/email_prompt_comparison.py --apps 1622,4951,3938,2428,2429 --out <dir>
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCRATCH = Path(tempfile.mkdtemp(prefix="jh-email-compare-"))


def make_scratch_db() -> Path:
    path = SCRATCH / "scratch.db"
    src = sqlite3.connect(f"file:{REPO / 'data' / 'jobhunter.db'}?mode=ro", uri=True)
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    return path


os.environ["DATABASE_URL"] = f"sqlite:///{make_scratch_db()}"
os.environ["SEND_WORKER_ENABLED"] = "false"
os.environ["GENERATION_WORKER_ENABLED"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"

from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Application, Company, Contact, CVVersion, Job, OutreachDraft  # noqa: E402
from app.models.base import utcnow  # noqa: E402
from app.models.enums import CVStatus, Stage  # noqa: E402
from app.providers.registry import email_drafter  # noqa: E402
from app.providers.registry import verifier as make_verifier  # noqa: E402
from app.services import applied_check as ac  # noqa: E402
from app.services import cv_service, model_choice, outreach  # noqa: E402
from app.services import verifier as vs  # noqa: E402
from app.services.cv_pool import load_pool  # noqa: E402

CLAUDE = "claude-sonnet-5"


def split(violations: list[dict]) -> dict[str, list[str]]:
    def fmt(v: dict) -> str:
        return f"[{v.get('type')}] {v.get('message', '')}"
    return {"errors": [fmt(v) for v in violations if v.get("severity") == "error"],
            "warnings": [fmt(v) for v in violations if v.get("severity") != "error"]}


def prepare(app_id: int, out: Path) -> dict[str, Any]:
    """Make sure the scratch copy has an approved CV and a verified contact for the job."""
    notes: list[str] = []
    with Session(engine) as s:
        app = s.get(Application, app_id)
        job = s.get(Job, app.job_id)
        approved = outreach.approved_cv(s, app)
        if approved is None:
            started = time.monotonic()
            pick = model_choice.choice(s, "cv")
            from app.providers.registry import cv_generator
            gen = cv_generator(mock=False, model=pick["model"], thinking_level=pick["thinking_level"],
                               engine=engine)
            v = cv_service.generate(engine, app_id, gen, None, verifier=make_verifier(mock=False))
            s.expire_all()
            v = s.get(CVVersion, v.id)
            v.status = CVStatus.approved
            s.add(v)
            notes.append(f"scratch only: no approved CV in the real data; a {gen.model} CV was generated "
                         f"({round(time.monotonic() - started)} s) and marked approved in the copy")
        contact = s.get(Contact, app.contact_id) if app.contact_id else None
        if contact is None or not contact.email:
            contact = s.exec(select(Contact).where(Contact.company_id == job.company_id,
                                                   Contact.email.is_not(None))).first()  # type: ignore[union-attr]
            if contact is not None:
                notes.append(f"scratch only: the job had no contact; {contact.full_name} "
                             f"({contact.title or 'no title'}) of the same company is used")
        if contact is None:
            company = s.get(Company, job.company_id)
            domain = re.sub(r"[^a-z0-9]", "", company.name.lower()) or "company"
            contact = Contact(company_id=company.id, full_name="Alex Morgan", first_name="Alex",
                              title="Engineering Manager", email=f"alex.morgan@{domain}.example",
                              normalized_name="alex morgan", role_rank=0)
            s.add(contact)
            s.flush()
            notes.append("scratch only: no contact for this company; a placeholder (Alex Morgan) is used")
        contact.verified_at, contact.verified_how = utcnow(), "still_there"
        contact.left_at = contact.left_reason = None
        app.contact_id = contact.id
        app.stage = Stage.cv_ready
        s.add_all([contact, app])
        s.commit()
        return {"app": app_id, "company": s.get(Company, job.company_id).name, "title": job.title,
                "track": job.matched_track, "country": job.country, "listing_chars": len(job.description or ""),
                "notes": notes}


def run_one(app_id: int, label: str, drafter: Any, cverifier: Any, rule_language: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        draft = outreach.generate_applied(engine, app_id, drafter)
    except Exception as exc:  # noqa: BLE001
        return {"label": label, "error": f"{type(exc).__name__}: {exc}",
                "seconds": round(time.monotonic() - started, 1)}
    seconds = round(time.monotonic() - started, 1)
    with Session(engine) as s:
        d = s.get(OutreachDraft, draft.id)
        pool = load_pool(s)
        facts = [f for item in pool.items.values() for f in pool.facts(item)]
        refs = outreach.applied_references(s)
        body = d.body
        runs = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
            run, source = ac.copy_run(sentence, facts, refs)
            runs.append((run, source, sentence.strip()))
        best = max(runs, key=lambda r: r[0])
        code = split(d.violations or [])
        blocked_by_code = bool(code["errors"])
        record = vs.verify_email(s, d, cverifier)
        s.commit()
        s.refresh(d)
        claims = [{k: c.get(k) for k in ("verdict", "claim", "source_id", "reason")}
                  for c in (d.verification or {}).get("claims") or []]
        verdicts: dict[str, int] = {}
        for c in claims:
            verdicts[c["verdict"]] = verdicts.get(c["verdict"], 0) + 1
        text = vs.email_text(s, d)
        runner = getattr(drafter, "runner", None)
        return {
            "label": label, "model": d.model, "prompt_version": d.prompt_version,
            "language": (d.plan or {}).get("language"), "language_rule": rule_language,
            "language_matches": (d.plan or {}).get("language") == rule_language,
            "words": len(re.findall(r"\w+", body)), "attempts": (d.plan or {}).get("attempts"),
            "copy_longest_run": best[0], "copy_source": best[1], "copy_quote": best[2],
            "errors": code["errors"], "warnings": code["warnings"],
            "would_block_before_verifier": blocked_by_code,
            "verifier_status": record.get("status"), "verifier_blocking": record.get("blocking"),
            "verdicts": verdicts, "claims": claims, "text": text,
            "seconds": seconds, "draft_seconds": round((d.duration_ms or 0) / 1000, 1),
            "verifier_seconds": round((record.get("duration_ms") or 0) / 1000, 1),
            "model_stats": runner.summary() if hasattr(runner, "summary") else None,
        }


def render(results: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for r in results:
        j = r["job"]
        out += [f"### {j['company']}: {j['title']}", "",
                f"Track {j['track']} · country {j['country']} · listing {j['listing_chars']:,} characters · "
                f"language rule: **{r['runs'][0].get('language_rule')}**", ""]
        out += [f"- {n}" for n in j["notes"]] + ([""] if j["notes"] else [])
        runs = r["runs"]
        out += ["| | " + " | ".join(x["label"] for x in runs) + " |", "|---|" + "---|" * len(runs)]

        def row(name: str, fn) -> None:  # noqa: ANN001
            out.append(f"| {name} | " + " | ".join(fn(x) if "error" not in x else "failed" for x in runs) + " |")

        row("Language (matches rule)", lambda x: f"{x['language']} ({'yes' if x['language_matches'] else 'NO'})")
        row("Words (aim 90-120, warn outside 90-170)", lambda x: str(x["words"]))
        row("Copy overlap, longest run with a pool bullet or the style reference", lambda x: f"{x['copy_longest_run']} words" + (f" ({x['copy_source']})" if x["copy_longest_run"] else ""))
        row("Draft attempts (2 = the automatic retry ran)", lambda x: str(x["attempts"]))
        row("Code errors", lambda x: str(len(x["errors"])))
        row("Code warnings", lambda x: str(len(x["warnings"])))
        row("Claude verifier", lambda x: f"{x['verifier_status']} ({x['verifier_blocking']} blocking)")
        row("Verdicts", lambda x: ", ".join(f"{k} {v}" for k, v in sorted(x["verdicts"].items())) or "none")
        row("Draft time", lambda x: f"{x['draft_seconds']} s")
        row("Verifier time", lambda x: f"{x['verifier_seconds']} s")
        row("Gemini calls / retries 429 / 503 / tokens in-out-thinking", lambda x: (
            f"{x['model_stats']['calls']} / {x['model_stats']['retries_429']} / {x['model_stats']['retries_503']} / "
            f"{x['model_stats']['tokens_in']}-{x['model_stats']['tokens_out']}-{x['model_stats']['tokens_thinking']}") if x["model_stats"] else "n/a (Claude CLI)")
        out.append("")
        for x in runs:
            out += [f"**{x['label']}**", ""]
            if "error" in x:
                out += [f"Failed: {x['error']}", ""]
                continue
            out += ["```text", x["text"], "```", ""]
            if x["errors"] or x["warnings"]:
                out += [f"- ERROR {m}" for m in x["errors"]] + [f"- warning {m}" for m in x["warnings"]] + [""]
            bad = [c for c in x["claims"] if c["verdict"] not in ("supported", "not_a_claim")]
            out += ["Verifier verdicts that are not supported / not_a_claim:"] + (
                [f"- **{c['verdict']}** “{c['claim']}” ({c['reason']})" for c in bad] or ["- none"]) + [""]
            if x["copy_longest_run"] >= 6:
                out += [f"Longest copied run ({x['copy_longest_run']} words, {x['copy_source']}): “{x['copy_quote']}”", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert str(engine.url).endswith("scratch.db")
    cv_service.CV_DIR = out / "cvfiles"
    verifier = make_verifier(mock=False)
    results = []
    for app_id in [int(x) for x in args.apps.split(",")]:
        print(f"== app {app_id}", flush=True)
        job = prepare(app_id, out)
        with Session(engine) as s:
            rule = outreach.language_choice(s, s.get(Job, s.get(Application, app_id).job_id),
                                            s.get(Application, app_id), None).language
            gem = model_choice.choice(s, "email")
        runs = []
        for label, drafter in (
                (f"{gem['model']} ({gem['thinking_level']})", email_drafter(
                    mock=False, model=gem["model"], thinking_level=gem["thinking_level"], engine=engine)),
                (CLAUDE, email_drafter(mock=False, model=CLAUDE, engine=engine))):
            print(f"   {label}", flush=True)
            runs.append(run_one(app_id, label, drafter, verifier, rule))
        results.append({"job": job, "runs": runs})
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    (out / "report-body.md").write_text(render(results))
    shutil.rmtree(out / "cvfiles", ignore_errors=True)
    print("done", out, flush=True)


if __name__ == "__main__":
    sys.exit(main())
