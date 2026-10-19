from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PrepSentenceOut(BaseModel):
    text: str
    citations: list[int] = []
    about_job: bool = False
    about_candidate: bool = False


class StarStoryOut(BaseModel):
    requirement: str
    title: str
    situation: list[PrepSentenceOut]
    task: list[PrepSentenceOut]
    action: list[PrepSentenceOut]
    result: list[PrepSentenceOut]


class PrepQuestionOut(BaseModel):
    question: str
    probes: str
    story: int = -1


class InterviewContent(BaseModel):
    pitch: list[PrepSentenceOut]
    stories: list[StarStoryOut]
    questions: list[PrepQuestionOut]
    ask_them: list[str]


class InterviewPrepOut(BaseModel):
    id: int
    application_id: int
    version: int
    status: str  # draft | approved | superseded
    language: str
    content: InterviewContent
    sources: dict[int, str]  # pool id -> "title · org" for the citations
    violations: list[dict[str, Any]]
    verification: dict[str, Any]
    verification_state: str  # none | passed | failed | error | stale
    generator_model: str | None
    prompt_version: str | None
    created_at: datetime


class InterviewStudio(BaseModel):
    application_id: int
    job_title: str
    company_name: str
    prep: InterviewPrepOut | None
    versions: int
    language: str  # the language a new one will be written in
    has_experience: bool  # the pool has something to build stories from


class InterviewGenerateIn(BaseModel):
    language: str | None = None


class InterviewPatch(BaseModel):
    content: InterviewContent
