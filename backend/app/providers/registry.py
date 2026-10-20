"""Single place that decides which implementation backs each provider interface.
Phase 0: always the mocks. Later: read `app_setting['models']` and return Ollama/Claude/etc."""

from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.models.enums import Source
from app.providers.base import (
    CVGenerator,
    EmailDrafter,
    FitScorer,
    JobSource,
    LetterDrafter,
    Mailer,
)
from app.providers.mock import (
    MockCVGenerator,
    MockEmailDrafter,
    MockFitScorer,
    MockJobSource,
    MockLetterDrafter,
    MockMailer,
)


def real_source(source: Source) -> JobSource:
    """Real implementation for a source (imported lazily so tests never touch HTTP code)."""
    from app.providers.sources import REAL_SOURCES

    factory = REAL_SOURCES.get(source)
    return factory() if factory else MockJobSource(source)


def unsupported_countries(source: Source, targets: list[str]) -> list[str]:
    """Target countries a source can't search (e.g. Adzuna has no Portugal endpoint)."""
    from app.providers.sources import REAL_SOURCES

    check = getattr(REAL_SOURCES.get(source), "unsupported_countries", None)
    return check(targets) if check else []


def job_sources(enabled: list[Source], *, mock: bool | None = None) -> dict[Source, JobSource]:
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    return {s: MockJobSource(s) if use_mock else real_source(s) for s in enabled}


def fit_scorer(*, mock: bool | None = None, model: str = "qwen2.5:7b",
               engine: Any = None) -> FitScorer:
    """Real workspace: Gemini for `gemini-*` models (bulk scoring on the free API keys), Ollama for
    the rest. Tests and the tour sandbox: the deterministic mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        return MockFitScorer()
    if model.startswith("gemini-"):
        from app.db import engine as default_engine
        from app.providers.gemini import GeminiFitScorer
        from app.services.gemini_keys import pool_for

        return GeminiFitScorer(model, pool_for(engine or default_engine, model))
    from app.providers.ollama import OllamaFitScorer

    return OllamaFitScorer(model)


@lru_cache
def cv_generator(*, mock: bool | None = None, model: str = "claude-sonnet-5") -> CVGenerator:
    """Real workspace: Claude Code headless. Tests and the tour sandbox: the deterministic mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        return MockCVGenerator()
    from app.providers.claude_cv import ClaudeCVGenerator

    return ClaudeCVGenerator(model)


def email_drafter(*, mock: bool | None = None, model: str = "claude-sonnet-5") -> EmailDrafter:
    """Real workspace: Claude Code headless (subscription only). Tests and the sandbox: mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        return MockEmailDrafter()
    from app.providers.claude_email import ClaudeEmailDrafter

    return ClaudeEmailDrafter(model)


def letter_drafter(*, mock: bool | None = None, model: str = "claude-sonnet-5") -> LetterDrafter:
    """Cover letters and application answers. Real workspace: Claude Code headless (subscription
    only). Tests and the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        return MockLetterDrafter()
    from app.providers.claude_letter import ClaudeLetterDrafter

    return ClaudeLetterDrafter(model)


def copilot(*, mock: bool | None = None, model: str = "gemma4:12b"):  # noqa: ANN201
    """The Copilot's local model (Ollama). Tests and the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.providers.ollama_chat import MockCopilot, OllamaCopilot

    return MockCopilot() if use_mock else OllamaCopilot(model)


def rewriter(*, mock: bool | None = None, model: str = "claude-sonnet-5"):  # noqa: ANN201
    """Claude, for Copilot answers you'll send to people. Tests and the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.providers.claude_rewrite import ClaudeRewriter, MockRewriter

    return MockRewriter() if use_mock else ClaudeRewriter(model)


def researcher(*, mock: bool | None = None, model: str = "gemma4:31b-cloud",
               fallback: str | None = "gemma4:12b"):  # noqa: ANN201
    """Company research signals (cold emails only). Tests and the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.services.research import MockResearcher, OllamaResearcher

    return MockResearcher() if use_mock else OllamaResearcher(model, fallback)


def hook_checker(*, mock: bool | None = None, model: str = "gemma4:31b-cloud",
                 fallback: str | None = "gemma4:12b"):  # noqa: ANN201
    """Checks an email's hook against the signals it cites (the research models). Tests and the
    sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.services.hook_check import MockHookChecker, OllamaHookChecker

    return MockHookChecker() if use_mock else OllamaHookChecker(model, fallback)


