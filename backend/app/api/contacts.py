import csv
import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlmodel import col, func, select

from app.api.deps import SessionDep, get_or_404
from app.models import Application, AppSetting, Company, Contact, Job
from app.models.enums import ContactTier, Stage
from app.schemas.contacts import (
    CompanyDetail,
    CompanyListItem,
    ImportPreview,
    ImportResult,
    LookupItem,
    LookupQueue,
)
from app.services.views import contact_out, latest_fits, related_jobs

router = APIRouter(tags=["contacts"])

# Our field -> header names Apollo exports commonly use.
FIELD_ALIASES: dict[str, list[str]] = {
    "full_name": ["name", "full name", "full_name"],
    "first_name": ["first name", "first_name"],
    "last_name": ["last name", "last_name"],
    "title": ["title", "job title"],
    "email": ["email", "email address", "work email"],
    "company": ["company", "company name", "organization name", "account name"],
    "domain": ["website", "company website", "domain", "company domain"],
    "linkedin_url": ["person linkedin url", "linkedin url", "linkedin"],
}


def _company_items(session: SessionDep, companies: list[Company]) -> list[CompanyListItem]:
    ids = [c.id for c in companies]
    counts = dict(
        session.exec(
            select(Contact.company_id, func.count())
            .where(col(Contact.company_id).in_(ids))
            .group_by(Contact.company_id)
        ).all()
    )
    open_jobs = dict(
        session.exec(
            select(Job.company_id, func.count())
            .join(Application, col(Application.job_id) == col(Job.id))
            .where(
                col(Job.company_id).in_(ids),
                Application.stage != Stage.closed,
                col(Job.duplicate_of_id).is_(None),
            )
            .group_by(Job.company_id)
        ).all()
    )
    return [
        CompanyListItem(
            id=c.id,
            name=c.name,
            domain=c.domain,
            contact_count=counts.get(c.id, 0),
            open_jobs=open_jobs.get(c.id, 0),
            contacted_at=c.contacted_at,
        )
        for c in companies
    ]


@router.get("/companies", response_model=list[CompanyListItem])
def list_companies(session: SessionDep, q: str | None = None) -> list[CompanyListItem]:
    stmt = select(Company).order_by(col(Company.name))
    if q:
        stmt = stmt.where(col(Company.name).icontains(q))
    return _company_items(session, list(session.exec(stmt).all()))


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int, session: SessionDep) -> CompanyDetail:
    company = get_or_404(session, Company, company_id, "Company")
    base = _company_items(session, [company])[0]
    contacts = session.exec(
        select(Contact).where(Contact.company_id == company.id).order_by(col(Contact.full_name))
    ).all()
    jobs = session.exec(
        select(Job).where(Job.company_id == company.id, col(Job.duplicate_of_id).is_(None))
    ).all()
    return CompanyDetail(
        **base.model_dump(),
        website=company.website,
        contacts=[contact_out(c) for c in contacts],
        jobs=related_jobs(session, jobs),
    )


@router.post("/contacts/import/preview", response_model=ImportPreview)
async def import_preview(file: UploadFile = File(...)) -> ImportPreview:
    """Parse the uploaded CSV locally and propose a column mapping. Nothing is stored."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(422, "The file has no header row")
    rows = list(reader)
    lower = {h.lower().strip(): h for h in reader.fieldnames}
    mapping = {
        field: next((lower[a] for a in aliases if a in lower), None)
        for field, aliases in FIELD_ALIASES.items()
    }
    return ImportPreview(
        filename=file.filename or "upload.csv",
        total_rows=len(rows),
        columns=list(reader.fieldnames),
        mapping=mapping,
        sample=[{k: (v or "") for k, v in r.items() if k} for r in rows[:5]],
    )


@router.post("/contacts/import", response_model=ImportResult)
async def import_contacts(file: UploadFile = File(...)) -> ImportResult:
    """Phase 0 mock: reports what *would* happen; no rows are written."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    with_email = sum(1 for r in rows if any("@" in (v or "") for v in r.values()))
    return ImportResult(
        created=int(with_email * 0.8),
        updated=with_email - int(with_email * 0.8),
        skipped=len(rows) - with_email,
    )


@router.get("/contacts/lookups", response_model=LookupQueue)
def lookup_queue(session: SessionDep) -> LookupQueue:
    setting = session.exec(select(AppSetting).where(AppSetting.key == "lookup")).first()
    cfg = setting.value if setting else {"daily_cap": 10, "used_today": 0}
    apps = session.exec(
        select(Application).where(
            Application.contact_tier == ContactTier.lookup_queued, Application.stage != Stage.closed
        )
    ).all()
    jobs = {
        j.id: j
        for j in session.exec(select(Job).where(col(Job.id).in_([a.job_id for a in apps]))).all()
    }
    companies = {
        c.id: c
        for c in session.exec(
            select(Company).where(col(Company.id).in_({j.company_id for j in jobs.values()}))
        ).all()
    }
    fits = latest_fits(session, jobs.keys())
    return LookupQueue(
        daily_cap=cfg.get("daily_cap", 10),
        used_today=cfg.get("used_today", 0),
        items=[
            LookupItem(
                application_id=a.id,
                job_id=a.job_id,
                job_title=jobs[a.job_id].title,
                company_name=companies[jobs[a.job_id].company_id].name,
                fit=fits[a.job_id].score if a.job_id in fits else None,
                queued_at=a.updated_at,
            )
            for a in apps
        ],
    )
