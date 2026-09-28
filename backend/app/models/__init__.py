"""Importing this package registers every table on SQLModel.metadata (used by Alembic)."""

from app.models.application import Application, ApplicationEvent, CVVersion, OutreachDraft
from app.models.company import (
    Company,
    CompanyAlias,
    CompanyLookup,
    CompanyMergeDecision,
    Contact,
    ContactImport,
)
from app.models.experience import ExperienceItem
from app.models.job import FitScore, Job
from app.models.profile import DiscoveryRun, SearchProfile, SourceRun
from app.models.queue import SendLog, SendQueue, SendQueueItem
from app.models.scoring import ScoringRun, ScoringTask
from app.models.settings import AppSetting
from app.models.tracking import ApplicationResponse, Interview, ReminderAction

__all__ = [
    "AppSetting",
    "Application",
    "ApplicationResponse",
    "ApplicationEvent",
    "CVVersion",
    "Company",
    "CompanyAlias",
    "CompanyLookup",
    "CompanyMergeDecision",
    "Contact",
    "ContactImport",
    "DiscoveryRun",
    "ExperienceItem",
    "FitScore",
    "Interview",
    "Job",
    "OutreachDraft",
    "ReminderAction",
    "SearchProfile",
    "ScoringRun",
    "ScoringTask",
    "SendLog",
    "SendQueue",
    "SendQueueItem",
    "SourceRun",
]
