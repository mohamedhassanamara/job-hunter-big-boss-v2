"""Is the contact still there? Signs they left or changed role, from what research fetched.

Research stores the company's pages and news (company_page). Each run also searches the news for
each contact's own name (kind "contact_news"). Two signs make an alert, never a model's guess:
- "left": a sentence naming the contact with a departure word (révoqué, quitte, ancien PDG,
  stepped down, former CEO…);
- "new_holder": a sentence announcing someone else in the contact's role (a new CEO named).

An active alert blocks the email's approval and suggests the next contact by the ranking rule.
You dismiss it once you've verified the contact yourself; found again, it stays dismissed.
Runs with research (the draft step, Research now; a cached reuse only rescans stored pages) and
with "Check again" on the contact. No model calls.
"""

import hashlib
import re
from collections.abc import Callable
from typing import Any

from sqlmodel import Session, col, select

from app.models import (
    Application,
    Company,
    CompanyPage,
    Contact,
    ContactAlert,
    Job,
)
from app.models.base import utcnow
from app.models.enums import Stage
from app.services.fit import _norm

# Sentences (not after "M." / "Mr." / "Dr." / "Mme.": "le conseil a révoqué M. Fontana").
_SENTENCE = re.compile(r"(?<!\bM\.)(?<!\bMr\.)(?<!\bDr\.)(?<!\bMs\.)(?<!\bMme\.)(?<=[.!?…])\s+"
                       r"|\n+|\s+[-–—|]\s+")
# A departure next to the name. Not "remercie" (thanks) or a bare "ancien" (a past job elsewhere).
_LEFT = re.compile(
    r"\b(?:révoqu\w*|revoqu\w*|limog\w*|démis(?:sion\w*)?|demis(?:sion\w*)?|licenci\w*|évinc\w*|"
    r"evinc\w*|écart[ée]\w*|quitt\w*|départ|remplac\w*|succède|succede|poussé vers la sortie|"
    r"ancien(?:ne)?s? (?:directeur|directrice|dg|pdg|président\w*|ceo|cto|patron\w*|dirigeant\w*)|"
    r"ex-(?:dg|pdg|ceo|cto|directeur|directrice|président\w*|patron\w*)|"
    r"dismiss\w*|ousted|fired|let go|stepp?(?:ed|s)? down|steps down|resign\w*|replaced|"
    r"succeeded by|departs?|departed|departure|leaves|left the company|has left|"
    r"former (?:ceo|cto|chief|head|director|president|managing|founder|vp)|ex-ceo)\b", re.I)
_APPOINTED = re.compile(
    r"\b(?:nomm[ée]\w*|nomme|nomination|appoint\w*|names|named|prend la tête|"
    r"prend les rênes|takes the helm|promu\w*|promoted|succède|succeeds|intérim|interim)\b", re.I)
# Role groups: a new holder of the contact's role matters; of another role, not.
ROLES: dict[str, list[str]] = {
    "CEO": ["ceo", "chief executive", "pdg", "p dg", "dg", "directeur general",
            "directrice generale", "managing director", "president directeur"],
    "CTO": ["cto", "chief technology", "chief technical", "directeur technique",
            "directrice technique"],
    "COO": ["coo", "chief operating", "directeur des operations", "directrice des operations"],
    "CPO": ["cpo", "chief product", "directeur produit", "directrice produit"],
    "CDO": ["cdo", "chief data", "directeur data", "directrice data", "head of data"],
}


