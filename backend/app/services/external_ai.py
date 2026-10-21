"""Write the email with another AI (Gemini, ChatGPT…), then bring it back through the checks.

`build_prompt` makes ONE self-contained prompt from the current email prompt (`outreach.md`,
sections external / external_applied / external_speculative): the full listing, the company and
recipient, only the experience that is relevant (your approved CV's items, else the best matches
for the listing), the language rule, the honest-follow-up (or speculative) structure and rules,
and an approved example for tone only. No phone, no email address, no other contacts: only what
the email needs. The prompt contains your experience and the listing, so the UI says to paste it
only into tools you trust.

`check_pasted` runs the code checks and the claim verifier on a pasted draft and returns each
claim with its verdict; `save_pasted` stores it as a normal draft (reviewed and approved like any
other: the verification is reused only while the text is unchanged).
"""

import re
from typing import Any

from sqlmodel import Session, col, select

from app.models import Application, Company, Contact, CVVersion, EmailExample, Job, OutreachDraft
from app.models.enums import DraftStatus, EventKind, Route
from app.providers.claude_email import load_sections
from app.services import applied_check as ac
from app.services import intro_check as ic
from app.services import outreach as ou
from app.services import outreach_check as oc
from app.services import pipeline, verifier
from app.services.cv_pool import Pool, load_pool, span

MODES = ou.EMAIL_MODES
MAX_ITEMS = 4  # relevant roles/projects when there is no approved CV to take them from
NOTE = ("This prompt contains your experience and the full job listing. Only paste it into AI "
        "tools you trust.")
_WORD = re.compile(r"[a-zà-ÿ][a-zà-ÿ0-9+#.\-]{3,}")


class ExternalError(ValueError):
    """Shown to the user."""


def _terms(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def relevant_items(s: Session, app: Application, pool: Pool, listing: str) -> list[Any]:
    """The items the email may use: the approved CV's (what the email attaches), else the roles
    and projects whose words overlap the listing most (never the whole pool)."""
    cv = ou.approved_cv(s, app)
    if cv is not None:
        subset = ou.cv_pool_subset(pool, cv)
        ids = [e["id"] for kind in ("roles", "projects") for e in subset.get(kind, [])]
        items = [pool.items[i] for i in ids if i in pool.items]
        if items:
            return items
    wanted = _terms(listing)
    ranked = sorted(
        ((len(_terms(" ".join([i.title, i.org or "", *pool.facts(i), *i.tags])) & wanted), i)
         for i in [*pool.of("job"), *pool.of("project")]),
        key=lambda x: -x[0])
    return [i for score, i in ranked if score > 0][:MAX_ITEMS]


def _render_items(pool: Pool, items: list[Any]) -> str:
    out = []
    for i in items:
        start, end = span(i)
        head = " · ".join(x for x in (i.title, i.org, f"{start} – {end}".strip(" –")) if x)
        out.append(f"{i.kind}: {head}\n" + "\n".join(f"- {f}" for f in pool.facts(i))
                   + (f"\nTools: {', '.join(i.tags)}" if i.tags else ""))
    return "\n\n".join(out) or "(no matching experience found)"


def _example(s: Session, mode: str, language: str) -> str:
    """An approved example of this mode, for tone and structure only."""
    rows = s.exec(select(EmailExample).where(
        col(EmailExample.kind).in_(["approved", "reference_good"]))
        .order_by(col(EmailExample.id).desc())).all()
    rows = [e for e in rows if (e.inputs or {}).get("channel") != "linkedin"
            and ((e.inputs or {}).get("mode") or "speculative") == mode]
    rows.sort(key=lambda e: e.language != language)  # the same language first
    if not rows:
        return ""
    e = rows[0]
    return ("\nEXAMPLE (tone and structure only: never reuse its facts, names or wording)\n"
            f"Subject: {e.subject}\n\n{e.body}\n")


def build_prompt(s: Session, app_id: int, *, mode: str | None = None,
                 language: str | None = None) -> dict[str, Any]:
    from app.services import honesty
    from app.services.cover_letter import _statements

    app = s.get(Application, app_id)
    if app is None:
        raise ExternalError("Application not found")
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    mode = ou.email_mode(job, mode)
    pool = load_pool(s)
    choice = ou.language_choice(s, job, app, language)
    listing = f"{job.title}\n{job.description or ''}".strip()
    items = relevant_items(s, app, pool, listing)
    _facts, english, french = _statements(s, pool)
    years = french if choice.language == "fr" and french else english
    hr = honesty.rules(s)
    facts = honesty.prompt_facts(hr)
    candidate = [f"Name: {(pool.profile.get('full_name') or '').strip()}",
                 f"Years of experience, in exactly this form: {years or 'do not state years'}",
                 facts["years_rule"]]
    candidate += [f"Track {t['track']}: experience is {t['experience']}"
                  + (f" ({t['how']})" if t.get("how") else "")
                  for t in facts["experience_by_track"]]
    where = ou.logistics(pool)
    if mode == "applied" and ac.listing_states_constraint(listing):
        candidate.append("Only if the listing states a requirement the candidate does not meet: "
                         + "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in where.items()
                                     if v))
    if mode == "applied":
        candidate.append("Application: " + ("already applied on "
                                            f"{app.web_applied_at.date().isoformat()}"
                                            if app.web_applied_at else "applying now"))
    recipient = (f"First name: {ou._first_name(contact)}\nFull name: {contact.full_name}\n"
                 f"Role: {contact.title or 'unknown'}" if contact
                 else "(no contact yet: address the email to the hiring team)")
    sections = load_sections()[1]
    language_line = f"Write the whole email in {_name(choice.language)}. ({choice.reason})"
    text = sections["external"]
    for key, value in {
        "[[LANGUAGE]]": language_line,
        "[[STRUCTURE]]": sections["external_" + mode],
        "[[CANDIDATE]]": "\n".join(candidate),
        "[[RECIPIENT]]": recipient,
        "[[JOB]]": (f"Company: {company.name}\nTitle: {job.title}\nLocation: "
                    f"{job.location or 'not stated'}\n\n{job.description or ''}"),
        "[[EXPERIENCE]]": _render_items(pool, items),
        "[[EXAMPLE]]": _example(s, mode, choice.language),
    }.items():
        text = text.replace(key, value)
    return {"prompt": text.strip() + "\n", "mode": mode, "language": choice.as_dict(),
            "chars": len(text), "items": [i.id for i in items], "note": NOTE,
            "listing_short": len(job.description or "") < ac.SNIPPET_CHARS}


