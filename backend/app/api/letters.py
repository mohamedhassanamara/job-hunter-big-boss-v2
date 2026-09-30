from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.api.deps import EngineDep, SessionDep, WorkspaceDep, get_or_404
from app.models import (
    Application,
    ApplicationAnswer,
    AppSetting,
    Company,
    CoverLetter,
    CVVersion,
    Job,
)
from app.providers.registry import letter_drafter
from app.schemas.letters import (
    AnswerOut,
    AnswerPatch,
    AnswersIn,
    LetterGenerateIn,
    LetterLanguageIn,
    LetterOut,
    LetterParagraphOut,
    LetterPatch,
    LetterSentenceOut,
    LetterStudio,
    LetterText,
)
from app.services import answers as answer_service
from app.services import cover_letter as cl
from app.services import outreach_check as oc
from app.services.cv_pool import load_pool
from app.services.cv_render import has_letter, load_template
from app.services.text import detect_language

router = APIRouter(tags=["cover letters"])


def letter_out(s: Session, letter: CoverLetter, pool=None) -> LetterOut:  # noqa: ANN001
    pool = pool or load_pool(s)
    content = letter.content or {}
    paragraphs, cited = [], set()
    for p in content.get("paragraphs") or []:
        sentences = [LetterSentenceOut(**x) for x in p.get("sentences") or []]
        cited |= {c for x in sentences for c in x.citations}
        paragraphs.append(LetterParagraphOut(text=cl.paragraph_text(p), edited="text" in p,
                                             sentences=sentences))
    sources = {}
    for item_id in sorted(cited):
        item = pool.get(item_id)
        if item:
            sources[item_id] = " · ".join(x for x in (item.title, item.org) if x)
    cv = s.get(CVVersion, letter.cv_version_id) if letter.cv_version_id else None
    body = cl.body_paragraphs(content)
    return LetterOut(
        id=letter.id, application_id=letter.application_id, version=letter.version,
        status=letter.status, language=letter.language,
        salutation=str(content.get("salutation") or ""), paragraphs=paragraphs,
        ask=str(content.get("ask") or ""), closing=cl.closing(s, letter.language),
        text=letter.text or cl.plain_text(s, letter), word_count=len(oc.words(" ".join(body))),
        page_count=letter.page_count,
        has_pdf=bool(letter.pdf_path and Path(letter.pdf_path).exists()),
        violations=letter.violations or [], sources=sources, cv_version_id=letter.cv_version_id,
        cv_version=cv.version if cv else None, generator_model=letter.generator_model,
        duration_ms=letter.duration_ms, error=letter.error, locked_at=letter.locked_at,
        download_name=cl.download_name(s, letter), created_at=letter.created_at,
        updated_at=letter.updated_at)


@router.get("/applications/{app_id}/letter", response_model=LetterStudio)
def get_letter_studio(app_id: int, session: SessionDep) -> LetterStudio:
    app = get_or_404(session, Application, app_id, "Application")
    job = get_or_404(session, Job, app.job_id)
    company = get_or_404(session, Company, job.company_id)
    cv = cl.approved_cv(session, app)
    template = load_template((cv.template if cv else None) or "default")
    pool = load_pool(session)
    return LetterStudio(
        application_id=app.id, job_id=job.id, job_title=job.title, company_name=company.name,
        stage=app.stage, route=app.route, language_setting=app.letter_language or "auto",
        detected_language=detect_language(f"{job.title}\n{job.description or ''}"),
        language=cl.resolve_language(session, app, job),
        approved_cv_id=cv.id if cv else None, approved_cv_version=cv.version if cv else None,
        template_ok=has_letter(template),
        letters=[letter_out(session, v, pool) for v in cl.versions(session, app.id)])


def _model(session: Session) -> str:
    row = session.exec(select(AppSetting).where(AppSetting.key == "models")).first()
    return ((row.value if row else {}).get("cv") or {}).get("model") or "claude-sonnet-5"


@router.post("/applications/{app_id}/letter/generate", response_model=LetterOut)
def generate_letter(app_id: int, body: LetterGenerateIn, session: SessionDep,
                    engine: EngineDep, workspace: WorkspaceDep) -> LetterOut:
    """One job at a time: one Claude call (mock in the sandbox/tests), checks, one retry."""
    get_or_404(session, Application, app_id, "Application")
    drafter = letter_drafter(mock=True if workspace == "demo" else None, model=_model(session))
    try:
        letter = cl.generate(engine, app_id, drafter, body.language)
    except cl.LetterError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return letter_out(session, session.get(CoverLetter, letter.id))


@router.put("/applications/{app_id}/letter/language", response_model=LetterStudio)
def set_letter_language(app_id: int, body: LetterLanguageIn, session: SessionDep) -> LetterStudio:
    app = get_or_404(session, Application, app_id, "Application")
    if body.language not in ("auto", *cl.LANGUAGES):
        raise HTTPException(422, "language must be auto, fr or en")
    app.letter_language = body.language
    session.add(app)
    session.commit()
    return get_letter_studio(app_id, session)


