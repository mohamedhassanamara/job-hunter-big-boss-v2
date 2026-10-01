"""The LinkedIn messages track for a job (Phase 10): who to message, the people you add, a
connection note per person (Claude, at most `linkedin.note_max_chars`), then after they accept a
follow-up with one proof and one direct ask. You send everything yourself on LinkedIn and mark
it here: to contact → request sent → accepted → messaged → replied.

Links are built in code (the model never writes a URL): a company-scoped people search when the
company's LinkedIn slug is known (from the bookmark), else a people search with the company name.
Ideas adapted from jobhunt-outreach (MIT, github.com/mohamedaminehamdi/job-hunter; see
docs/CREDITS.md): code-built links, alumni by school keyword, groups by reply odds.

Coordination: no email and LinkedIn request to the same person within `linkedin.gap_days`
(a hint; it never blocks). Research for a follow-up runs only at that step, through the same
`research.ensure` as the email draft step (tests/test_research_guard.py).
"""

import contextlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.models import (
    Application,
    ApplicationResponse,
    Company,
    Contact,
    Job,
    LinkedInOutreach,
    OutreachDraft,
)
from app.models.base import utcnow
from app.models.enums import (
    DraftStatus,
    LinkedInGroup,
    LinkedInStatus,
    ResponseChannel,
    ResponseKind,
    Stage,
)
from app.providers.base import DraftFailed, LinkedInRequest
from app.services import linkedin
from app.services import linkedin_check as lc
from app.services.contacts import local_midnight
from app.services.cv_pool import Pool, load_pool, prompt_pool

ORDER = [LinkedInGroup.hiring_team, LinkedInGroup.alumni, LinkedInGroup.lead,
         LinkedInGroup.recruiter, LinkedInGroup.other]
_STATUS_ORDER = {s: i for i, s in enumerate(LinkedInStatus)}
FOLLOWUP_MAX_CHARS = 600


class LinkedInError(ValueError):
    pass


def school(pool: Pool) -> tuple[str | None, str | None]:
    """(short, full) school name from your education in the pool (newest first)."""
    org = next((i.org for i in pool.of("education") if i.org), None)
    return lc.school_short(org), org


# ---------------------------------------------------------------------------- who to message


def people_search(company: Company, keywords: str) -> str:
    slug = linkedin.company_slug(company.linkedin_url)
    if slug:
        return f"https://www.linkedin.com/company/{slug}/people/?keywords={quote(keywords)}"
    return ("https://www.linkedin.com/search/results/people/?keywords="
            + quote(f'{keywords} "{company.name}"'))


def suggestions(s: Session, app: Application) -> list[dict[str, Any]]:
    """The groups to message, in order, each with why and a ready LinkedIn search link. At a
    recruiting agency (employer not named): the recruiter first, no alumni or team leads (they'd
    be the agency's own staff)."""
    from app.services import agency
    from app.services.contacts import who_to_contact

    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    hiring = {"group": "hiring_team", "label": "Hiring team",
              "why": "They posted this opening: the shortest path to a reply about it.",
              "search": None}
    recruiters = {"group": LinkedInGroup.recruiter, "label": "Recruiters",
                  "why": "They run the process: plain words, your match, an easy ask.",
                  "search": people_search(company, '"Recruiter" OR "Talent Acquisition"')}
    if agency.is_agency(company, job):
        recruiters["why"] = ("A recruiting agency, employer not named: the recruiter is who to "
                             "write to (alumni and team leads there are the agency's own staff).")
        return [hiring, recruiters]
    short, _full = school(load_pool(s))
    who = who_to_contact(s, job, company)
    lead_titles = [t for r in who["roles"] if "talent" not in r["label"].lower()
                   and "hr" not in r["label"].lower().split() for t in r["titles"]][:3]
    team = (job.matched_track or "").split("/")[0].strip()
    out = [hiring]
    if short:
        out.append({"group": LinkedInGroup.alumni, "label": f"{short} alumni",
                    "why": f"A shared school ({short}): ask for advice or a referral.",
                    "search": people_search(company, short)})
    lead_kw = " OR ".join(f'"{t}"' for t in lead_titles) or (f'"Head of {team}"' if team
                                                              else '"Engineering Manager"')
    out.append({"group": LinkedInGroup.lead, "label": "Team leads",
                "why": (f"People leading the {team} team" if team else "Team leads")
                + " know what the opening is really about: one technical proof, a short chat.",
                "search": people_search(company, lead_kw), "titles": lead_titles})
    out.append(recruiters)
    return out


