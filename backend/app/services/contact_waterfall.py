"""The contact waterfall (Phase 12): one click at the Get contact step.

Order: company cache → Hunter → Prospeo → Apollo → Apify → local email pattern (+ a verifier call
when a credit is left) → the manual Apollo-extension flow. It stops at the first VERIFIED email.
Unverified, catch-all (accept_all) and guessed addresses are shown, never used silently.

- Cache first: a company already looked up costs zero credits. A provider is queried again only
  when you ask (`requery`) or when its last run is older than `providers.max_age_days`.
- Every contact keeps its provenance (provider, key label, Actor, date).
- Credits are counted per key (services/provider_quota.py); a refused key is disabled, a key out of
  credits is skipped, and neither is retried in a loop.
- Called only from api/get_contact.py (tests/test_waterfall.py guards that).
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlmodel import Session, col, or_, select

from app.models import Application, Company, CompanyProviderRun, Contact, Job
from app.models.base import utcnow
from app.models.enums import ContactSource
from app.providers import registry
from app.providers.contact_finders import (
    Candidate,
    Cost,
    FinderError,
    KeyRefused,
    OutOfCredits,
    RateLimited,
    Search,
)
from app.services import (
    company_resolve,
    contact_check,
    dns_check,
    domains,
    email_pattern,
    listing,
    provider_quota,
)
from app.services import contacts as contacts_svc
from app.services.contacts import UNRANKED, rank, ranking_settings

WATERFALL = ("hunter", "prospeo", "apollo", "apify")
NEED = {"hunter": 1.0, "prospeo": 1.0, "apollo": 1.0, "apify": 0.10}  # to start a search
REVEAL_NEED = {"prospeo": 1.0, "apollo": 1.0}
PATTERN_TRIES = 2  # addresses built from the pattern and verified per click
ACCEPTED = "valid"  # the only email status ever used


class WaterfallError(ValueError):
    pass


class _Stop(Exception):
    """This provider can't continue (rate limited, error, no usable key)."""


@dataclass
class Step:
    provider: str  # cache | hunter | prospeo | apollo | apify | pattern | manual
    status: str  # found | empty | cached | skipped | no_key | exhausted | rate_limited | error
    detail: str = ""
    key_label: str | None = None
    credits: float = 0.0
    usd: float = 0.0


@dataclass
class Outcome:
    domain: str | None
    domain_source: str | None
    steps: list[Step] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    found_by: str | None = None
    from_cache: bool = False
    lookup_domain: str | None = None  # the domain the providers were asked about
    email_domain: str | None = None  # the company's stored email domain after this run
    # A question for you instead of another paid call: {reason, domain, alternatives:[{domain,
    # source, mx}]} (domains that receive email), answered by running again with email_domain.
    choice: dict[str, Any] | None = None

    @property
    def credits(self) -> float:
        return round(sum(s.credits for s in self.steps), 4)

    @property
    def usd(self) -> float:
        return round(sum(s.usd for s in self.steps), 4)


# ------------------------------------------------------------------------------------ helpers


def _order_titles(s: Session, company: Company, job: Job) -> tuple[Any, list[int], list[str]]:
    ranking = ranking_settings(s)
    order = ranking.order_for(company, job)
    titles: list[str] = []
    for i in order[:4]:  # the most relevant role groups for this company's size
        for kw in (ranking.groups[i].get("keywords") or [])[:3]:
            if kw not in titles:
                titles.append(kw)
    return ranking, order, titles


def _position(title: str | None, ranking: Any, order: list[int]) -> tuple[int, str | None]:
    idx, label = rank(title, ranking.groups)
    return (order.index(idx) if idx in order else UNRANKED), label