@router.patch("/letters/{letter_id}", response_model=LetterOut)
def patch_letter(letter_id: int, body: LetterPatch, session: SessionDep,
                 engine: EngineDep) -> LetterOut:
    """Your edits: re-checked and re-rendered, no Claude call. A locked letter gets a new draft."""
    get_or_404(session, CoverLetter, letter_id, "Cover letter")
    try:
        letter = cl.edit(engine, letter_id, salutation=body.salutation,
                         paragraphs=body.paragraphs, ask=body.ask)
    except cl.LetterError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return letter_out(session, session.get(CoverLetter, letter.id))


@router.post("/letters/{letter_id}/approve", response_model=LetterOut)
def approve_letter(letter_id: int, session: SessionDep, engine: EngineDep) -> LetterOut:
    get_or_404(session, CoverLetter, letter_id, "Cover letter")
    try:
        letter = cl.approve(engine, letter_id)
    except cl.LetterError as exc:
        raise HTTPException(409, str(exc)) from exc
    session.expire_all()
    return letter_out(session, session.get(CoverLetter, letter.id))


@router.get("/letters/{letter_id}/pdf")
def letter_pdf(letter_id: int, session: SessionDep, engine: EngineDep, download: bool = False):  # noqa: ANN201
    letter = get_or_404(session, CoverLetter, letter_id, "Cover letter")
    path = cl.ensure_pdf(engine, letter)
    if path is None:
        raise HTTPException(404, "No PDF for this version (LaTeX failed; see the error)")
    # Drafts are re-rendered in place (same URL): never let the browser keep an older copy.
    return FileResponse(path, media_type="application/pdf",
                        filename=cl.download_name(session, letter),
                        content_disposition_type="attachment" if download else "inline",
                        headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/letters/{letter_id}/text", response_model=LetterText)
def letter_text(letter_id: int, session: SessionDep) -> LetterText:
    letter = get_or_404(session, CoverLetter, letter_id, "Cover letter")
    return LetterText(text=cl.plain_text(session, letter))


# ------------------------------------------------------------------------ application questions


def answer_out(s: Session, a: ApplicationAnswer, pool=None) -> AnswerOut:  # noqa: ANN001
    pool = pool or load_pool(s)
    sentences = [LetterSentenceOut(**x) for x in (a.plan or {}).get("sentences") or []]
    sources = {}
    for item_id in sorted({c for x in sentences for c in x.citations}):
        if item := pool.get(item_id):
            sources[item_id] = " · ".join(x for x in (item.title, item.org) if x)
    return AnswerOut(id=a.id, application_id=a.application_id, question=a.question,
                     char_limit=a.char_limit, answer=a.answer, length=len(a.answer),
                     language=a.language, edited=a.edited,
                     sentences=[] if a.edited else sentences, sources=sources,
                     violations=a.violations or [], created_at=a.created_at,
                     updated_at=a.updated_at)


@router.get("/applications/{app_id}/answers", response_model=list[AnswerOut])
def list_answers(app_id: int, session: SessionDep) -> list[AnswerOut]:
    get_or_404(session, Application, app_id, "Application")
    pool = load_pool(session)
    return [answer_out(session, a, pool) for a in answer_service.answers(session, app_id)]


@router.post("/applications/{app_id}/answers", response_model=list[AnswerOut], status_code=201)
def answer_questions(app_id: int, body: AnswersIn, session: SessionDep, engine: EngineDep,
                     workspace: WorkspaceDep) -> list[AnswerOut]:
    """One Claude call for the batch (mock in the sandbox/tests), checks, one retry."""
    get_or_404(session, Application, app_id, "Application")
    drafter = letter_drafter(mock=True if workspace == "demo" else None, model=_model(session))
    try:
        rows = answer_service.generate(engine, app_id, drafter,
                                       [q.model_dump() for q in body.questions])
    except answer_service.AnswerError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return [answer_out(session, session.get(ApplicationAnswer, r.id)) for r in rows]


@router.patch("/answers/{answer_id}", response_model=AnswerOut)
def patch_answer(answer_id: int, body: AnswerPatch, session: SessionDep) -> AnswerOut:
    a = get_or_404(session, ApplicationAnswer, answer_id, "Answer")
    if body.char_limit is not None and body.char_limit < 20:
        raise HTTPException(422, "A character limit must be at least 20")
    limit = None if body.clear_limit else (body.char_limit if body.char_limit is not None
                                            else "keep")
    return answer_out(session, answer_service.update(session, a, text=body.answer,
                                                     question=body.question, char_limit=limit))


@router.delete("/answers/{answer_id}", status_code=204)
def delete_answer(answer_id: int, session: SessionDep) -> None:
    a = get_or_404(session, ApplicationAnswer, answer_id, "Answer")
    session.delete(a)
    session.commit()