def rows(s: Session, app: Application) -> list[LinkedInOutreach]:
    found = list(s.exec(select(LinkedInOutreach).where(
        LinkedInOutreach.application_id == app.id)).all())
    return sorted(found, key=lambda r: (not r.hiring_team, ORDER.index(LinkedInGroup(r.group)),
                                        r.id or 0))


def track_status(found: list[LinkedInOutreach]) -> str:
    """The LinkedIn track of a job: the furthest person ('none' when nobody was added)."""
    if not found:
        return "none"
    best = max(found, key=lambda r: _STATUS_ORDER[LinkedInStatus(r.status)])
    return str(best.status)


def add(s: Session, app: Application, *, full_name: str, title: str | None,
        linkedin_url: str | None, group: LinkedInGroup | None = None, alumni: bool = False,
        hiring_team: bool = False) -> LinkedInOutreach:
    try:
        return linkedin.add_person(s, app, full_name=full_name, title=title,
                                   linkedin_url=linkedin_url, group=group, alumni=alumni,
                                   hiring_team=hiring_team)
    except linkedin.CaptureError as exc:
        raise LinkedInError(str(exc)) from exc


# ------------------------------------------------------------------------------ coordination


def last_email(s: Session, contact_id: int) -> datetime | None:
    d = s.exec(select(OutreachDraft).where(
        OutreachDraft.contact_id == contact_id,
        col(OutreachDraft.status).in_([DraftStatus.sent, DraftStatus.queued]))
        .order_by(col(OutreachDraft.updated_at).desc())).first()
    return (d.sent_at or d.updated_at) if d else None


def last_request(s: Session, contact_id: int) -> datetime | None:
    r = s.exec(select(LinkedInOutreach).where(
        LinkedInOutreach.contact_id == contact_id, col(LinkedInOutreach.sent_at).is_not(None))
        .order_by(col(LinkedInOutreach.sent_at).desc())).first()
    return r.sent_at if r else None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


def gap_hint(s: Session, contact_id: int, *, channel: str = "linkedin") -> str | None:
    """"Emailed on 1 Oct: request after 4 Oct" when the other channel reached them recently."""
    days = int(linkedin.linkedin_settings(s)["gap_days"])
    other = last_email(s, contact_id) if channel == "linkedin" else last_request(s, contact_id)
    if other is None or days <= 0:
        return None
    other = _aware(other)
    after = other + timedelta(days=days)
    if utcnow() >= after:
        return None
    what = "Emailed" if channel == "linkedin" else "LinkedIn request sent"
    nxt = "request" if channel == "linkedin" else "email"
    return f"{what} on {other:%-d %b}: {nxt} after {after:%-d %b}"


def requests_today(s: Session) -> int:
    since = local_midnight()
    return len(s.exec(select(LinkedInOutreach.id).where(
        col(LinkedInOutreach.sent_at) >= since)).all())


# ---------------------------------------------------------------------------------- drafting


ANGLE = {
    LinkedInGroup.recruiter: "recruiter",
    LinkedInGroup.lead: "lead",
    LinkedInGroup.alumni: "alumni",
    LinkedInGroup.other: "lead",
    LinkedInGroup.hiring_team: "recruiter",
}


def matching_tools(pool: Pool, job_text: str, limit: int = 3) -> list[str]:
    """Tools the listing names that you have (as your pool writes them), in listing order."""
    found = []
    for tag in {t for i in pool.items.values() for t in (i.tags or []) if len(t) >= 2}:
        m = re.search(rf"(?<![A-Za-z0-9]){re.escape(tag)}(?![A-Za-z0-9])", job_text, re.I)
        if m:
            found.append((m.start(), tag))
    return [t for _, t in sorted(found)][:limit]


def project_tools(pool: Pool, terms: list[str], job_text: str, limit: int = 2) -> list[str]:
    """Tools from your projects (project, education and certification items) for the transition
    line: the track's own tools first (dbt, Airflow), then ones the listing names, then the most
    used; never a concept word (ETL, data modeling)."""
    from collections import Counter

    from app.services.honesty import CONCEPTS

    counts: Counter[str] = Counter(t for kind in ("project", "education", "certification")
                                   for i in pool.of(kind) for t in (i.tags or [])
                                   if len(t) >= 2 and t.lower() not in CONCEPTS)
    folded = {t.lower() for t in terms}

    def rank(tag: str) -> tuple[bool, bool, int]:
        listed = re.search(rf"(?<![A-Za-z0-9]){re.escape(tag)}(?![A-Za-z0-9])", job_text, re.I)
        return (tag.lower() not in folded, not listed, -counts[tag])

    return sorted(counts, key=rank)[:limit]