def _fresh_run(s: Session, company_id: int, provider: str, max_age_days: int,
               domain: str | None = None) -> CompanyProviderRun | None:
    """A recent run for this company and domain (runs from before domains were recorded match)."""
    cutoff = utcnow() - timedelta(days=max_age_days)
    return s.exec(select(CompanyProviderRun).where(
        CompanyProviderRun.company_id == company_id, CompanyProviderRun.provider == provider,
        or_(col(CompanyProviderRun.domain).is_(None), CompanyProviderRun.domain == domain),
        CompanyProviderRun.status.in_(["ok", "empty"]),  # type: ignore[attr-defined]
        CompanyProviderRun.queried_at >= cutoff)
        .order_by(col(CompanyProviderRun.queried_at).desc())).first()


def _call(s: Session, provider: str, need: float, fn: Callable[[str], tuple[Any, Cost, str]], *,
          keys: list[tuple[str, str]] | None, company_id: int, step: Step) -> Any:
    """Run `fn(key)` on the first usable key of the provider. A refused key is disabled and the
    next one tried; one out of credits is parked; a rate limit or other error stops the provider."""
    tried: set[str] = set()
    while True:
        nk = provider_quota.next_key(s, provider, need, tried, keys=keys)
        if nk is None:
            all_keys = keys if keys is not None else provider_quota.keys_for(provider)
            step.status = "no_key" if not all_keys else "exhausted"
            step.detail = ("no key in .env" if not all_keys else
                           "all keys are disabled or out of credits this month")
            raise _Stop
        label, key = nk
        tried.add(label)
        try:
            result, cost, endpoint = fn(key)
        except KeyRefused as exc:
            provider_quota.record(s, provider, label, "refused", Cost(), ok=False,
                                  result=str(exc), company_id=company_id)
            provider_quota.disable(s, provider, label, f"refused by {provider}: {exc}"[:200])
            step.detail = f"{label} refused by the provider and disabled; "
            continue
        except OutOfCredits as exc:
            provider_quota.record(s, provider, label, "out_of_credits", Cost(), ok=False,
                                  result=str(exc), company_id=company_id)
            provider_quota.exhaust(s, provider, label)
            step.detail += f"{label} is out of credits; "
            continue
        except RateLimited as exc:
            provider_quota.record(s, provider, label, "rate_limited", Cost(), ok=False,
                                  result=str(exc), company_id=company_id)
            step.status, step.detail = "rate_limited", f"{label} is rate limited, skipped"
            raise _Stop from exc
        except FinderError as exc:
            provider_quota.record(s, provider, label, "error", Cost(), ok=False, result=str(exc),
                                  company_id=company_id)
            step.status, step.detail = "error", f"{label}: {exc}"[:200]
            raise _Stop from exc
        provider_quota.record(s, provider, label, endpoint, cost, result="ok",
                              company_id=company_id)
        step.key_label = step.key_label or label
        step.credits += cost.credits
        step.usd += cost.usd
        return result


def _persist(s: Session, company: Company, c: Candidate, source: ContactSource,
             ranking: Any) -> Contact | None:
    """The company's contact row for a verified candidate, with provenance. Not verified by you
    yet (verified_at stays empty): the Get contact step still asks "still there?"."""
    email_n = (c.email or "").strip().lower()
    if not email_n:
        return None
    existing = s.exec(select(Contact).where(Contact.email_normalized == email_n)).first()
    if existing is not None and existing.company_id != company.id:
        return None  # that address belongs to another company's contact
    if existing is None:
        name = " ".join(c.full_name.split())
        parts = name.split(" ", 1)
        existing = Contact(company_id=company.id, full_name=name, first_name=parts[0],
                           last_name=parts[1] if len(parts) > 1 else None,
                           normalized_name=contacts_svc.normalize_person(name), email=c.email,
                           email_normalized=email_n, source=source)
    existing.title = existing.title or c.title
    existing.linkedin_url = existing.linkedin_url or c.linkedin_url
    existing.role_rank = rank(existing.title, ranking.groups)[0]
    existing.verification_status = c.email_status
    if not existing.found_by_provider:
        existing.found_by_provider = c.provider
        existing.found_by_key, existing.found_by_actor = c.key_label, c.actor
        existing.found_at = utcnow()
    s.add(existing)
    s.flush()
    return existing


