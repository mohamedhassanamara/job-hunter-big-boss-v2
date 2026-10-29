"""People captured from LinkedIn profiles (docs/LINKEDIN_EXTENSION_DESIGN.md §5).

A profile the user views becomes a contact at their company plus a `LinkedInProfile` snapshot (only
the parsed fields; the raw page lines are used for the parse and dropped). The person is attached to
the best open job at that company, or kept as a contact without a job and linked automatically the
moment a job at that company is captured (`link_waiting`). Persona is by ROLE; being an alum is a
separate flag. Nothing here requests linkedin.com."""

from typing import Any

from sqlmodel import Session, col, select

from app.models import Application, Company, Contact, Job, LinkedInOutreach, LinkedInProfile
from app.models.base import utcnow
from app.models.enums import LinkedInGroup, Stage
from app.services import contact_paste, dnc, linkedin, linkedin_page
from app.services.cv_pool import load_pool
from app.services.ingest import _company
from app.services.linkedin_track import school

PERSONAS = {g.value for g in LinkedInGroup if g != LinkedInGroup.hiring_team}


def _fields(payload: dict[str, Any] | None, paste: str | None,
            url: str) -> linkedin_page.ProfileFields:
    """The parsed profile: from the extension's payload, or from pasted profile text."""
    if payload:
        return linkedin_page.parse_profile(payload)
    parsed = contact_paste.parse(paste or "")
    link = linkedin.profile_url(parsed.linkedin_url or url) or ""
    return linkedin_page.ProfileFields(
        name=parsed.full_name or "", public_id=link.rstrip("/").rsplit("/", 1)[-1] if link else "",
        url=link, headline=parsed.title or "", current_title=parsed.title or "",
        current_company=parsed.company or "",
        sources={"name": "paste", "headline": "paste" if parsed.title else "missing",
                 "company": "paste" if parsed.company else "missing"})


def candidate_job(s: Session, company_id: int) -> dict[str, Any] | None:
    """The best open job at the company: past New first, then the newest."""
    from app.services import open_jobs

    rows = s.exec(select(Job, Application).join(Application, col(Application.job_id) == Job.id)
                  .where(Job.company_id == company_id, col(Job.duplicate_of_id).is_(None),
                         Application.stage != Stage.closed)).all()
    ok = open_jobs.open_ids(s, [j.id for j, _ in rows])
    rows = [(j, a) for j, a in rows if j.id in ok]
    if not rows:
        return None
    job, app = sorted(rows, key=lambda r: (r[1].stage == Stage.new, -(r[0].id or 0)))[0]
    return {"job_id": job.id, "application_id": app.id, "title": job.title,
            "stage": str(app.stage)}


def _existing(s: Session, company_id: int | None, f: linkedin_page.ProfileFields
              ) -> tuple[Contact | None, LinkedInProfile | None]:
    if company_id is None:
        return None, None
    people = s.exec(select(Contact).where(Contact.company_id == company_id)).all()
    url = linkedin.profile_url(f.url)
    contact = next((p for p in people if url and linkedin.profile_url(p.linkedin_url) == url),
                   None)
    if contact is None:
        from app.services.contacts import normalize_person

        contact = next((p for p in people if p.normalized_name == normalize_person(f.name)), None)
    prof = s.exec(select(LinkedInProfile).where(
        LinkedInProfile.contact_id == contact.id)).first() if contact else None
    return contact, prof