def _name(code: str) -> str:
    from app.services.language import NAMES

    return NAMES.get(code, code)


# ------------------------------------------------------------------------ a pasted draft


_SUBJECT = re.compile(r"^\s*(?:\*\*)?(?:subject|objet|betreff)\s*(?:\*\*)?\s*:\s*(?:\*\*)?", re.I)
_SIGNOFF = re.compile(r"^(?:best regards|kind regards|regards|best|sincerely|thanks|thank you|"
                      r"cordialement|bien cordialement|bien à vous|cdlt)[,.!]?\s*$", re.I)


def split_pasted(text: str, name: str = "") -> tuple[str, str]:
    """(subject, body) from what another AI wrote: its "Subject:" line, and the body without its
    sign-off and name (the signature is added from Settings at send time)."""
    lines = (text or "").strip().replace("\r", "").split("\n")
    subject = ""
    if lines and _SUBJECT.match(lines[0]):
        subject = _SUBJECT.sub("", lines[0], count=1).strip(" *")
        lines = lines[1:]
    body = "\n".join(lines).strip()
    tail = body.split("\n")
    while tail and not tail[-1].strip():
        tail.pop()
    if tail and name and tail[-1].strip().lower() == name.strip().lower():
        tail.pop()
        while tail and not tail[-1].strip():
            tail.pop()
        if tail and _SIGNOFF.match(tail[-1].strip()):
            tail.pop()
    return subject, "\n".join(tail).strip()


def _contact_for(s: Session, app: Application) -> tuple[Job, Company, Contact]:
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    if contact is None:
        raise ExternalError("Get a contact first: the checks and the draft need a recipient")
    return job, company, contact


