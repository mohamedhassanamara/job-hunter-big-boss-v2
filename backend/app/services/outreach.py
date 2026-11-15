"""Cold-email drafts: one job at a time, from the approved CV, checked before you see them.

The model only writes the subject, greeting, 2-4 sentences (with citations) and one ask. Code
checks them (services/outreach_check.py), retries once with the problems as feedback, then
stores the draft with anything still wrong highlighted; nothing is ever fixed silently. The
signature and the opt-out line come from Settings → Email and are added at preview/send time.
"""

import re
import threading
import time
from datetime import datetime
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
from app.models.enums import ApplyMethod, CVStatus, DraftStatus, EventKind, Route
from app.providers.base import (
    CVPlan,
    DraftFailed,
    EmailDrafter,
    EmailDraftPlan,
    EmailRequest,
    HookSentence,
    Mailer,
    OutgoingEmail,
    SendFailed,
)
from app.services import applied_check as ac
from app.services import get_contact, pipeline, visibility
from app.services import intro_check as ic
from app.services import outreach_check as oc
from app.services.contacts import ranking_settings
from app.services.cv_check import violation
from app.services.cv_claims import exact_statement
from app.services.cv_pool import Pool, load_pool, prompt_pool, years_facts

DEFAULT_OUTREACH: dict[str, Any] = {
    # The signature ends with your name; the contact line (title, email, LinkedIn) is opt-in:
    # nothing is attached, so the signature carries your links.
    "signature": {"name": "", "title": "", "email": "", "phone": "", "photo_path": "",
                  "linkedin": "", "show_phone": False, "show_contacts": False},
    "sign_off": "Best regards,",
    "opt_out": "",  # an optional last line after the signature (empty: none)
    # French emails (the language follows the listing).
    "sign_off_fr": "Bien cordialement,",
    "opt_out_fr": "",
    "banned_phrases": oc.DEFAULT_BANNED,
    "max_words": oc.DEFAULT_MAX_WORDS,
    "language": "auto",  # "auto" = the listing's language (French listing → French email)
    # Approving an email also adds it to the send queue (Remove from queue undoes it).
    "approve_adds_to_queue": True,
    # Added by code (never the model) when you already applied on the website; {date} = that day.
    "application_mention": {
        "en": "I have also applied through your careers page on {date}.",
        "fr": "J'ai également postulé via votre site carrières le {date}.",
    },
}
_one_at_a_time = threading.Lock()
# "applied": the job-linked email, an honest application follow-up (prompt v11). "speculative":
# the research-based introduction, for a company with no posting (the older structure).
EMAIL_MODES = ("applied", "speculative")


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
    linkedin = next((x.get("url") for x in profile.get("links") or []
                     if x.get("type") == "linkedin" and x.get("url")), "")
    sig["linkedin"] = sig.get("linkedin") or linkedin
    headline = (profile.get("headline") or "").strip()
    sig["title"] = sig["title"] or (headline if len(headline) <= 60 else "")
    out["signature"] = sig
    return out


def approved_cv(s: Session, app: Application) -> CVVersion | None:
    return s.exec(select(CVVersion).where(CVVersion.application_id == app.id,
                                          CVVersion.status == CVStatus.approved)
                  .order_by(col(CVVersion.version).desc())).first()


def cv_pool_subset(pool: Pool, cv: CVVersion) -> dict[str, Any]:
    """The experience items that are on the CV the email is written from (what it may cite)."""
    plan = CVPlan.model_validate((cv.plan or {}).get("plan") or {})
    ids = {e.item_id for e in [*plan.roles, *plan.projects, *plan.volunteering]}
    ids |= {g.item_id for g in plan.skills} | set(plan.certification_ids) | set(plan.education_ids)
    full = prompt_pool(pool)
    return {k: [e for e in v if e.get("id") in ids] for k, v in full.items()
            if k != "summary_snippets"}


def language_choice(s: Session, job: Job, app: Application | None = None,
                    override: str | None = None) -> Any:
    """The language to write in and why (services/language.py): your explicit choice (the draft's
    dropdown, the job's language setting, Settings → Email), else the listing's language when you
    speak it at a working level and the app can write it, else English."""
    from app.services import language

    return language.choose(
        f"{job.title}\n{job.description or ''}", _setting(s, "profile"),
        setting=outreach_settings(s).get("language") or "auto",
        job_setting=(app.letter_language if app else None) or "auto", override=override)


def email_language(s: Session, job: Job, app: Application | None = None,
                   override: str | None = None) -> str:
    return str(language_choice(s, job, app, override).language)


def email_mode(job: Job, requested: str | None = None) -> str:
    """Which email to write: an application follow-up when there is a posting, else the
    speculative introduction. `requested` (the API's `mode`) wins when valid."""
    if requested in EMAIL_MODES:
        return str(requested)
    return "applied" if (job.description or "").strip() or job.url or job.apply_url \
        else "speculative"


PORTAL_METHODS = (ApplyMethod.company_site, ApplyMethod.job_board, ApplyMethod.linkedin)


def applied_gate(s: Session, app: Application, job: Job | None = None) -> str | None:
    """Portal first: an email about a job with a posting is drafted and approved only after the
    application went in through the company site, a job board or LinkedIn (Mark applied). None
    when it may go on; else the message to show. A job without a posting has no gate."""
    job = job or s.get(Job, app.job_id)
    if job is None or email_mode(job) != "applied":
        return None
    if app.web_applied_at is None:
        return ("Apply through the portal first, then mark the job applied: the email follows "
                "an application, it never replaces one")
    if app.web_method not in PORTAL_METHODS:
        return ("The email follows an application made on the company site, a job board or "
                "LinkedIn: this one was not")
    return None


def draft_gate(s: Session, draft: OutreachDraft) -> str | None:
    """`applied_gate` for a draft written in the applied format (speculative has none)."""
    if (draft.plan or {}).get("format") != "applied":
        return None
    app = s.get(Application, draft.application_id)
    return applied_gate(s, app) if app is not None else None


