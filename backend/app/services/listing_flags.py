"""Red flags in a listing, in code (no model call): no pay range, "rockstar"-style wording, and a
posting that has been up for months. They are hints shown on the job (never a score, never a
filter): a listing without a salary is normal in some countries, an old one may be evergreen.

Only what the listing text says is read. A truncated listing (a snippet) can't prove that a salary
is missing, so that flag needs the full description.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models import Job
from app.models.base import utcnow
from app.models.enums import DescriptionLevel

STALE_DAYS = 90

# Hype wording that stands in for a real description of the work.
HYPE = (
    "rockstar", "rock star", "rock-star", "ninja", "guru", "wizard", "superhero", "unicorn",
    "10x", "work hard play hard", "work hard, play hard", "like a family", "we are a family",
    "thick skin", "thrive in chaos", "sacrifice", "eat sleep", "no 9 to 5", "no nine to five",
)
_HYPE = re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in HYPE) + r")(?![\w])", re.I)

_CUR = r"(?:€|\$|£|chf|eur|euros?|usd|gbp|aed|sar|qar|dhs?|dkk|sek|pln)"
_PAY = re.compile(
    rf"(?:{_CUR}\s?\d"                                      # €60,000  $120k  AED 25,000
    rf"|\d[\d.,\s]*\s?k?\s?{_CUR}(?!\w)"                      # 55 000 €  60k€  45K EUR
    r"|\b\d{2,3}\s?(?:-|–|to|à|bis)\s?\d{2,3}\s?k\b"          # 45-55k  45 à 55k
    r"|\b\d{2,3}\s?k\b\s?(?:per|/|a|par|pro)\s?(?:year|yr|an|jahr|anno|año))",
    re.I)


@dataclass
class Flag:
    kind: str  # no_salary | hype | stale
    text: str


def has_pay(job: Job) -> bool:
    return bool((job.salary_text or "").strip()) or bool(_PAY.search(job.description or ""))


def hype_words(job: Job) -> list[str]:
    seen: list[str] = []
    for m in _HYPE.finditer(f"{job.title}\n{job.description or ''}"):
        word = m.group(1).lower()
        if word not in seen:
            seen.append(word)
    return seen


def age_days(job: Job, now: datetime | None = None) -> int | None:
    if job.posted_at is None:
        return None
    return max(0, ((now or utcnow()) - job.posted_at).days)


def scan(job: Job, now: datetime | None = None) -> list[Flag]:
    flags: list[Flag] = []
    full = job.description_level == DescriptionLevel.full and len(job.description or "") > 300
    if full and not has_pay(job):
        flags.append(Flag("no_salary", "No salary or pay range in the listing."))
    words = hype_words(job)
    if words:
        flags.append(Flag("hype", "Hype wording instead of the work: " + ", ".join(
            f"“{w}”" for w in words[:4]) + "."))
    days = age_days(job, now)
    if days is not None and days > STALE_DAYS:
        flags.append(Flag("stale", f"Posted {days} days ago (over {STALE_DAYS}): it may be "
                                   "filled, or an evergreen ad."))
    return flags


def is_stale(job: Job, now: datetime | None = None) -> bool:
    return (job.posted_at is not None
            and job.posted_at < (now or utcnow()) - timedelta(days=STALE_DAYS))
