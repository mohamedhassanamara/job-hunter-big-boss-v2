"""Fill the Get contact form from a block of text you copied (the Apollo extension's panel, a
LinkedIn profile header, an email signature). Pure: nothing is saved, you confirm the fields.

What it looks for: the email (a work address before a personal one), a LinkedIn profile URL, the
person's name (the first line that looks like a name), their title ("CTO at Zaion", "Directeur
technique chez Nomadia", or a line with a role word) and the company named with it.
"""

import re
from dataclasses import asdict, dataclass, field

_EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%.]+)/?",
                       re.I)
_FREEMAIL = {"gmail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr", "outlook.com",
             "outlook.fr", "live.com", "icloud.com", "proton.me", "protonmail.com", "gmx.de",
             "orange.fr", "free.fr", "wanadoo.fr", "laposte.net", "web.de"}
_AT = re.compile(r"^(?P<title>.+?)\s+(?:at|chez|@|bei|·|\|)\s+(?P<company>[^·|]+?)\s*$", re.I)
_ROLE = re.compile(
    r"\b(?:ceo|cto|coo|cpo|cfo|cdo|cio|vp|svp|evp|head|director|directeur|directrice|manager|"
    r"lead|leader|founder|co-founder|cofounder|fondateur|fondatrice|président\w*|president|"
    r"chief|engineer|ingénieur\w*|ingenieur\w*|responsable|recruiter|recruteur|recruteuse|"
    r"talent|hr|rh|partner|owner|gérant\w*|principal|architect\w*|scientist|analyst|"
    r"developer|développeur\w*|officer|dg|pdg)\b", re.I)
# Lines that are never the name or the title.
_NOISE = re.compile(
    r"^(?:verified|unverified|likely to engage|·?\s*\d(?:st|nd|rd|th)\+?|message|follow|more|"
    r"connect|save|contact info|view profile|email|phone|mobile|work|direct|corporate|"
    r"add to sequence|access email|copy|show more|see all|\d+\+? connections?|"
    r"\d+\+? relations?|\d+ followers?|abonnés?|open to work|he/him|she/her|they/them|"
    r"il/lui|elle/elle)$", re.I)
_PHONE = re.compile(r"^[+()\d][\d\s().-]{6,}$")
_NAME = re.compile(r"^[A-ZÀ-ÖØ-Þ][\w'’.-]*(?:\s+(?:de|du|des|van|von|der|da|di|la|le|el|al|"
                   r"[A-ZÀ-ÖØ-Þ][\w'’.-]*)){1,3}$")


@dataclass
class Parsed:
    full_name: str | None = None
    title: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    company: str | None = None  # the company named next to the title (to compare with the job's)
    notes: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return asdict(self)


def _clean(line: str) -> str:
    line = re.sub(r"[​‎‏﻿]", "", line)
    line = re.sub(r"\s+", " ", line).strip(" \t•·|-–—")
    return line


def _pick_email(emails: list[str]) -> str | None:
    work = [e for e in emails if e.split("@")[1].lower() not in _FREEMAIL
            and not re.match(r"(?:no-?reply|info|contact|hello|jobs|careers|rh|hr)@", e, re.I)]
    return (work or emails or [None])[0]


def parse(text: str) -> Parsed:
    out = Parsed()
    emails = list(dict.fromkeys(m.group(0).strip(".") for m in _EMAIL.finditer(text)))
    out.email = _pick_email(emails)
    if len(emails) > 1:
        out.notes.append(f"{len(emails)} emails found: kept {out.email}")
    if m := _LINKEDIN.search(text):
        out.linkedin_url = f"https://www.linkedin.com/in/{m.group(1).rstrip('/.')}"
    lines = []
    for raw in text.splitlines():
        line = _clean(raw)
        if not line or _EMAIL.search(line) or _LINKEDIN.search(line) or "http" in line.lower():
            continue
        if _NOISE.match(line) or _PHONE.match(line) or len(line) > 140:
            continue
        lines.append(line)
    name_at = None
    for i, line in enumerate(lines):
        words = line.split()
        if 2 <= len(words) <= 5 and _NAME.match(line) and not _ROLE.search(line) \
                and not _AT.match(line) and "," not in line:
            out.full_name, name_at = line, i
            break
    for line in lines[(name_at + 1) if name_at is not None else 0:]:
        if m := _AT.match(line):
            if _ROLE.search(m.group("title")) or len(m.group("title").split()) <= 5:
                out.title, out.company = m.group("title").strip(), m.group("company").strip()
                break
        elif _ROLE.search(line) and "," not in line[:20]:
            out.title = line
            break
    if out.full_name is None and out.email:  # jean.dupont@acme.fr → Jean Dupont
        local = out.email.split("@")[0]
        parts = [p for p in re.split(r"[._-]", local) if p.isalpha() and len(p) > 1]
        if len(parts) >= 2:
            out.full_name = " ".join(p.capitalize() for p in parts[:3])
            out.notes.append("Name guessed from the email: check it")
    return out
