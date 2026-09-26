"""Importing this package registers every table on SQLModel.metadata (used by Alembic)."""

from app.models.application import Application, ApplicationEvent, CVVersion, OutreachDraft
from app.models.company import Company, Contact
from app.models.experience import ExperienceItem
from app.models.job import FitScore, Job
from app.models.profile import SearchProfile, SourceRun
from app.models.queue import SendQueue, SendQueueItem
from app.models.settings import AppSetting

__all__ = [
    "AppSetting",
    "Application",
    "ApplicationEvent",
    "CVVersion",
    "Company",
    "Contact",
    "ExperienceItem",
    "FitScore",
    "Job",
    "OutreachDraft",
    "SearchProfile",
    "SendQueue",
    "SendQueueItem",
    "SourceRun",
]
