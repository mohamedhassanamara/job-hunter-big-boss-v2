"""Provider interfaces. Real implementations (Ollama, Claude, pdflatex, Gmail SMTP, job APIs)
plug in behind these Protocols. Phase 0 ships deterministic mocks only (see providers/mock)."""

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.models.enums import DescriptionLevel, RemoteType, Source


class ScoringFailed(RuntimeError):
    """The scorer couldn't produce a valid assessment. The message is shown to the user.
    Plain ScoringFailed = non-retryable (invalid output after the repair retry, model missing)."""


class ConcurrencyLimited(ScoringFailed):
    """Too many requests at once (cloud plan limit). Never a failure: retry the same job."""


class QuotaExceeded(ScoringFailed):
    """Cloud usage limit reached (session/hourly/weekly). Switch the run to the local model."""


class QuotaWait(ScoringFailed):
    """Every API key is out of quota for today (or none is usable). Never a failure and never a
    reason to switch model: the queue pauses and carries on at `resume_at` (None: it needs you,
    e.g. every key was refused)."""

    def __init__(self, message: str, resume_at: datetime | None = None):
        super().__init__(message)
        self.resume_at = resume_at


class TransientError(ScoringFailed):
    """Timeout, connection problem or 5xx: worth a few more attempts."""


class RawJob(BaseModel):
    source: Source
    external_id: str
    url: str
    apply_url: str | None = None
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
    evidence: str = Field(default="", description="Verbatim quote from the job text, or empty")


class RedFlag(BaseModel):
    type: RedFlagType
    text: str
    evidence: str = Field(description="Verbatim quote from the job text")


class FlagCheck(BaseModel):
    present: bool = False
    evidence: str = Field(default="", description="Verbatim quote when present, else empty")


