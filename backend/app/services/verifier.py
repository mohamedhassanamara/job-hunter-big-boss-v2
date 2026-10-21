"""The claim verifier: zero tolerance for anything the sources don't say.

A second Claude call (`claude -p`, Opus by default; `providers/claude_verify.py`), separate from
the one that wrote the text. It receives only the final text (an email with its subject, a
LinkedIn note or follow-up, a cover letter, a form answer) and its sources:
- about you: your experience pool (item by item), the approved CV, FACTS (your name, the years
  wording, which tracks are professional and which are projects);
- about the company: the company signals with their quotes (and the listing for letters and
  form answers).
It splits the whole text into claims and judges each one. Code then checks the verifier itself:
a "supported" verdict whose quote isn't in the named source counts as unsupported, and every
sentence of the text must have been judged. Anything unsupported, exaggerated, merged or causal
blocks approval (emails, letters) or Copy (LinkedIn, form answers).

The code checks (`intro_check`, `letter_check`, `linkedin_check`) run first, as the fast pass.
A verification is tied to the exact text (and attachment) by hash: any change makes it stale.
"""

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, select

from app.models import (
    Application,
    ApplicationAnswer,
    CompanySignal,
    CoverLetter,
    CVVersion,
    Job,
    LinkedInOutreach,
    OutreachDraft,
)
from app.models.base import utcnow
from app.models.enums import CVStatus
from app.providers.base import DraftFailed, VerifyClaim
from app.services import glossary
from app.services.cv_pool import Pool, load_pool

BLOCKING = {"unsupported", "exaggerated", "merged", "causal"}
LABEL = {"unsupported": "isn't in your sources", "exaggerated": "says more than the source",
         "merged": "merges separate facts", "causal": "adds a cause the source doesn't state"}


DEFAULT_MODEL = "claude-opus-5-5"


def for_workspace(s: Session, workspace: str) -> Any:
    """The verifier to use: the mock in the sandbox (and tests), else Claude (Settings → Models
    `verifier.model`, Opus by default)."""
    from app.models import AppSetting
    from app.providers.registry import verifier

    row = s.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    model = (((row.value if row else {}) or {}).get("verifier") or {}).get("model") \
        or DEFAULT_MODEL
    return verifier(mock=True if workspace == "demo" else None, model=model)


class VerifyError(Exception):
    """Shown to the user: the text didn't pass, or the verifier couldn't run."""


def code_checks_first(violations: list[dict[str, Any]] | None) -> None:
    """The code checks are the fast first pass: Claude only sees a text that passes them."""
    errors = [v for v in violations or [] if v.get("severity") == "error"]
    if errors:
        raise VerifyError(f"Fix the {len(errors)} problem{'s' if len(errors) > 1 else ''} the "
                          f"checks found first: {errors[0]['message']}")


# ------------------------------------------------------------------------------- hashing


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def file_hash(path: str | None) -> str | None:
    if not path or not Path(path).exists():
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_current(record: dict[str, Any] | None, text: str,
               attachment_sha256: str | None = None) -> bool:
    """A passed verification of exactly this text (and attachment, when there is one)."""
    return bool(record) and record.get("status") == "passed" \
        and record.get("hash") == text_hash(text) \
        and (attachment_sha256 is None or record.get("attachment_sha256") == attachment_sha256)


def state(record: dict[str, Any] | None, text: str) -> str:
    """passed | failed | error | stale (verified, then the text changed) | none."""
    if not record:
        return "none"
    if record.get("hash") != text_hash(text):
        return "stale"
    return str(record.get("status") or "none")


# ------------------------------------------------------------------------------- sources


def _item_text(item: Any) -> str:
    head = " · ".join(x for x in (item.title, item.org,
                                  " – ".join(str(d) for d in (item.start_date, item.end_date) if d))
                      if x)
    lines = [f"{item.kind}: {head}"]
    if item.summary:
        lines.append(item.summary)
    lines += [f"- {b}" for b in item.bullets or []]
    if item.tags:
        lines.append("Tags: " + ", ".join(item.tags))
    return "\n".join(lines)