def _has(folded: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", folded) is not None


def role_group(title: str | None) -> str | None:
    folded = _norm(title or "")
    for group, terms in ROLES.items():
        if any(_has(folded, t) for t in terms):
            return group
    return None


def _names(contact: Contact) -> tuple[str, str]:
    full = _norm(contact.full_name)
    last = _norm(contact.last_name or contact.full_name.split()[-1])
    return full, last


def _mentions(sentence: str, full: str, last: str, page_names_them: bool) -> bool:
    """The sentence is about them: the full name, or the last name on a page that names them."""
    folded = _norm(sentence)
    return _has(folded, full) or (page_names_them and len(last) >= 4 and _has(folded, last))


def _key(contact_id: int, url: str, kind: str) -> str:
    return hashlib.sha256(f"{contact_id}|{url}|{kind}".encode()).hexdigest()[:24]


def findings(contact: Contact, company: Company, pages: list[CompanyPage]) -> list[dict[str, Any]]:
    """What the pages say about the contact leaving (pure: no database writes)."""
    full, last = _names(contact)
    group = role_group(contact.title)
    company_name = _norm(company.name)
    out: list[dict[str, Any]] = []
    for page in pages:
        text = f"{page.title}\n{page.text}"
        folded_page = _norm(text)
        names_them = _has(folded_page, full)
        seen: set[str] = set()
        for sentence in _SENTENCE.split(text):
            sentence = sentence.strip()
            if len(sentence) < 12 or sentence in seen:
                continue
            seen.add(sentence)
            about_them = _mentions(sentence, full, last, names_them)
            if about_them and (m := _LEFT.search(sentence)):
                out.append({"kind": "left", "reason": f"“{m.group(0)}” next to their name",
                            "excerpt": sentence[:400], "page": page})
                break
            folded = _norm(sentence)
            role = next((t for t in ROLES[group] if _has(folded, t)), None) if group else None
            if role and not about_them and (_APPOINTED.search(sentence) or re.search(
                    rf"\b(?:new|nouveau|nouvelle)\s+{re.escape(role)}\b", folded)) \
                    and (_has(folded, company_name) or _has(folded_page, company_name)):
                out.append({"kind": "new_holder", "reason": f"a new {group} is named at "
                            f"{company.name}", "excerpt": sentence[:400], "page": page})
                break
    return out


def contacts_to_check(s: Session, company_id: int) -> list[Contact]:
    """The contacts your open jobs at this company would write to."""
    rows = s.exec(select(Contact).join(Application, col(Application.contact_id) == col(Contact.id))
                  .join(Job, col(Job.id) == col(Application.job_id))
                  .where(Job.company_id == company_id,
                         col(Application.stage).not_in([Stage.closed]))).all()
    return list({c.id: c for c in rows}.values())


def scan(s: Session, company_id: int, contacts: list[Contact] | None = None) -> list[ContactAlert]:
    """Record an alert for every sign found in the company's stored pages (idempotent: an alert
    found again keeps its state, dismissed included). Returns the active alerts."""
    company = s.get(Company, company_id)
    if company is None:
        return []
    contacts = contacts if contacts is not None else contacts_to_check(s, company_id)
    pages = list(s.exec(select(CompanyPage).where(CompanyPage.company_id == company_id)
                        .order_by(col(CompanyPage.id))).all())
    for contact in contacts:
        for f in findings(contact, company, pages):
            page = f["page"]
            key = _key(contact.id, page.url, f["kind"])
            if s.exec(select(ContactAlert).where(ContactAlert.key == key)).first():
                continue
            s.add(ContactAlert(contact_id=contact.id, company_id=company_id, key=key,
                               kind=f["kind"], reason=f["reason"], excerpt=f["excerpt"],
                               source_url=page.url, source_title=page.title[:300],
                               page_date=page.page_date))
    s.flush()
    return [a for c in contacts for a in active(s, c.id)]


def fetch_contact_news(s: Session, company_id: int, fetcher: Any, language: str,
                       news_settings: dict[str, Any],
                       contacts: list[Contact] | None = None) -> list[str]:
    """Search the news for each contact's name (with the company name) and store what it finds
    as company pages (kind "contact_news"). Returns warnings."""
    company = s.get(Company, company_id)
    search: Callable[..., Any] | None = getattr(fetcher, "person_news", None)
    if company is None or search is None:
        return []
    warnings: list[str] = []
    known = {p.url for p in s.exec(select(CompanyPage).where(
        CompanyPage.company_id == company_id)).all()}
    for contact in contacts if contacts is not None else contacts_to_check(s, company_id):
        if len(re.sub(r"\W", "", contact.full_name.split()[-1])) <= 1:
            warnings.append(f"No news search for {contact.full_name}: only an initial for the "
                            "last name (the company's pages are still scanned)")
            continue
        sources, w = search(contact.full_name, company.name, language, news_settings)
        warnings += w
        for src in sources:
            if src.url in known:
                continue
            known.add(src.url)
            s.add(CompanyPage(company_id=company_id, url=src.url, kind="contact_news",
                              title=src.title, text=src.text, page_date=src.page_date))
    s.flush()
    return warnings


def active(s: Session, contact_id: int) -> list[ContactAlert]:
    return list(s.exec(select(ContactAlert).where(
        ContactAlert.contact_id == contact_id, col(ContactAlert.dismissed_at).is_(None))
        .order_by(col(ContactAlert.page_date).desc(), col(ContactAlert.id).desc())).all())


def next_contact(s: Session, app: Application) -> Contact | None:
    """The next contact by the ranking rule: the company's best-ranked contact with an email,
    other than the current one and anyone with an active alert."""
    from app.services.contacts import ranked, ranking_settings

    job = s.get(Job, app.job_id)
    if job is None:
        return None
    flagged = {a.contact_id for a in s.exec(select(ContactAlert).where(
        ContactAlert.company_id == job.company_id,
        col(ContactAlert.dismissed_at).is_(None))).all()}
    pool = [c for c in s.exec(select(Contact).where(Contact.company_id == job.company_id)).all()
            if c.id != app.contact_id and c.id not in flagged and c.email]
    order = ranking_settings(s).order_for(s.get(Company, job.company_id), job)
    return ranked(pool, order)[0] if pool else None


def dismiss(s: Session, alert: ContactAlert, dismissed: bool = True) -> ContactAlert:
    alert.dismissed_at = utcnow() if dismissed else None
    s.add(alert)
    return alert
