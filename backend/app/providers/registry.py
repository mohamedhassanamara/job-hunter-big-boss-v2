"""Single place that decides which implementation backs each provider interface.
Phase 0: always the mocks. Later: read `app_setting['models']` and return Ollama/Claude/etc."""

from functools import lru_cache

from app.config import get_settings
from app.models.enums import Source
from app.providers.base import CVGenerator, CVRenderer, EmailDrafter, FitScorer, JobSource, Mailer
from app.providers.mock import (
    MockCVGenerator,
    MockCVRenderer,
    MockEmailDrafter,
    MockFitScorer,
    MockJobSource,
    MockMailer,
)


def real_source(source: Source) -> JobSource:
    """Real implementation for a source (imported lazily so tests never touch HTTP code)."""
    from app.providers.sources import REAL_SOURCES

    factory = REAL_SOURCES.get(source)
    return factory() if factory else MockJobSource(source)


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
def cv_generator() -> CVGenerator:
    return MockCVGenerator()


@lru_cache
def cv_renderer() -> CVRenderer:
    return MockCVRenderer()


@lru_cache
def email_drafter() -> EmailDrafter:
    return MockEmailDrafter()


@lru_cache
def mailer() -> Mailer:
    return MockMailer()
