"""Do-not-contact: people (and whole domains) nobody may write to.

One rule for the whole app: `blocked_reason` says why a contact or an address is off limits, or
None. Imports, drafting, approval, LinkedIn notes, the send queue and the contact finders all ask
it. Only you lift it (`clear`, from the contact card): no automated flow ever revives a contact
marked do-not-contact. No network, no model calls.
"""

import re

from sqlmodel import Session, col, select

from app.models import Contact, DoNotContactRule
from app.models.base import utcnow

_SPLIT = re.compile(r"[\s,;]+")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


class DncError(ValueError):
    pass


def parse(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Pasted emails and domains → ([(kind, value)], [what was not understood])."""
    rules: list[tuple[str, str]] = []
    bad: list[str] = []
    for raw in _SPLIT.split(text or ""):
        item = raw.strip().strip("<>\"'").lower()
        if not item:
            continue
        item = item.removeprefix("mailto:").removeprefix("https://").removeprefix("http://")
        item = item.split("/")[0].removeprefix("www.")
        if item.startswith("@"):
            item = item[1:]
        if _EMAIL.match(item):
            kind = "email"
        elif _DOMAIN.match(item):
            kind = "domain"
        else:
            bad.append(raw)
            continue
        if (kind, item) not in rules:
            rules.append((kind, item))
    return rules, bad


def _domain_of(email: str | None) -> str:
    return (email or "").rpartition("@")[2].strip().lower()


def rules(s: Session) -> list[DoNotContactRule]:
    return list(s.exec(select(DoNotContactRule).order_by(col(DoNotContactRule.id).desc())).all())


def rule_for(email: str | None, all_rules: list[DoNotContactRule]) -> DoNotContactRule | None:
    """The rule that covers this address: the exact email, or its domain (subdomains included)."""
    address = (email or "").strip().lower()
    if not address or "@" not in address:
        return None
    domain = _domain_of(address)
    for r in all_rules:
        if r.kind == "email" and r.value == address:
            return r
        if r.kind == "domain" and (domain == r.value or domain.endswith("." + r.value)):
            return r
    return None


def _why(reason: str | None) -> str:
    return f" ({reason})" if reason else ""


def blocked_reason(s: Session, contact: Contact | None = None, email: str | None = None,
                   *, all_rules: list[DoNotContactRule] | None = None) -> str | None:
    """Why this person or address may not be contacted, in words, or None."""
    if contact is not None and contact.do_not_contact:
        return f"{contact.full_name} asked not to be contacted{_why(contact.dnc_reason)}"
    all_rules = rules(s) if all_rules is None else all_rules
    for address in {a for a in ((contact.email if contact else None), email) if a}:
        r = rule_for(address, all_rules)
        if r is not None:
            what = "this address" if r.kind == "email" else f"everyone at {r.value}"
            return f"Do-not-contact list: {what}{_why(r.reason)}"
    return None


def flag(s: Session, contact: Contact, reason: str | None) -> Contact:
    contact.do_not_contact = True
    contact.dnc_reason = (reason or "").strip() or None
    contact.dnc_at = utcnow()
    s.add(contact)
    return contact


def clear(s: Session, contact: Contact) -> Contact:
    """Lift the flag. Only the user's own click does this."""
    contact.do_not_contact = False
    contact.dnc_reason = None
    contact.dnc_at = None
    s.add(contact)
    return contact


def apply_rules(s: Session) -> int:
    """Flag every existing contact a rule covers. Returns how many were newly flagged."""
    all_rules = rules(s)
    if not all_rules:
        return 0
    n = 0
    for c in s.exec(select(Contact).where(col(Contact.email_normalized).is_not(None),
                                          col(Contact.do_not_contact).is_(False))).all():
        r = rule_for(c.email_normalized, all_rules)
        if r is not None:
            flag(s, c, r.reason or f"On the do-not-contact list ({r.value})")
            n += 1
    return n


def add_rules(s: Session, text: str, reason: str = "") -> dict[str, object]:
    """Add pasted emails/domains (several at once). Existing contacts they cover are flagged."""
    parsed, bad = parse(text)
    if not parsed and not bad:
        raise DncError("Paste at least one email address or domain")
    have = {r.value for r in rules(s)}
    added = 0
    for kind, value in parsed:
        if value in have:
            continue
        s.add(DoNotContactRule(kind=kind, value=value, reason=reason.strip()))
        added += 1
    s.flush()
    flagged = apply_rules(s)
    return {"added": added, "already_listed": len(parsed) - added, "flagged_contacts": flagged,
            "not_understood": bad}


def remove_rule(s: Session, rule: DoNotContactRule) -> None:
    """Remove the rule only: contacts already flagged stay flagged until you clear them."""
    s.delete(rule)
