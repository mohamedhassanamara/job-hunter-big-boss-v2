"""Apollo CSV import: preview, column mapping, dedupe (email, then company + name), batches.

The parsing and row mapping are pure (tested offline); `run_import` writes in batches of 500 and
records progress on a `contact_import` row so the UI can poll it. Re-running is safe: a known
contact is only filled in, never duplicated.
"""

import csv
import hashlib
import io
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models import Company, CompanyAlias, Contact, ContactImport
from app.models.base import utcnow
from app.models.enums import ContactSource, ImportStatus
from app.services import dnc
from app.services.contacts import normalize_person, rank, role_ranking
from app.services.dedupe import normalize_company

BATCH = 500
FIELDS = ["first_name", "last_name", "full_name", "title", "email", "company", "domain",
          "linkedin_url"]
# Our field -> header names Apollo exports commonly use (lowercased).
FIELD_ALIASES: dict[str, list[str]] = {
    "first_name": ["first name", "first_name", "firstname", "prenom", "prénom"],
    "last_name": ["last name", "last_name", "lastname", "surname", "nom"],
    "full_name": ["name", "full name", "full_name", "contact name"],
    "title": ["title", "job title", "position", "poste"],
    "email": ["email", "email address", "work email", "e-mail", "business email"],
    "company": ["company", "company name", "organization name", "account name", "organization"],
    "domain": ["website", "company website", "domain", "company domain"],
    "linkedin_url": ["person linkedin url", "linkedin url", "linkedin", "linkedin profile"],
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContactImportError(ValueError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_csv(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ContactImportError("The file has no header row")
    headers = [h for h in reader.fieldnames if h is not None]
    rows = [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in reader]
    return headers, rows


def detect_mapping(headers: list[str]) -> dict[str, str | None]:
    lower = {h.lower().strip(): h for h in headers}
    return {f: next((lower[a] for a in FIELD_ALIASES[f] if a in lower), None) for f in FIELDS}


@dataclass
class ContactRow:
    first_name: str | None
    last_name: str | None
    full_name: str
    title: str | None
    email: str | None  # valid and lowercased, or None
    company: str
    domain: str | None
    linkedin_url: str | None


def map_row(row: dict[str, str], mapping: dict[str, str | None]) -> ContactRow | str:
    """A clean row, or the reason it's skipped."""
    def get(f: str) -> str:
        col = mapping.get(f)
        return " ".join((row.get(col) or "").split()) if col else ""

    first, last = get("first_name"), get("last_name")
    full = get("full_name") or " ".join(p for p in (first, last) if p)
    email = get("email").lower()
    if email and not _EMAIL.match(email):
        email = ""
    company = get("company")
    if not company:
        return "no_company"
    if not full and not email:
        return "no_name_or_email"
    if not full:  # an email without a name: keep it, named after the address
        full = email.split("@")[0]
    domain = get("domain").lower().removeprefix("https://").removeprefix("http://")
    return ContactRow(first or None, last or None, full, get("title") or None, email or None,
                      company, domain.removeprefix("www.").strip("/") or None,
                      get("linkedin_url") or None)


# -------------------------------------------------------------------------------- backups


def backup_db(engine: Engine, label: str, backups: Path | None = None) -> Path | None:
    """SQLite online backup (safe while the app runs, WAL included). None for non-file DBs."""
    db = engine.url.database
    if not db or db == ":memory:":
        return None
    src = Path(db)
    folder = backups or src.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{src.stem}-before-{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    with sqlite3.connect(src) as a, sqlite3.connect(target) as b:
        a.backup(b)
    return target


# --------------------------------------------------------------------------------- import


def already_imported(s: Session, digest: str) -> ContactImport | None:
    return s.exec(select(ContactImport).where(ContactImport.file_sha256 == digest,
                                              ContactImport.status == ImportStatus.done)).first()


def begin(s: Session, filename: str, digest: str, total: int,
          mapping: dict[str, str | None]) -> ContactImport:
    row = ContactImport(filename=filename, file_sha256=digest, total=total, mapping=mapping)
    s.add(row)
    s.commit()
    s.refresh(row)
    return row


def _fill(contact: Contact, r: ContactRow, email_free: bool) -> bool:
    """Fill empty fields only (never overwrite what's there). True when something changed.
    The email is only added when no other contact has it (`email_free`)."""
    changed = False
    fills = [("first_name", r.first_name), ("last_name", r.last_name), ("title", r.title),
             ("linkedin_url", r.linkedin_url)]
    if email_free:
        fills += [("email", r.email), ("email_normalized", r.email)]
    for attr, value in fills:
        if value and not getattr(contact, attr):
            setattr(contact, attr, value)
            changed = True
    return changed


def run_import(engine: Engine, import_id: int, rows: list[dict[str, str]],
               mapping: dict[str, str | None]) -> ContactImport:
    """Process `rows` in batches, updating the import row's counters after each batch."""
    with Session(engine) as s:
        ranking = role_ranking(s)
        companies = {c.normalized_name: c.id for c in s.exec(select(Company)).all()}
        companies.update({a.normalized_name: a.company_id  # merged-away spellings
                          for a in s.exec(select(CompanyAlias)).all()})
        by_email = {c.email_normalized: c.id for c in s.exec(select(Contact)).all()
                    if c.email_normalized}
        by_name = {(c.company_id, c.normalized_name): c.id for c in s.exec(select(Contact)).all()
                   if c.normalized_name}
        dnc_rules = dnc.rules(s)
    seen: set[tuple[Any, ...]] = set()
    counts = {"created": 0, "updated": 0, "skipped": 0, "companies_created": 0}
    reasons: dict[str, int] = {}

    def skip(reason: str) -> None:
        counts["skipped"] += 1
        reasons[reason] = reasons.get(reason, 0) + 1

    try:
        for start in range(0, len(rows), BATCH):
            with Session(engine) as s:
                for raw in rows[start:start + BATCH]:
                    r = map_row(raw, mapping)
                    if isinstance(r, str):
                        skip(r)
                        continue
                    if r.email and dnc.rule_for(r.email, dnc_rules):
                        skip("do_not_contact")  # on the do-not-contact list: never imported
                        continue
                    norm_company = normalize_company(r.company)
                    norm_name = normalize_person(r.full_name)
                    key = ("email", r.email) if r.email else ("name", norm_company, norm_name)
                    if key in seen:
                        skip("duplicate_in_file")
                        continue
                    seen.add(key)
                    company_id = companies.get(norm_company)
                    if company_id is None:
                        company = Company(name=r.company, normalized_name=norm_company,
                                          domain=r.domain)
                        s.add(company)
                        s.flush()
                        company_id = companies[norm_company] = company.id
                        counts["companies_created"] += 1
                    existing_id = (by_email.get(r.email) if r.email else None) or \
                        by_name.get((company_id, norm_name))
                    if existing_id is not None:
                        contact = s.get(Contact, existing_id)
                        if contact is not None and contact.do_not_contact:
                            skip("do_not_contact")  # never touched, never revived
                            continue
                        if contact is not None and contact.left_at is not None:
                            skip("left")
                            continue
                        free = bool(r.email) and r.email not in by_email
                        if contact is not None and _fill(contact, r, free):
                            contact.role_rank = rank(contact.title, ranking)[0]
                            s.add(contact)
                            counts["updated"] += 1
                            if r.email:
                                by_email[r.email] = contact.id
                        else:
                            skip("already_known")
                        continue
                    contact = Contact(
                        company_id=company_id, full_name=r.full_name, first_name=r.first_name,
                        last_name=r.last_name, normalized_name=norm_name, title=r.title,
                        email=r.email, email_normalized=r.email, linkedin_url=r.linkedin_url,
                        source=ContactSource.apollo_dump, imported_batch=str(import_id),
                        role_rank=rank(r.title, ranking)[0])
                    s.add(contact)
                    s.flush()
                    counts["created"] += 1
                    if r.email:
                        by_email[r.email] = contact.id
                    by_name[(company_id, norm_name)] = contact.id
                run = s.get(ContactImport, import_id)
                assert run is not None
                run.processed = min(len(rows), start + BATCH)
                run.created, run.updated = counts["created"], counts["updated"]
                run.skipped, run.companies_created = counts["skipped"], counts["companies_created"]
                run.skipped_reasons = dict(reasons)
                s.add(run)
                s.commit()
        status, error = ImportStatus.done, None
    except Exception as exc:  # committed batches stay; re-running fills in the rest
        status, error = ImportStatus.failed, f"{type(exc).__name__}: {exc}"
    with Session(engine) as s:
        run = s.get(ContactImport, import_id)
        assert run is not None
        run.status, run.error, run.finished_at = status, error, utcnow()
        s.add(run)
        s.commit()
        s.refresh(run)
        return run
