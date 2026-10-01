"""Recruiting agencies: the listing is posted by a recruiter for an employer it doesn't name.

Then the job shows "Agency, employer not named", and LinkedIn messages skip the alumni and
team-lead searches (they'd find the agency's own staff) and put the recruiter first, in the
messages and in the contact ranking. Your per-company answer (`company.agency_override`:
"It's an employer" / "It's an agency") always wins over the signals. No model calls.
"""

import re

from sqlmodel import Session

from app.models import Company, Job

_NAME = re.compile(r"\b(?:talent acquisition|talent partners?|recruit(?:ment|ing|ers?)?|"
                   r"recrutement|staffing|headhunt\w*|executive search|search partners|interim|"
                   r"intérim|cabinet de recrutement|personalberatung|personaldienst\w*)\b", re.I)
# Only phrases that mean recruiting on someone's behalf. A consultancy's "notre client" / "our
# client" (a mission at a named or unnamed client) isn't one: the consultancy is the employer.
_LISTING = re.compile(r"\b(?:on behalf of (?:our|a) client|for one of our clients|we(?: are|'re) "
                      r"recruiting for|our partner company|pour l.un de nos clients|un de nos "
                      r"clients|pour le compte d.(?:un|une|l.un) de nos clients|pour le compte de "
                      r"notre client|unser kunde|für unseren kunden|für einen unserer kunden|"
                      r"para uno de nuestros clientes)\b", re.I)
# A consultancy placing its own consultant on a client mission is the employer, not an agency.
_CONSULTANCY = re.compile(r"\bmissions?\b|\bTJM\b|\bconsultan\w*|\brégie\b|\bprestations?\b|"
                          r"grands? comptes|\bassignments?\b|\bfreelance\b|\bEinsatz\w*|"
                          r"\bProjektgeschäft\b", re.I)


OVERRIDES = ("employer", "agency")


def detected(company: Company, job: Job | None = None) -> list[str]:
    """What the rule sees, ignoring your override."""
    out = []
    if m := _NAME.search(company.name or ""):
        out.append(f"the name says “{m.group(0)}”")
    text = job.description or "" if job is not None else ""
    for m in _LISTING.finditer(text):
        around = text[max(0, m.start() - 150):m.end() + 150]
        if not _CONSULTANCY.search(around):
            out.append(f"the listing says “{m.group(0)}”")
            break
    return out


def signals(company: Company, job: Job | None = None) -> list[str]:
    """Why the job counts as an agency's (empty: it doesn't). Your override wins: "It's an
    employer" clears the rule, "It's an agency" sets it."""
    if company.agency_override == "employer":
        return []
    if company.agency_override == "agency":
        return ["you marked it as an agency"]
    return detected(company, job)


def set_override(s: Session, company: Company, value: str | None) -> str | None:
    """Your answer ("employer", "agency", or None to go back to the rule); the company's open
    jobs are matched again so the contact ranking follows. Returns the previous value (undo)."""
    from app.services import contacts

    if value is not None and value not in OVERRIDES:
        raise ValueError("Choose employer, agency, or nothing (the rule decides)")
    previous = company.agency_override
    company.agency_override = value
    s.add(company)
    s.flush()
    contacts.resolve_company(s, company.id)
    return previous


def is_agency(company: Company, job: Job | None = None) -> bool:
    return bool(signals(company, job))