def candidate_sources(s: Session, pool: Pool, cv: CVVersion | None) -> dict[str, str]:
    from app.services import honesty
    from app.services.cover_letter import _statements
    from app.services.cv_fit import tailored_text

    _facts, english, french = _statements(s, pool)
    facts = honesty.prompt_facts(honesty.rules(s))
    lines = [f"Name: {pool.profile.get('full_name') or ''}",
             f"Years wording (English): {english or 'none'}",
             f"Years wording (French): {french or 'none'}",
             f"Years rule: {facts['years_rule']}"]
    lines += [f"Track {t['track']}: experience is {t['experience']}"
              + (f" ({t['how']})" if t.get("how") else "")
              for t in facts["experience_by_track"]]
    from app.services.outreach import logistics

    where = logistics(pool)
    if where["based_in"]:
        lines.append(f"Based in: {where['based_in']}")
    if where["work_authorization"]:
        lines.append(f"Work authorization: the candidate {where['work_authorization']}")
    if where["languages"]:
        lines.append(f"Languages the candidate works in: {where['languages']} (no other language "
                     "is claimed)")
    if where["relocation"]:
        lines.append(f"Relocation: the candidate is {where['relocation']}")
    if words := glossary.verifier_lines(pool.profile):
        lines.append(words)
    out = {"facts": "\n".join(lines)}
    out |= {f"pool:{item.id}": _item_text(item) for item in pool.items.values()
            if item.kind != "summary"}  # your own summary snippets aren't evidence
    if cv is not None and cv.content:
        out["cv"] = tailored_text(cv.content)
    return out


def signal_sources(s: Session, company_id: int, ids: list[int] | None = None) -> dict[str, str]:
    stmt = select(CompanySignal).where(CompanySignal.company_id == company_id)
    if ids is not None:
        stmt = stmt.where(col(CompanySignal.id).in_(ids or [-1]))
    else:
        stmt = stmt.where(col(CompanySignal.verified).is_(True))
    return {f"signal:{x.id}": f"{x.fact}\nQuote: {x.quote}\nPage: {x.source_url}"
            for x in s.exec(stmt).all()}


def recipient_source(s: Session, job: Job, contact_id: int | None = None) -> dict[str, str]:
    """Who the text is addressed to (names are facts too): the company, the job title, the
    contact's name and title."""
    from app.models import Company, Contact

    company = s.get(Company, job.company_id)
    lines = [f"Company: {company.name if company else ''}", f"Job title: {job.title}"]
    contact = s.get(Contact, contact_id) if contact_id else None
    if contact is not None:
        lines.append(f"Contact: {contact.full_name}" + (f", {contact.title}" if contact.title
                                                        else ""))
    return {"recipient": "\n".join(lines)}


def application_line(app: Application) -> str:
    """Whether the candidate has applied, as of now (Mark applied may have come after a draft)."""
    from app.services.outreach import application_facts

    facts = application_facts(app)
    return "\nApplication: " + (f"the candidate applied for this job on {facts['date']}"
                                if facts["applied"] else "the candidate is applying for this job")


def _approved_cv(s: Session, app_id: int) -> CVVersion | None:
    return s.exec(select(CVVersion).where(CVVersion.application_id == app_id,
                                          CVVersion.status == CVStatus.approved)
                  .order_by(col(CVVersion.version).desc())).first()


# ------------------------------------------------------------------------- the check


_SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n+")


def _norm(text: str) -> str:
    text = text.lower().translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"',
                                                 "–": "-", "—": "-", " ": " "}))
    return re.sub(r"\s+", " ", text).strip(" .")


def sentences(text: str) -> list[str]:
    return [x.strip() for x in _SENTENCE.split(text) if len(x.strip()) > 1]


def postcheck(claims: list[VerifyClaim], sources: dict[str, str],
              text: str) -> list[dict[str, Any]]:
    """Check the verifier: quotes must be in their source; every sentence must be judged."""
    out = []
    for c in claims:
        row = c.model_dump()
        if c.verdict == "supported":
            source = sources.get(c.source_id)
            if source is None or not c.source_quote.strip() \
                    or _norm(c.source_quote) not in _norm(source):
                row["verdict"] = "unsupported"
                row["reason"] = (f"Marked supported, but the quote isn't in {c.source_id or 'any '
                                 'source'}: treated as unsupported")
                row["quote_not_found"] = True
        out.append(row)
    judged = [_norm(c.sentence) for c in claims]
    for sentence in sentences(text):
        n = _norm(sentence)
        if n and not any(n in j or (j and j in n) for j in judged):
            out.append({"sentence": sentence, "claim": sentence, "about": "other",
                        "verdict": "unsupported", "source_id": "", "source_quote": "",
                        "reason": "The verifier didn't judge this sentence: not verified",
                        "skipped": True})
    return out