def linkedin_drafter(*, mock: bool | None = None, model: str = "claude-sonnet-5"):  # noqa: ANN201
    """LinkedIn connection notes and follow-ups: Claude Code headless (your subscription). Tests
    and the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.providers.claude_linkedin import ClaudeLinkedInDrafter
    from app.providers.mock import MockLinkedInDrafter

    return MockLinkedInDrafter() if use_mock else ClaudeLinkedInDrafter(model)


def critic(*, mock: bool | None = None, model: str = "claude-sonnet-5"):  # noqa: ANN201
    """Critique (claude -p). Tests and the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.providers.claude_critique import ClaudeCritic
    from app.providers.mock import MockCritic

    return MockCritic() if use_mock else ClaudeCritic(model)


def verifier(*, mock: bool | None = None, model: str = "claude-opus-5-5"):  # noqa: ANN201
    """The claim verifier (claude -p, never an API key). Tests and the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.providers.claude_verify import ClaudeVerifier
    from app.providers.mock import MockVerifier

    return MockVerifier() if use_mock else ClaudeVerifier(model)


_mock_hunter = None


def hunter(*, mock: bool | None = None):  # noqa: ANN201
    """Hunter.io for Try Hunter (a click, never automatic). Tests and the sandbox: the mock.
    Raises HunterError when HUNTER_API_KEY isn't set."""
    global _mock_hunter
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    from app.providers.hunter import HunterClient, MockHunter

    if use_mock:
        _mock_hunter = _mock_hunter or MockHunter()
        return _mock_hunter
    return HunterClient(get_settings().hunter_api_key)


def interview_drafter(*, mock: bool | None = None, model: str = "claude-sonnet-5"):  # noqa: ANN201
    """Interview preparation. Real workspace: Claude Code headless (subscription only). Tests and
    the sandbox: the mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        from app.providers.mock import MockInterviewDrafter

        return MockInterviewDrafter()
    from app.providers.claude_interview import ClaudeInterviewDrafter

    return ClaudeInterviewDrafter(model)


def contact_finders(*, mock: bool | None = None) -> dict:
    """Hunter, Prospeo, Apollo and Apify, in waterfall order. Only the Get contact waterfall
    (one click) calls them. The sandbox and tests: the mock, which makes no request."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        from app.providers.contact_finders.mock import MockFinder

        return {"hunter": MockFinder("hunter"),
                "prospeo": MockFinder("prospeo", needs_reveal=True, finds=True),
                "apollo": MockFinder("apollo", needs_reveal=True),
                "apify": MockFinder("apify", "usd")}
    from app.providers.contact_finders.apify import ApifyFinder
    from app.providers.contact_finders.apollo import ApolloFinder
    from app.providers.contact_finders.hunter import HunterFinder
    from app.providers.contact_finders.prospeo import ProspeoFinder

    return {"hunter": HunterFinder(), "prospeo": ProspeoFinder(), "apollo": ApolloFinder(),
            "apify": ApifyFinder()}


_mock_mailer = MockMailer()


def mailer(*, mock: bool | None = None, address: str = "", from_name: str = "") -> Mailer:
    """Gmail SMTP when an address and SMTP_APP_PASSWORD are configured; otherwise (and in the
    sandbox and tests) the mock, which never sends anything."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    password = get_settings().smtp_app_password
    if use_mock:
        return _mock_mailer
    if not address or not password:
        from app.providers.base import SendFailed

        raise SendFailed("Email isn't configured: set the Gmail address in Settings → Email and "
                         "SMTP_APP_PASSWORD in .env", fatal=True)
    from app.providers.smtp_mailer import GmailMailer

    return GmailMailer(address, password, from_name)


def confirmers(*, mock: bool | None = None, engine: Any = None,
               claude_model: str = "claude-sonnet-5-5") -> list[tuple[str, Any]]:
    """Ask Claude, in order: Claude Code headless (your subscription), then Gemma through the
    Gemini API. The last fallback (copy-paste into the Gemini Pro app) is a user flow. Tests and
    the tour sandbox: the mock only."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        from app.providers.mock import MockConfirmer

        return [("mock", MockConfirmer())]
    from app.db import engine as default_engine
    from app.providers.claude_confirm import ClaudeConfirmer
    from app.providers.gemini import GeminiConfirmer
    from app.services.gemini_keys import pool_for

    model = "gemma-4-31b-it"
    return [("claude", ClaudeConfirmer(claude_model)),
            ("gemma", GeminiConfirmer(model, pool_for(engine or default_engine, model),
                                      native=False, timeout=240.0))]
