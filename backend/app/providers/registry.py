"""Single place that decides which implementation backs each provider interface.
Phase 0: always the mocks. Later: read `app_setting['models']` and return Ollama/Claude/etc."""

from functools import lru_cache

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


def fit_scorer(*, mock: bool | None = None, model: str = "qwen2.5:7b") -> FitScorer:
    """Real workspace: Ollama. Tests and the tour sandbox: the deterministic mock."""
    use_mock = get_settings().job_sources == "mock" if mock is None else mock
    if use_mock:
        return MockFitScorer()
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