class CoreRequirement(BaseModel):
    """What the role is built around (prompt v5): the primary language or stack, or the central
    skill. `missing` = the candidate's experience has nothing of it at all."""

    requirement: str = Field(description="Short name, e.g. 'Go' or 'large-scale web scraping'")
    evidence: str = Field(default="",
                          description="Verbatim quote from the job text showing it is core")
    missing: bool = False


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
    core_requirements: list[CoreRequirement] = Field(default_factory=list, max_length=4)
    red_flags: list[RedFlag] = Field(default_factory=list, max_length=8)
    strengths: list[str] = Field(default_factory=list, max_length=3)
    gaps: list[str] = Field(default_factory=list, max_length=3)
    summary: str

    # Fields returned by APInex / fit_score.md v7
    overall_score: int | None = None
    verdict: str | None = None
    disqualifying_flags: list[str] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _from_flexible_schema(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Adapt APInex / fit_score v7 response if 'dimensions' is present
        if "dimensions" in data and isinstance(data["dimensions"], dict):
            dims = data["dimensions"]
            for dim_name in DIMENSIONS:
                dim_val = dims.get(dim_name)
                # A missing or invalid sub-score is never defaulted: leaving it out (or out of
                # range) makes validation fail, and the scorer retries once, then gives up.
                if isinstance(dim_val, dict):
                    entry = {
                        "reason": str(dim_val.get("reason") or ""),
                        "evidence": str(dim_val.get("evidence") or ""),
                    }
                    raw_s = dim_val.get("score")
                    if isinstance(raw_s, (int, float)) and not isinstance(raw_s, bool):
                        entry["score"] = int(round(raw_s))
                    data[dim_name] = entry

            if "key_strengths" in data and "strengths" not in data:
                data["strengths"] = [str(s) for s in data["key_strengths"] if str(s).strip()][:3]
            if "critical_gaps" in data and "gaps" not in data:
                data["gaps"] = [str(g) for g in data["critical_gaps"] if str(g).strip()][:3]
            if "disqualifying_flags" in data and "red_flags" not in data:
                flags = data["disqualifying_flags"] or []
                data["red_flags"] = [
                    {"type": "other", "text": str(f).strip(), "evidence": ""}
                    for f in flags if str(f).strip()
                ][:8]
            if "summary" not in data and "verdict" in data:
                data["summary"] = f"Verdict: {data['verdict']}"
            elif "summary" in data and not isinstance(data["summary"], str):
                data["summary"] = str(data["summary"])

        return data

    def sub_scores(self) -> dict[str, SubScore]:
        return {d: getattr(self, d) for d in DIMENSIONS}


class Verdict(BaseModel):
    """A second opinion in plain words (Ask Claude): should the candidate apply to this job?"""

    advice: Literal["apply", "maybe", "skip"]
    why: str = Field(description="At most 40 words: the deciding factor")
    seniority: str = Field(description="One short sentence: is the level right?")
    skills: str = Field(description="One short sentence: do the skills match?")
    location_visa: str = Field(description="One short sentence: can they take it from where they "
                                           "live with their work authorization?")
    language: str = Field(description="One short sentence: is the language requirement met?")


class ConfirmationAnswer(FitAssessment):
    """The scoring answer plus a verdict: what Ask Claude / Gemma / the Gemini Pro app return."""

    verdict: Verdict


class PlanBullet(BaseModel):
    source_index: int = Field(description="Index of the fact this bullet rewords")
    text: str = Field(description=(
        "The bullet, lightly adapted to the job: every number, tool and product of the source "
        "kept, about the same length"))
    priority: int = Field(ge=1, description="1 = most relevant to this job")
    strength: int = Field(default=3, ge=1, le=5, description=(
        "How strong the bullet is on its own: 5 = a concrete outcome or impact, 3 = a specific "
        "thing built, 1 = a generic process line (e.g. 'collaborated in Agile sprints')"))
    # Set by code (services/bullet_tailor.py), never by the model: is `text` an adaptation of the
    # pool original (True) or the original itself (False), and why an adaptation was refused.
    adapted: SkipJsonSchema[bool] = False
    fallback: SkipJsonSchema[str | None] = None


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


class PlanExtra(BaseModel):
    """A pool bullet (or a whole project) the model did not pick as essential, rated for this job.
    Code adds them in relevance order only while the page is under the fill target, after
    checking each one (services/cv_build.py `fill_by_relevance`)."""

    kind: Literal["role", "project"]
    item_id: int
    source_index: int | None = Field(
        default=None, description="Fact index, or None for a whole project")
    relevance: int = Field(ge=0, le=10)


class CVPlanDraft(SummaryDraft):
    """What the model returns: selection, order and rewording, referencing pool ids. Never
    titles, companies, dates or locations (those come from the pool rows)."""

    skills: list[PlanSkillGroup] = []
    roles: list[PlanEntry] = Field(default=[], description="EVERY role, all its facts ranked")
    projects: list[PlanProject] = Field(default=[], description="Relevant projects, ranked")
    certification_ids: list[int] = []
    education_ids: list[int] = []
    volunteering: list[PlanEntry] = []
    extras: SkipJsonSchema[list[PlanExtra]] = []  # rated leftovers (the 2-pass generator)


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
    extras: list[PlanExtra] = []  # not yet on the page; consumed by fill_by_relevance
    fill_log: list[dict[str, Any]] = []  # what fill_by_relevance added or skipped, and why


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
    about_candidate: bool = Field(default=False, description=(
        "Cover letters only: True for a fit sentence stated only from FACTS (where the "
        "candidate is based, work authorization/visa sponsorship, languages); it cites nothing"))


class EmailDraftPlan(BaseModel):
    """What the model returns; code adds the signature and the opt-out line."""

    subject: str = Field(description="Specific to the role and company, at most 8 words")
    greeting: str = Field(description="e.g. 'Hi Franck,' with the contact's first name")
    sentences: list[EmailSentence] = Field(description=(
        "2-4 body sentences: why this company and role, then 1-2 proof points from the CV"))
    ask: str = Field(description="The one clear ask, one sentence (e.g. a 15-minute call)")


class HookSentence(BaseModel):
    text: str = Field(description=(
        "How the candidate came across the company (described by its field, never a job board "
        "or listing) and 1-2 facts from SIGNALS, stated plainly"))
    signal_ids: list[int] = Field(default_factory=list, description=(
        "The SIGNALS ids every company fact in the hook comes from"))


class IntroEmailPlan(BaseModel):
    """A personal introduction (not a reply to a listing). Code builds the intro line from the
    profile and assembles: greeting, hook, intro, value (problem + proofs), ask."""

    subject: str = Field(description="About the value, at most 8 words; never the role/position")
    greeting: str = Field(description="'Hi <first name>,' / 'Bonjour <prénom>,'")
    hook: HookSentence
    intro_focus: str = Field(description=(
        "The 2-3 areas of the candidate's experience relevant to this company, as a short "
        "phrase in the email's language (e.g. 'backend, mobile and AI systems')"))
    problem: str = Field(description=(
        "One sentence: the problem their team is dealing with, phrased as their problem, "
        "inferred from the job listing and the signals, never mentioning the listing"))
    proofs: list[EmailSentence] = Field(description=(
        "1-2 sentences from the EXPERIENCE POOL showing the candidate solved something similar, "
        "each citing pool ids, in plain language"))
    ask: str = Field(description="A direct question: do they have an opening where this helps")


class AppliedEmailPlan(BaseModel):
    """An honest application follow-up for a job the candidate applied (or is applying) for.
    Code builds the greeting and the subject and assembles: opening, experience, signal, ask.
    Immigration, visa and relocation constraints are strictly excluded from cold emails."""

    model_config = ConfigDict(extra="ignore")

    role: str = Field(description=(
        "The role's name in plain words for the subject line (e.g. 'Mobile Developer'): the "
        "JOB title without gender tags, location or tech suffixes"))
    greeting: str = Field(description="'Hi <first name>,' / 'Bonjour <prénom>,'")
    opening: str = Field(description=(
        "One or two sentences: the candidate applied (or is applying) for the role at the "
        "company and wanted to reach out directly. The role and the listing may be named"))
    experience: list[EmailSentence] = Field(description=(
        "One or two sentences (at most two proofs, one sentence each) from the EXPERIENCE POOL "
        "on the experience that best answers the recipient's domain and the listing's core "
        "requirements, "
        "plain language, each citing pool ids"))
    signal: HookSentence = Field(default_factory=lambda: HookSentence(text=""), description=(
        "Optional: one company fact from SIGNALS that genuinely adds something, with its id. "
        "Empty text when none"))
    ask: str = Field(description=(
        "A simple, natural ask (look at the attached CV, a short call); a statement or a "
        "question"))

    @property
    def constraint(self) -> str:
        return ""

    @property
    def constraint_quote(self) -> str:
        return ""


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
        "2-3 paragraphs: why this company and role (one specific thing from the listing), at "
        "most 2 examples explained in plain words, then fit and availability"))
    ask: str = Field(default="", description=(
        "The ask for an interview, its own short final paragraph (a form text may leave it "
        "empty)"))


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

    def generate_summary(self, request: CVRequest, feedback: str, current: str = "",
                         user_feedback: str = "") -> SummaryDraft:
        """Only the summary again, told which sentences were rejected and why; with `current` and
        `user_feedback` it edits the current summary toward the user's feedback."""
        ...


