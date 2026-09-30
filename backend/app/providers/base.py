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


class FlagCheck(BaseModel):
    present: bool = False
    evidence: str = Field(default="", description="Verbatim quote when present, else empty")


class FlagChecks(BaseModel):
    """One explicit yes/no per disqualifier type (prompt v3+). Structured output makes the model
    answer every check instead of taking the "empty red_flags list" shortcut."""

    no_visa_sponsorship: FlagCheck = Field(default_factory=FlagCheck)
    work_authorization_required: FlagCheck = Field(default_factory=FlagCheck)
    must_be_based_in: FlagCheck = Field(default_factory=FlagCheck)
    nationality_restricted: FlagCheck = Field(default_factory=FlagCheck)
    language_required: FlagCheck = Field(default_factory=FlagCheck)
    seniority_mismatch: FlagCheck = Field(default_factory=FlagCheck)


class FitAssessment(BaseModel):
    """What the LLM returns. The 0-100 score is computed from this in code (services/fit.py)."""

    role_match: SubScore
    skills_match: SubScore
    seniority_fit: SubScore
    location_eligibility: SubScore
    language_requirements: SubScore
    flag_checks: FlagChecks = Field(default_factory=FlagChecks)
    red_flags: list[RedFlag] = Field(default_factory=list, max_length=8)
    strengths: list[str] = Field(default_factory=list, max_length=3)
    gaps: list[str] = Field(default_factory=list, max_length=3)
    summary: str

    def sub_scores(self) -> dict[str, SubScore]:
        return {d: getattr(self, d) for d in DIMENSIONS}


class PlanBullet(BaseModel):
    source_index: int = Field(description="Index of the fact this bullet rewords")
    text: str = Field(description="The reworded bullet (same facts and numbers as the source)")
    priority: int = Field(ge=1, description="1 = most relevant to this job")
    strength: int = Field(default=3, ge=1, le=5, description=(
        "How strong the bullet is on its own: 5 = a concrete outcome or impact, 3 = a specific "
        "thing built, 1 = a generic process line (e.g. 'collaborated in Agile sprints')"))


class PlanEntry(BaseModel):
    item_id: int
    relevance: int = Field(ge=1, le=10, description="How relevant this entry is to the job")
    bullets: list[PlanBullet] = []


class PlanProject(PlanEntry):
    stack: list[str] = Field(default=[], description="Tech shown next to the name, from its tags")


class PlanSkillGroup(BaseModel):
    item_id: int = Field(description="Skill group id")
    items: list[str] = Field(description="Skills of that group, most relevant first")


class SummarySentence(BaseModel):
    text: str
    citations: list[int] = Field(description="Pool ids this sentence is based on (summary "
                                             "snippets, roles, projects, skill groups…)")


class SummaryDraft(BaseModel):
    """The summary only (used for the one regeneration after grounding rejects a sentence)."""

    summary_sentences: list[SummarySentence] = Field(description="2-3 sentences, each cited")
    summary_short_sentences: list[SummarySentence] = Field(
        description="About half the length, each cited (used when the page is tight)")


class CVPlanDraft(SummaryDraft):
    """What the model returns: selection, order and rewording, referencing pool ids. Never
    titles, companies, dates or locations (those come from the pool rows)."""

    skills: list[PlanSkillGroup] = []
    roles: list[PlanEntry] = Field(default=[], description="EVERY role, all its facts ranked")
    projects: list[PlanProject] = Field(default=[], description="Relevant projects, ranked")
    certification_ids: list[int] = []
    education_ids: list[int] = []
    volunteering: list[PlanEntry] = []


class CVPlan(BaseModel):
    """The plan code works with: the model's draft plus the summary as plain text (joined from
    the grounded sentences, or the fallback snippet)."""

    summary: str
    summary_short: str = Field(description="A shorter version of the summary (for tight pages)")
    summary_source_ids: list[int] = []
    summary_sentences: list[SummarySentence] = []
    summary_short_sentences: list[SummarySentence] = []
    skills: list[PlanSkillGroup] = []
    roles: list[PlanEntry] = Field(default=[], description="EVERY role, all its facts ranked")
    projects: list[PlanProject] = Field(default=[], description="Relevant projects, ranked")
    certification_ids: list[int] = []
    education_ids: list[int] = []
    volunteering: list[PlanEntry] = []


def plan_from_draft(draft: "CVPlanDraft") -> "CVPlan":
    return CVPlan(
        summary=" ".join(s.text.strip() for s in draft.summary_sentences),
        summary_short=" ".join(s.text.strip() for s in draft.summary_short_sentences),
        summary_source_ids=sorted({c for s in draft.summary_sentences for c in s.citations}),
        **draft.model_dump(),
    )