def _known_samples(s: Session, company: Company, domain: str) -> list[tuple[str, str]]:
    rows = s.exec(select(Contact.full_name, Contact.email).where(
        Contact.company_id == company.id, col(Contact.email).is_not(None))).all()
    return [(n, e) for n, e in rows if e and e.lower().endswith("@" + domain)]


# ----------------------------------------------------------------------------- the waterfall


def run(s: Session, app: Application, *, requery: bool = False, domain: str | None = None,
        email_domain: str | None = None, mock: bool | None = None,
        finders: dict[str, Any] | None = None, mx_lookup: dns_check.Lookup | None = None,
        site_fetcher: Callable[[str], str | None] | None = None) -> Outcome:
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    use_mock = (mock if mock is not None else registry.get_settings().job_sources == "mock")
    resolved = company_resolve.resolve(
        s, company, domain=domain, fetcher=None if use_mock else listing.company_url_of)
    out = Outcome(resolved.domain, resolved.source)
    if not resolved.domain and not email_domain and not company.email_domain:
        out.steps.append(Step("manual", "skipped", "no domain for this company: enter it, or use "
                              "the Apollo extension"))
        return out
    # The domain providers are asked about: one you just chose, else the stored email domain, else
    # the website's.
    lookup = domains.clean_domain(email_domain) or domains.lookup_domain(company) \
        or resolved.domain
    out.lookup_domain = lookup
    if use_mock and mx_lookup is None:  # the sandbox never touches DNS: only this domain has MX
        mx_lookup = lambda d, _own=lookup: ["mx.sandbox.test"] if d == _own else []  # noqa: E731
    cfg = provider_quota.settings(s)
    ranking, order, titles = _order_titles(s, company, job)
    finders = finders or registry.contact_finders(mock=use_mock)
    pool: list[Candidate] = []  # ranked people without a verified email yet
    verified: list[tuple[Candidate, Contact]] = []

    def keys_of(provider: str) -> list[tuple[str, str]] | None:
        return [(f"{provider}#1", "mock")] if use_mock else None

    # 1. The cache: contacts already stored for this company with a verified email.
    if not requery:
        cached = [c for c in s.exec(select(Contact).where(
            Contact.company_id == company.id, col(Contact.email).is_not(None),
            col(Contact.left_at).is_(None), Contact.verification_status == ACCEPTED)).all()
            if _position(c.title, ranking, order)[0] != UNRANKED]
        if cached:
            cached.sort(key=lambda c: (_position(c.title, ranking, order)[0], c.id or 0))
            out.steps.append(Step("cache", "found", f"{len(cached)} verified contact(s) already "
                                  "stored for this company: 0 credits"))
            out.from_cache, out.found_by = True, "cache"
            _finish(s, out, [(None, c) for c in cached], pool, ranking, order, company)
            return out
        out.steps.append(Step("cache", "empty", "nobody verified stored for this company yet"))

    def add_pool(cands: list[Candidate]) -> None:
        for cand in cands:
            if _position(cand.title, ranking, order)[0] != UNRANKED and not any(
                    p.full_name == cand.full_name for p in pool):
                pool.append(cand)

    # Free first: does the domain receive email at all? If not, another known domain does (PDL's
    # other companies, the listing, the apply link, the website's contact page); only if none
    # does, stop and ask, before a credit is spent.
    # (a domain you just picked is always checked afresh, whatever was cached)
    if domains.mx(company, lookup, mx_lookup, force=bool(email_domain)) is False:
        for d in domains.site_domains(company.website or resolved.domain,
                                      None if use_mock else site_fetcher or listing.fetch_text):
            domains.register(company, d, "website contact page")
        known_mx = domains.alternatives(company, lookup, mx_lookup)
        if known_mx:
            use = known_mx[0]
            out.steps.append(Step("manual", "skipped", f"{lookup} receives no email (no MX): "
                                  f"using {use['domain']} instead ({use['source']})"))
            lookup = out.lookup_domain = known_mx[0]["domain"]
        else:
            guesses = domains.alternatives(company, lookup, mx_lookup, guess=True)
            out.steps.append(Step("manual", "no_mx", f"{lookup} receives no email (no MX "
                                  "records) and no other known domain does: nothing was spent"))
            out.choice = {"reason": f"{lookup} receives no email", "domain": lookup,
                          "alternatives": guesses}
            _finish(s, out, [], pool, ranking, order, company)
            return out
    tried = {lookup}
    if not use_mock:  # about to spend: start from the providers' real balances (free calls)
        for warning in provider_quota.sync_remote(s):
            out.steps.append(Step("manual", "skipped", warning))
    for provider in WATERFALL:
        finder, step = finders[provider], Step(provider, "empty")
        prior = None if requery else _fresh_run(s, company.id, provider, cfg["max_age_days"],
                                                lookup)
        if prior is not None:
            step.status = "cached"
            step.detail = (f"already queried {prior.queried_at:%Y-%m-%d} "
                           f"({prior.candidates and len(prior.candidates) or 0} people): 0 credits")
            add_pool([Candidate.load(d) for d in prior.candidates if not d.get("email")
                      or d.get("email_status") != ACCEPTED])
            out.steps.append(step)
            continue
        try:
            search: Search = _call(
                s, provider, NEED[provider],
                lambda key, f=finder: _timed(f.search(key, lookup, titles)),
                keys=keys_of(provider), company_id=company.id, step=step)
        except _Stop:
            out.steps.append(step)
            continue
        label = step.key_label
        for cand in search.candidates:
            cand.key_label = label
        ranked_c = sorted((c for c in search.candidates
                           if _position(c.title, ranking, order)[0] != UNRANKED),
                          key=lambda c: (_position(c.title, ranking, order)[0], c.email is None))
        s.add(CompanyProviderRun(company_id=company.id, provider=provider, key_label=label,
                                 domain=lookup, status="ok" if search.candidates else "empty",
                                 credits=step.credits, cost_usd=step.usd,
                                 candidates=[c.as_dict() for c in search.candidates]))
        if search.pattern and not company.email_pattern:
            company.email_pattern, company.pattern_confidence = search.pattern, 70
            company.pattern_evidence = {"source": provider, "domain": lookup}
        company.last_enriched_at = utcnow()
        for k, v in (("industry", search.organization.get("industry")),
                     ("linkedin_url", search.organization.get("linkedin_url"))):
            if v and not getattr(company, k):
                setattr(company, k, v)
        s.add(company)
        if not search.candidates:  # nobody at all: is it the right domain? (free check) then ask
            others = domains.alternatives(company, lookup, mx_lookup, guess=True, skip=tried)
            if others:
                step.detail = f"found nobody at {lookup}"
                out.steps.append(step)
                out.choice = {"reason": f"{provider.capitalize()} found nobody at {lookup}",
                              "domain": lookup, "alternatives": others}
                break
        good = [c for c in ranked_c if c.verified]
        # Reveal (paid) the best-ranked people who have an email, up to max_reveals.
        reveals = 0
        for cand in ranked_c:
            if good or reveals >= cfg["max_reveals"] or cand.email or not cand.has_email \
                    or provider not in REVEAL_NEED:
                continue
            try:
                got = _call(s, provider, REVEAL_NEED[provider],
                            lambda key, f=finder, c=cand: _reveal(f, key, c),
                            keys=keys_of(provider), company_id=company.id, step=step)
            except _Stop:
                break
            reveals += 1
            got.key_label = step.key_label
            if got.verified:
                good.append(got)
        if good:
            step.status, step.detail = "found", f"verified email from {provider}"
            out.steps.append(step)
            for cand in good:
                verified.append((cand, _persist(s, company, cand, ContactSource(provider),
                                                ranking)))
            out.found_by = provider
            _remember_email_domain(company, [c for c, _ in verified], lookup, out)
            add_pool([c for c in ranked_c if not c.verified])
            break
        step.detail = step.detail or (f"{len(ranked_c)} relevant people, no verified email"
                                      if ranked_c else "nobody relevant")
        add_pool(ranked_c)
        out.steps.append(step)

    # 6. Local pattern: build the address from the company's pattern, verify it before use.
    if not verified and pool and out.choice is None:
        _pattern_step(s, out, company, lookup, pool, finders, keys_of, cfg, ranking,
                      order, verified)
        if verified:
            _remember_email_domain(company, [c for c, _ in verified], lookup, out)
    if not verified and out.choice is None:
        out.steps.append(Step("manual", "skipped", "no verified email found: use the Apollo "
                              "extension (Get contact panel)"))
    _finish(s, out, [(c, ct) for c, ct in verified], pool, ranking, order, company)
    return out


