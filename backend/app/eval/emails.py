"""The email regression set (make eval-emails).

Cases are your reference examples (data/eval/email_examples.json, imported once) and every email
you approve or reject (recorded automatically, with the request it was written from). The eval
writes each case again with the current prompt, runs the checks, and writes a side-by-side
report (old vs new) to data/eval/emails/. A case's `mode` (inputs) is "applied" (the job-linked
application follow-up) or "speculative" (the research-based introduction); must_fail rows belong
to the claim verifier's set (`make eval-verifier`) and are skipped here. A change to
app/prompts/outreach.md is adopted only after a run: prompts/eval_log.json records the
report for each version (tests check it).

    .venv/bin/python -m app.eval.emails --import          # load the reference examples
    .venv/bin/python -m app.eval.emails [--limit N] [--case ID] [--mock]
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.config import DATA_DIR
from app.models import Application, Company, Contact, EmailExample, Job, OutreachDraft
from app.providers.base import EmailRequest

EXAMPLES_FILE = DATA_DIR / "eval" / "email_examples.json"
OUT_DIR = DATA_DIR / "eval" / "emails"
EVAL_LOG = Path(__file__).resolve().parents[1] / "prompts" / "eval_log.json"


def record(s: Session, draft: OutreachDraft, kind: str) -> EmailExample:
    """An email you approved or rejected joins the regression set (with its inputs)."""
    app = s.get(Application, draft.application_id)
    job = s.get(Job, app.job_id) if app else None
    company = s.get(Company, job.company_id) if job else None
    plan = draft.plan or {}
    row = EmailExample(kind=kind, language=plan.get("language") or "en", subject=draft.subject,
                       body=draft.body, draft_id=draft.id,
                       company=company.name if company else "",
                       inputs={"request": plan.get("request"),
                               "application_id": draft.application_id,
                               "mode": plan.get("mode") or "speculative",
                               "prompt_version": draft.prompt_version})
    s.add(row)
    return row


def import_examples(engine: Engine, path: Path = EXAMPLES_FILE) -> int:
    """Load the reference examples (idempotent: same subject + body are skipped)."""
    if not path.exists():
        return 0
    added = 0
    with Session(engine) as s:
        existing = {(e.subject, e.body) for e in s.exec(select(EmailExample)).all()}
        for e in json.loads(path.read_text()):
            if (e["subject"], e["body"]) in existing:
                continue
            s.add(EmailExample(kind=e["kind"], language=e.get("language", "en"),
                               subject=e["subject"], body=e["body"],
                               company=e.get("company", ""), note=e.get("note", ""),
                               inputs={"application_id": e.get("application_id"),
                                       **{k: e[k] for k in ("mode", "case", "expect")
                                          if k in e}}))
            added += 1
        s.commit()
    return added


def case_contact(s: Session, example: EmailExample, app: Application | None) -> Contact | None:
    """Who the case writes to: the job's contact, else the one its draft was written to (a
    contact being verified is unassigned from the job meanwhile)."""
    if app is None:
        return None
    if app.contact_id:
        return s.get(Contact, app.contact_id)
    draft = s.get(OutreachDraft, example.draft_id) if example.draft_id else s.exec(
        select(OutreachDraft).where(OutreachDraft.application_id == app.id)
        .order_by(col(OutreachDraft.id).desc())).first()
    return s.get(Contact, draft.contact_id) if draft and draft.contact_id else None


def _request(s: Session, example: EmailExample) -> tuple[EmailRequest | None, str]:
    """The inputs to write this case again: its snapshot, or today's for its job."""
    from app.services import honesty, outreach

    inputs = example.inputs or {}
    if inputs.get("mode") == "applied" and not inputs.get("request"):
        app = s.get(Application, inputs.get("application_id") or -1)
        contact = case_contact(s, example, app)
        cv = outreach.approved_cv(s, app) if app else None
        if app is None or contact is None or cv is None:
            return None, example.language
        from app.services.cv_pool import load_pool

        job = s.get(Job, app.job_id)
        return outreach.applied_request(s, app, job, s.get(Company, job.company_id), contact,
                                        cv, load_pool(s), example.language), example.language
    if inputs.get("request"):
        # The snapshot, with today's honesty facts (they're rules, not the case's inputs).
        req = EmailRequest.model_validate(inputs["request"])
        hr = honesty.rules(s)
        req.candidate = {**req.candidate, **honesty.prompt_facts(hr),
                         "areas_you_can_use": honesty.professional_areas(
                             [a for a in req.candidate.get("areas_you_can_use") or []
                              if a not in {t.name for t in hr.projects}], hr)}
        return req, req.rules.get("language") or example.language
    app = s.get(Application, inputs.get("application_id") or -1)
    contact = case_contact(s, example, app)
    if app is None or contact is None:
        return None, example.language
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    cv = outreach.approved_cv(s, app)
    if cv is None:
        return None, example.language
    from app.services.cv_pool import load_pool

    return outreach.intro_request(s, app, job, company, contact, cv, load_pool(s),
                                  example.language), example.language