def _resolve(s: Session, *, payload: dict[str, Any] | None, paste: str | None, url: str,
             company: str | None, persona: str | None, alumni: bool | None,
             job_id: int | None) -> dict[str, Any]:
    f = _fields(payload, paste, url)
    company_name = (company or f.current_company or "").strip()
    short, full = school(load_pool(s))
    group, reasons = linkedin.persona(f.current_title, f.headline)
    auto_alum = linkedin_page.is_alum(f.education, short, full)
    missing = [k for k, v in (("name", f.name), ("company", company_name)) if not v]
    comp = _company_lookup(s, company_name) if company_name else None
    contact, prof = _existing(s, comp.id if comp else None, f)
    source = "auto"
    if persona:
        if persona not in PERSONAS:
            raise linkedin.CaptureError(f"Unknown role: {persona}")
        group, reasons, source = LinkedInGroup(persona), ["set by you"], "manual"
    elif prof and prof.persona_source == "manual":  # a recapture never overwrites your choice
        group, reasons, source = LinkedInGroup(prof.persona), ["set by you earlier"], "manual"
    is_alum = auto_alum if alumni is None else alumni
    job = None
    if comp and missing == []:
        if job_id is None:
            job = candidate_job(s, comp.id)
        elif job_id > 0:
            app = s.exec(select(Application).where(Application.job_id == job_id)).first()
            picked = s.get(Job, job_id)
            if app and picked:
                job = {"job_id": picked.id, "application_id": app.id, "title": picked.title,
                       "stage": str(app.stage)}
    warnings = []
    blocked = dnc.blocked_reason(s, contact) if contact else None
    if blocked:
        warnings.append(blocked)
    if f.sources.get("company") == "headline":
        warnings.append("The company comes from the headline: check it")
    return {"fields": f, "company": company_name, "persona": group.value, "reasons": reasons,
            "persona_source": source, "alumni": is_alum, "school": short, "missing": missing,
            "job": job, "contact": contact, "profile": prof, "do_not_contact": blocked,
            "warnings": warnings}


def _company_lookup(s: Session, name: str) -> Company | None:
    """The company if we already know it (no row is created by a preview)."""
    from app.services.company_merge import resolve_alias
    from app.services.dedupe import normalize_company

    norm = normalize_company(name)
    return s.exec(select(Company).where(Company.normalized_name == norm)).first() \
        or resolve_alias(s, norm)


def _out(r: dict[str, Any], saved: bool) -> dict[str, Any]:
    f: linkedin_page.ProfileFields = r["fields"]
    return {
        "saved": saved, "missing": r["missing"], "warnings": r["warnings"],
        "name": f.name, "headline": f.headline, "location": f.location,
        "current_title": f.current_title, "current_company": r["company"],
        "degree": f.degree, "persona": r["persona"], "persona_reasons": r["reasons"],
        "persona_source": r["persona_source"], "alumni": r["alumni"], "school": r["school"],
        "education": [e.get("school") for e in f.education],
        "job": r["job"], "existing": r["profile"] is not None,
        "contact_id": r["contact"].id if r["contact"] else None,
        "do_not_contact": r["do_not_contact"],
    }


def preview(s: Session, **kw: Any) -> dict[str, Any]:
    """What a capture would save, and why: nothing is written."""
    return _out(_resolve(s, **kw), saved=False)


def save(s: Session, *, extension_version: str = "", **kw: Any) -> dict[str, Any]:
    r = _resolve(s, **kw)
    if r["missing"]:
        return _out(r, saved=False)
    f: linkedin_page.ProfileFields = r["fields"]
    company = _company(s, r["company"])
    if company.linkedin_url is None and f.company_url:
        company.linkedin_url = f.company_url
        s.add(company)
    title = f.current_title or f.headline
    contact = linkedin.ensure_contact(s, company.id, full_name=f.name, title=title,
                                      linkedin_url=f.url)
    group = LinkedInGroup(r["persona"])
    prof = s.exec(select(LinkedInProfile).where(
        LinkedInProfile.contact_id == contact.id)).first() or LinkedInProfile(
        contact_id=contact.id)
    prof.profile_url, prof.public_id = f.url, f.public_id
    prof.headline, prof.current_title, prof.current_company = f.headline, f.current_title, \
        r["company"]
    prof.company_linkedin_url, prof.location, prof.connection_degree = f.company_url, \
        f.location, f.degree
    prof.education, prof.experience, prof.about, prof.badges = f.education, f.experience, \
        f.about, f.badges
    prof.persona, prof.persona_source, prof.persona_reasons = group, r["persona_source"], \
        r["reasons"]
    prof.is_alum, prof.capture_sources = bool(r["alumni"]), f.sources
    prof.captured_at, prof.extension_version = utcnow(), extension_version
    s.add(prof)
    if r["job"]:
        app = s.get(Application, r["job"]["application_id"])
        row = linkedin.add_person(s, app, full_name=f.name, title=title, linkedin_url=f.url,
                                  group=group, alumni=bool(r["alumni"]), source="extension")
        row.alumni = bool(r["alumni"]) or row.alumni
        if r["persona_source"] == "manual":
            row.group = group
        s.add(row)
    s.commit()
    r["contact"], r["profile"] = contact, prof
    return _out(r, saved=True)