def _remember_email_domain(company: Company, found: list[Candidate], lookup: str,
                           out: Outcome) -> None:
    """Verified emails prove which domain mail goes to: store it beside the website's, and use
    it next time (sekoia.com's people are all @sekoia.io)."""
    common = Counter((c.email or "").rsplit("@", 1)[-1].lower() for c in found if c.email)
    if not common:
        return
    domain = common.most_common(1)[0][0]
    company.email_domain = domain
    domains.register(company, domain, "verified email")
    known = dict(company.domains)
    known[domain] = {**known[domain], "mx": True, "checked_at": utcnow().isoformat()}
    company.domains = known
    out.email_domain = domain
    if company.domain and domain != company.domain:
        out.steps.append(Step("manual", "found", f"verified emails are at @{domain} but the "
                              f"website is {company.domain}: both are stored, @{domain} is used "
                              "next time"))


def _timed(search: Search) -> tuple[Search, Cost, str]:
    return search, search.cost, "search"


def _reveal(finder: Any, key: str, cand: Candidate) -> tuple[Candidate, Cost, str]:
    got, cost = finder.reveal(key, cand)
    return got, cost, "reveal"


def _pattern_step(s: Session, out: Outcome, company: Company, domain: str, pool: list[Candidate],
                  finders: dict[str, Any], keys_of: Callable[[str], Any], cfg: dict[str, Any],
                  ranking: Any, order: list[int], verified: list) -> None:
    step = Step("pattern", "empty")
    samples = _known_samples(s, company, domain)
    pattern, conf, evidence = (company.email_pattern, company.pattern_confidence or 0, []) \
        if company.email_pattern else email_pattern.infer(samples)
    if pattern and not company.email_pattern:
        company.email_pattern, company.pattern_confidence = pattern, conf
        company.pattern_evidence = {"source": "local", "samples": evidence}
        s.add(company)
    if not pattern:
        step.detail = "no known emails at this domain to infer a pattern from"
        out.steps.append(step)
        return
    tried = 0
    for cand in pool:
        guess = email_pattern.build(pattern, cand.full_name, domain)
        if not guess or tried >= PATTERN_TRIES or " " not in cand.full_name.strip():
            continue
        cand.email, cand.email_status, cand.provider = guess, None, "pattern"
        tried += 1
        try:
            status = _call(s, "hunter", 0.5,
                           lambda key, e=guess: _verify(finders["hunter"], key, e),
                           keys=keys_of("hunter"), company_id=company.id, step=step)
        except _Stop:
            step.detail = (step.detail + "; " if step.detail else "") + \
                "address built from the pattern, not verified (no verifier credit)"
            break
        cand.email_status = status
        cand.key_label = step.key_label
        cand.actor = "hunter-verifier"
        if status == ACCEPTED:
            step.status, step.detail = "found", f"{guess} built from {pattern} and verified"
            verified.append((cand, _persist(s, company, cand, ContactSource.pattern, ranking)))
            out.found_by = "pattern"
            break
        step.detail = f"{guess} is {status} (catch-all/unknown/invalid: not used)"
    out.steps.append(step)