class LinkedInMessage(BaseModel):
    """A LinkedIn connection note or follow-up, as one short text. Facts about you cite pool
    ids; the program checks length, grounding, years and banned phrases."""

    subject: str = Field(default="", description="InMail only: the subject line (at most 80 "
                                                  "characters); empty for a note or follow-up")
    text: str = Field(description="The whole message, ready to paste (no greeting line breaks)")
    citations: list[int] = Field(default_factory=list,
                                 description="Pool ids of every fact about you it states")
    signal_ids: list[int] = Field(default_factory=list,
                                  description="Company signals it uses (follow-up only)")


class LinkedInRequest(BaseModel):
    kind: str  # note | followup | inmail
    job: dict[str, Any]
    person: dict[str, Any]  # first_name, full_name, title, group, alumni, warm_opener
    candidate: dict[str, Any]
    pool: dict[str, Any]
    rules: dict[str, Any]


class LinkedInDrafter(Protocol):
    model: str
    prompt_version: str

    def draft(self, request: LinkedInRequest, feedback: str = "") -> LinkedInMessage: ...


class CritiqueIssue(BaseModel):
    where: str
    issue: str
    why: str


class CritiquePlan(BaseModel):
    """What's still weak from the reader's side (never a rewrite)."""

    issues: list[CritiqueIssue] = Field(default_factory=list)