class CVRequest(BaseModel):
    """Input for one tailored CV."""

    job: dict[str, Any]  # title, company, description, matched_track, strengths, gaps
    pool: dict[str, Any]  # services.cv_pool.prompt_pool()
    emphasis: dict[str, Any] = {}  # Settings → CV track emphasis for the job's track
    # Facts computed in code that the model may state, e.g. {"years": [{"label", "years"}]}.
    facts: dict[str, Any] = {}
    guide: str = ""  # Settings → CV writing guide
    style: dict[str, Any] = {}  # the reference CV's summary and bullets (tone and length only)
    layout: dict[str, Any] = {}  # how many bullets code will show per entry, skills limits


class CVGenerationFailed(RuntimeError):
    """The CV generator couldn't produce a valid plan; the message is shown to the user."""


class DraftResult(BaseModel):
    subject: str
    body: str
    model: str


class DraftFailed(RuntimeError):
    """The email drafter couldn't produce a valid draft; the message is shown to the user."""


class EmailSentence(BaseModel):
    text: str
    citations: list[int] = Field(default_factory=list, description=(
        "Pool ids this sentence is based on (roles, projects, skill groups, education…). Empty "
        "only for a sentence about the company or the role, which must then set about_job"))
    about_job: bool = Field(default=False, description=(
        "True when the sentence is about the company or the role, stated only from the JOB "
        "listing (no claims about the candidate)"))


class EmailDraftPlan(BaseModel):
    """What the model returns; code adds the signature and the opt-out line."""

    subject: str = Field(description="Specific to the role and company, at most 8 words")
    greeting: str = Field(description="e.g. 'Hi Franck,' with the contact's first name")
    sentences: list[EmailSentence] = Field(description=(
        "2-4 body sentences: why this company and role, then 1-2 proof points from the CV"))
    ask: str = Field(description="The one clear ask, one sentence (e.g. a 15-minute call)")


class EmailRequest(BaseModel):
    job: dict[str, Any]
    contact: dict[str, Any]
    candidate: dict[str, Any]  # name, headline, location, years facts
    pool: dict[str, Any]  # the experience items used in the approved CV, with ids
    rules: dict[str, Any] = Field(default_factory=dict)  # max words, banned phrases


class LetterParagraph(BaseModel):
    sentences: list[EmailSentence] = Field(description=(
        "The paragraph's sentences, each cited (or about_job for the company/role)"))


class CoverLetterPlan(BaseModel):
    """What the model returns for a cover letter; code adds the header, date, recipient,
    salutation, closing formula and signature."""

    paragraphs: list[LetterParagraph] = Field(description=(
        "3-4 paragraphs: why this company and role (from the listing), 2-3 concrete things "
        "you built that match it, then fit and availability"))
    ask: str = Field(description="The one clear ask that ends the letter, one sentence")


class LetterRequest(BaseModel):
    job: dict[str, Any]
    candidate: dict[str, Any]
    pool: dict[str, Any]  # the experience items on the approved CV, with ids
    rules: dict[str, Any] = Field(default_factory=dict)  # language, words, banned, guide


class AnswerDraft(BaseModel):
    question_id: int = Field(description="The id of the question answered")
    sentences: list[EmailSentence] = Field(description="The answer, each sentence cited")


class AnswersPlan(BaseModel):
    answers: list[AnswerDraft]


class AnswersRequest(BaseModel):
    job: dict[str, Any]
    candidate: dict[str, Any]
    pool: dict[str, Any]
    questions: list[dict[str, Any]]  # {id, question, char_limit}
    rules: dict[str, Any] = Field(default_factory=dict)


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

    def generate(self, request: CVRequest) -> CVPlan:
        """Raises CVGenerationFailed with a human-readable reason."""
        ...

    def generate_summary(self, request: CVRequest, feedback: str) -> SummaryDraft:
        """Only the summary again, told which sentences were rejected and why."""
        ...


class EmailDrafter(Protocol):
    model: str
    prompt_version: str

    def draft(self, request: EmailRequest, feedback: str = "") -> EmailDraftPlan: ...


class LetterDrafter(Protocol):
    model: str
    prompt_version: str

    def draft_letter(self, request: LetterRequest, feedback: str = "") -> CoverLetterPlan: ...

    def answer(self, request: AnswersRequest, feedback: str = "") -> AnswersPlan: ...


class SendFailed(RuntimeError):
    """A send attempt failed. `fatal` (auth/config) pauses the queue; otherwise only this item
    fails and can be retried."""

    def __init__(self, message: str, *, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


class OutgoingEmail(BaseModel):
    to: str
    subject: str
    body: str  # plain text
    html: str | None = None  # optional alternative (signature photo)
    attachment_path: str | None = None
    attachment_name: str | None = None
    inline_images: dict[str, str] = Field(default_factory=dict)  # cid -> file path


class Mailer(Protocol):
    def send(self, email: OutgoingEmail) -> str: ...  # returns the Message-ID
