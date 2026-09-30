"""Cover letters (lettres de motivation) for web applications: one job at a time, written from
the approved CV, checked before you see them, rendered with the CV template's look.

The model writes only the paragraphs (cited sentences) and the closing ask, in the letter's
language (the listing's, unless you pick one for the job). Code adds the header, the place and
date, the recipient, the subject line, the salutation, the formal closing and the signature.
Checks (services/letter_check.py) run on every version; one retry with the problems as
feedback, then the letter is kept with anything still wrong listed. Errors block approval.
A version sent with an application is locked: edits create a new draft.
"""

import hashlib
import re
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.config import DATA_DIR
from app.models import Application, AppSetting, Company, Contact, CoverLetter, CVVersion, Job
from app.models.base import utcnow
from app.models.enums import CVStatus, EventKind
from app.providers.base import CoverLetterPlan, DraftFailed, LetterDrafter, LetterRequest
from app.services import letter_check as lc
from app.services import pipeline
from app.services.cv_check import violation
from app.services.cv_claims import exact_statement
from app.services.cv_pool import Pool, cv_profile, load_pool, years_facts
from app.services.cv_render import (
    LetterDocument,
    compile_tex,
    has_letter,
    load_template,
    render_letter_tex,
)
from app.services.text import detect_language

LETTER_DIR = DATA_DIR / "letters"
LANGUAGES = ("fr", "en")
DEFAULT_GUIDE = "\n".join([
    "- Open with the company and one specific thing from the listing (product, problem, stack),"
    " not with yourself.",
    "- Show 2-3 concrete things you built that match what the listing asks: what, with which"
    " tools, and the result your experience states.",
    "- Say it once: no summary of the CV, no list of adjectives, no motivation you can't back"
    " with a fact.",
    "- Close with one clear ask (an interview), not with thanks or hopes.",
])
DEFAULT_LETTER: dict[str, Any] = {
    "language": "auto",  # auto = the listing's language; a job can override it (studio)
    "guide": DEFAULT_GUIDE,
    "min_words": lc.DEFAULT_MIN_WORDS,
    "max_words": lc.DEFAULT_MAX_WORDS,
    "banned_phrases": lc.DEFAULT_BANNED,
    "salutation": {"fr": "Madame, Monsieur,", "en": "Dear Hiring Manager,"},
    "closing": {
        "fr": "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations "
              "distinguées.",
        "en": "Kind regards,",
    },
    "years_statement_fr": "",  # "" = derived from Settings → Candidate's statement
    "filename_pattern": "{full_name}_Cover_Letter_{company}.pdf",
}
MONTHS = {
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}
_one_at_a_time = threading.Lock()


class LetterError(ValueError):
    """Shown to the user (no approved CV, a letter already generating, checks failing…)."""


def letter_settings(s: Session) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == "cover_letter")).first()
    saved = dict(row.value) if row else {}
    out = {**DEFAULT_LETTER, **saved}
    for key in ("banned_phrases", "salutation", "closing"):
        out[key] = {**DEFAULT_LETTER[key], **(saved.get(key) or {})}
    return out


def resolve_language(s: Session, app: Application, job: Job) -> str:
    """The job's choice, else Settings → Cover letter, else the listing's language."""
    if app.letter_language in LANGUAGES:
        return app.letter_language
    setting = letter_settings(s).get("language")
    if setting in LANGUAGES:
        return setting
    return detect_language(f"{job.title}\n{job.description or ''}")


def approved_cv(s: Session, app: Application) -> CVVersion | None:
    return s.exec(select(CVVersion).where(CVVersion.application_id == app.id,
                                          CVVersion.status == CVStatus.approved)
                  .order_by(col(CVVersion.version).desc())).first()


def versions(s: Session, app_id: int) -> list[CoverLetter]:
    return list(s.exec(select(CoverLetter).where(CoverLetter.application_id == app_id)
                       .order_by(col(CoverLetter.version).desc())).all())


def approved_letter(s: Session, app: Application) -> CoverLetter | None:
    return next((v for v in versions(s, app.id) if v.status == CVStatus.approved), None)


def _statements(s: Session, pool: Pool) -> tuple[list[dict[str, Any]], str | None, str | None]:
    from app.services.cv_service import _tracks

    facts = years_facts(pool, _tracks(s))
    english = exact_statement(facts)
    return facts, english, lc.french_statement(
        english, letter_settings(s).get("years_statement_fr") or "")


