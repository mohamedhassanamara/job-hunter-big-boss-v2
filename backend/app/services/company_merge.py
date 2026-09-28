"""Company merge suggestions ("Devoteam Belgium" vs "Devoteam"). Never automatic: each one is
confirmed or rejected by you, and the answer is remembered.

A pair is suggested when one name is the other plus country / legal-form / group words, or when
both have the same web domain. Merging moves jobs, contacts and the lookup into the kept company
and records the other spelling as an alias so future jobs and imports land on the kept one.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlmodel import Session, col, func, select

from app.models import (
    Company,
    CompanyAlias,
    CompanyLookup,
    CompanyMergeDecision,
    Contact,
    Job,
)
from app.services import contacts as contacts_svc

# Trailing words that don't make a different employer.
_SUFFIX = {
    # countries / regions (EN + local)
    "belgium", "belgique", "belgie", "spain", "espana", "france", "germany", "deutschland",
    "italy", "italia", "portugal", "netherlands", "nederland", "uk", "ireland", "switzerland",
    "suisse", "schweiz", "austria", "osterreich", "luxembourg", "poland", "polska", "iberia",
    "benelux", "dach", "emea", "europe", "uae", "qatar", "mena", "middle", "east", "gulf",
    # legal forms and group words (normalize_company already drops the commonest)
    "se", "nv", "oy", "ab", "as", "spa", "srl", "sarl", "sas", "sasu", "gmbh", "kg", "co",
    "company", "corp", "corporation", "holding", "holdings", "group", "groupe", "gruppo",
    "international", "global",
}
_MIN_BASE = 4


def pair_key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def base_name(normalized: str) -> str:
    words = normalized.split()
    while len(words) > 1 and words[-1] in _SUFFIX:
        words.pop()
    return " ".join(words)


@dataclass
class Suggestion:
    a: Company
    b: Company
    reason: str
    a_jobs: int
    b_jobs: int
    a_contacts: int
    b_contacts: int


def suggestions(s: Session, limit: int = 200) -> list[Suggestion]:
    decided = set(s.exec(select(CompanyMergeDecision.pair_key)).all())
    companies = list(s.exec(select(Company)).all())
    by_norm = {c.normalized_name: c for c in companies}
    jobs = dict(s.exec(select(Job.company_id, func.count()).group_by(Job.company_id)).all())
    people = dict(s.exec(select(Contact.company_id, func.count())
                         .group_by(Contact.company_id)).all())
    pairs: dict[str, tuple[Company, Company, str]] = {}

    for c in companies:
        base = base_name(c.normalized_name)
        other = by_norm.get(base)
        if base != c.normalized_name and len(base) >= _MIN_BASE and other is not None:
            pairs.setdefault(pair_key(c.normalized_name, base),
                             (other, c, f"“{c.name}” is “{other.name}” plus "
                                        f"“{c.normalized_name[len(base):].strip()}”"))
    by_domain: dict[str, list[Company]] = defaultdict(list)
    for c in companies:
        if c.domain:
            by_domain[c.domain.lower().removeprefix("www.")].append(c)
    for domain, group in by_domain.items():
        for other in group[1:]:
            first = group[0]
            key = pair_key(first.normalized_name, other.normalized_name)
            pairs.setdefault(key, (first, other, f"same website: {domain}"))

    out = []
    for key, (a, b, reason) in pairs.items():
        if key in decided:
            continue
        # Only pairs that matter now: at least one side has jobs.
        if not (jobs.get(a.id) or jobs.get(b.id)):
            continue
        out.append(Suggestion(a, b, reason, jobs.get(a.id, 0), jobs.get(b.id, 0),
                              people.get(a.id, 0), people.get(b.id, 0)))
    out.sort(key=lambda x: -(x.a_jobs + x.b_jobs + x.a_contacts + x.b_contacts))
    return out[:limit]


class MergeError(ValueError):
    pass


def merge(s: Session, keep_id: int, merge_id: int) -> Company:
    """Move everything of `merge_id` into `keep_id`, then delete it. You confirmed this pair."""
    if keep_id == merge_id:
        raise MergeError("Pick two different companies")
    keep, gone = s.get(Company, keep_id), s.get(Company, merge_id)
    if keep is None or gone is None:
        raise MergeError("Company not found")
    for job in s.exec(select(Job).where(Job.company_id == gone.id)).all():
        job.company_id = keep.id
        s.add(job)
    for person in s.exec(select(Contact).where(Contact.company_id == gone.id)).all():
        person.company_id = keep.id
        s.add(person)
    lookups = {lk.company_id: lk for lk in s.exec(select(CompanyLookup).where(
        col(CompanyLookup.company_id).in_([keep.id, gone.id]))).all()}
    if gone.id in lookups:
        if keep.id in lookups:
            s.delete(lookups[gone.id])
        else:
            lookups[gone.id].company_id = keep.id
            s.add(lookups[gone.id])
    for alias in s.exec(select(CompanyAlias).where(CompanyAlias.company_id == gone.id)).all():
        alias.company_id = keep.id
        s.add(alias)
    for attr in ("domain", "website", "linkedin_url", "employees", "employees_max", "size_source"):
        if getattr(keep, attr) is None and getattr(gone, attr) is not None:
            setattr(keep, attr, getattr(gone, attr))
    if gone.contacted_at and (keep.contacted_at is None or gone.contacted_at < keep.contacted_at):
        keep.contacted_at = gone.contacted_at
    s.add(keep)
    s.flush()
    key = pair_key(keep.normalized_name, gone.normalized_name)
    s.add(CompanyAlias(normalized_name=gone.normalized_name, company_id=keep.id))
    s.add(CompanyMergeDecision(pair_key=key, decision="merged", kept_company_id=keep.id,
                               merged_name=gone.name))
    s.delete(gone)
    s.flush()
    contacts_svc.resolve_company(s, keep.id)
    return keep


def reject(s: Session, a_id: int, b_id: int) -> None:
    a, b = s.get(Company, a_id), s.get(Company, b_id)
    if a is None or b is None:
        raise MergeError("Company not found")
    key = pair_key(a.normalized_name, b.normalized_name)
    if s.exec(select(CompanyMergeDecision).where(CompanyMergeDecision.pair_key == key)).first():
        return
    s.add(CompanyMergeDecision(pair_key=key, decision="rejected"))


def resolve_alias(s: Session, normalized: str) -> Company | None:
    """The company a (merged-away) spelling now belongs to."""
    alias = s.exec(select(CompanyAlias).where(CompanyAlias.normalized_name == normalized)).first()
    return s.get(Company, alias.company_id) if alias else None