def framing(s: Session, job: Job, years: int | None, pool: Pool) -> dict[str, Any] | None:
    """For a job in a projects-only track (e.g. Data/AI): the transparent transition, built in
    code: "a software engineer (3 years, mobile and backend) moving into data, with … projects"."""
    from app.services import honesty

    r = honesty.rules(s)
    track = next((t for t in r.projects if t.name == job.matched_track), None)
    if track is None:
        return None
    pro = " and ".join(n.lower() for n in r.professional) or "software"
    into = track.name.split("/")[0].strip().lower()
    head = f"a software engineer ({years} years, {pro})" if years else f"a {pro} software engineer"
    tools = project_tools(pool, track.terms, f"{job.title}\n{job.description or ''}")
    return {"use": True, "text": f"{head} moving into {into}"
            + (f", with {' and '.join(tools)} projects" if tools else ""),
            "tools": tools, "how": track.note,
            "words": [w for n in r.professional for w in re.split(r"[^A-Za-z]+", n) if w]}


def reference_notes(s: Session, row_id: int | None = None) -> list[str]:
    """Approved LinkedIn notes (the regression set): structure and honesty, never wording. A
    note saved from this very row isn't a copy of itself."""
    from app.models import EmailExample

    return [e.body for e in s.exec(select(EmailExample)).all()
            if (e.inputs or {}).get("channel") == "linkedin"
            and (row_id is None or (e.inputs or {}).get("linkedin_outreach_id") != row_id)]


def _request(s: Session, row: LinkedInOutreach, kind: str,
             signals: list[dict[str, Any]] | None = None) -> tuple[LinkedInRequest, lc.Context]:
    from app.services import agency, honesty
    from app.services.cover_letter import _statements
    from app.services.outreach import _places, email_language
    from app.services.outreach_check import DEFAULT_BANNED

    app = s.get(Application, row.application_id)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    person = s.get(Contact, row.contact_id)
    pool = load_pool(s)
    facts, english, french = _statements(s, pool)
    short, full = school(pool)
    cfg = linkedin.linkedin_settings(s)
    language = email_language(s, job)
    max_chars = int(cfg["note_max_chars"]) if kind == "note" else FOLLOWUP_MAX_CHARS
    first = person.first_name or person.full_name.split(" ")[0]
    alumni = bool(row.alumni or row.group == LinkedInGroup.alumni)
    angle = "alumni" if row.group == LinkedInGroup.alumni else ANGLE[LinkedInGroup(row.group)]
    job_text = f"{job.title}\n{job.description or ''}"
    tools = matching_tools(pool, job_text)
    years = max((int(f["years"]) for f in facts), default=None)
    rules_ = honesty.rules(s)
    transition = framing(s, job, years, pool)
    request = LinkedInRequest(
        kind=kind,
        job={"title": job.title, "company": company.name, "track": job.matched_track,
             "agency": agency.is_agency(company, job),
             "description": (job.description or "")[:4000]},
        person={"first_name": first, "full_name": person.full_name, "title": person.title,
                "group": angle, "hiring_team": row.hiring_team, "alumni": alumni},
        candidate={"first_name": (pool.profile.get("full_name") or "").split(" ")[0],
                   "years_statement": english if language != "fr" else french,
                   "school": short if alumni else None,
                   "matching_tools": tools,
                   "transition": transition and {k: transition[k] for k in ("use", "text", "how")},
                   **honesty.prompt_facts(rules_)},
        pool=prompt_pool(pool),
        rules={"max_chars": max_chars, "language": language,
               "banned_phrases": DEFAULT_BANNED + lc.LINKEDIN_BANNED,
               **({"signals": signals} if signals else {})})
    ctx = lc.Context(
        pool=pool, allowed_years={int(f["years"]) for f in facts},
        job_text=job_text + "\n"
        + " ".join(f"{x['fact']} {x.get('quote', '')}" for x in signals or []),
        company=company.name, kind=kind, max_chars=max_chars, alumni=alumni, school=short,
        school_full=full, first_name=first, places=_places(pool), banned=list(DEFAULT_BANNED),
        honesty=rules_, examples=reference_notes(s, row.id), group=angle,
        matching_tools=tools + (transition["tools"] + transition["words"] if transition else []))
    return request, ctx