def source_cv(s: Session, app: Application) -> CVVersion | None:
    """The CV the proof sentences come from: the one the application was sent with, else the
    newest approved one. It is attached to the email."""
    if app.applied_cv_version_id:
        cv = s.get(CVVersion, app.applied_cv_version_id)
        if cv is not None:
            return cv
    return approved_cv(s, app)


def application_mention(s: Session, app: Application) -> str | None:
    """"I have also applied through your careers page on 30 September." once Mark applied is
    recorded (both routes); None before that. The wording is Settings → Email's, per language."""
    if app.web_applied_at is None:
        return None
    from app.services.cover_letter import MONTHS

    job = s.get(Job, app.job_id)
    lang = email_language(s, job, app)
    cfg = outreach_settings(s).get("application_mention") or DEFAULT_OUTREACH["application_mention"]
    template = cfg.get(lang) or cfg.get("en") or ""
    day = app.web_applied_at
    months = MONTHS.get(lang, MONTHS["en"])
    return template.format(date=f"{day.day} {months[day.month - 1]}") if template else None


def with_mention(body: str, mention: str) -> str:
    """The sentence ends the body's middle paragraph (before the ask)."""
    parts = body.split("\n\n")
    if len(parts) >= 3:
        parts[-2] = f"{parts[-2].rstrip()} {mention}"
        return "\n\n".join(parts)
    return f"{body.rstrip()}\n\n{mention}"


def without_mention(body: str, mention: str) -> str:
    return body.replace(f" {mention}", "").replace(f"\n\n{mention}", "").replace(mention, "")


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
    from app.services import cover_letter as cl

    job_text = f"{job.title}\n{job.description}"
    allowed_auth = cl.mention_authorization(s, job_text)
    role = cl.current_role(pool, job_text)
    reason = (app.company_reason or "").strip()
    return oc.Context(
        facts_text=cl._facts_text(pool, allowed_auth, reason), mention_authorization=allowed_auth,
        company_reason=reason, current_role_id=role.id if role else None,
        current_role_org=(role.org or "") if role else "",
        pool=pool, allowed_years=allowed, job_text=job_text,
        company=company.name, first_name=_first_name(contact),
        banned=list(cfg.get("banned_phrases") or []), max_words=int(cfg.get("max_words") or 150),
        other_companies=sorted(other_companies), others=others,
        years_statement=exact_statement(facts),
        fixed_sentences=[m] if (m := application_mention(s, app)) else [])


def build_request(s: Session, app: Application, job: Job, company: Company, contact: Contact,
                  cv: CVVersion, pool: Pool) -> EmailRequest:
    from app.services import cover_letter as cl
    from app.services.cv_service import _tracks

    cfg = outreach_settings(s)
    profile = _setting(s, "profile")
    ranking = ranking_settings(s)
    job_text = f"{job.title}\n{job.description or ''}"
    role = cl.current_role(pool, job_text)
    return EmailRequest(
        job={"title": job.title, "clean_title": ac.clean_job_title(job.title),
             "company": company.name, "location": job.location,
             "description": (job.description or "")[:6000]},
        contact={"first_name": _first_name(contact), "full_name": contact.full_name,
                 "title": contact.title, "role_group": ranking.label(contact.role_rank)},
        candidate={"name": profile.get("full_name", ""),
                   "first_name": (profile.get("full_name", "") or "").split(" ")[0],
                   "company_reason": (app.company_reason or "").strip() or None,
                   "current_role": {"id": role.id, "title": role.title, "org": role.org}
                   if role else None,
                   "years": years_facts(pool, _tracks(s))},
        pool=cv_pool_subset(pool, cv),
        rules={"max_words": int(cfg.get("max_words") or 150),
               "banned_phrases": list(cfg.get("banned_phrases") or []),
               "language": email_language(s, job, app),
               "jargon": list(_letter_jargon(s))},
    )


def _letter_jargon(s: Session) -> list[str]:
    from app.services.cover_letter import letter_settings

    return letter_settings(s).get("jargon") or []


def body_text(plan: EmailDraftPlan) -> str:
    """Greeting, sentences and the ask (what you review and edit; no signature)."""
    return f"{plan.greeting}\n\n{' '.join(s.text for s in plan.sentences)}\n\n{plan.ask}"


def _display_link(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (url or "").strip()).rstrip("/")


def candidate_links(cfg: dict[str, Any], profile_links: list[dict[str, Any]]) -> str:
    """"<portfolio> · <github> · <linkedin>" from Settings → Candidate links (LinkedIn may be
    overridden in Settings → Email). Only the ones that are set."""
    def first(kind: str) -> str:
        return next((x.get("url") for x in profile_links
                     if x.get("type") == kind and x.get("url")), "")

    linkedin = cfg["signature"].get("linkedin") or first("linkedin")
    urls = [first("portfolio"), first("github"), linkedin]
    return " · ".join(_display_link(u) for u in urls if u)


def signature_block(cfg: dict[str, Any], language: str = "en",
                    links: str = "", show_phone: bool = True) -> str:
    """Sign-off, your name, then your links on one line (the only attachment is the CV, so
    the links live here). Title, email and phone are opt-in (Settings → Email). `show_phone`
    is the document-wide switch (Settings → Candidate → Visibility): it can only hide the phone,
    never reveal one the email settings keep off."""
    sig = cfg["signature"]
    sign_off = (cfg.get("sign_off_fr") if language == "fr" else None) or cfg.get("sign_off") \
        or "Best regards,"
    lines = [sign_off, sig.get("name") or "", links]
    if not sig.get("show_contacts"):
        return "\n".join(x for x in lines if x)
    if sig.get("title"):
        lines.append(sig["title"])
    # The phone number reveals the country code: off unless you turn it on (Settings → Email).
    phone = sig.get("phone") if sig.get("show_phone") and show_phone else ""
    reach = " · ".join(x for x in (sig.get("email"), phone) if x)
    if reach:
        lines.append(reach)
    return "\n".join(x for x in lines if x)


