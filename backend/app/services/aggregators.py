"""Does a "company" look like a job board or recruiting aggregator rather than the employer?

Only a suggestion shown in the lookup queue: you confirm "Never look up" (or dismiss it). The
signals are shown as reasons, so you can judge them.
"""

import re

from app.models import Company, Job
from app.services.dedupe import _ascii_words

# Words that name a job board / recruiter rather than an employer (matched inside the name too,
# e.g. "RemoteJobsOne").
_NAME_PARTS = ("remote", "jobs", "hire", "hiring", "recruit", "staffing", "careers", "talent",
               "jobboard", "jobfeed", "feed", "headhunt", "interim", "placement", "workforce")
_CLIENT = re.compile(
    r"\b(our client|for a client|on behalf of (?:our|a) client|notre client|"
    r"pour (?:le compte d'un|un) client|nuestro cliente|para (?:un|nuestro) cliente|"
    r"unser(?:e|en)? kunde|il nostro cliente|per (?:un|il nostro) cliente)\b", re.I)
MANY_JOBS = 8


def signals(company: Company, jobs: list[Job]) -> list[str]:
    """Human-readable reasons; empty when nothing suggests a job board."""
    out: list[str] = []
    joined = "".join(_ascii_words(company.name))
    hits = [p for p in _NAME_PARTS if p in joined]
    if hits:
        out.append(f"name contains “{hits[0]}”")
    if jobs:
        client = sum(1 for j in jobs if _CLIENT.search(j.description or ""))
        if client and client >= max(1, len(jobs) // 2):
            out.append(f"{client} of {len(jobs)} listings are “for a client”")
        tracks = {j.matched_track for j in jobs if j.matched_track}
        if len(jobs) >= MANY_JOBS and len(tracks) >= 2:
            out.append(f"{len(jobs)} open jobs across {len(tracks)} tracks")
        titles = [j.title.lower() for j in jobs]
        if any("worldwide" in t or "100% remote" in t for t in titles):
            out.append("job titles advertise “100% remote worldwide”")
    # One weak hint alone isn't enough, except the name (the strongest signal).
    return out if hits or len(out) >= 2 else []
