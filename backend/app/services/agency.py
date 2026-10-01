"""Recruiting agencies: the listing is posted by a recruiter for an employer it doesn't name.

Then the job shows "Agency, employer not named", and LinkedIn messages skip the alumni and
team-lead searches (they'd find the agency's own staff) and put the recruiter first. A
suggestion from signals, never a hard block. No model calls.
"""

import re

from app.models import Company, Job

_NAME = re.compile(r"\b(?:talent acquisition|talent partners?|recruit\w*|recrutement|staffing|"
                   r"headhunt\w*|executive search|search partners|placement|interim|intérim|"
                   r"cabinet de recrutement|personalberatung|personaldienst\w*|"
                   r"consulting group hr)\b", re.I)
_LISTING = re.compile(r"\b(?:our client|our partner company|on behalf of (?:our|a) client|for a "
                      r"client|for one of our clients|we are recruiting for|we're recruiting for|"
                      r"notre client|pour le compte de|pour l.un de nos clients|un de nos "
                      r"clients|unser kunde|für unseren kunden|nuestro cliente)\b", re.I)


def signals(company: Company, job: Job | None = None) -> list[str]:
    out = []
    if m := _NAME.search(company.name or ""):
        out.append(f"the name says “{m.group(0)}”")
    if job is not None and (m := _LISTING.search(job.description or "")):
        out.append(f"the listing says “{m.group(0)}”")
    return out


def is_agency(company: Company, job: Job | None = None) -> bool:
    return bool(signals(company, job))