def context(s: Session, app: Application, language: str,
            pool: Pool | None = None) -> lc.Context:
    pool = pool or load_pool(s)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    cfg = letter_settings(s)
    facts, english, french = _statements(s, pool)
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    others = {c.name for _l, c in s.exec(
        select(CoverLetter, Company)
        .join(Application, col(Application.id) == col(CoverLetter.application_id))
        .join(Job, col(Job.id) == col(Application.job_id))
        .join(Company, col(Company.id) == col(Job.company_id))
        .where(CoverLetter.status != CVStatus.superseded,
               CoverLetter.application_id != app.id)).all()}
    return lc.Context(
        pool=pool, allowed_years={int(f["years"]) for f in facts},
        job_text=f"{job.title}\n{job.description or ''}", company=company.name,
        language=language, banned=list(cfg["banned_phrases"].get(language) or []),
        min_words=int(cfg.get("min_words") or lc.DEFAULT_MIN_WORDS),
        max_words=int(cfg.get("max_words") or lc.DEFAULT_MAX_WORDS),
        years_statement=english, years_statement_fr=french,
        other_companies=sorted(others - {company.name}),
        contact_name=contact.full_name if contact and language == "en" else "")


def build_request(s: Session, app: Application, cv: CVVersion, pool: Pool,
                  language: str) -> LetterRequest:
    from app.services.outreach import cv_pool_subset

    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    cfg = letter_settings(s)
    facts, english, french = _statements(s, pool)
    profile = pool.profile
    return LetterRequest(
        job={"title": job.title, "company": company.name, "location": job.location,
             "description": (job.description or "")[:8000]},
        candidate={"based_in": profile.get("based_in", ""),
                   "work_authorization": profile.get("work_authorization", ""),
                   "years": facts, "years_statement": english,
                   "years_statement_fr": french},
        pool=cv_pool_subset(pool, cv),
        rules={"language": language, "min_words": int(cfg["min_words"]),
               "max_words": int(cfg["max_words"]),
               "banned_phrases": list(cfg["banned_phrases"].get(language) or []),
               "guide": cfg.get("guide") or ""},
    )


# ------------------------------------------------------------------------------------ content


def paragraph_text(p: dict[str, Any]) -> str:
    if "text" in p:
        return str(p["text"]).strip()
    return " ".join(str(x["text"]).strip() for x in p.get("sentences") or [])


def content_from_plan(plan: CoverLetterPlan, salutation: str) -> dict[str, Any]:
    return {"salutation": salutation, "ask": plan.ask.strip(),
            "paragraphs": [{"sentences": [x.model_dump() for x in p.sentences]}
                           for p in plan.paragraphs]}


def body_paragraphs(content: dict[str, Any]) -> list[str]:
    """The paragraphs as shown and sent: the ask ends the last one."""
    texts = [t for t in (paragraph_text(p) for p in content.get("paragraphs") or []) if t]
    ask = str(content.get("ask") or "").strip()
    if ask:
        texts = [*texts[:-1], f"{texts[-1]} {ask}".strip()] if texts else [ask]
    return texts


def default_salutation(s: Session, app: Application, language: str) -> str:
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    if contact and language == "en":
        return f"Dear {contact.full_name},"
    return letter_settings(s)["salutation"].get(language) or ""


def closing(s: Session, language: str) -> str:
    return letter_settings(s)["closing"].get(language) or ""


def plain_text(s: Session, letter: CoverLetter) -> str:
    """For web forms (Copy as text): salutation, paragraphs, closing, name."""
    content = letter.content or {}
    name = (load_pool(s).profile.get("full_name") or "").strip()
    parts = [str(content.get("salutation") or ""), *body_paragraphs(content),
             "\n".join(x for x in (closing(s, letter.language), name) if x)]
    return "\n\n".join(p for p in parts if p.strip())


def format_date(day: date, language: str) -> str:
    return f"{day.day} {MONTHS.get(language, MONTHS['en'])[day.month - 1]} {day.year}"


def document(s: Session, letter: CoverLetter, pool: Pool) -> LetterDocument:
    app = s.get(Application, letter.application_id)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    fr = letter.language == "fr"
    day = format_date((letter.created_at or utcnow()).date(), letter.language)
    city = (pool.profile.get("based_in") or "").split(",")[0].strip()
    place_date = (f"{city}, le {day}" if city else day) if fr else day
    attention = ""
    if contact:
        attention = (f"À l'attention de {contact.full_name}" if fr
                     else f"Attn: {contact.full_name}")
    subject = (f"Objet : candidature au poste de {job.title}" if fr
               else f"Application for the {job.title} position")
    return LetterDocument(
        language=letter.language, place_date=place_date, company=company.name,
        attention=attention, subject=subject,
        salutation=str((letter.content or {}).get("salutation") or ""),
        paragraphs=body_paragraphs(letter.content or {}), closing=closing(s, letter.language))


