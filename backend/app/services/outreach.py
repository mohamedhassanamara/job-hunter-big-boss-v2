"""Cold-email drafts: one job at a time, from the approved CV, checked before you see them.

The model only writes the subject, greeting, 2-4 sentences (with citations) and one ask. Code
checks them (services/outreach_check.py), retries once with the problems as feedback, then
stores the draft with anything still wrong highlighted; nothing is ever fixed silently. The
signature and the opt-out line come from Settings → Email and are added at preview/send time.
"""

import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import (
    Application,
    AppSetting,
    Company,
    Contact,
    CVVersion,
    Job,
    OutreachDraft,
    SendLog,
)
from app.models.base import utcnow
from app.models.enums import CVStatus, DraftStatus, EventKind, Route
from app.providers.base import (
    CVPlan,
    DraftFailed,
    EmailDrafter,
    EmailDraftPlan,
    EmailRequest,
    Mailer,
    OutgoingEmail,
    SendFailed,
)
from app.services import outreach_check as oc
from app.services import pipeline
from app.services.contacts import ranking_settings
from app.services.cv_claims import exact_statement
from app.services.cv_pool import Pool, load_pool, prompt_pool, years_facts

DEFAULT_OUTREACH: dict[str, Any] = {
    "signature": {"name": "", "title": "", "email": "", "phone": "", "photo_path": ""},
    "sign_off": "Best regards,",
    "opt_out": "If this isn't relevant for you, just let me know and I won't follow up.",
    "banned_phrases": oc.DEFAULT_BANNED,
    "max_words": oc.DEFAULT_MAX_WORDS,
    "language": "en",  # the CV and signature are in English; "auto" = the listing's language
}
_one_at_a_time = threading.Lock()


class OutreachError(ValueError):
    """Shown to the user (no approved CV, no email address, a draft already generating…)."""


def _setting(s: Session, key: str) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == key)).first()
    return dict(row.value) if row else {}


def outreach_settings(s: Session) -> dict[str, Any]:
    saved = _setting(s, "outreach")
    profile = _setting(s, "profile")
    out = {**DEFAULT_OUTREACH, **saved}
    sig = {**DEFAULT_OUTREACH["signature"], **(saved.get("signature") or {})}
    # Empty signature fields fall back to Settings → Candidate.
    sig["name"] = sig["name"] or profile.get("full_name", "")
    sig["email"] = sig["email"] or profile.get("email", "")
    sig["phone"] = sig["phone"] or profile.get("phone", "")
    headline = (profile.get("headline") or "").strip()
    sig["title"] = sig["title"] or (headline if len(headline) <= 60 else "")
    out["signature"] = sig
    return out


def approved_cv(s: Session, app: Application) -> CVVersion | None:
    return s.exec(select(CVVersion).where(CVVersion.application_id == app.id,
                                          CVVersion.status == CVStatus.approved)
                  .order_by(col(CVVersion.version).desc())).first()


def cv_pool_subset(pool: Pool, cv: CVVersion) -> dict[str, Any]:
    """The experience items that are on the CV being attached (what the email may cite)."""
    plan = CVPlan.model_validate((cv.plan or {}).get("plan") or {})
    ids = {e.item_id for e in [*plan.roles, *plan.projects, *plan.volunteering]}
    ids |= {g.item_id for g in plan.skills} | set(plan.certification_ids) | set(plan.education_ids)
    full = prompt_pool(pool)
    return {k: [e for e in v if e.get("id") in ids] for k, v in full.items()
            if k != "summary_snippets"}


def _first_name(contact: Contact) -> str:
    return contact.first_name or contact.full_name.split(" ")[0]


def _context(s: Session, app: Application, job: Job, company: Company, contact: Contact,
             pool: Pool, exclude_draft: int | None = None) -> oc.Context:
    from app.services.cv_service import _tracks

    cfg = outreach_settings(s)
    facts = years_facts(pool, _tracks(s))
    allowed = {int(f["years"]) for f in facts}
    others = []
    other_companies = set()
    for d, _app, _job, c, person in s.exec(
            select(OutreachDraft, Application, Job, Company, Contact)
            .join(Application, col(Application.id) == col(OutreachDraft.application_id))
            .join(Job, col(Job.id) == col(Application.job_id))
            .join(Company, col(Company.id) == col(Job.company_id))
            .join(Contact, col(Contact.id) == col(OutreachDraft.contact_id))
            .where(OutreachDraft.status != DraftStatus.rejected)).all():
        if d.id == exclude_draft or d.application_id == app.id:
            continue
        if person.id != contact.id:
            others.append((d.id, f"{person.full_name} ({c.name})", d.body))
        if c.id != company.id:
            other_companies.add(c.name)
    return oc.Context(
        pool=pool, allowed_years=allowed, job_text=f"{job.title}\n{job.description}",
        company=company.name, first_name=_first_name(contact),
        banned=list(cfg.get("banned_phrases") or []), max_words=int(cfg.get("max_words") or 150),
        other_companies=sorted(other_companies), others=others,
        years_statement=exact_statement(facts))


