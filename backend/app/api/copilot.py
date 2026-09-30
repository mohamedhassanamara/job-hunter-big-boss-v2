from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, func, select

from app.api.deps import EngineDep, SessionDep, WorkspaceDep, get_or_404
from app.models import Application, AppSetting, CopilotMessage, CopilotThread
from app.providers.registry import copilot
from app.schemas.copilot import (
    CopilotAsk,
    CopilotMessageOut,
    CopilotStatus,
    CopilotThreadDetail,
    CopilotThreadOut,
)
from app.services import copilot as svc

router = APIRouter(tags=["copilot"])


def _model(session: Session) -> str:
    row = session.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    return ((row.value if row else {}).get("copilot") or {}).get("model") or "gemma4:12b"


def _thread_out(session: Session, t: CopilotThread) -> CopilotThreadOut:
    app = session.get(Application, t.application_id) if t.application_id else None
    count = session.exec(select(func.count()).select_from(CopilotMessage)
                         .where(CopilotMessage.thread_id == t.id)).one()
    return CopilotThreadOut(id=t.id, application_id=t.application_id,
                            job_id=app.job_id if app else None, title=t.title or "New chat",
                            message_count=count, updated_at=t.updated_at)


def _detail(session: Session, t: CopilotThread) -> CopilotThreadDetail:
    base = _thread_out(session, t)
    return CopilotThreadDetail(
        **base.model_dump(),
        messages=[CopilotMessageOut.model_validate(m, from_attributes=True)
                  for m in svc.messages(session, t.id)],
        starters=svc.STARTERS["job" if t.application_id else "global"],
        model=_model(session))


@router.get("/copilot/status", response_model=CopilotStatus)
def copilot_status(session: SessionDep, workspace: WorkspaceDep) -> CopilotStatus:
    """Is the local model ready? (Ollama running and the model pulled.)"""
    model = _model(session)
    if workspace == "demo":
        return CopilotStatus(ok=True, model="mock", message="Sample answers (tour)")
    from app.providers.ollama import OllamaFitScorer

    health = OllamaFitScorer(model).health()
    return CopilotStatus(ok=health.ok, model=model, message=health.message)


@router.get("/copilot/threads", response_model=list[CopilotThreadOut])
def list_threads(session: SessionDep, application_id: int | None = None) -> list[CopilotThreadOut]:
    """Global conversations (default), or a job's (current and cleared ones)."""
    stmt = select(CopilotThread)
    stmt = stmt.where(CopilotThread.application_id == application_id) if application_id \
        else stmt.where(col(CopilotThread.application_id).is_(None))
    rows = session.exec(stmt.order_by(col(CopilotThread.updated_at).desc())).all()
    return [_thread_out(session, t) for t in rows]


@router.post("/copilot/threads", response_model=CopilotThreadDetail, status_code=201)
def new_thread(session: SessionDep) -> CopilotThreadDetail:
    t = CopilotThread(application_id=None, title="")
    session.add(t)
    session.commit()
    session.refresh(t)
    return _detail(session, t)


@router.get("/copilot/threads/{thread_id}", response_model=CopilotThreadDetail)
def get_thread(thread_id: int, session: SessionDep) -> CopilotThreadDetail:
    return _detail(session, get_or_404(session, CopilotThread, thread_id, "Conversation"))


@router.delete("/copilot/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, session: SessionDep) -> None:
    t = get_or_404(session, CopilotThread, thread_id, "Conversation")
    for m in svc.messages(session, t.id):
        session.delete(m)
    session.delete(t)
    session.commit()


@router.get("/applications/{app_id}/copilot", response_model=CopilotThreadDetail)
def job_copilot(app_id: int, session: SessionDep) -> CopilotThreadDetail:
    get_or_404(session, Application, app_id, "Application")
    return _detail(session, svc.job_thread(session, app_id))


@router.post("/applications/{app_id}/copilot/clear", response_model=CopilotThreadDetail)
def clear_job_copilot(app_id: int, session: SessionDep) -> CopilotThreadDetail:
    get_or_404(session, Application, app_id, "Application")
    return _detail(session, svc.clear_job_thread(session, app_id))


@router.post("/copilot/threads/{thread_id}/messages")
def ask(thread_id: int, body: CopilotAsk, session: SessionDep, engine: EngineDep,
        workspace: WorkspaceDep) -> StreamingResponse:
    """The answer streams as plain text; it's saved (with its warnings) when it ends."""
    get_or_404(session, CopilotThread, thread_id, "Conversation")
    model = copilot(mock=True if workspace == "demo" else None, model=_model(session))
    try:
        chunks = svc.ask(engine, thread_id, body.question, model)
    except svc.CopilotError as exc:
        raise HTTPException(422, str(exc)) from exc
    return StreamingResponse(chunks, media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
