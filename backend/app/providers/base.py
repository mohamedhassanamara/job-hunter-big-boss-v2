"""Provider interfaces. Real implementations (Ollama, Claude, pdflatex, Gmail SMTP, job APIs)
plug in behind these Protocols. Phase 0 ships deterministic mocks only (see providers/mock)."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from app.models.enums import RemoteType, Source


class RawJob(BaseModel):
    source: Source
    external_id: str
    url: str
    title: str
    company: str
    location: str = ""
    country: str | None = None
    remote_type: RemoteType = RemoteType.unknown
    description: str = ""
    salary_text: str | None = None
    posted_at: datetime | None = None


class ProfileSpec(BaseModel):
    roles: list[str] = []
    keywords: list[str] = []
    excluded_keywords: list[str] = []
    locations: list[str] = []
    remote_policy: str = "remote_ok"
    max_age_days: int = 30


class JobSnapshot(BaseModel):
    title: str
    company: str
    location: str = ""
    remote_type: str = "unknown"
    description: str = ""


class ExperienceSnapshot(BaseModel):
    kind: str
    title: str
    org: str | None = None
    summary: str | None = None
    bullets: list[str] = []
    tags: list[str] = []
    dates: str | None = None


class FitResult(BaseModel):
    score: int = Field(ge=0, le=100)
    strengths: list[str]
    gaps: list[str]
    summary: str
    model: str


class CVEntry(BaseModel):
    title: str
    org: str = ""
    location: str = ""
    dates: str = ""
    bullets: list[str] = []


class CVSkillGroup(BaseModel):
    group: str
    items: list[str]


class CVContent(BaseModel):
    """The structured CV that the universal LaTeX template renders."""

    name: str
    headline: str
    contact: list[str] = []
    summary: str = ""
    experience: list[CVEntry] = []
    projects: list[CVEntry] = []
    skills: list[CVSkillGroup] = []
    education: list[CVEntry] = []


class RenderedCV(BaseModel):
    tex: str
    pdf_path: str | None
    page_count: int


class DraftResult(BaseModel):
    subject: str
    body: str
    model: str


class ContactSnapshot(BaseModel):
    full_name: str
    title: str | None = None
    email: str | None = None


class JobSource(Protocol):
    source: Source
    # Minimum hours between real fetches (e.g. Remotive asks for <= 4 requests/day).
    cooldown_hours: float
    # HTTP requests made by the last fetch (for the run report).
    requests: int

    def configured(self) -> str | None:
        """None when ready, otherwise a human-readable reason (e.g. missing API keys)."""
        ...

    def fetch(self, profile: ProfileSpec) -> list[RawJob]: ...


class FitScorer(Protocol):
    def score(self, job: JobSnapshot, experience: list[ExperienceSnapshot]) -> FitResult: ...


class CVGenerator(Protocol):
    model: str

    def generate(self, job: JobSnapshot, experience: list[ExperienceSnapshot]) -> CVContent: ...


class CVRenderer(Protocol):
    def render(self, content: CVContent, out_name: str) -> RenderedCV: ...


class EmailDrafter(Protocol):
    def draft(
        self, job: JobSnapshot, contact: ContactSnapshot, cv: CVContent | None
    ) -> DraftResult: ...


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str, attachment_path: str | None) -> None: ...