def check(s: Session, letter: CoverLetter, pool: Pool | None = None) -> list[dict[str, str]]:
    app = s.get(Application, letter.application_id)
    content = letter.content or {}
    return lc.check_letter(str(content.get("salutation") or ""),
                           list(content.get("paragraphs") or []),
                           str(content.get("ask") or ""),
                           context(s, app, letter.language, pool))


def render(s: Session, letter: CoverLetter, pool: Pool,
           engine_key: str = "") -> list[dict[str, str]]:
    """Compile the PDF; returns the page problems (the letter must fit on one page)."""
    template = load_template(letter.template or "default")
    if not has_letter(template):
        letter.error = f"The '{template.name}' template has no cover letter layout"
        return [violation("render", letter.error, "letter", "error")]
    profile = cv_profile(pool)
    if not profile.full_name:
        profile = profile.model_copy(update={"full_name": "Your Name"})
    tex = render_letter_tex(document(s, letter, pool), profile, template)
    out_dir = LETTER_DIR / f"{engine_key}{letter.application_id}" / f"v{letter.version}"
    result = compile_tex(tex, out_dir, "cover_letter")
    letter.tex = tex
    if not result.ok:
        letter.error, letter.pdf_path, letter.page_count = result.error, None, None
        return [violation("render", f"LaTeX failed: {result.error}", "letter", "error")]
    letter.error, letter.pdf_path, letter.page_count = None, str(result.pdf_path), result.pages
    if result.pages > 1:
        return [violation("page", f"{result.pages} pages: a cover letter fits on one page",
                          "letter", "error")]
    return []


def _refresh(s: Session, letter: CoverLetter, pool: Pool, engine_key: str) -> None:
    letter.text = plain_text(s, letter)
    letter.violations = check(s, letter, pool) + render(s, letter, pool, engine_key)


def _engine_key(engine: Engine) -> str:
    return "" if str(engine.url).endswith("jobhunter.db") else f"{id(engine)}-"


# --------------------------------------------------------------------------------- generating


def generate(engine: Engine, app_id: int, drafter: LetterDrafter,
             language: str | None = None) -> CoverLetter:
    """Write the cover letter for one job (never in bulk: one at a time)."""
    if not _one_at_a_time.acquire(blocking=False):
        raise LetterError("Another cover letter is being written; one at a time")
    try:
        with Session(engine) as s:
            app = s.get(Application, app_id)
            if app is None:
                raise LetterError("Application not found")
            cv = approved_cv(s, app)
            if cv is None:
                raise LetterError("Approve the CV first: the letter is written from it")
            job = s.get(Job, app.job_id)
            template = load_template(cv.template or "default")
            if not has_letter(template):
                raise LetterError(f"The '{template.name}' template has no cover letter layout "
                                  "(add cover_letter.tex.j2 to it)")
            language = language if language in LANGUAGES else resolve_language(s, app, job)
            pool = load_pool(s)
            request = build_request(s, app, cv, pool, language)
            ctx = context(s, app, language, pool)
            salutation = default_salutation(s, app, language)
        started = time.monotonic()

        def checked(plan: CoverLetterPlan) -> list[dict[str, str]]:
            content = content_from_plan(plan, salutation)
            return lc.check_letter(salutation, content["paragraphs"], content["ask"], ctx)

        try:
            plan = drafter.draft_letter(request)
            found, attempts = checked(plan), 1
            if lc.errors(found):  # one retry with the problems as feedback
                retry = drafter.draft_letter(request, lc.feedback(found))
                retry_found, attempts = checked(retry), 2
                if len(lc.errors(retry_found)) <= len(lc.errors(found)):
                    plan = retry
        except DraftFailed as exc:
            raise LetterError(str(exc)) from exc
        with Session(engine) as s:
            app = s.get(Application, app_id)
            existing = versions(s, app_id)
            for old in existing:
                if old.status == CVStatus.draft and old.locked_at is None:
                    old.status = CVStatus.superseded  # regenerate replaces the draft under review
                    s.add(old)
            letter = CoverLetter(
                application_id=app_id, version=(existing[0].version + 1) if existing else 1,
                language=language, content=content_from_plan(plan, salutation),
                template=cv.template or "default", cv_version_id=cv.id,
                generator_model=drafter.model, prompt_version=drafter.prompt_version,
                plan={"plan": plan.model_dump(), "attempts": attempts},
                duration_ms=int((time.monotonic() - started) * 1000))
            s.add(letter)
            s.flush()
            _refresh(s, letter, pool, _engine_key(engine))
            problems = len(lc.errors(letter.violations))
            pipeline.log_event(s, app, EventKind.letter_generated,
                               f"Cover letter v{letter.version} ({language}) written"
                               + (f" ({problems} problems to review)" if problems else ""))
            s.commit()
            s.refresh(letter)
            return letter
    finally:
        _one_at_a_time.release()