def run(verifier: Any, kind: str, text: str, sources: dict[str, str],
        attachment_sha256: str | None = None) -> dict[str, Any]:
    """One verification; never raises (a verifier that can't run gives status "error")."""
    started = time.monotonic()
    base = {"hash": text_hash(text), "attachment_sha256": attachment_sha256,
            "model": getattr(verifier, "model", None),
            "prompt_version": getattr(verifier, "prompt_version", None),
            "via": getattr(verifier, "via", None), "at": utcnow().isoformat(),
            "sources": sorted(sources)}
    try:
        plan = verifier.verify({"kind": kind, "text": text, "sources": sources})
    except DraftFailed as exc:
        return {**base, "status": "error", "error": str(exc)[:500], "claims": [],
                "duration_ms": int((time.monotonic() - started) * 1000)}
    claims = postcheck(plan.claims, sources, text)
    blocking = [c for c in claims if c["verdict"] in BLOCKING]
    return {**base, "status": "failed" if blocking else "passed", "claims": claims,
            "blocking": len(blocking), "auth": getattr(verifier, "auth_source", None),
            "duration_ms": int((time.monotonic() - started) * 1000)}


def problem(record: dict[str, Any]) -> str:
    """Why it can't go out, in one line."""
    if record.get("status") == "error":
        return f"The claim verifier couldn't run ({record.get('error')}): try again"
    bad = [c for c in record.get("claims") or [] if c["verdict"] in BLOCKING]
    first = bad[0] if bad else {}
    return (f"{'1 claim doesn' if len(bad) == 1 else f'{len(bad)} claims don'}'t hold: "
            f"“{first.get('claim', '')}” "
            f"{LABEL.get(first.get('verdict', ''), '')}"
            + (f" ({first['reason'].rstrip('.')})" if first.get("reason") else ""))


# ------------------------------------------------------------------- per document


def email_text(s: Session, draft: OutreachDraft) -> str:
    """Exactly what the recipient reads: the subject, then the body as sent (signature too)."""
    from app.services.outreach import full_body

    return f"Subject: {draft.subject}\n\n{full_body(s, draft)}"


def email_attachment(s: Session, draft: OutreachDraft) -> str | None:
    """The hash of the exact file sending attaches (the same `ensure_pdf` the send uses)."""
    from app.services import cv_service

    cv = s.get(CVVersion, draft.cv_version_id) if draft.cv_version_id else None
    if cv is None:
        return None
    pdf = cv_service.ensure_pdf(s.get_bind(), cv)
    return file_hash(str(pdf)) if pdf else None


def verify_email(s: Session, draft: OutreachDraft, verifier: Any) -> dict[str, Any]:
    app = s.get(Application, draft.application_id)
    job = s.get(Job, app.job_id)
    cv = s.get(CVVersion, draft.cv_version_id) if draft.cv_version_id else None
    plan = draft.plan or {}
    offered = [int(x["id"]) for x in plan.get("signals") or [] if x.get("id") is not None]
    ids = sorted(set(offered) | {x.id for x in s.exec(select(CompanySignal).where(
        CompanySignal.company_id == job.company_id,
        col(CompanySignal.selected).is_(True))).all()})
    sources = candidate_sources(s, load_pool(s), cv) | signal_sources(s, job.company_id, ids) \
        | recipient_source(s, job, draft.contact_id)
    kind = "cold email (with its subject)"
    if plan.get("format") == "applied":  # the follow-up names the job: the listing is a source
        sources["listing"] = f"{job.title}\n{job.description or ''}"
        sources["facts"] += application_line(app)
        kind = "email about a job application, to the person at the company (with its subject)"
    record = run(verifier, kind, email_text(s, draft), sources, email_attachment(s, draft))
    draft.verification = record
    s.add(draft)
    return record


def require_email(s: Session, draft: OutreachDraft, verifier: Any) -> dict[str, Any]:
    """Approval: reuse a passed verification of this exact text and CV, else verify now."""
    record = draft.verification
    if is_current(record, email_text(s, draft), email_attachment(s, draft)):
        return record
    record = verify_email(s, draft, verifier)
    if record["status"] != "passed":
        raise VerifyError(problem(record))
    return record