def _verify(finder: Any, key: str, email: str) -> tuple[str, Cost, str]:
    status, cost = finder.verify(key, email)
    return status, cost, "verify"


def _finish(s: Session, out: Outcome, picks: list[tuple[Candidate | None, Contact | None]],
            pool: list[Candidate], ranking: Any, order: list[int], company: Company) -> None:
    """The top 3 by your ranking: verified people first, then others (emails not revealed or
    unverified, shown as such), with the "may have left" check on every verified one."""
    rows: list[dict[str, Any]] = []
    for _cand, contact in picks:
        if contact is None:
            continue
        pos, label = _position(contact.title, ranking, order)
        alerts = contact_check.scan(s, company.id, [contact])
        rows.append({
            "contact_id": contact.id, "full_name": contact.full_name, "title": contact.title,
            "email": contact.email, "email_status": contact.verification_status,
            "verified": contact.verification_status == ACCEPTED, "rank_label": label,
            "provider": contact.found_by_provider or str(contact.source),
            "key_label": contact.found_by_key, "actor": contact.found_by_actor,
            "found_at": contact.found_at, "note": "",
            "alerts": [a.reason for a in alerts if a.contact_id == contact.id],
            "_pos": pos})
    for cand in pool:
        pos, label = _position(cand.title, ranking, order)
        note = ("email not revealed (no credit spent)" if not cand.email else
                f"{cand.email_status or 'unverified'}: not used")
        rows.append({"contact_id": None, "full_name": cand.full_name, "title": cand.title,
                     "email": cand.email, "email_status": cand.email_status, "verified": False,
                     "rank_label": label, "provider": cand.provider, "key_label": cand.key_label,
                     "actor": cand.actor, "found_at": None, "note": note, "alerts": [],
                     "_pos": pos})
    rows.sort(key=lambda r: (not r["verified"], r["_pos"]))
    for r in rows:
        r.pop("_pos")
    out.candidates = rows[:3]
    s.flush()
    contacts_svc.resolve_company(s, company.id)


