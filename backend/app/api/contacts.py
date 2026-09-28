import json
import threading
import time
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlmodel import Session, col, func, select

from app.api.deps import EngineDep, SessionDep, get_or_404
from app.models import (
    Application,
    AppSetting,
    Company,
    CompanyLookup,
    Contact,
    ContactImport,
    Job,
)
from app.models.enums import ContactSource, Stage
from app.schemas.contacts import (
    CompanyDetail,
    CompanyJob,
    CompanyList,
    CompanyListItem,
    FilePreview,
    ImportRunOut,
    LookupFound,
    LookupItem,
    LookupNotFound,
    LookupQueue,
    MatchReport,
    NewContact,
)
from app.schemas.jobs import JobDetail
from app.services import contacts, contacts_import
from app.services.pipeline import stage_label
from app.services.views import contact_out, fit_brief, job_detail, latest_fits

router = APIRouter(tags=["contacts"])

# One backup covers a burst of imports (several files in a row).
_BACKUP_WINDOW_S = 15 * 60
_last_backup: dict[str, tuple[float, str]] = {}

# ------------------------------------------------------------------------------ companies


def _company_items(s: Session, companies: list[Company]) -> list[CompanyListItem]:
    ids = [c.id for c in companies]
    counts = dict(s.exec(select(Contact.company_id, func.count())
                         .where(col(Contact.company_id).in_(ids))
                         .group_by(Contact.company_id)).all())
    open_jobs = dict(s.exec(
        select(Job.company_id, func.count())
        .join(Application, col(Application.job_id) == col(Job.id))
        .where(col(Job.company_id).in_(ids), Application.stage != Stage.closed,
               col(Job.duplicate_of_id).is_(None))
        .group_by(Job.company_id)).all())
    lookups = {lk.company_id: lk.status for lk in s.exec(
        select(CompanyLookup).where(col(CompanyLookup.company_id).in_(ids))).all()}
    by_company: dict[int, list[Contact]] = defaultdict(list)
    for c in s.exec(select(Contact).where(col(Contact.company_id).in_(ids))).all():
        by_company[c.company_id].append(c)
    out = []
    for c in companies:
        best = contacts.best_contact(by_company.get(c.id, []))
        out.append(CompanyListItem(
            id=c.id, name=c.name, domain=c.domain, contact_count=counts.get(c.id, 0),
            open_jobs=open_jobs.get(c.id, 0), contacted_at=c.contacted_at,
            lookup_status=lookups.get(c.id),
            best_contact=f"{best.full_name}{f' · {best.title}' if best.title else ''}"
            if best else None))
    return out


@router.get("/companies", response_model=CompanyList)
def list_companies(
    session: SessionDep, q: str | None = None,
    filter: Literal["all", "with_jobs", "has_contacts", "needs_lookup", "no_contact"] = "with_jobs",
    limit: int = 100, offset: int = 0,
) -> CompanyList:
    """Companies with open jobs first (the ones that matter), then the imported ones."""
    stmt = select(Company)
    if q:
        stmt = stmt.where(col(Company.name).icontains(q))
    with_jobs = set(session.exec(
        select(Job.company_id).join(Application, col(Application.job_id) == col(Job.id))
        .where(Application.stage != Stage.closed, col(Job.duplicate_of_id).is_(None))).all())
    has_contacts = set(session.exec(select(Contact.company_id)).all())
    statuses = {lk.company_id: lk.status for lk in session.exec(select(CompanyLookup)).all()}
    companies = list(session.exec(stmt.order_by(col(Company.name))).all())
    keep = {
        "all": lambda c: True,
        "with_jobs": lambda c: c.id in with_jobs,
        "has_contacts": lambda c: c.id in has_contacts,
        "needs_lookup": lambda c: c.id in with_jobs and c.id not in has_contacts
        and statuses.get(c.id) in (None, "queued", "skipped"),
        "no_contact": lambda c: c.id in with_jobs and statuses.get(c.id) == "not_found",
    }[filter]
    companies = [c for c in companies if keep(c)]
    return CompanyList(items=_company_items(session, companies[offset:offset + limit]),
                       total=len(companies))


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, session: SessionDep) -> CompanyDetail:
    company = get_or_404(session, Company, company_id, "Company")
    base = _company_items(session, [company])[0]
    ranking = contacts.role_ranking(session)
    people = sorted(session.exec(select(Contact).where(Contact.company_id == company.id)).all(),
                    key=lambda c: (c.role_rank, c.email is None, c.full_name))
    rows = session.exec(
        select(Application, Job).join(Job, col(Job.id) == col(Application.job_id))
        .where(Job.company_id == company.id, col(Job.duplicate_of_id).is_(None))
        .order_by(col(Application.stage_changed_at).desc())).all()
    fits = latest_fits(session, [j.id for _, j in rows])
    return CompanyDetail(
        **base.model_dump(), website=company.website,
        contacts=[contact_out(c, ranking) for c in people],
        jobs=[CompanyJob(application_id=a.id, job_id=j.id, title=j.title, stage=a.stage,
                         stage_label=stage_label(a.stage, a.route), route=a.route,
                         contact_tier=a.contact_tier, contact_id=a.contact_id,
                         fit=fit_brief(fits.get(j.id))) for a, j in rows],
    )