# ---------------------------------------------------------------------------- editing, approving


def edit(engine: Engine, letter_id: int, *, salutation: str | None = None,
         paragraphs: list[str] | None = None, ask: str | None = None) -> CoverLetter:
    """Your edits: changed paragraphs become plain text (re-checked at text level) and the PDF is
    re-rendered, with no Claude call. A locked letter is never changed: a new draft is made."""
    with Session(engine) as s:
        letter = s.get(CoverLetter, letter_id)
        if letter is None:
            raise LetterError("Cover letter not found")
        content = dict(letter.content or {})
        if salutation is not None:
            content["salutation"] = salutation.strip()
        if ask is not None:
            content["ask"] = ask.strip()
        if paragraphs is not None:
            old = list(content.get("paragraphs") or [])
            new = []
            for i, text in enumerate(p.strip() for p in paragraphs):
                if not text:
                    continue
                keep = i < len(old) and paragraph_text(old[i]) == text
                new.append(old[i] if keep else {"text": text})
            content["paragraphs"] = new
        if letter.locked_at is not None or letter.status == CVStatus.superseded:
            latest = versions(s, letter.application_id)[0]
            letter = CoverLetter(
                application_id=letter.application_id, version=latest.version + 1,
                language=letter.language, template=letter.template,
                cv_version_id=letter.cv_version_id, generator_model=letter.generator_model,
                prompt_version=letter.prompt_version, plan=letter.plan)
        elif letter.status == CVStatus.approved:
            letter.status = CVStatus.draft  # edited after approval: review it again
        letter.content = content
        s.add(letter)
        s.flush()
        _refresh(s, letter, load_pool(s), _engine_key(engine))
        s.commit()
        s.refresh(letter)
        return letter


def approve(engine: Engine, letter_id: int) -> CoverLetter:
    with Session(engine) as s:
        letter = s.get(CoverLetter, letter_id)
        if letter is None:
            raise LetterError("Cover letter not found")
        if letter.status == CVStatus.superseded:
            raise LetterError("This version was replaced by a newer one")
        found = lc.errors(letter.violations or [])
        if found:
            raise LetterError(f"Fix {len(found)} problem{'s' if len(found) > 1 else ''} first: "
                              + found[0]["message"])
        if not letter.pdf_path or not Path(letter.pdf_path).exists():
            raise LetterError("The PDF isn't rendered")
        for other in versions(s, letter.application_id):
            if other.id != letter.id and other.status == CVStatus.approved \
                    and other.locked_at is None:
                other.status = CVStatus.superseded
                s.add(other)
        letter.status = CVStatus.approved
        s.add(letter)
        app = s.get(Application, letter.application_id)
        pipeline.log_event(s, app, EventKind.letter_approved,
                           f"Cover letter v{letter.version} approved")
        s.commit()
        s.refresh(letter)
        return letter


def ensure_pdf(engine: Engine, letter: CoverLetter) -> Path | None:
    """Letters without a PDF (sandbox fixtures) are compiled on first view. Locked letters are
    only ever served from their stored file."""
    if letter.pdf_path and Path(letter.pdf_path).exists():
        return Path(letter.pdf_path)
    if letter.locked_at is not None:
        return None
    with Session(engine) as s:
        row = s.get(CoverLetter, letter.id)
        render(s, row, load_pool(s), _engine_key(engine))
        s.add(row)
        s.commit()
        return Path(row.pdf_path) if row.pdf_path else None


def lock(letter: CoverLetter) -> None:
    """The version sent with an application: never edited, re-rendered or superseded."""
    if letter.locked_at is None:
        letter.locked_at = utcnow()
    if letter.pdf_path and Path(letter.pdf_path).exists() and not letter.pdf_sha256:
        letter.pdf_sha256 = hashlib.sha256(Path(letter.pdf_path).read_bytes()).hexdigest()


def download_name(s: Session, letter: CoverLetter) -> str:
    pattern = letter_settings(s).get("filename_pattern") or DEFAULT_LETTER["filename_pattern"]
    app = s.get(Application, letter.application_id)
    job = s.get(Job, app.job_id) if app else None
    company = s.get(Company, job.company_id) if job else None
    values = {"full_name": (load_pool(s).profile.get("full_name") or "Cover_Letter").strip(),
              "company": company.name if company else "Company",
              "job_title": job.title if job else "Job", "version": str(letter.version)}
    try:
        name = pattern.format(**values)
    except (KeyError, IndexError, ValueError):
        name = DEFAULT_LETTER["filename_pattern"].format(**values)
    name = re.sub(r"[^\w.\- ]+", "", name).strip().replace(" ", "_")
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"