def send_gate(draft: OutreachDraft, subject: str, body: str,
              attachment_path: str | None) -> str | None:
    """Right before a queued email goes out: the exact text and attachment must be the ones
    approved and verified. Returns why not, or None when it may go."""
    record = draft.verification
    if not record or record.get("status") != "passed":
        return "It has no passed claim verification"
    if record.get("hash") != text_hash(f"Subject: {subject}\n\n{body}"):
        return "Its text changed since it was verified (the email, the subject or the signature)"
    if record.get("attachment_sha256") != file_hash(attachment_path):
        return "The attached CV changed since the email was verified"
    return None


def verify_linkedin(s: Session, row: LinkedInOutreach, kind: str,
                    verifier: Any) -> dict[str, Any]:
    message = dict({"note": row.note, "followup": row.followup, "inmail": row.inmail}[kind] or {})
    if not message.get("text"):
        raise VerifyError("Draft the message first")
    app = s.get(Application, row.application_id)
    job = s.get(Job, app.job_id)
    ids = [int(i) for i in message.get("signal_ids") or []]
    # The listing too: a note may name their opening (Settings rules for LinkedIn).
    sources = candidate_sources(s, load_pool(s), _approved_cv(s, app.id)) \
        | signal_sources(s, job.company_id, ids or None) \
        | {"listing": f"{job.title}\n{job.description or ''}"} \
        | recipient_source(s, job, row.contact_id)
    sources["facts"] += application_line(app)
    from app.services.linkedin_check import inmail_text

    label = {"note": "LinkedIn connection note", "followup": "LinkedIn follow-up",
             "inmail": "LinkedIn InMail (subject line, then body)"}[kind]
    record = run(verifier, label, inmail_text(message) if kind == "inmail" else message["text"],
                 sources)
    message["verification"] = record
    setattr(row, kind, message)
    s.add(row)
    return record


def letter_text(s: Session, letter: CoverLetter) -> str:
    from app.services.cover_letter import plain_text

    return plain_text(s, letter)


def verify_letter(s: Session, letter: CoverLetter, verifier: Any) -> dict[str, Any]:
    app = s.get(Application, letter.application_id)
    job = s.get(Job, app.job_id)
    cv = s.get(CVVersion, letter.cv_version_id) if letter.cv_version_id else \
        _approved_cv(s, app.id)
    sources = candidate_sources(s, load_pool(s), cv) | signal_sources(s, job.company_id) \
        | {"listing": f"{job.title}\n{job.description or ''}"} | recipient_source(s, job)
    kind = "cover letter" if (letter.format or "pdf") == "pdf" else "text for an application form"
    record = run(verifier, kind, letter_text(s, letter), sources)
    letter.verification = record
    s.add(letter)
    return record


def require_letter(s: Session, letter: CoverLetter, verifier: Any) -> dict[str, Any]:
    record = letter.verification
    if is_current(record, letter_text(s, letter)):
        return record
    record = verify_letter(s, letter, verifier)
    if record["status"] != "passed":
        raise VerifyError(problem(record))
    return record


def interview_text(prep: Any) -> str:
    from app.services.interview_prep import plain_text

    return plain_text(prep.content or {})


def verify_interview_prep(s: Session, prep: Any, verifier: Any) -> dict[str, Any]:
    """Everything the candidate would say aloud (pitch and STAR parts) against the pool, the facts
    and the listing, sentence by sentence."""
    app = s.get(Application, prep.application_id)
    job = s.get(Job, app.job_id)
    sources = candidate_sources(s, load_pool(s), _approved_cv(s, app.id)) \
        | {"listing": f"{job.title}\n{job.description or ''}"}
    record = run(verifier, "interview preparation (what the candidate would say aloud)",
                 interview_text(prep), sources)
    prep.verification = record
    s.add(prep)
    return record


def require_interview_prep(s: Session, prep: Any, verifier: Any) -> dict[str, Any]:
    record = prep.verification
    if is_current(record, interview_text(prep)):
        return record
    record = verify_interview_prep(s, prep, verifier)
    if record["status"] != "passed":
        raise VerifyError(problem(record))
    return record


def verify_answer(s: Session, answer: ApplicationAnswer, verifier: Any) -> dict[str, Any]:
    if not answer.answer.strip():
        raise VerifyError("Write the answer first")
    app = s.get(Application, answer.application_id)
    job = s.get(Job, app.job_id)
    sources = candidate_sources(s, load_pool(s), _approved_cv(s, app.id)) \
        | signal_sources(s, job.company_id) \
        | {"listing": f"{job.title}\n{job.description or ''}"}
    record = run(verifier, f"answer to the application question “{answer.question}”",
                 answer.answer, sources)
    answer.verification = record
    s.add(answer)
    return record
