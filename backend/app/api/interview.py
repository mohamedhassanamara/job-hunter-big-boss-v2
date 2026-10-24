"""Interview preparation: one job at a time, checked in code and by the claim verifier."""

from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.api.deps import EngineDep, SessionDep, WorkspaceDep, get_or_404
from app.models import Application, Company, InterviewPrep, Job
from app.providers.registry import interview_drafter
from app.schemas.interview import (
    InterviewGenerateIn,
    InterviewPatch,
    InterviewPrepOut,
    InterviewStudio,
)
from app.services import cover_letter, model_choice, verifier
from app.services import interview_prep as ip
from app.services.cv_pool import load_pool

router = APIRouter(tags=["interview prep"])


def _model(session: Session) -> str:
    return model_choice.claude_model(session, "interview")


def prep_out(s: Session, prep: InterviewPrep, pool=None) -> InterviewPrepOut:  # noqa: ANN001
    pool = pool or load_pool(s)
    content = prep.content or {}
    cited = {c for _w, x in ip.candidate_sentences(content) for c in x.get("citations") or []}
    sources = {}
    for item_id in sorted(cited):
        item = pool.get(item_id)
        if item:
            sources[item_id] = " · ".join(x for x in (item.title, item.org) if x)
    return InterviewPrepOut(
        id=prep.id, application_id=prep.application_id, version=prep.version,
        status=prep.status, language=prep.language, content=content, sources=sources,
        violations=prep.violations or [], verification=prep.verification or {},
        verification_state=verifier.state(prep.verification, verifier.interview_text(prep)),
        generator_model=prep.generator_model, prompt_version=prep.prompt_version,
        created_at=prep.created_at)


@router.get("/applications/{app_id}/interview-prep", response_model=InterviewStudio)
def get_interview_prep(app_id: int, session: SessionDep) -> InterviewStudio:
    app = get_or_404(session, Application, app_id, "Application")
    job = session.get(Job, app.job_id)
    company = session.get(Company, job.company_id)
    pool = load_pool(session)
    prep = ip.current(session, app_id)
    return InterviewStudio(
        application_id=app_id, job_title=job.title, company_name=company.name,
        prep=prep_out(session, prep, pool) if prep else None,
        versions=len(ip.versions(session, app_id)),
        language=cover_letter.resolve_language(session, app, job),
        has_experience=any(i.kind in ("job", "project") and pool.facts(i)
                           for i in pool.items.values()))


@router.post("/applications/{app_id}/interview-prep/generate", response_model=InterviewPrepOut)
def generate_interview_prep(app_id: int, body: InterviewGenerateIn, session: SessionDep,
                            engine: EngineDep, workspace: WorkspaceDep) -> InterviewPrepOut:
    """One job at a time: one Claude call (the mock in the sandbox and tests), checks, one retry."""
    get_or_404(session, Application, app_id, "Application")
    drafter = interview_drafter(mock=True if workspace == "demo" else None, model=_model(session))
    try:
        prep = ip.generate(engine, app_id, drafter, body.language)
    except ip.InterviewError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return prep_out(session, session.get(InterviewPrep, prep.id))


@router.patch("/interview-prep/{prep_id}", response_model=InterviewPrepOut)
def patch_interview_prep(prep_id: int, body: InterviewPatch, engine: EngineDep,
                         session: SessionDep) -> InterviewPrepOut:
    try:
        prep = ip.edit(engine, prep_id, body.content.model_dump())
    except ip.InterviewError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return prep_out(session, session.get(InterviewPrep, prep.id))


@router.post("/interview-prep/{prep_id}/approve", response_model=InterviewPrepOut)
def approve_interview_prep(prep_id: int, session: SessionDep, engine: EngineDep,
                           workspace: WorkspaceDep) -> InterviewPrepOut:
    prep = get_or_404(session, InterviewPrep, prep_id, "Interview preparation")
    found = ip.errors(ip.check(session, prep.content))
    if found:  # the code checks first (fast); Claude only on a text that passes them
        raise HTTPException(409, f"Fix {len(found)} problem{'s' if len(found) > 1 else ''} "
                            f"first: {found[0]['message']}")
    if prep.status == "draft":
        try:
            verifier.require_interview_prep(session, prep,
                                            verifier.for_workspace(session, workspace))
        except verifier.VerifyError as exc:
            session.commit()  # keep the verdicts on screen
            raise HTTPException(409, str(exc)) from exc
        session.commit()
    try:
        prep = ip.approve(engine, prep_id)
    except ip.InterviewError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.expire_all()
    return prep_out(session, session.get(InterviewPrep, prep.id))


@router.post("/interview-prep/{prep_id}/verify", response_model=InterviewPrepOut)
def verify_interview_prep(prep_id: int, session: SessionDep,
                          workspace: WorkspaceDep) -> InterviewPrepOut:
    """Check every claim now (Claude), without approving."""
    prep = get_or_404(session, InterviewPrep, prep_id, "Interview preparation")
    try:
        verifier.code_checks_first(ip.check(session, prep.content))
    except verifier.VerifyError as exc:
        raise HTTPException(409, str(exc)) from exc
    verifier.verify_interview_prep(session, prep, verifier.for_workspace(session, workspace))
    session.commit()
    session.refresh(prep)
    return prep_out(session, prep)