@router.post("/companies/{company_id}/contacts", response_model=CompanyDetail, status_code=201)
def add_company_contact(company_id: int, body: NewContact, session: SessionDep) -> CompanyDetail:
    get_or_404(session, Company, company_id, "Company")
    try:
        contacts.add_contact(session, company_id, full_name=body.full_name, title=body.title,
                             email=body.email, linkedin_url=body.linkedin_url,
                             source=ContactSource.manual, notes=body.notes)
    except contacts.ContactError as exc:
        raise HTTPException(422, str(exc)) from exc
    contacts.resolve_company(session, company_id)
    session.commit()
    return get_company(company_id, session)


# --------------------------------------------------------------------------------- import


def _run_out(r: ContactImport, backup: str | None = None) -> ImportRunOut:
    out = ImportRunOut.model_validate(r, from_attributes=True)
    out.backup_path = backup
    return out


@router.post("/contacts/import/preview", response_model=list[FilePreview])
async def import_preview(session: SessionDep,
                         files: list[UploadFile] = File(...)) -> list[FilePreview]:
    """Parse the uploaded CSVs and propose a column mapping. Nothing is stored."""
    out = []
    for f in files:
        raw = await f.read()
        try:
            headers, rows = contacts_import.parse_csv(raw)
        except contacts_import.ContactImportError as exc:
            raise HTTPException(422, f"{f.filename}: {exc}") from exc
        digest = contacts_import.sha256(raw)
        done = contacts_import.already_imported(session, digest)
        out.append(FilePreview(filename=f.filename or "upload.csv", sha256=digest,
                               total_rows=len(rows), columns=headers,
                               mapping=contacts_import.detect_mapping(headers),
                               sample=rows[:5],
                               already_imported_at=done.finished_at if done else None))
    return out


