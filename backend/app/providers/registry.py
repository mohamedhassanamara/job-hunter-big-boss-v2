"""Single place that decides which implementation backs each provider interface.
Phase 0: always the mocks. Later: read `app_setting['models']` and return Ollama/Claude/etc."""

from functools import lru_cache

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


def job_sources(enabled: list[Source]) -> list[JobSource]:
    return [MockJobSource(s) for s in enabled]


@lru_cache
def fit_scorer() -> FitScorer:
    return MockFitScorer()


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
