"""Company research: signals (pick/unpick, add your own), the company's website, and the manual
Research now / Refresh signals button: the only trigger besides the email draft step."""

import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import EngineDep, SessionDep, WorkspaceDep, get_or_404
from app.models import AppSetting, Company, CompanySignal
from app.providers.registry import researcher as research_provider
from app.services import research

router = APIRouter(tags=["research"])


class SignalOut(BaseModel):
    id: int
    kind: str
    fact: str
    quote: str
    source_url: str
    page_date: datetime | None
    fetched_at: datetime
    origin: str
    selected: bool


class RunOut(BaseModel):
    id: int
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    pages: int
    signals_kept: int
    signals_dropped: int
    calls: list[dict[str, Any]]
    warnings: list[str]
    error: str | None


class ResearchOut(BaseModel):
    company_id: int
    company_name: str
    site: str | None
    fresh: bool
    refreshed_at: datetime | None
    refresh_days: int
    signals: list[SignalOut]
    last_run: RunOut | None  # the last real run (fetch + model calls)
    reused_at: datetime | None = None  # the last time a draft reused the fresh signals
    progress: dict[str, Any] | None


class SignalPatch(BaseModel):
    selected: bool | None = None
    dismissed: bool | None = None


class SignalIn(BaseModel):
    fact: str
    source_url: str = ""
    kind: str = "other"


class WebsiteIn(BaseModel):
    website: str


class ResearchIn(BaseModel):
    force: bool = True  # Refresh signals; False = reuse fresh ones


_runs: dict[tuple[str, int], dict[str, Any]] = {}
_lock = threading.Lock()


def _out(s: Session, company: Company, workspace: str) -> ResearchOut:
    run = research.last_run(s, company.id, real=True)
    latest = research.last_run(s, company.id)
    with _lock:
        progress = dict(_runs[(workspace, company.id)]) if (workspace, company.id) in _runs \
            else None
    return ResearchOut(
        company_id=company.id, company_name=company.name, site=research.company_site(s, company),
        fresh=research.is_fresh(s, company), refreshed_at=company.research_refreshed_at,
        refresh_days=int(research.research_settings(s)["refresh_days"]),
        signals=[SignalOut.model_validate(x, from_attributes=True)
                 for x in research.signals(s, company.id)],
        last_run=RunOut.model_validate(run, from_attributes=True) if run else None,
        reused_at=latest.started_at if latest and latest.status == "cached" else None,
        progress=progress)


@router.get("/companies/{company_id}/research", response_model=ResearchOut)
def get_research(company_id: int, session: SessionDep, workspace: WorkspaceDep) -> ResearchOut:
    return _out(session, get_or_404(session, Company, company_id, "Company"), workspace)


def _models(session: Session) -> tuple[str, str | None]:
    row = session.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    cfg = (row.value if row else {}).get("research") or {}
    return cfg.get("model") or "gemma4:31b-cloud", cfg.get("fallback", "gemma4:12b")


@router.post("/companies/{company_id}/research", response_model=ResearchOut, status_code=202)
def research_now(company_id: int, body: ResearchIn, session: SessionDep, engine: EngineDep,
                 workspace: WorkspaceDep) -> ResearchOut:
    """The manual trigger (Research now / Refresh signals). Runs in the background; poll GET."""
    company = get_or_404(session, Company, company_id, "Company")
    key = (workspace, company_id)
    with _lock:
        if (_runs.get(key) or {}).get("status") == "running":
            raise HTTPException(409, "This company is already being researched")
        _runs[key] = {"status": "running", "phase": "starting", "done": 0, "total": 0,
                      "error": None}
    demo = workspace == "demo"
    model, fallback = _models(session)
    researcher = research_provider(mock=True if demo else None, model=model, fallback=fallback)
    fetcher = research.SampleFetcher() if demo else None

    def progress(phase: str, done: int, total: int) -> None:
        with _lock:
            _runs[key].update(phase=phase, done=done, total=total)

    def work() -> None:
        try:
            research.ensure(engine, company_id, trigger="manual", researcher=researcher,
                            fetcher=fetcher, force=body.force, progress=progress)
            with _lock:
                _runs[key].update(status="done", phase="done")
        except Exception as exc:  # noqa: BLE001 (shown to the user)
            with _lock:
                _runs[key].update(status="failed", error=str(exc)[:400])

    threading.Thread(target=work, name=f"research-{company_id}", daemon=True).start()
    return _out(session, company, workspace)


@router.patch("/signals/{signal_id}", response_model=SignalOut)
def patch_signal(signal_id: int, body: SignalPatch, session: SessionDep) -> SignalOut:
    row = get_or_404(session, CompanySignal, signal_id, "Signal")
    if body.selected is not None:
        row.selected = body.selected
    if body.dismissed is not None:
        row.dismissed = body.dismissed
        row.selected = row.selected and not body.dismissed
    session.add(row)
    session.commit()
    session.refresh(row)
    return SignalOut.model_validate(row, from_attributes=True)


@router.post("/companies/{company_id}/signals", response_model=SignalOut, status_code=201)
def add_signal(company_id: int, body: SignalIn, session: SessionDep) -> SignalOut:
    get_or_404(session, Company, company_id, "Company")
    try:
        row = research.add_manual(session, company_id, body.fact, body.source_url, body.kind)
    except research.ResearchError as exc:
        raise HTTPException(422, str(exc)) from exc
    return SignalOut.model_validate(row, from_attributes=True)


@router.put("/companies/{company_id}/website", response_model=ResearchOut)
def set_website(company_id: int, body: WebsiteIn, session: SessionDep,
                workspace: WorkspaceDep) -> ResearchOut:
    company = get_or_404(session, Company, company_id, "Company")
    site = body.website.strip()
    if site and "." not in site:
        raise HTTPException(422, "Enter the company's website (e.g. example.com)")
    company.website = site or None
    session.add(company)
    session.commit()
    session.refresh(company)
    return _out(session, company, workspace)
