"""Provider interfaces. Real implementations (Ollama, Claude, pdflatex, Gmail SMTP, job APIs)
plug in behind these Protocols. Phase 0 ships deterministic mocks only (see providers/mock)."""

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.models.enums import DescriptionLevel, RemoteType, Source


class ScoringFailed(RuntimeError):
    """The scorer couldn't produce a valid assessment. The message is shown to the user.
    Plain ScoringFailed = non-retryable (invalid output after the repair retry, model missing)."""


class ConcurrencyLimited(ScoringFailed):
    """Too many requests at once (cloud plan limit). Never a failure: retry the same job."""


class QuotaExceeded(ScoringFailed):
    """Cloud usage limit reached (session/hourly/weekly). Switch the run to the local model."""


class TransientError(ScoringFailed):
    """Timeout, connection problem or 5xx: worth a few more attempts."""


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
    # How complete `description` is (drives scoring confidence).
    description_level: DescriptionLevel = DescriptionLevel.full
    # Set by the pre-filter: which of the user's tracks/roles the title matched.
    matched_track: str | None = None
    matched_role: str | None = None


class ProfileSpec(BaseModel):
    roles: list[str] = []  # flat list of all role titles (derived from tracks)
    # [{name, years_experience, roles: [{title, variants: {lang: [..]}}]}] from Settings
    tracks: list[dict[str, Any]] = []
    keywords: list[str] = []
    excluded_keywords: list[str] = []
    locations: list[str] = []
    remote_policy: str = "remote_ok"
    remote_scope: str = "anywhere"
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


DIMENSIONS = (
    "role_match",
    "skills_match",
    "seniority_fit",
    "location_eligibility",
    "language_requirements",
)
RedFlagType = Literal[
    "no_visa_sponsorship",
    "work_authorization_required",
    "must_be_based_in",
    "nationality_restricted",
    "language_required",
    "seniority_mismatch",
    "other",
]


class SubScore(BaseModel):
    score: int = Field(ge=0, le=10)
    reason: str
    evidence: str = Field(description="Verbatim quote from the job text, or empty")


class RedFlag(BaseModel):
    type: RedFlagType
    text: str
    evidence: str = Field(description="Verbatim quote from the job text")


class FitAssessment(BaseModel):
    """What the LLM returns. The 0-100 score is computed from this in code (services/fit.py)."""

    role_match: SubScore
    skills_match: SubScore
    seniority_fit: SubScore
    location_eligibility: SubScore
    language_requirements: SubScore
    red_flags: list[RedFlag] = Field(default_factory=list, max_length=8)
    strengths: list[str] = Field(default_factory=list, max_length=3)
    gaps: list[str] = Field(default_factory=list, max_length=3)
    summary: str

    def sub_scores(self) -> dict[str, SubScore]:
        return {d: getattr(self, d) for d in DIMENSIONS}


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
    model: str

    def assess(self, system: str, user: str, job: JobSnapshot) -> FitAssessment:
        """Raises ScoringFailed (with a human-readable reason) when no valid answer is possible."""
        ...


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
