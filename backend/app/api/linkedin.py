"""LinkedIn section: daily search links (built in code), and the one-click import of a job
page you capture with the bookmark. Nothing here requests linkedin.com."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import EngineDep, SessionDep, WorkspaceDep
from app.services import linkedin

router = APIRouter(tags=["linkedin"])


class LinkOut(BaseModel):
    key: str
    role: str
    country: str
    country_name: str
    url: str
    opened_today: bool


class LinkGroupOut(BaseModel):
    track: str
    role: str
    links: list[LinkOut]


class LinksOut(BaseModel):
    groups: list[LinkGroupOut]
    total: int
    opened: int


class OpenIn(BaseModel):
    key: str


class CaptureIn(BaseModel):
    """What the bookmarklet sends (or the import window, after your edits)."""

    url: str = ""
    job_id: str | None = None
    title: str = ""
    company: str = ""
    company_url: str | None = None
    location: str = ""
    workplace: str = ""
    description: str = ""
    poster: dict[str, Any] | None = None
    sources: dict[str, str] = {}


class PasteIn(BaseModel):
    url: str = ""
    text: str


class CaptureOut(BaseModel):
    url: str
    job_id: str | None
    title: str
    company: str
    company_url: str | None
    location: str
    workplace: str
    description: str
    poster: dict[str, str] | None
    sources: dict[str, str]
    missing: list[str]
    warnings: list[str]
    existing: dict[str, Any] | None


class ImportOut(BaseModel):
    job_id: int
    application_id: int
    created: bool
    duplicate_of: dict[str, Any] | None
    matched_track: str | None
    warnings: list[str]
    scoring: str


@router.get("/linkedin/links", response_model=LinksOut)
def links(session: SessionDep, remote: bool = False, easy: bool = False) -> LinksOut:
    """One LinkedIn job search per role × target country, past 24 hours, newest first."""
    groups = linkedin.search_links(session, remote=remote, easy=easy)
    out = [LinkGroupOut(track=g.track, role=g.role,
                        links=[LinkOut(**vars(x)) for x in g.links]) for g in groups]
    every = [x for g in groups for x in g.links]
    return LinksOut(groups=out, total=len(every), opened=sum(x.opened_today for x in every))


@router.post("/linkedin/links/open", status_code=204)
def open_link(body: OpenIn, session: SessionDep) -> None:
    """You opened a search link today (the mark resets tomorrow)."""
    linkedin.mark_opened(session, body.key)
    session.commit()


def _capture_out(session, c: linkedin.Capture) -> CaptureOut:  # noqa: ANN001
    return CaptureOut(**vars(c), existing=linkedin.existing(session, c))


@router.post("/linkedin/capture", response_model=CaptureOut)
def check_capture(body: CaptureIn, session: SessionDep) -> CaptureOut:
    """The import window's preview: every field, how it was found, what's missing, and whether
    the job is already in your list. Nothing is saved."""
    try:
        return _capture_out(session, linkedin.validate(body.model_dump()))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/linkedin/paste", response_model=CaptureOut)
def check_paste(body: PasteIn, session: SessionDep) -> CaptureOut:
    """The fallback when the capture fails: a pasted URL and listing."""
    try:
        return _capture_out(session, linkedin.validate(linkedin.from_paste(body.url, body.text)))
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/linkedin/import", response_model=ImportOut)
def import_job(body: CaptureIn, engine: EngineDep, workspace: WorkspaceDep) -> ImportOut:
    """Save the job (source LinkedIn): deduped, its track matched, scored on its own now."""
    try:
        c = linkedin.validate(body.model_dump())
        result = linkedin.import_job(engine, c, workspace=workspace)
    except linkedin.CaptureError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ImportOut(**vars(result))