def build_request(s: Session, app: Application, job: Job, company: Company, contact: Contact,
                  cv: CVVersion, pool: Pool) -> EmailRequest:
    from app.services.cv_service import _tracks

    cfg = outreach_settings(s)
    profile = _setting(s, "profile")
    ranking = ranking_settings(s)
    return EmailRequest(
        job={"title": job.title, "company": company.name, "location": job.location,
             "description": (job.description or "")[:6000]},
        contact={"first_name": _first_name(contact), "full_name": contact.full_name,
                 "title": contact.title, "role_group": ranking.label(contact.role_rank)},
        candidate={"name": profile.get("full_name", ""), "based_in": profile.get("based_in", ""),
                   "work_authorization": profile.get("work_authorization", ""),
                   "years": years_facts(pool, _tracks(s))},
        pool=cv_pool_subset(pool, cv),
        rules={"max_words": int(cfg.get("max_words") or 150),
               "banned_phrases": list(cfg.get("banned_phrases") or []),
               "language": cfg.get("language") or "auto"},
    )


def body_text(plan: EmailDraftPlan) -> str:
    """Greeting, sentences and the ask (what you review and edit; no signature)."""
    return f"{plan.greeting}\n\n{' '.join(s.text for s in plan.sentences)}\n\n{plan.ask}"


def signature_block(cfg: dict[str, Any]) -> str:
    sig = cfg["signature"]
    lines = [cfg.get("sign_off") or "Best regards,", sig.get("name") or ""]
    if sig.get("title"):
        lines.append(sig["title"])
    reach = " · ".join(x for x in (sig.get("email"), sig.get("phone")) if x)
    if reach:
        lines.append(reach)
    return "\n".join(x for x in lines if x)


def full_body(s: Session, draft: OutreachDraft) -> str:
    """The email as it is sent: your text, the signature and the opt-out line."""
    cfg = outreach_settings(s)
    parts = [draft.body.strip(), signature_block(cfg)]
    if cfg.get("opt_out"):
        parts.append(cfg["opt_out"])
    return "\n\n".join(parts)


def generate(engine: Engine, app_id: int, drafter: EmailDrafter) -> OutreachDraft:
    """Draft the email for one job (never in bulk: one generation at a time)."""
    if not _one_at_a_time.acquire(blocking=False):
        raise OutreachError("Another email is being drafted; one at a time")
    try:
        with Session(engine) as s:
            app = s.get(Application, app_id)
            if app is None:
                raise OutreachError("Application not found")
            if app.contact_id is None:
                raise OutreachError("No contact for this job yet (see Contacts)")
            job, contact = s.get(Job, app.job_id), s.get(Contact, app.contact_id)
            company = s.get(Company, job.company_id)
            if not contact.email:
                raise OutreachError(f"{contact.full_name} has no email address")
            cv = approved_cv(s, app)
            if cv is None:
                raise OutreachError("Approve the CV first: the email is written from it and "
                                    "attaches it")
            pool = load_pool(s)
            request = build_request(s, app, job, company, contact, cv, pool)
            ctx = _context(s, app, job, company, contact, pool)
        started = time.monotonic()
        try:
            plan = drafter.draft(request)
            found = oc.check_plan(plan, ctx)
            attempts = 1
            if oc.errors(found):  # one retry with the problems as feedback
                retry = drafter.draft(request, oc.feedback(found))
                retry_found = oc.check_plan(retry, ctx)
                attempts = 2
                if len(oc.errors(retry_found)) <= len(oc.errors(found)):
                    plan, found = retry, retry_found
        except DraftFailed as exc:
            raise OutreachError(str(exc)) from exc
        with Session(engine) as s:
            app = s.get(Application, app_id)
            for old in s.exec(select(OutreachDraft).where(
                    OutreachDraft.application_id == app_id,
                    OutreachDraft.status == DraftStatus.draft)).all():
                old.status = DraftStatus.rejected  # regenerate replaces the draft under review
                s.add(old)
            draft = OutreachDraft(
                application_id=app_id, contact_id=app.contact_id, subject=plan.subject.strip(),
                body=body_text(plan), model=drafter.model, cv_version_id=cv.id,
                plan={"plan": plan.model_dump(), "attempts": attempts}, violations=found,
                prompt_version=drafter.prompt_version,
                duration_ms=int((time.monotonic() - started) * 1000))
            if app.route == Route.undecided:
                app.route = Route.cold_email
                s.add(app)
            s.add(draft)
            problems = len(oc.errors(found))
            pipeline.log_event(s, app, EventKind.draft_created,
                               f"Email draft created for {contact.full_name}"
                               + (f" ({problems} problems to review)" if problems else ""))
            s.commit()
            s.refresh(draft)
            return draft
    finally:
        _one_at_a_time.release()