def check_pasted(s: Session, app_id: int, text: str, *, mode: str | None, verifier_: Any,
                 language: str | None = None) -> dict[str, Any]:
    """The code checks and the claim verifier on a pasted draft. Nothing is stored."""
    app = s.get(Application, app_id)
    if app is None:
        raise ExternalError("Application not found")
    if not (text or "").strip():
        raise ExternalError("Paste the draft first")
    job, company, contact = _contact_for(s, app)
    mode = ou.email_mode(job, mode)
    pool = load_pool(s)
    choice = ou.language_choice(s, job, app, language)
    subject, body = split_pasted(text, (pool.profile.get("full_name") or "").strip())
    if not subject:
        subject = (ac.subject_line("", pool.profile.get("full_name") or "", choice.language)
                   if mode == "applied" else ic.subject_line(company.name, choice.language))
    found = _code_checks(s, app, job, company, contact, pool, subject, body, mode, choice.language)
    draft = OutreachDraft(application_id=app.id, contact_id=contact.id, subject=subject,
                          body=body, cv_version_id=(ou.approved_cv(s, app) or CVVersion()).id,
                          plan={"language": choice.language, "format": _format(mode)})
    record = _verify(s, app, job, draft, verifier_, mode)
    return {"subject": subject, "body": body, "mode": mode, "language": choice.as_dict(),
            "violations": found, "verification": record,
            "errors": len(oc.errors(found)), "text_hash": record.get("hash")}


def _format(mode: str) -> str:
    return "applied" if mode == "applied" else "intro"


def _code_checks(s: Session, app: Application, job: Job, company: Company, contact: Contact,
                 pool: Pool, subject: str, body: str, mode: str,
                 language: str) -> list[dict[str, str]]:
    if mode == "applied":
        ctx = ou.applied_context(s, app, job, company, contact, pool, language=language)
        return ac.check_text(subject, body, ctx)
    ctx = ou.intro_context(s, app, job, company, contact, pool, language=language, intro="")
    return ic.check_text(subject, body, ctx)


def _verify(s: Session, app: Application, job: Job, draft: OutreachDraft, verifier_: Any,
            mode: str) -> dict[str, Any]:
    """The same sources the approval uses, on the text exactly as it would be sent."""
    pool = load_pool(s)
    cv = ou.approved_cv(s, app)
    sources = verifier.candidate_sources(s, pool, cv) \
        | verifier.signal_sources(s, job.company_id, None) \
        | verifier.recipient_source(s, job, draft.contact_id)
    kind = "cold email (with its subject)"
    if mode == "applied":
        sources["listing"] = f"{job.title}\n{job.description or ''}"
        sources["facts"] += verifier.application_line(app)
        kind = "email about a job application, to the person at the company (with its subject)"
    return verifier.run(verifier_, kind, verifier.email_text(s, draft), sources,
                        verifier.email_attachment(s, draft) if draft.cv_version_id else None)


def save_pasted(s: Session, app_id: int, text: str, *, mode: str | None, verifier_: Any,
                language: str | None = None) -> OutreachDraft:
    """Keep a pasted draft as a draft under review (checks and verification stored on it)."""
    app = s.get(Application, app_id)
    if app is None:
        raise ExternalError("Application not found")
    job, company, contact = _contact_for(s, app)
    cv = ou.approved_cv(s, app)
    if cv is None:
        raise ExternalError("Approve the CV first: the email attaches it")
    if not contact.email:
        raise ExternalError(f"{contact.full_name} has no email address")
    checked = check_pasted(s, app_id, text, mode=mode, verifier_=verifier_, language=language)
    mode = checked["mode"]
    for old in s.exec(select(OutreachDraft).where(
            OutreachDraft.application_id == app_id,
            OutreachDraft.status == DraftStatus.draft)).all():
        old.status = DraftStatus.rejected
        s.add(old)
    draft = OutreachDraft(
        application_id=app_id, contact_id=contact.id, subject=checked["subject"],
        body=checked["body"], model="external AI (pasted)", cv_version_id=cv.id,
        plan={"format": _format(mode), "mode": mode, "source": "external", "plan": {},
              "attempts": 1, "language": checked["language"]["language"],
              "language_choice": checked["language"], "intro_line": "", "signals": [],
              "application": ou.application_facts(app), "via": "external",
              "name_source": None, "auth": None},
        violations=checked["violations"], verification=checked["verification"],
        prompt_version="external", edited=True)
    # The verification was made on the text as it will be sent: keep it only if it still is.
    if checked["verification"].get("hash") != verifier.text_hash(verifier.email_text(s, draft)):
        draft.verification = {}
    if app.route == Route.undecided:
        app.route = Route.cold_email
        s.add(app)
    s.add(draft)
    pipeline.log_event(s, app, EventKind.draft_created,
                       f"Email draft saved from another AI for {contact.full_name}")
    s.commit()
    s.refresh(draft)
    return draft