def _draft(drafter: Any, request: LinkedInRequest, ctx: lc.Context) -> dict[str, Any]:
    from app.services import outreach_check as oc

    try:
        msg = drafter.draft(request)
        found = lc.check(msg.text, ctx)
        attempts = 1
        if oc.errors(found):  # one retry with the problems as feedback
            retry = drafter.draft(request, oc.feedback(oc.errors(found)))
            retry_found = lc.check(retry.text, ctx)
            attempts = 2
            if len(oc.errors(retry_found)) <= len(oc.errors(found)):
                msg, found = retry, retry_found
    except DraftFailed as exc:
        raise LinkedInError(str(exc)) from exc
    return {"text": msg.text.strip(), "citations": msg.citations, "signal_ids": msg.signal_ids,
            "violations": found, "attempts": attempts, "model": drafter.model,
            "prompt_version": drafter.prompt_version, "via": getattr(drafter, "via", "mock"),
            "auth": getattr(drafter, "auth_source", None), "created_at": utcnow().isoformat(),
            "edited": False, "max_chars": ctx.max_chars}


def draft_note(engine: Engine, row_id: int, drafter: Any) -> LinkedInOutreach:
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, row_id)
        if row is None:
            raise LinkedInError("Person not found")
        request, ctx = _request(s, row, "note")
    note = _draft(drafter, request, ctx)
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, row_id)
        row.note = note
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def draft_followup(engine: Engine, row_id: int, drafter: Any, *, researcher: Any = None,
                   fetcher: Any = None) -> LinkedInOutreach:
    """After they accept: one proof and one direct ask. Fresh company signals are reused; the
    company is researched here only if it has none (same trigger rules as the email)."""
    from app.services import research

    with Session(engine) as s:
        row = s.get(LinkedInOutreach, row_id)
        if row is None:
            raise LinkedInError("Person not found")
        if LinkedInStatus(row.status) not in (LinkedInStatus.accepted, LinkedInStatus.messaged):
            raise LinkedInError("Mark the request accepted first")
        job = s.get(Job, s.get(Application, row.application_id).job_id)
        company_id = job.company_id
    if researcher is not None:  # if it fails, the follow-up still works from pool + listing
        with contextlib.suppress(research.ResearchError):
            research.ensure(engine, company_id, trigger="linkedin", researcher=researcher,
                            fetcher=fetcher)
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, row_id)
        signals = [{"id": x.id, "fact": x.fact, "quote": x.quote}
                   for x in research.signals(s, company_id, selected_only=True)]
        request, ctx = _request(s, row, "followup", signals)
    followup = _draft(drafter, request, ctx)
    with Session(engine) as s:
        row = s.get(LinkedInOutreach, row_id)
        row.followup = followup
        s.add(row)
        s.commit()
        s.refresh(row)
        return row


def edit(s: Session, row: LinkedInOutreach, which: str, text: str) -> LinkedInOutreach:
    """Your edit of the note or the follow-up: checked again (text-level)."""
    kind = "note" if which == "note" else "followup"
    _request_obj, ctx = _request(s, row, kind)
    current = dict(getattr(row, which) or {})
    current.update(text=text.strip(), edited=True, violations=lc.check(text, ctx),
                   max_chars=ctx.max_chars)
    setattr(row, which, current)
    s.add(row)
    return row


# ---------------------------------------------------------------------------------- statuses

_STAMP = {LinkedInStatus.sent: "sent_at", LinkedInStatus.accepted: "accepted_at",
          LinkedInStatus.messaged: "messaged_at", LinkedInStatus.replied: "replied_at"}