VerifyVerdict = Literal["supported", "unsupported", "exaggerated", "merged", "causal",
                        "not_a_claim", "garbled"]  # garbled: a warning only (never blocking)


class VerifyClaim(BaseModel):
    """One atomic statement of the text, judged against one named source."""

    sentence: str  # the sentence of the text it comes from, copied exactly
    claim: str  # the single statement being judged
    about: Literal["candidate", "company", "other"]
    verdict: VerifyVerdict
    source_id: str = ""  # e.g. "pool:5", "cv", "facts", "signal:12", "listing"; "" when none
    source_quote: str = ""  # copied verbatim from that source ("" when none)
    reason: str = ""
    # For a flagged claim only: the whole sentence rewritten with facts from the sources ("" = no
    # support for it, so the sentence should go), the source it relies on and its exact quote.
    suggestion: str = ""
    suggestion_source_id: str = ""
    suggestion_quote: str = ""


class VerifyPlan(BaseModel):
    """The claim verifier's answer: every sentence of the text split into claims."""

    claims: list[VerifyClaim] = Field(default_factory=list)


class EmailDrafter(Protocol):
    model: str
    prompt_version: str

    def draft(self, request: EmailRequest, feedback: str = "") -> EmailDraftPlan: ...

    def draft_intro(self, request: EmailRequest, feedback: str = "") -> IntroEmailPlan: ...

    def draft_applied(self, request: EmailRequest, feedback: str = "") -> AppliedEmailPlan: ...


class LetterDrafter(Protocol):
    model: str
    prompt_version: str

    def draft_letter(self, request: LetterRequest, feedback: str = "") -> CoverLetterPlan: ...

    def draft_form(self, request: LetterRequest, feedback: str = "") -> CoverLetterPlan: ...

    def answer(self, request: AnswersRequest, feedback: str = "") -> AnswersPlan: ...


class StarStory(BaseModel):
    requirement: str = Field(description=(
        "The requirement or theme from the JOB listing this story answers, in a few words"))
    title: str = Field(description="What the story is, in a few words, from the pool item")
    situation: list[EmailSentence] = Field(description="The context, only what the cited items say")
    task: list[EmailSentence] = Field(description="What the candidate had to do, from the items")
    action: list[EmailSentence] = Field(description="What the candidate did, tools as written")
    result: list[EmailSentence] = Field(default_factory=list, description=(
        "What came of it, ONLY when the cited items say so (numbers exactly as written). Leave "
        "empty when they don't: never invent an outcome"))


class PrepQuestion(BaseModel):
    question: str = Field(description="A question this interviewer is likely to ask for this job")
    probes: str = Field(description="What the question is really checking, in a few words")
    story: int = Field(default=-1, description="Index of the story to answer with, -1 for none")


class InterviewPrepPlan(BaseModel):
    """Interview preparation for one job, from the experience pool only. Every sentence about the
    candidate cites pool ids; questions are about the job and carry no claims."""

    pitch: list[EmailSentence] = Field(description=(
        "3-4 sentences for 'tell me about yourself', linking the current role to this one"))
    stories: list[StarStory] = Field(description="3-4 STAR stories, each from a different item")
    questions: list[PrepQuestion] = Field(description="6-8 likely questions, from the listing")
    ask_them: list[str] = Field(description=(
        "3-4 questions to ask the interviewer, from the listing"))


class InterviewRequest(BaseModel):
    job: dict[str, Any]
    candidate: dict[str, Any]
    pool: dict[str, Any]  # the experience pool with ids
    rules: dict[str, Any] = Field(default_factory=dict)


class InterviewDrafter(Protocol):
    model: str
    prompt_version: str

    def prepare(self, request: InterviewRequest, feedback: str = "") -> InterviewPrepPlan: ...


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