def full_body(s: Session, draft: OutreachDraft) -> str:
    """The email as it is sent: your text and the signature (plus your last line, if set)."""
    cfg = outreach_settings(s)
    language = (draft.plan or {}).get("language") or "en"
    links = candidate_links(cfg, _setting(s, "profile").get("links") or [])
    parts = [draft.body.strip(),
             signature_block(cfg, language, links, visibility.load(s)["show_phone"])]
    opt_out = (cfg.get("opt_out_fr") if language == "fr" else None) or cfg.get("opt_out")
    if opt_out:
        parts.append(opt_out)
    return "\n\n".join(parts)


def revision_of(s: Session, app_id: int, base_draft_id: int | None) -> OutreachDraft | None:
    """The draft a regeneration edits: the one you name, else the draft under review."""
    if base_draft_id:
        base = s.get(OutreachDraft, base_draft_id)
        return base if base and base.application_id == app_id else None
    return s.exec(select(OutreachDraft).where(
        OutreachDraft.application_id == app_id, OutreachDraft.status == DraftStatus.draft)
        .order_by(col(OutreachDraft.id).desc())).first()


def _sticky_language(base: OutreachDraft | None, language: str | None) -> str | None:
    """A language you picked for a draft stays for its regenerations until you pick another."""
    if language or base is None:
        return language
    choice = (base.plan or {}).get("language_choice") or {}
    return choice.get("language") if choice.get("source") == "override" else None