def set_status(s: Session, row: LinkedInOutreach, status: LinkedInStatus) -> LinkedInOutreach:
    """You did it on LinkedIn; this records it (going back clears the later dates: undo)."""
    order = list(LinkedInStatus)
    for st in order[order.index(status) + 1:]:
        if st in _STAMP:
            setattr(row, _STAMP[st], None)
    if status in _STAMP and getattr(row, _STAMP[status]) is None:
        setattr(row, _STAMP[status], utcnow())
    if status == LinkedInStatus.to_contact:
        row.sent_at = None
    previous = LinkedInStatus(row.status)
    row.status = status
    s.add(row)
    person = s.get(Contact, row.contact_id)
    if status == LinkedInStatus.replied and previous != LinkedInStatus.replied:
        s.add(ApplicationResponse(application_id=row.application_id, kind=ResponseKind.other,
                                  channel=ResponseChannel.linkedin,
                                  notes=f"LinkedIn reply from {person.full_name} "
                                        f"({str(row.group).replace('_', ' ')})"))
    if previous == LinkedInStatus.replied and status != LinkedInStatus.replied:
        reply = s.exec(select(ApplicationResponse).where(
            ApplicationResponse.application_id == row.application_id,
            ApplicationResponse.channel == ResponseChannel.linkedin,
            col(ApplicationResponse.notes).startswith(f"LinkedIn reply from {person.full_name}"))
            .order_by(col(ApplicationResponse.id).desc())).first()
        if reply is not None:
            s.delete(reply)
    return row


# --------------------------------------------------------------------------------- reminders


@dataclass
class FollowUp:
    row_id: int
    application_id: int
    job_id: int
    person: str
    company: str
    kind: str  # no_answer (request) | no_reply (message) | write_followup (accepted)
    since: datetime


def reminders(s: Session, now: datetime | None = None) -> list[FollowUp]:
    """Requests with no answer after `followup_days`, accepted connections still waiting for
    your follow-up, and follow-ups with no reply."""
    now = now or utcnow()
    days = int(linkedin.linkedin_settings(s)["followup_days"])
    out = []
    for row in s.exec(select(LinkedInOutreach).where(col(LinkedInOutreach.status).in_(
            [LinkedInStatus.sent, LinkedInStatus.accepted, LinkedInStatus.messaged]))).all():
        app = s.get(Application, row.application_id)
        job = s.get(Job, app.job_id)
        company = s.get(Company, job.company_id)
        person = s.get(Contact, row.contact_id)
        if row.status == LinkedInStatus.accepted:
            out.append(FollowUp(row.id, app.id, job.id, person.full_name, company.name,
                                "write_followup", _aware(row.accepted_at or now)))
            continue
        stamp = row.sent_at if row.status == LinkedInStatus.sent else row.messaged_at
        if stamp and now - _aware(stamp) >= timedelta(days=days):
            out.append(FollowUp(row.id, app.id, job.id, person.full_name, company.name,
                                "no_answer" if row.status == LinkedInStatus.sent else "no_reply",
                                _aware(stamp)))
    return sorted(out, key=lambda f: f.since)


def to_send(s: Session) -> list[dict[str, Any]]:
    """People added but not requested yet whose note is ready (the gap rule respected)."""
    out = []
    for row in s.exec(select(LinkedInOutreach).where(
            LinkedInOutreach.status == LinkedInStatus.to_contact)).all():
        if gap_hint(s, row.contact_id):
            continue
        app = s.get(Application, row.application_id)
        job = s.get(Job, app.job_id)
        person = s.get(Contact, row.contact_id)
        out.append({"row_id": row.id, "application_id": app.id, "job_id": job.id,
                    "job_title": job.title, "company": s.get(Company, job.company_id).name,
                    "person": person.full_name, "group": str(row.group),
                    "note_ready": bool(row.note and row.note.get("text"))})
    return out


def summary(s: Session) -> dict[str, Any]:
    """The LinkedIn card on Today and the LinkedIn page: searches not opened today, imported
    jobs still to decide on, requests to send, follow-ups due, and today's request counter."""
    from app.models.enums import Source

    found = linkedin.search_links(s)
    links = [x for g in found.groups for x in g.links]
    new_imports = s.exec(select(Job, Application).join(
        Application, col(Application.job_id) == col(Job.id)).where(
        Job.source == Source.linkedin, Application.stage == Stage.new)
        .order_by(col(Job.discovered_at).desc())).all()
    cfg = linkedin.linkedin_settings(s)
    return {
        "links_total": len(links), "links_unopened": sum(not x.opened_today for x in links),
        "to_decide": [{"job_id": j.id, "title": j.title,
                       "company": s.get(Company, j.company_id).name} for j, _ in new_imports[:5]],
        "to_decide_total": len(new_imports),
        "to_send": to_send(s)[:5],
        "followups": [vars(f) for f in reminders(s)[:5]],
        "requests_today": requests_today(s), "daily_limit": int(cfg["daily_requests"]),
    }