@router.post("/contacts/import", response_model=ImportRunOut, status_code=202)
async def import_contacts(session: SessionDep, engine: EngineDep, file: UploadFile = File(...),
                          mapping: str = Form(...), force: bool = Form(False)) -> ImportRunOut:
    """Start importing one file in the background (poll GET /contacts/imports/{id}). The
    database is backed up first (once per 15 minutes of imports)."""
    raw = await file.read()
    try:
        headers, rows = contacts_import.parse_csv(raw)
        columns = json.loads(mapping)
    except (contacts_import.ContactImportError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if not isinstance(columns, dict) or not columns.get("company"):
        raise HTTPException(422, "Map the Company column")
    if not (columns.get("email") or columns.get("full_name") or columns.get("first_name")):
        raise HTTPException(422, "Map a name or an email column")
    unknown = [v for v in columns.values() if v and v not in headers]
    if unknown:
        raise HTTPException(422, f"Unknown columns: {', '.join(unknown)}")
    digest = contacts_import.sha256(raw)
    done = contacts_import.already_imported(session, digest)
    if done and not force:
        raise HTTPException(409, f"{file.filename} was already imported on "
                                 f"{done.finished_at:%d %b %Y}; re-import only fills gaps")
    key = str(engine.url)
    last = _last_backup.get(key)
    if last is None or time.time() - last[0] > _BACKUP_WINDOW_S:
        path = contacts_import.backup_db(engine, "import")
        if path is not None:
            last = _last_backup[key] = (time.time(), str(path))
    run = contacts_import.begin(session, file.filename or "upload.csv", digest, len(rows),
                                {k: v for k, v in columns.items() if v})

    def work() -> None:
        contacts_import.run_import(engine, run.id, rows, run.mapping)
        with Session(engine) as s:  # new contacts: re-match every open job
            contacts.match_all(s)
            s.commit()

    threading.Thread(target=work, name=f"contact-import-{run.id}", daemon=True).start()
    return _run_out(run, last[1] if last else None)


@router.get("/contacts/imports", response_model=list[ImportRunOut])
def list_imports(session: SessionDep) -> list[ImportRunOut]:
    rows = session.exec(select(ContactImport).order_by(col(ContactImport.id).desc())).all()
    return [_run_out(r) for r in rows]


@router.get("/contacts/imports/{import_id}", response_model=ImportRunOut)
def get_import(import_id: int, session: SessionDep) -> ImportRunOut:
    return _run_out(get_or_404(session, ContactImport, import_id, "Import"))


# -------------------------------------------------------------------------------- matching


@router.post("/contacts/match", response_model=MatchReport)
def run_match(session: SessionDep) -> MatchReport:
    out = contacts.match_all(session)
    session.commit()
    return MatchReport(**out)


@router.get("/contacts/match/report", response_model=MatchReport | None)
def match_report(session: SessionDep) -> MatchReport | None:
    row = session.exec(select(AppSetting).where(AppSetting.key == "contacts_last_match")).first()
    return MatchReport(**row.value) if row else None


# --------------------------------------------------------------------------------- lookups


@router.get("/contacts/lookups", response_model=LookupQueue)
def lookup_queue(session: SessionDep, limit: int = 100) -> LookupQueue:
    view = contacts.lookup_queue(session, limit=limit)
    return LookupQueue(
        daily_cap=view.daily_cap, used_today=view.used_today, total=view.total,
        items=[LookupItem(company_id=r.company.id, company_name=r.company.name,
                          domain=r.company.domain, status=r.lookup.status,
                          priority=r.lookup.priority, open_jobs=r.open_jobs,
                          best_job_id=r.best_job_id, best_job_title=r.best_job_title,
                          best_fit=r.best_fit, queued_at=r.lookup.queued_at) for r in view.rows])


@router.post("/contacts/lookups/{company_id}/found", response_model=LookupQueue)
def lookup_found(company_id: int, body: LookupFound, session: SessionDep) -> LookupQueue:
    get_or_404(session, Company, company_id, "Company")
    try:
        contacts.lookup_found(session, company_id, full_name=body.full_name, title=body.title,
                              email=body.email, linkedin_url=body.linkedin_url, notes=body.notes)
    except contacts.ContactError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return lookup_queue(session)


@router.post("/contacts/lookups/{company_id}/not-found", response_model=LookupQueue)
def lookup_not_found(company_id: int, body: LookupNotFound, session: SessionDep) -> LookupQueue:
    get_or_404(session, Company, company_id, "Company")
    contacts.lookup_not_found(session, company_id, body.notes)
    session.commit()
    return lookup_queue(session)


@router.post("/contacts/lookups/{company_id}/skip", response_model=LookupQueue)
def lookup_skip(company_id: int, session: SessionDep) -> LookupQueue:
    get_or_404(session, Company, company_id, "Company")
    contacts.lookup_skip(session, company_id)
    session.commit()
    return lookup_queue(session)


# --------------------------------------------------------------------------------- per job


@router.post("/applications/{app_id}/contact", response_model=JobDetail)
def set_job_contact(app_id: int, session: SessionDep, contact_id: int | None = None,
                    body: NewContact | None = None) -> JobDetail:
    """Your pick for this job (an existing contact, or a new one at its company)."""
    app = get_or_404(session, Application, app_id, "Application")
    job = get_or_404(session, Job, app.job_id)
    if contact_id is not None:
        contact = get_or_404(session, Contact, contact_id, "Contact")
        if contact.company_id != job.company_id:
            raise HTTPException(422, "That contact works at another company")
    elif body is not None:
        try:
            contact = contacts.add_contact(
                session, job.company_id, full_name=body.full_name, title=body.title,
                email=body.email, linkedin_url=body.linkedin_url, source=ContactSource.manual,
                notes=body.notes)
        except contacts.ContactError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        raise HTTPException(422, "Pass contact_id or a new contact")
    contacts.set_contact(session, app, contact)
    session.commit()
    return job_detail(session, job)


@router.delete("/applications/{app_id}/contact", response_model=JobDetail)
def clear_job_contact(app_id: int, session: SessionDep) -> JobDetail:
    app = get_or_404(session, Application, app_id, "Application")
    contacts.clear_contact(session, app)
    session.commit()
    return job_detail(session, get_or_404(session, Job, app.job_id))