def link_waiting(s: Session, app: Application, company_id: int) -> int:
    """A job at this company was just captured: people captured earlier with no job join it."""
    waiting = s.exec(select(Contact, LinkedInProfile).join(
        LinkedInProfile, col(LinkedInProfile.contact_id) == Contact.id).where(
        Contact.company_id == company_id)).all()
    done = 0
    for contact, prof in waiting:
        has_row = s.exec(select(LinkedInOutreach).where(
            LinkedInOutreach.contact_id == contact.id)).first()
        if has_row:
            continue
        linkedin.add_person(s, app, full_name=contact.full_name,
                            title=prof.current_title or prof.headline,
                            linkedin_url=contact.linkedin_url or prof.profile_url,
                            group=LinkedInGroup(prof.persona), alumni=prof.is_alum,
                            source="extension")
        done += 1
    return done


def update(s: Session, contact_id: int, *, persona: str | None = None,
           alumni: bool | None = None, job_id: int | None = None) -> dict[str, Any]:
    """Change a captured person's role / alum flag, or attach them to another job."""
    contact = s.get(Contact, contact_id)
    prof = s.exec(select(LinkedInProfile).where(
        LinkedInProfile.contact_id == contact_id)).first()
    if contact is None or prof is None:
        raise linkedin.CaptureError("This person has no captured profile")
    if persona is not None:
        if persona not in PERSONAS:
            raise linkedin.CaptureError(f"Unknown role: {persona}")
        prof.persona, prof.persona_source, prof.persona_reasons = LinkedInGroup(persona), \
            "manual", ["set by you"]
    if alumni is not None:
        prof.is_alum = alumni
    s.add(prof)
    rows = s.exec(select(LinkedInOutreach).where(
        LinkedInOutreach.contact_id == contact_id)).all()
    for row in rows:
        if persona is not None and not row.hiring_team:
            row.group = LinkedInGroup(persona)
        if alumni is not None:
            row.alumni = alumni
        s.add(row)
    job = None
    if job_id:
        app = s.exec(select(Application).where(Application.job_id == job_id)).first()
        picked = s.get(Job, job_id)
        if app is None or picked is None:
            raise linkedin.CaptureError("That job was not found")
        linkedin.add_person(s, app, full_name=contact.full_name,
                            title=prof.current_title or prof.headline,
                            linkedin_url=contact.linkedin_url, group=LinkedInGroup(prof.persona),
                            alumni=prof.is_alum, source="extension")
        job = {"job_id": picked.id, "application_id": app.id, "title": picked.title,
               "stage": str(app.stage)}
    s.commit()
    return {"saved": True, "contact_id": contact_id, "persona": str(prof.persona),
            "alumni": prof.is_alum, "job": job}


def listing(s: Session) -> list[dict[str, Any]]:
    """Every captured person with the jobs they are on (the People list in the app)."""
    out = []
    pairs = s.exec(select(Contact, LinkedInProfile).join(
        LinkedInProfile, col(LinkedInProfile.contact_id) == Contact.id)
        .order_by(col(LinkedInProfile.captured_at).desc())).all()
    for contact, prof in pairs:
        company = s.get(Company, contact.company_id)
        jobs = s.exec(select(Job, LinkedInOutreach).join(
            Application, col(Application.job_id) == Job.id).join(
            LinkedInOutreach, col(LinkedInOutreach.application_id) == Application.id).where(
            LinkedInOutreach.contact_id == contact.id)).all()
        out.append({
            "contact_id": contact.id, "full_name": contact.full_name,
            "headline": prof.headline, "current_title": prof.current_title,
            "company": company.name if company else "", "company_id": contact.company_id,
            "persona": str(prof.persona), "alumni": prof.is_alum,
            "degree": prof.connection_degree, "profile_url": prof.profile_url,
            "captured_at": prof.captured_at,
            "jobs": [{"job_id": j.id, "title": j.title, "status": str(o.status)}
                     for j, o in jobs],
            "do_not_contact": bool(contact.do_not_contact)})
    return out
