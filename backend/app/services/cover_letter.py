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
from app.models import (
    Application,
    AppSetting,
    Company,
    Contact,
    CoverLetter,
    CVVersion,
    ExperienceItem,
    Job,
)
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
FORMATS = ("pdf", "form")
DEFAULT_GUIDE = "\n".join([
    "- Never restate the listing back to the company. Open with why you want THIS company and"
    " role, citing one specific thing from the listing or the company.",
    "- Don't copy or translate CV bullets. Explain how your experience connects to their needs,"
    " in plain language, without CV jargon (schema drift, test counts, collision classes).",
    "- Use your current role when it's relevant: it comes first among the examples.",
    "- At most 2 concrete examples, each in 1-2 sentences.",
    "- The ask for an interview is its own short final paragraph.",
])
DEFAULT_LETTER: dict[str, Any] = {
    "language": "auto",  # auto = the listing's language; a job can override it (studio)
    "guide": DEFAULT_GUIDE,
    "min_words": lc.DEFAULT_MIN_WORDS,
    "max_words": lc.DEFAULT_MAX_WORDS,
    "form_min_words": lc.FORM_MIN_WORDS,
    "form_max_words": lc.FORM_MAX_WORDS,
    "jargon": lc.DEFAULT_JARGON,
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


def versions(s: Session, app_id: int, fmt: str | None = None) -> list[CoverLetter]:
    """Newest first; `fmt` = pdf | form keeps one format (each has its own versions)."""
    rows = s.exec(select(CoverLetter).where(CoverLetter.application_id == app_id)
                  .order_by(col(CoverLetter.version).desc())).all()
    return [r for r in rows if fmt is None or (r.format or "pdf") == fmt]


def approved_letter(s: Session, app: Application, fmt: str = "pdf") -> CoverLetter | None:
    return next((v for v in versions(s, app.id, fmt) if v.status == CVStatus.approved), None)


# Title words that say nothing about the work itself.
_GENERIC_TITLE = {"developer", "developpeur", "developpeuse", "engineer", "ingenieur",
                  "ingenieure", "senior", "junior", "software", "logiciel", "stage", "stagiaire",
                  "alternance", "lead", "confirme", "confirmee", "experimente", "with", "pour",
                  "and", "the",
                  # Too broad to make a role "about" the job ("data-driven screens"): tags decide.
                  "data", "donnees"}


def current_role(pool: Pool, job_text: str) -> ExperienceItem | None:
    """Your current job (no end date, latest start) when it matches the listing: two of its
    tags/tools appear there, or a word of the job title ("Backend") is a theme of the role (its
    title or tags, or at least two of its bullets). The letter must use it."""
    from app.services.cv_claims import Vocabulary
    from app.services.dedupe import _ascii_words

    jobs = [i for i in pool.of("job") if i.end_date is None]
    if not jobs:
        return None
    role = max(jobs, key=lambda i: i.start_date or date.min)
    listing = Vocabulary(job_text)
    tags = {t for t in role.tags if t.strip()}
    if len({t for t in tags if listing.knows(t) or listing.knows(t.replace("-", " "))}) >= 2:
        return role
    title = {w for w in _ascii_words(job_text.split("\n", 1)[0])
             if len(w) >= 4 and w not in _GENERIC_TITLE}
    head = set(_ascii_words(" ".join([role.title, *(t.replace("-", " ") for t in tags)])))
    per_bullet = [set(_ascii_words(b)) for b in role.bullets]
    themes = head | {w for w in title if sum(w in b for b in per_bullet) >= 2}
    return role if title & themes else None


def _statements(s: Session, pool: Pool) -> tuple[list[dict[str, Any]], str | None, str | None]:
    from app.services.cv_service import _tracks

    facts = years_facts(pool, _tracks(s))
    english = exact_statement(facts)
    return facts, english, lc.french_statement(
        english, letter_settings(s).get("years_statement_fr") or "")


_AUTHORIZATION = {
    "needs_sponsorship": "needs visa sponsorship to work; besoin d'un parrainage de visa "
                         "sponsorisation autorisation de travail",
    "eu_authorized": "authorized to work in the EU; autorisé à travailler dans l'UE",
}


def _facts_text(pool: Pool) -> str:
    """What a fit sentence may state (Settings → Candidate)."""
    p = pool.profile
    langs = ", ".join(f"{x.get('language')} ({x.get('level')})" for x in p.get("languages") or [])
    return " ".join(x for x in (p.get("based_in") or "", p.get("nationality") or "",
                                _AUTHORIZATION.get(p.get("work_authorization") or "", ""),
                                langs) if x)


def context(s: Session, app: Application, language: str, pool: Pool | None = None,
            fmt: str = "pdf", char_limit: int | None = None) -> lc.Context:
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
    job_text = f"{job.title}\n{job.description or ''}"
    role = current_role(pool, job_text)
    form = fmt == "form"
    return lc.Context(
        pool=pool, allowed_years={int(f["years"]) for f in facts},
        job_text=job_text, company=company.name,
        language=language, banned=list(cfg["banned_phrases"].get(language) or []),
        min_words=int(cfg.get("form_min_words" if form else "min_words")
                      or (lc.FORM_MIN_WORDS if form else lc.DEFAULT_MIN_WORDS)),
        max_words=int(cfg.get("form_max_words" if form else "max_words")
                      or (lc.FORM_MAX_WORDS if form else lc.DEFAULT_MAX_WORDS)),
        format=fmt, char_limit=char_limit, jargon=list(cfg.get("jargon") or lc.DEFAULT_JARGON),
        current_role_id=role.id if role else None, current_role_org=role.org or "" if role else "",
        facts_text=_facts_text(pool),
        years_statement=english, years_statement_fr=french,
        other_companies=sorted(others - {company.name}),
        contact_name=contact.full_name if contact and language == "en" else "")


def build_request(s: Session, app: Application, cv: CVVersion, pool: Pool, language: str,
                  fmt: str = "pdf", question: str | None = None,
                  char_limit: int | None = None) -> LetterRequest:
    from app.services.outreach import cv_pool_subset

    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    cfg = letter_settings(s)
    facts, english, french = _statements(s, pool)
    profile = pool.profile
    role = current_role(pool, f"{job.title}\n{job.description or ''}")
    ctx_words = context(s, app, language, pool, fmt, char_limit)
    return LetterRequest(
        job={"title": job.title, "company": company.name, "location": job.location,
             "description": (job.description or "")[:8000]},
        candidate={"based_in": profile.get("based_in", ""),
                   "work_authorization": profile.get("work_authorization", ""),
                   "years": facts, "years_statement": english,
                   "years_statement_fr": french,
                   "current_role": {"id": role.id, "title": role.title, "org": role.org}
                   if role else None},
        pool=cv_pool_subset(pool, cv),
        rules={"language": language, "format": fmt, "min_words": ctx_words.min_words,
               "max_words": ctx_words.max_words, "question": question,
               "char_limit": char_limit,
               "banned_phrases": list(cfg["banned_phrases"].get(language) or []),
               "jargon": ctx_words.jargon, "guide": cfg.get("guide") or ""},
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
    """The paragraphs as shown and sent: the ask is its own short final paragraph."""
    texts = [t for t in (paragraph_text(p) for p in content.get("paragraphs") or []) if t]
    ask = str(content.get("ask") or "").strip()
    return [*texts, ask] if ask else texts


def default_salutation(s: Session, app: Application, language: str) -> str:
    contact = s.get(Contact, app.contact_id) if app.contact_id else None
    if contact and language == "en":
        return f"Dear {contact.full_name},"
    return letter_settings(s)["salutation"].get(language) or ""


def closing(s: Session, language: str) -> str:
    return letter_settings(s)["closing"].get(language) or ""


def plain_text(s: Session, letter: CoverLetter) -> str:
    """For web forms (Copy as text): salutation, paragraphs, closing, name. A form text is just
    its paragraphs."""
    content = letter.content or {}
    if (letter.format or "pdf") == "form":
        return "\n\n".join(body_paragraphs(content))
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
                           context(s, app, letter.language, pool, letter.format or "pdf",
                                   letter.char_limit))


def render(s: Session, letter: CoverLetter, pool: Pool,
           engine_key: str = "") -> list[dict[str, str]]:
    """Compile the PDF; returns the page problems (the letter must fit on one page). A form
    text has no PDF."""
    if (letter.format or "pdf") == "form":
        letter.tex, letter.pdf_path, letter.page_count = None, None, None
        return []
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
             language: str | None = None, *, fmt: str = "pdf", question: str | None = None,
             char_limit: int | None = None) -> CoverLetter:
    """Write the cover letter for one job (never in bulk: one at a time). `fmt="form"` writes
    the text for a form's text box answering `question`, within `char_limit`."""
    if fmt not in FORMATS:
        raise LetterError("format must be pdf or form")
    question = (question or "").strip() or None
    if fmt == "form" and not question:
        raise LetterError("Paste the form's question first")
    if char_limit is not None and char_limit < 100:
        raise LetterError("A character limit must be at least 100")
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
            if fmt == "pdf" and not has_letter(template):
                raise LetterError(f"The '{template.name}' template has no cover letter layout "
                                  "(add cover_letter.tex.j2 to it)")
            language = language if language in LANGUAGES else resolve_language(s, app, job)
            pool = load_pool(s)
            request = build_request(s, app, cv, pool, language, fmt, question, char_limit)
            ctx = context(s, app, language, pool, fmt, char_limit)
            salutation = default_salutation(s, app, language) if fmt == "pdf" else ""
        started = time.monotonic()

        def checked(plan: CoverLetterPlan) -> list[dict[str, str]]:
            content = content_from_plan(plan, salutation)
            return lc.check_letter(salutation, content["paragraphs"], content["ask"], ctx)

        write = drafter.draft_letter if fmt == "pdf" else drafter.draft_form
        try:
            plan = write(request)
            found, attempts = checked(plan), 1
            if lc.errors(found):  # one retry with the problems as feedback
                retry = write(request, lc.feedback(found))
                retry_found, attempts = checked(retry), 2
                if len(lc.errors(retry_found)) <= len(lc.errors(found)):
                    plan = retry
        except DraftFailed as exc:
            raise LetterError(str(exc)) from exc
        with Session(engine) as s:
            app = s.get(Application, app_id)
            existing = versions(s, app_id, fmt)
            for old in existing:
                if old.status == CVStatus.draft and old.locked_at is None:
                    old.status = CVStatus.superseded  # regenerate replaces the draft under review
                    s.add(old)
            letter = CoverLetter(
                application_id=app_id, version=(existing[0].version + 1) if existing else 1,
                language=language, format=fmt, question=question, char_limit=char_limit,
                content=content_from_plan(plan, salutation),
                template=cv.template or "default", cv_version_id=cv.id,
                generator_model=drafter.model, prompt_version=drafter.prompt_version,
                plan={"plan": plan.model_dump(), "attempts": attempts},
                duration_ms=int((time.monotonic() - started) * 1000))
            s.add(letter)
            s.flush()
            _refresh(s, letter, pool, _engine_key(engine))
            problems = len(lc.errors(letter.violations))
            kind = "Cover letter" if fmt == "pdf" else "Form text"
            pipeline.log_event(s, app, EventKind.letter_generated,
                               f"{kind} v{letter.version} ({language}) written"
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
            latest = versions(s, letter.application_id, letter.format or "pdf")[0]
            letter = CoverLetter(
                application_id=letter.application_id, version=latest.version + 1,
                language=letter.language, template=letter.template, format=letter.format,
                question=letter.question, char_limit=letter.char_limit,
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
        if (letter.format or "pdf") == "pdf" and (not letter.pdf_path
                                                  or not Path(letter.pdf_path).exists()):
            raise LetterError("The PDF isn't rendered")
        for other in versions(s, letter.application_id, letter.format or "pdf"):
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
    if letter.locked_at is not None or (letter.format or "pdf") == "form":
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