def generate(engine: Engine, app_id: int, drafter: EmailDrafter, *, researcher: Any = None,
             fetcher: Any = None, progress: Any = None, hook_checker: Any = None,
             mode: str | None = None, language: str | None = None, feedback: str = "",
             base_draft_id: int | None = None, persona: str | None = None,
             scenario: str | None = None) -> OutreachDraft:
    """Draft the email for one job (never in bulk: one generation at a time). A job with a
    posting gets the application follow-up (prompt v11 `applied`, no research started); a
    speculative email (`mode`, or a company with no posting) researches the company first
    (prompt v4+: Claude, the mock). The older reply-style path remains for the send-queue
    tests."""
    with Session(engine) as s:
        app = s.get(Application, app_id)
        job = s.get(Job, app.job_id) if app else None
        base = revision_of(s, app_id, base_draft_id) if (feedback or base_draft_id) else None
        base_id = base.id if base else None
        if mode is None and base is not None:  # regenerating keeps the draft's own mode
            mode = (base.plan or {}).get("mode")
        language = None if language == "auto" else _sticky_language(
            revision_of(s, app_id, None), language)  # "auto" clears a language you picked
        chosen = email_mode(job, mode) if job else "speculative"
    options = {"language": language, "feedback": feedback.strip(), "base_draft_id": base_id}
    if hasattr(drafter, "draft_applied") and chosen == "applied":
        return generate_applied(engine, app_id, drafter, progress=progress, persona=persona,
                                scenario=scenario, **options)
    if hasattr(drafter, "draft_intro"):
        return generate_intro(engine, app_id, drafter, researcher=researcher, fetcher=fetcher,
                              progress=progress, hook_checker=hook_checker, **options)
    if not _one_at_a_time.acquire(blocking=False):
        raise OutreachError("Another email is being drafted; one at a time")
    try:
        with Session(engine) as s:
            app = s.get(Application, app_id)
            if app is None:
                raise OutreachError("Application not found")
            try:  # the Get contact step: a verified contact first (so no research before it)
                get_contact.require_ready(s, app)
            except get_contact.GetContactError as exc:
                raise OutreachError(str(exc)) from exc
            job, contact = s.get(Job, app.job_id), s.get(Contact, app.contact_id)
            company = s.get(Company, job.company_id)
            if not contact.email:
                raise OutreachError(f"{contact.full_name} has no email address")
            cv = approved_cv(s, app)
            if cv is None:
                raise OutreachError("Approve the CV first: the email is written from it")
            pool = load_pool(s)
            request = build_request(s, app, job, company, contact, cv, pool)
            ctx = _context(s, app, job, company, contact, pool)
            mention = application_mention(s, app)
            if mention:
                ctx.extra_words = len(oc.words(mention))
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
            body = body_text(plan)
            if mention:
                body = with_mention(body, mention)
            draft = OutreachDraft(
                application_id=app_id, contact_id=app.contact_id, subject=plan.subject.strip(),
                body=body, model=drafter.model, cv_version_id=cv.id,
                plan={"delivery": "cv", "plan": plan.model_dump(), "attempts": attempts,
                      "application_mention": mention,
                      "language": request.rules.get("language"),
                      "via": getattr(drafter, "via", "mock"),
                      "auth": getattr(drafter, "auth_source", None)}, violations=found,
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


def generate_intro(engine: Engine, app_id: int, drafter: EmailDrafter, *, researcher: Any = None,
                   fetcher: Any = None, progress: Any = None, hook_checker: Any = None,
                   language: str | None = None, feedback: str = "",
                   base_draft_id: int | None = None) -> OutreachDraft:
    """The email draft step: research the company (fresh signals are reused: no fetch, no model
    call), then write the introduction from the selected signals and your pool. Each attempt's
    hook is checked against the signals it cites (hook_check: one model call)."""
    from app.services import hook_check, research

    progress = progress or (lambda *_: None)
    if not _one_at_a_time.acquire(blocking=False):
        raise OutreachError("Another email is being drafted; one at a time")
    try:
        with Session(engine) as s:
            app = s.get(Application, app_id)
            if app is None:
                raise OutreachError("Application not found")
            try:  # the Get contact step: a verified contact first (so no research before it)
                get_contact.require_ready(s, app)
            except get_contact.GetContactError as exc:
                raise OutreachError(str(exc)) from exc
            job, contact = s.get(Job, app.job_id), s.get(Contact, app.contact_id)
            company = s.get(Company, job.company_id)
            if not contact.email:
                raise OutreachError(f"{contact.full_name} has no email address")
            cv = approved_cv(s, app)
            if cv is None:
                raise OutreachError("Approve the CV first: the email is written from it")
            choice = language_choice(s, job, app, language)
            language = choice.language
            company_id = company.id
        research_note, run_id = None, None
        if researcher is not None:
            try:
                outcome = research.ensure(engine, company_id, trigger="draft",
                                          researcher=researcher, fetcher=fetcher,
                                          language=language, progress=progress)
                run_id = outcome.run.id
            except research.ResearchError as exc:
                research_note = str(exc)  # the draft still happens; the hook then needs a signal
        progress("drafting", 0, 1)
        with Session(engine) as s:
            app = s.get(Application, app_id)
            job, contact = s.get(Job, app.job_id), s.get(Contact, app.contact_id)
            company = s.get(Company, job.company_id)
            pool = load_pool(s)
            request = intro_request(s, app, job, company, contact, cv, pool, language)
            base = s.get(OutreachDraft, base_draft_id) if base_draft_id else None
            add_revision(request, base, feedback)
            first = request.candidate["first_name"] or "I"
            english, french = request.candidate["years_statement"], \
                request.candidate["years_statement_fr"]

            def checked(plan: Any) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
                plan.greeting = ic.greeting_line(request.contact["first_name"], language)
                plan.subject = ac.speculative_subject(job.title, company.name, language)  # code
                intro = ic.intro_line(first, plan.intro_focus, language, english, french)
                ctx = intro_context(s, app, job, company, contact, pool, language=language,
                                    intro=intro)
                review = hook_check.check(hook_checker, plan.hook.text,
                                          cited_signals(s, company.id, plan.hook.signal_ids))
                return intro, ic.check_plan(plan, ctx) + hook_check.violations(review), review

            started = time.monotonic()
            try:
                plan = drafter.draft_intro(request)
                intro, found, review = checked(plan)
                attempts = 1
                fixable = [v for v in oc.errors(found) if v["type"] != "needs_signal"]
                if fixable:  # one retry with the problems as feedback
                    retry = drafter.draft_intro(request, oc.feedback(fixable))
                    retry_intro, retry_found, retry_review = checked(retry)
                    attempts = 2
                    review["superseded"] = True
                    if len(oc.errors(retry_found)) <= len(oc.errors(found)):
                        plan, intro, found, review = retry, retry_intro, retry_found, \
                            retry_review
            except DraftFailed as exc:
                raise OutreachError(str(exc)) from exc
            for old in s.exec(select(OutreachDraft).where(
                    OutreachDraft.application_id == app_id,
                    OutreachDraft.status == DraftStatus.draft)).all():
                old.status = DraftStatus.rejected  # regenerate replaces the draft under review
                s.add(old)
            signals = request.rules.get("signals") or []
            draft = OutreachDraft(
                application_id=app_id, contact_id=app.contact_id, subject=plan.subject.strip(),
                body=ic.body(plan, intro), model=drafter.model, cv_version_id=cv.id,
                parent_id=base.id if base else None, feedback=feedback,
                plan={"delivery": "cv", "format": "intro", "mode": "speculative",
                      "plan": plan.model_dump(),
                      "attempts": attempts, "intro_line": intro, "language": language,
                      "language_choice": choice.as_dict(),
                      "signal_ids": plan.hook.signal_ids, "signals": signals,
                      "research_run_id": run_id, "research_note": research_note,
                      "hook_check": review, "name_source": request.contact.get("name_source"),
                      "request": request.model_dump(),
                      "via": getattr(drafter, "via", "mock"),
                      "auth": getattr(drafter, "auth_source", None)},
                violations=found, prompt_version=drafter.prompt_version,
                duration_ms=int((time.monotonic() - started) * 1000))
            if app.route == Route.undecided:
                app.route = Route.cold_email
                s.add(app)
            s.add(draft)
            problems = len(oc.errors(found))
            pipeline.log_event(s, app, EventKind.draft_created,
                               f"Email draft created for {contact.full_name}"
                               + (f" ({problems} problem{'s' if problems > 1 else ''} to "
                                  "review)" if problems else ""))
            s.commit()
            s.refresh(draft)
            progress("done", 1, 1)
            return draft
    finally:
        _one_at_a_time.release()


def draft_history(s: Session, app_id: int) -> list[dict[str, Any]]:
    """Every version of this application's email, newest first, with the feedback that made it."""
    rows = s.exec(select(OutreachDraft).where(OutreachDraft.application_id == app_id)
                  .order_by(col(OutreachDraft.id).desc())).all()
    total = len(rows)
    out = []
    for n, d in enumerate(rows):
        plan = d.plan or {}
        out.append({
            "id": d.id, "version": total - n, "status": str(d.status), "created_at": d.created_at,
            "subject": d.subject, "words": len(d.body.split()), "feedback": d.feedback or "",
            "parent_id": d.parent_id, "mode": plan.get("mode"), "language": plan.get("language"),
            "source": plan.get("source") or "generated", "prompt_version": d.prompt_version,
            "unverified": bool(d.unverified_approval),
            "current": d.status in (DraftStatus.draft, DraftStatus.approved, DraftStatus.queued,
                                    DraftStatus.sent)})
    return out


def recheck(s: Session, draft: OutreachDraft) -> list[dict[str, str]]:
    """After you edit: text-level checks (citations no longer apply)."""
    app = s.get(Application, draft.application_id)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    contact = s.get(Contact, draft.contact_id) if draft.contact_id else None
    if contact is None:
        return []
    if (draft.plan or {}).get("format") == "applied":
        ctx = applied_context(s, app, job, company, contact, load_pool(s),
                              language=draft.plan.get("language") or "en",
                              exclude_draft=draft.id)
        guided = (draft.plan or {}).get("guidance") or {}
        detail = guided.get("scenario_detail") or {}
        ctx.scenario = guided.get("scenario") or "direct"  # what the draft was written for
        if detail.get("required_years"):
            ctx.required_years = {int(detail["required_years"])}
        if ctx.scenario == "stack_pivot":
            ctx.target_stack = detail.get("target_stack") or ""
        return ac.check_text(draft.subject, draft.body, ctx)
    if (draft.plan or {}).get("format") == "intro":
        from app.services import hook_check

        intro = draft.plan.get("intro_line") or ""
        ctx = intro_context(s, app, job, company, contact, load_pool(s),
                            language=draft.plan.get("language") or "en", intro=intro,
                            exclude_draft=draft.id)
        stored = draft.plan.get("hook_check")
        if stored and stored.get("hash") == hook_check.fingerprint(ic.hook_paragraph(
                draft.body, intro)):
            hook = hook_check.violations(stored)  # the hook is as it was checked
        else:
            hook = [violation("hook_edited", ("The hook changed since it was checked"
                              if stored else "The hook hasn't been checked against the signals "
                              "yet") + ": it's checked when you approve", "hook")]
        return ic.check_text(draft.subject, draft.body, ctx) + hook
    ctx = _context(s, app, job, company, contact, load_pool(s), exclude_draft=draft.id)
    return oc.check_text(draft.subject, draft.body, ctx)


# ------------------------------------------------------- the introduction email (prompt v4+)


def _places(pool: Pool) -> list[str]:
    """Where you are and your nationality, in the words an email could use (never allowed)."""
    from app.services.geo import COUNTRY_ALIASES, country_from_text

    p = pool.profile
    out = [x.strip() for x in (p.get("based_in") or "").split(",") if x.strip()]
    if code := country_from_text(p.get("based_in")):
        out += COUNTRY_ALIASES.get(code, [])
    nationality = (p.get("nationality") or "").strip()
    if nationality:
        out += [nationality, nationality.lower().replace("ian", "ien")]
    return sorted({x for x in out if len(x) >= 3})


def honesty_rules(s: Session) -> Any:
    from app.services import honesty

    return honesty.rules(s)


def reference_examples(s: Session) -> list[tuple[str, str]]:
    from app.models import EmailExample

    return [(f"{e.kind} #{e.id}", f"{e.subject}\n{e.body}") for e in s.exec(
        select(EmailExample).where(col(EmailExample.kind).in_(
            ["reference_good", "reference_bad"]))).all()
        if (e.inputs or {}).get("channel") != "linkedin"]  # LinkedIn notes: their own set


def applied_references(s: Session) -> list[str]:
    """Style references for the application follow-up (kind `style_reference`, mode applied):
    the level of detail to aim for, never wording to reuse (the copy check flags a draft that
    does). A kind of their own, so the intro examples and the verifier eval never see them."""
    from app.models import EmailExample

    return [e.body.strip() for e in s.exec(select(EmailExample).where(
        EmailExample.kind == "style_reference").order_by(col(EmailExample.id))).all()
        if (e.inputs or {}).get("mode") == "applied" and e.body.strip()]


def email_first_name(s: Session, company_id: int, contact: Contact) -> tuple[str,
                                                                          dict | None]:
    """The contact's first name for the greeting: as the company's researched pages spell it
    when they name them with accents (Stéphane vs Stephane), otherwise the contact record's."""
    from app.services import research

    name = _first_name(contact)
    found = research.name_on_pages(s, company_id, name, contact.full_name)
    return (found["first_name"], found) if found else (name, None)


def cited_signals(s: Session, company_id: int, ids: list[int]) -> dict[int, str]:
    """The hook's cited signals as the hook check reads them: fact and source quote."""
    from app.services import research

    return {x.id: f"{x.fact} (source: “{x.quote}”)" for x in research.signals(
        s, company_id, selected_only=True) if x.id in set(ids)}


def ensure_hook_checked(s: Session, draft: OutreachDraft, checker: Any) -> None:
    """Before approval: check the hook again when you edited it since the last check (or it was
    never checked), and store the result and the violations on the draft."""
    from app.services import hook_check

    plan = dict(draft.plan or {})
    if plan.get("format") != "intro":
        return
    hook = ic.hook_paragraph(draft.body, plan.get("intro_line") or "")
    stored = plan.get("hook_check")
    if stored and stored.get("hash") == hook_check.fingerprint(hook) \
            and stored.get("status") == "ok":
        return
    app = s.get(Application, draft.application_id)
    job = s.get(Job, app.job_id)
    # After your edits the citations may no longer hold: every selected signal is a source.
    signals = cited_signals(s, job.company_id, list(selected_signals(s, job.company_id)))
    plan["hook_check"] = hook_check.check(checker, hook, signals)
    draft.plan = plan
    draft.violations = recheck(s, draft)


def selected_signals(s: Session, company_id: int) -> dict[int, str]:
    from app.services import research

    return {x.id: f"{x.fact} {x.quote}" for x in research.signals(s, company_id,
                                                                 selected_only=True)}


def intro_context(s: Session, app: Application, job: Job, company: Company, contact: Contact,
                  pool: Pool, *, language: str, intro: str,
                  exclude_draft: int | None = None) -> ic.Context:
    from app.services.cover_letter import _statements, letter_settings

    base = _context(s, app, job, company, contact, pool, exclude_draft)
    _facts, english, french = _statements(s, pool)
    return ic.Context(
        pool=pool, allowed_years=base.allowed_years, job_title=job.title,
        job_text=f"{job.title}\n{job.description or ''}", company=company.name,
        first_name=email_first_name(s, company.id, contact)[0],
        signals=selected_signals(s, company.id),
        intro_line=intro, language=language, years_statement=english,
        years_statement_fr=french, banned=base.banned + list(
            letter_settings(s)["banned_phrases"].get(language) or []),
        jargon=list(letter_settings(s).get("jargon") or []), places=_places(pool),
        examples=reference_examples(s), others=base.others, honesty=honesty_rules(s),
        other_companies=base.other_companies)


def intro_request(s: Session, app: Application, job: Job, company: Company, contact: Contact,
                  cv: CVVersion, pool: Pool, language: str) -> EmailRequest:
    from app.services import research
    from app.services.cover_letter import _statements
    from app.services.cv_service import _tracks

    request = build_request(s, app, job, company, contact, cv, pool)
    first_name, source = email_first_name(s, company.id, contact)
    request.contact["first_name"] = first_name
    if source:
        request.contact["name_source"] = source
    _facts, english, french = _statements(s, pool)
    from app.services import honesty

    hr = honesty.rules(s)
    projects = {t.name for t in hr.projects}
    # The intro's areas carry the years: only the professional tracks and skill groups outside
    # a projects track's domain (services/honesty.py).
    tracks = [t.get("name") for t in _tracks(s) if t.get("name") and t.get("name") not in projects]
    skill_groups = honesty.professional_areas([i.title for i in pool.of("skill")], hr)
    candidate = {"first_name": (pool.profile.get("full_name") or "").split(" ")[0],
                 "years_statement": english, "years_statement_fr": french,
                 "areas_you_can_use": tracks + skill_groups,
                 **honesty.prompt_facts(hr),
                 "current_role": request.candidate.get("current_role")}
    signals = [{"id": x.id, "kind": x.kind, "fact": x.fact, "quote": x.quote,
                "connects_to": research.connection(x.fact, pool)}
               for x in research.signals(s, company.id, selected_only=True)]
    signals.sort(key=lambda x: -len(x["connects_to"]))  # connected to your proofs first
    rules = {"language": language, "min_words": ic.MIN_WORDS, "max_words": ic.MAX_WORDS,
             "banned_phrases": request.rules.get("banned_phrases"),
             "jargon": request.rules.get("jargon"), "signals": signals,
             "style": "four short parts: a hook naming the company's field and one or two of "
                      "its signals; the intro line (written by the program); their problem in "
                      "one sentence, then one or two proofs of having solved something similar; "
                      "one direct question about an opening. Warm, plain, specific."}
    return EmailRequest(job=request.job, contact=request.contact, candidate=candidate,
                        pool=request.pool, rules=rules)


# ------------------------------------------------- the application follow-up (prompt v11)


_AUTH_TEXT = {"needs_sponsorship": "would need visa sponsorship to work in the job's country",
              "eu_authorized": "authorized to work in the EU"}


def logistics(pool: Pool) -> dict[str, str]:
    """Languages as the profile lists them. Immigration and visa status are excluded."""
    p = pool.profile
    langs = ", ".join(f"{x.get('language')} ({x.get('level')})" for x in p.get("languages") or []
                      if x.get("language"))
    return {"languages": langs}


def application_facts(app: Application) -> dict[str, Any]:
    """The application record the opening is built from: whether it went in (Mark applied), when,
    and how (company site, job board or LinkedIn). `reference` is None: the app stores none."""
    return {"applied": app.web_applied_at is not None,
            "date": app.web_applied_at.date().isoformat() if app.web_applied_at else None,
            "method": str(app.web_method) if app.web_method else None,
            "reference": None}


def applied_context(s: Session, app: Application, job: Job, company: Company, contact: Contact,
                    pool: Pool, *, language: str, exclude_draft: int | None = None) -> ic.Context:
    ctx = intro_context(s, app, job, company, contact, pool, language=language, intro="",
                        exclude_draft=exclude_draft)
    ctx.min_words, ctx.max_words = ac.MIN_WORDS, ac.MAX_WORDS
    ctx.candidate_name = (pool.profile.get("full_name") or "").strip()
    ctx.track = job.matched_track or ""
    ctx.examples = []  # the intro examples don't apply here
    ctx.references = applied_references(s)  # the follow-up's style references (copy check)
    return ctx


def applied_request(s: Session, app: Application, job: Job, company: Company, contact: Contact,
                    cv: CVVersion, pool: Pool, language: str) -> EmailRequest:
    from app.services import honesty
    from app.services.cover_letter import _statements
    from app.services.cv_service import _tracks

    request = build_request(s, app, job, company, contact, cv, pool)
    first_name, source = email_first_name(s, company.id, contact)
    request.contact["first_name"] = first_name
    if source:
        request.contact["name_source"] = source
    _facts, english, french = _statements(s, pool)
    hr = honesty.rules(s)
    projects = {t.name for t in hr.projects}
    tracks = [t.get("name") for t in _tracks(s) if t.get("name") and t.get("name") not in projects]
    candidate = {"first_name": (pool.profile.get("full_name") or "").split(" ")[0],
                 "full_name": pool.profile.get("full_name") or "",
                 "years_statement": english, "years_statement_fr": french,
                 "areas_you_can_use": tracks + honesty.professional_areas(
                     [i.title for i in pool.of("skill")], hr),
                 **honesty.prompt_facts(hr), "logistics": logistics(pool),
                 "application": application_facts(app),
                 "track": job.matched_track,
                 "track_experience": "projects" if job.matched_track in projects
                 else "professional",
                 "current_role": request.candidate.get("current_role")}
    rules = {"language": language, "max_words": ac.MAX_WORDS,
             "banned_phrases": request.rules.get("banned_phrases"),
             "jargon": request.rules.get("jargon"), "signals": [],
             "style": "only the proof: one or two plain first-person sentences, one concrete "
                      "proof of stack alignment for the job's track, in the pool's own wording. "
                      "The program writes the rest. No link, no apology, no mention of an "
                      "attachment, visa, sponsorship, location or relocation.",
             "style_reference": applied_references(s)}
    return EmailRequest(job=request.job, contact=request.contact, candidate=candidate,
                        pool=request.pool, rules=rules)


def applied_guidance(contact: Contact, request: EmailRequest, job: Job, pool: Pool,
                     ctx: ic.Context, *, persona: str | None = None,
                     scenario: str | None = None) -> dict[str, Any]:
    """Who the recipient is and which situation the email handles, both computed in code and
    both overridable: they steer tone and emphasis in the prompt, never the facts. Sets the
    context's scenario fields (the checks allow the posting's years / target stack to be named
    once, in the acknowledgement)."""
    auto = ac.persona_for(contact.title, request.contact.get("role_group"))
    if persona is not None and persona not in ac.PERSONAS:
        raise OutreachError(f"Unknown persona “{persona}”")
    if scenario is not None and scenario not in ac.SCENARIOS:
        raise OutreachError(f"Unknown scenario “{scenario}”")
    found = ac.scenario_for(job.title, job.description or "", pool.all_text(),
                            max(ctx.allowed_years) if ctx.allowed_years else None)
    asked = ac.required_years(job.description or "")
    chosen = scenario or found["scenario"]
    if scenario == "years_gap" and not found.get("required_years"):
        if not asked:
            raise OutreachError("The listing states no years of experience to acknowledge")
        found.update(required_years=asked, have_years=max(ctx.allowed_years, default=0))
    if scenario == "stack_pivot" and not found.get("target_stack"):
        raise OutreachError("No stack in the listing that your experience pool lacks")
    ctx.scenario = chosen
    ctx.required_years = {int(found["required_years"])} if found.get("required_years") else (
        {asked} if asked else set())
    ctx.target_stack = found.get("target_stack", "") if chosen == "stack_pivot" else ""
    who = persona or auto
    detail = {} if chosen == "direct" else {k: v for k, v in found.items() if k != "scenario"}
    request.rules["persona"] = who
    request.rules["persona_focus"] = ac.PERSONA_FOCUS[who]
    request.rules["scenario"] = {"kind": chosen, **detail,
                                 "pattern": ac.SCENARIO_PATTERN[chosen]}
    return {"persona": who, "persona_auto": auto,
            "persona_source": "manual" if persona else "auto", "scenario": chosen,
            "scenario_auto": found["scenario"],
            "scenario_source": "manual" if scenario else "auto", "scenario_detail": detail}


def add_revision(request: EmailRequest, base: OutreachDraft | None, feedback: str) -> None:
    """A regeneration with feedback: the model gets the previous draft and what you want changed
    (the normal sources and rules stay), and edits toward it. The facts checks still apply."""
    if base is not None and (feedback or "").strip():
        request.rules["revision"] = {"previous_subject": base.subject,
                                     "previous_body": base.body, "feedback": feedback.strip()}


def local_weekday(s: Session | None = None, now: datetime | None = None) -> int:
    """Monday = 0, in your timezone (Settings → Motivation), else the machine's."""
    from zoneinfo import ZoneInfo

    name = (_setting(s, "motivation").get("timezone") if s is not None else None) or ""
    try:
        zone = ZoneInfo(name) if name else None
    except Exception:  # an unknown zone name: fall back to the machine's
        zone = None
    if now is None:
        now = datetime.now(zone) if zone else datetime.now().astimezone()
    elif zone:
        now = now.astimezone(zone)
    return now.weekday()


def previous_cta_variant(s: Session, company_id: int,
                         exclude_draft: int | None = None) -> int | None:
    """The closing wording of the latest earlier email to this company (any application)."""
    rows = s.exec(select(OutreachDraft).join(Application, col(Application.id) == col(
        OutreachDraft.application_id)).join(Job, col(Job.id) == col(Application.job_id)).where(
        Job.company_id == company_id).order_by(col(OutreachDraft.id).desc())).all()
    for d in rows:
        if d.id != exclude_draft and (d.plan or {}).get("cta_variant") is not None:
            return int(d.plan["cta_variant"])
    return None


def complete_applied(plan: Any, app: Application, job: Job, request: EmailRequest,
                     language: str, variant: int = 0, *, recruiter: bool = False,
                     cta: int = 0, weekday: int = 0, company: str = "") -> None:
    """Everything but the proof, built from the application record: the role, the greeting, the
    opening (how and when you applied) and the ask. The model's own values are overwritten."""
    facts = application_facts(app)
    plan.experience = ac.strip_model_opening(plan.experience)  # one opening, written here
    plan.role = ac.plain_role(job.title)
    plan.greeting = ic.greeting_line(request.contact["first_name"], language)
    plan.opening = ac.opening_line(
        plan.role, facts["method"],
        app.web_applied_at.date() if app.web_applied_at else None,
        datetime.now().astimezone().date(), language, variant, company,
        getattr(plan, "hook_clause", ""))
    plan.ask = ac.cta_line(language, recruiter, cta, weekday)
    plan.signal = HookSentence(text="")


def generate_applied(engine: Engine, app_id: int, drafter: Any, *, progress: Any = None,
                     language: str | None = None, feedback: str = "",
                     base_draft_id: int | None = None, persona: str | None = None,
                     scenario: str | None = None) -> OutreachDraft:
    """The job-linked email draft: one call (plus one retry with the problems as feedback). No
    research is started: signals the company already has are optional extras."""
    progress = progress or (lambda *_: None)
    if not _one_at_a_time.acquire(blocking=False):
        raise OutreachError("Another email is being drafted; one at a time")
    try:
        with Session(engine) as s:
            app = s.get(Application, app_id)
            if app is None:
                raise OutreachError("Application not found")
            try:  # the Get contact step: a verified contact first
                get_contact.require_ready(s, app)
            except get_contact.GetContactError as exc:
                raise OutreachError(str(exc)) from exc
            job, contact = s.get(Job, app.job_id), s.get(Contact, app.contact_id)
            company = s.get(Company, job.company_id)
            if not contact.email:
                raise OutreachError(f"{contact.full_name} has no email address")
            if reason := applied_gate(s, app, job):
                raise OutreachError(reason)
            cv = source_cv(s, app)
            if cv is None:
                raise OutreachError("No CV is recorded for this application: the email's proof "
                                    "is written from it")
            choice = language_choice(s, job, app, language)
            language = choice.language
            pool = load_pool(s)
            progress("drafting", 0, 1)
            request = applied_request(s, app, job, company, contact, cv, pool, language)
            base = s.get(OutreachDraft, base_draft_id) if base_draft_id else None
            add_revision(request, base, feedback)
            ctx = applied_context(s, app, job, company, contact, pool, language=language)
            earlier = (base.plan or {}).get("guidance") or {} if base else {}
            persona = None if persona == "auto" else persona or (
                earlier.get("persona") if earlier.get("persona_source") == "manual" else None)
            scenario = None if scenario == "auto" else scenario or (
                earlier.get("scenario") if earlier.get("scenario_source") == "manual" else None)
            guidance = applied_guidance(contact, request, job, pool, ctx, persona=persona,
                                        scenario=scenario)
            variant = len(s.exec(select(OutreachDraft.id).where(
                OutreachDraft.application_id == app_id)).all())  # a new wording each time
            cta = ac.cta_variant(previous_cta_variant(s, company.id), variant)
            weekday = local_weekday(s)

            def checked(plan: Any) -> list[dict[str, str]]:
                recruiter = (guidance.get("persona") == "recruiter"
                             or ac.is_recruiter(contact.title, request.contact.get("role_group")))
                complete_applied(plan, app, job, request, language, variant,
                                 recruiter=recruiter, cta=cta, weekday=weekday,
                                 company=company.name)
                return ac.check_plan(plan, ctx, recruiter=recruiter)

            started = time.monotonic()
            try:
                plan = drafter.draft_applied(request)
                found = checked(plan)
                attempts = 1
                if oc.errors(found) or ac.copies(found):
                    # One retry with the problems as feedback; a copied CV bullet gets "summarize
                    # in your own words". Kept unless it is worse; still copying = a warning.
                    notes = oc.feedback(found)
                    if ac.copies(found):
                        notes += ("\n" if notes else "") + (
                            "- Your experience sentences copy the pool bullets word for word: "
                            "summarize in your own words, as a short first-person summary of "
                            "the one or two things that matter most for this job")
                    retry = drafter.draft_applied(request, notes)
                    retry_found = checked(retry)
                    attempts = 2
                    if (len(oc.errors(retry_found)), ac.copies(retry_found)) <= (
                            len(oc.errors(found)), ac.copies(found)):
                        plan, found = retry, retry_found
            except DraftFailed as exc:
                raise OutreachError(str(exc)) from exc
            for old in s.exec(select(OutreachDraft).where(
                    OutreachDraft.application_id == app_id,
                    OutreachDraft.status == DraftStatus.draft)).all():
                old.status = DraftStatus.rejected  # regenerate replaces the draft under review
                s.add(old)
            draft = OutreachDraft(
                application_id=app_id, contact_id=app.contact_id,
                subject=ac.subject_line(plan.role, language, company.name),
                body=ac.body(plan), model=drafter.model, cv_version_id=cv.id,
                parent_id=base.id if base else None, feedback=feedback,
                plan={"delivery": "cv", "format": "applied", "mode": "applied",
                      "cta_variant": cta, "guidance": guidance, "plan": plan.model_dump(),
                      "attempts": attempts, "language": language,
                      "language_choice": choice.as_dict(),
                      "signal_ids": plan.signal.signal_ids,
                      "signals": request.rules.get("signals") or [],
                      "application": application_facts(app),
                      "name_source": request.contact.get("name_source"),
                      "request": request.model_dump(),
                      "via": getattr(drafter, "via", "mock"),
                      "auth": getattr(drafter, "auth_source", None)},
                violations=found, prompt_version=drafter.prompt_version,
                duration_ms=int((time.monotonic() - started) * 1000))
            if app.route == Route.undecided:
                app.route = Route.cold_email
                s.add(app)
            s.add(draft)
            problems = len(oc.errors(found))
            pipeline.log_event(s, app, EventKind.draft_created,
                               f"Email draft created for {contact.full_name}"
                               + (f" ({problems} problem{'s' if problems > 1 else ''} to "
                                  "review)" if problems else ""))
            s.commit()
            s.refresh(draft)
            progress("done", 1, 1)
            return draft
    finally:
        _one_at_a_time.release()


# ----------------------------------------------------------------------------------- sending


def outgoing(s: Session, engine: Engine, draft: OutreachDraft, *, to: str | None = None,
             test: bool = False) -> OutgoingEmail:
    """The email exactly as it will go out: a text/plain body (no image, no HTML) with the
    application's CV as its one PDF attachment."""
    contact = s.get(Contact, draft.contact_id) if draft.contact_id else None
    recipient = to or (contact.email if contact else None)
    if not recipient:
        raise OutreachError("No recipient email address")
    path, name = cv_attachment(s, engine, draft)
    return OutgoingEmail(to=recipient, subject=("[TEST] " if test else "") + draft.subject,
                         body=full_body(s, draft), attachment_path=path, attachment_name=name)


def cv_file_name(s: Session) -> str:
    """"First_Last_CV.pdf" from the profile's name (data, never code)."""
    name = (_setting(s, "profile").get("full_name") or "").split()
    return "_".join([*name, "CV"]) + ".pdf" if name else "CV.pdf"


def cv_attachment(s: Session, engine: Engine, draft: OutreachDraft) -> tuple[str, str]:
    """(path, file name) of the CV this email carries: the one the application was sent with,
    else the newest approved one (re-rendered if its file is gone). No file stops the send."""
    from app.services import cv_service  # local: cv_service imports this module's neighbours

    app = s.get(Application, draft.application_id)
    cv = source_cv(s, app) if app is not None else None
    path = None
    if cv is not None:
        path = Path(cv.pdf_path) if cv.pdf_path and Path(cv.pdf_path).is_file() \
            else cv_service.ensure_pdf(engine, cv)
    if path is None or not Path(path).is_file():
        raise OutreachError("No CV file to attach: approve or re-render this job's CV first")
    return str(path), cv_file_name(s)


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
                      status="sent")
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