def run_eval(engine: Engine, drafter: Any, *, limit: int | None = None,
             case: int | None = None, out_dir: Path = OUT_DIR,
             hook_checker: Any = None) -> tuple[Path, list[dict]]:
    from app.services import hook_check, outreach
    from app.services import intro_check as ic
    from app.services.cv_pool import load_pool

    results = []
    with Session(engine) as s:
        stmt = select(EmailExample).order_by(col(EmailExample.id))
        if case is not None:
            stmt = stmt.where(EmailExample.id == case)
        examples = [e for e in s.exec(stmt).all()
                    if (e.inputs or {}).get("channel") != "linkedin"  # emails only
                    and e.kind != "must_fail"]  # the verifier's set
        examples = examples[:limit] if limit else examples
        for ex in examples:
            request, language = _request(s, ex)
            row: dict[str, Any] = {"id": ex.id, "kind": ex.kind, "company": ex.company,
                                   "language": language, "old": {"subject": ex.subject,
                                                                  "body": ex.body}}
            if request is None:
                row["skipped"] = "no inputs (the job needs a contact and an approved CV)"
                results.append(row)
                continue
            app = s.get(Application, (ex.inputs or {}).get("application_id") or -1)
            if (ex.inputs or {}).get("mode") == "applied" or "application" in request.candidate:
                results.append(_applied_row(s, row, ex, request, language, app, drafter))
                continue
            plan = drafter.draft_intro(request)
            plan.greeting = ic.greeting_line(request.contact.get("first_name") or "", language)
            plan.subject = ic.subject_line(str((request.job or {}).get("company") or ex.company),
                                           language)
            first = request.candidate.get("first_name") or "I"
            intro = ic.intro_line(first, plan.intro_focus, language,
                                  request.candidate.get("years_statement"),
                                  request.candidate.get("years_statement_fr"))
            text = ic.body(plan, intro)
            found: list[dict] = []
            contact = case_contact(s, ex, app)
            if app is not None and contact is not None:
                job = s.get(Job, app.job_id)
                ctx = outreach.intro_context(s, app, job, s.get(Company, job.company_id),
                                             contact, load_pool(s), language=language,
                                             intro=intro)
                ctx.examples = [(label, t) for label, t in ctx.examples
                                if label != f"{ex.kind} #{ex.id}"]
                found = ic.check_plan(plan, ctx)
                review = hook_check.check(hook_checker, plan.hook.text, outreach.cited_signals(
                    s, job.company_id, plan.hook.signal_ids))
                found += hook_check.violations(review)
            from app.services import outreach_check as oc

            row.update(new={"subject": plan.subject, "body": text},
                       errors=[v["message"] for v in found if v["severity"] == "error"],
                       warnings=[v["message"] for v in found if v["severity"] != "error"],
                       similarity_to_old=round(oc.similarity(text, ex.body), 2))
            results.append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = getattr(drafter, "prompt_version", "?").replace("/", "_")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{stamp}_{version}.md"
    path.write_text(render_md(results, getattr(drafter, "prompt_version", "?")))
    path.with_suffix(".json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    return path, results


def _applied_row(s: Session, row: dict[str, Any], ex: EmailExample, request: EmailRequest,
                 language: str, app: Application | None, drafter: Any) -> dict[str, Any]:
    """One case in the job-linked mode: written again with the application follow-up prompt
    and checked with the applied rules (errors protect facts, everything else is a warning)."""
    from app.services import applied_check as ac
    from app.services import intro_check as ic
    from app.services import outreach
    from app.services import outreach_check as oc
    from app.services.cv_pool import load_pool

    plan = drafter.draft_applied(request)
    plan.greeting = ic.greeting_line(request.contact.get("first_name") or "", language)
    name = str(request.candidate.get("full_name") or "")
    text = ac.body(plan)
    subject = ac.subject_line(plan.role, name, language)
    found: list[dict] = []
    contact = case_contact(s, ex, app)
    if app is not None and contact is not None:
        job = s.get(Job, app.job_id)
        ctx = outreach.applied_context(s, app, job, s.get(Company, job.company_id), contact,
                                       load_pool(s), language=language)
        found = ac.check_plan(plan, ctx)
    row.update(new={"subject": subject, "body": text},
               errors=[v["message"] for v in found if v["severity"] == "error"],
               warnings=[v["message"] for v in found if v["severity"] != "error"],
               similarity_to_old=round(oc.similarity(text, ex.body), 2))
    return row


def render_md(results: list[dict], version: str) -> str:
    lines = [f"# Email eval · {version} · {datetime.now(UTC):%Y-%m-%d %H:%M} UTC", ""]
    for r in results:
        lines += [f"## Case {r['id']} · {r['kind']} · {r['company']} · {r['language']}", ""]
        if r.get("skipped"):
            lines += [f"_Skipped: {r['skipped']}_", ""]
            continue
        lines += ["| Old | New |", "|---|---|",
                  f"| **{r['old']['subject']}** | **{r['new']['subject']}** |",
                  f"| {_cell(r['old']['body'])} | {_cell(r['new']['body'])} |", "",
                  f"Similarity old/new: {r['similarity_to_old']}", ""]
        lines += ["Errors: " + ("; ".join(r["errors"]) if r["errors"] else "none"),
                  "Warnings: " + ("; ".join(r["warnings"]) if r["warnings"] else "none"), ""]
    return "\n".join(lines)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n\n", "<br><br>").replace("\n", "<br>")


def main() -> None:
    from app.db import engine
    from app.providers.registry import email_drafter

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import", dest="do_import", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case", type=int)
    parser.add_argument("--mock", action="store_true", help="the mock drafter (no Claude)")
    args = parser.parse_args()
    if args.do_import:
        print(f"Imported {import_examples(engine)} example(s) from {EXAMPLES_FILE}")
        return
    from app.api.outreach import _research_models
    from app.providers.registry import hook_checker

    drafter = email_drafter(mock=args.mock or None)
    with Session(engine) as s:
        model, fallback = _research_models(s)  # Settings → Models (research)
    checker = hook_checker(mock=args.mock or None, model=model, fallback=fallback)
    path, results = run_eval(engine, drafter, limit=args.limit, case=args.case,
                             hook_checker=checker)
    done = [r for r in results if not r.get("skipped")]
    print(f"{len(done)} case(s) written with {drafter.prompt_version}: {path}")
    for r in done:
        print(f"  #{r['id']} {r['kind']} {r['company']}: {len(r['errors'])} error(s)")


if __name__ == "__main__":
    main()
