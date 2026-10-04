from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LetterSentenceOut(BaseModel):
    text: str
    citations: list[int] = []
    about_job: bool = False


class LetterParagraphOut(BaseModel):
    text: str
    edited: bool  # your text: citations no longer apply (checked against experience + listing)
    sentences: list[LetterSentenceOut] = []


class LetterOut(BaseModel):
    id: int
    application_id: int
    version: int
    status: str  # draft | approved | superseded
    language: str  # fr | en
    format: str = "pdf"  # pdf | form
    question: str | None = None  # form: the form's question
    char_limit: int | None = None
    length: int = 0  # characters of the text (the form's limit counts these)
    salutation: str
    paragraphs: list[LetterParagraphOut]
    ask: str
    closing: str
    text: str  # plain text for web forms
    word_count: int
    page_count: int | None
    has_pdf: bool
    violations: list[dict[str, Any]]
    sources: dict[int, str]  # cited pool item id → "Title · Org"
    cv_version_id: int | None
    cv_version: int | None
    generator_model: str
    duration_ms: int | None
    error: str | None
    locked_at: datetime | None
    download_name: str
    created_at: datetime
    updated_at: datetime
    # The claim verifier (services/verifier.py): its last run and whether it still applies.
    verification: dict[str, Any] = {}
    verification_state: str = "none"  # passed | failed | error | stale | none


class LetterStudio(BaseModel):
    application_id: int
    job_id: int
    job_title: str
    company_name: str
    stage: str
    route: str
    language_setting: str  # the job's choice: auto | fr | en
    detected_language: str  # the listing's language
    language: str  # what the next letter will be written in
    approved_cv_id: int | None
    approved_cv_version: int | None
    template_ok: bool
    letters: list[LetterOut]


class LetterGenerateIn(BaseModel):
    language: str | None = None  # fr | en; default: the job's setting or the listing's
    format: str = "pdf"  # pdf | form
    question: str | None = None  # form: the question to answer
    char_limit: int | None = None


class LetterPatch(BaseModel):
    salutation: str | None = None
    paragraphs: list[str] | None = None
    ask: str | None = None


class LetterLanguageIn(BaseModel):
    language: str  # auto | fr | en


class LetterText(BaseModel):
    text: str


class QuestionIn(BaseModel):
    question: str
    char_limit: int | None = None


class AnswersIn(BaseModel):
    questions: list[QuestionIn]


class AnswerPatch(BaseModel):
    answer: str | None = None
    question: str | None = None
    char_limit: int | None = None
    clear_limit: bool = False  # char_limit None means "unchanged" unless this is set


class AnswerOut(BaseModel):
    id: int
    application_id: int
    question: str
    char_limit: int | None
    answer: str
    length: int
    language: str
    edited: bool
    sentences: list[LetterSentenceOut]
    sources: dict[int, str]
    violations: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    # The claim verifier (services/verifier.py): its last run and whether it still applies.
    verification: dict[str, Any] = {}
    verification_state: str = "none"  # passed | failed | error | stale | none