# ------------------------------------------------------------------------------ batch preview


def estimate_batch(s: Session, company_ids: list[int]) -> dict[str, dict[str, float | str | int]]:
    """The most a batch could spend, per provider, before anything runs (an upper bound: the
    waterfall stops at the first verified email, and a company looked up within
    `providers.max_age_days` costs nothing). Read-only: it never calls a provider."""
    cfg = provider_quota.settings(s)
    reveals = cfg["max_reveals"]
    per_company = {  # worst case for one company with nothing cached
        "hunter": NEED["hunter"] + 0.5 * PATTERN_TRIES,  # search + pattern verifications
        "prospeo": NEED["prospeo"] + reveals * REVEAL_NEED["prospeo"],
        "apollo": reveals * REVEAL_NEED["apollo"],  # the search itself is free
        "apify": NEED["apify"],
    }
    fresh = {p: 0 for p in WATERFALL}
    for company_id in set(company_ids):
        for provider in WATERFALL:
            if _fresh_run(s, company_id, provider, cfg["max_age_days"]) is None:
                fresh[provider] += 1  # this provider would be asked for this company
    out: dict[str, dict[str, float | str | int]] = {}
    for provider in WATERFALL:
        keys = provider_quota.keys_for(provider)
        left = sum(provider_quota.remaining(s, provider, label) for label, _ in keys
                   if provider_quota.usable(s, provider, label, 0.0))
        out[provider] = {"companies": fresh[provider],
                         "worst_case": round(fresh[provider] * per_company[provider], 2),
                         "remaining": round(left, 2), "unit": provider_quota.UNITS[provider],
                         "keys": len(keys)}
    return out