def recheck(s: Session, draft: OutreachDraft) -> list[dict[str, str]]:
    """After you edit: text-level checks (citations no longer apply)."""
    app = s.get(Application, draft.application_id)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    contact = s.get(Contact, draft.contact_id) if draft.contact_id else None
    if contact is None:
        return []
    ctx = _context(s, app, job, company, contact, load_pool(s), exclude_draft=draft.id)
    return oc.check_text(draft.subject, draft.body, ctx)


# ----------------------------------------------------------------------------------- sending


def outgoing(s: Session, engine: Engine, draft: OutreachDraft, *, to: str | None = None,
             test: bool = False) -> OutgoingEmail:
    """The email exactly as it will go out, with the approved CV attached."""
    from app.services.cv_service import download_name, ensure_pdf

    cv = s.get(CVVersion, draft.cv_version_id) if draft.cv_version_id else None
    if cv is None or cv.status != CVStatus.approved:
        raise OutreachError("The CV this email was written from is no longer approved; "
                            "regenerate the email")
    pdf = ensure_pdf(engine, cv)
    if pdf is None:
        raise OutreachError("The CV PDF couldn't be rendered")
    contact = s.get(Contact, draft.contact_id) if draft.contact_id else None
    recipient = to or (contact.email if contact else None)
    if not recipient:
        raise OutreachError("No recipient email address")
    cfg = outreach_settings(s)
    body = full_body(s, draft)
    photo = (cfg["signature"].get("photo_path") or "").strip()
    html = None
    images: dict[str, str] = {}
    if photo and Path(photo).exists():
        import html as h

        paragraphs = "".join(f"<p>{h.escape(p).replace(chr(10), '<br>')}</p>"
                             for p in body.split("\n\n"))
        html = f'{paragraphs}<p><img src="cid:signature-photo" width="72" alt=""></p>'
        images["signature-photo"] = photo
    return OutgoingEmail(to=recipient, subject=("[TEST] " if test else "") + draft.subject,
                         body=body, html=html, attachment_path=str(pdf),
                         attachment_name=download_name(s, cv), inline_images=images)


def own_address(s: Session) -> str:
    return (_setting(s, "smtp").get("address") or _setting(s, "profile").get("email") or "")


def test_send(engine: Engine, draft_id: int, mailer: Mailer) -> SendLog:
    """Send this exact email to yourself (subject prefixed "[TEST]"). Nothing else changes."""
    with Session(engine) as s:
        draft = s.get(OutreachDraft, draft_id)
        if draft is None:
            raise OutreachError("Draft not found")
        to = own_address(s)
        if not to:
            raise OutreachError("Set your Gmail address in Settings → Email first")
        email = outgoing(s, engine, draft, to=to, test=True)
        log = SendLog(draft_id=draft.id, kind="test", to=to, subject=email.subject,
                      status="sent", attachment=email.attachment_name)
        try:
            log.message_id = mailer.send(email)
            draft.test_sent_at = utcnow()
            s.add(draft)
        except SendFailed as exc:
            log.status, log.error = "failed", str(exc)
        s.add(log)
        s.commit()
        s.refresh(log)
        return log


def has_successful_test(s: Session) -> bool:
    return s.exec(select(SendLog.id).where(SendLog.kind == "test",
                                           SendLog.status == "sent")).first() is not None
