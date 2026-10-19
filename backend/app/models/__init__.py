"""Importing this package registers every table on SQLModel.metadata (used by Alembic)."""

from app.models.application import (
    Application,
    ApplicationAnswer,
    ApplicationEvent,
    CoverLetter,
    CVVersion,
    OutreachDraft,
)
from app.models.company import (
    Company,
    CompanyAlias,
    CompanyMergeDecision,
    Contact,
    ContactImport,
)
from app.models.copilot import CopilotMessage, CopilotThread
from app.models.experience import ExperienceHistory, ExperienceItem
from app.models.job import FitScore, Job
from app.models.linkedin import CVFit, LinkedInLinkOpen, LinkedInOutreach
from app.models.motivation import (
    ChestOpen,
    GoalTile,
    Purchase,
    ShopItem,
    TokenEntry,
    WinEntry,
    Woop,
)
from app.models.profile import DiscoveryRun, SearchProfile, SourceRun
from app.models.queue import SendLog, SendQueue, SendQueueItem
from app.models.research import (
    CompanyPage,
    CompanySignal,
    ContactAlert,
    EmailExample,
    ResearchRun,
)
from app.models.scoring import ScoringRun, ScoringTask
from app.models.settings import AppSetting
from app.models.tracking import ApplicationResponse, Interview, ReminderAction

__all__ = [
    "ChestOpen",
    "GoalTile",
    "Purchase",
    "ShopItem",
    "TokenEntry",
    "WinEntry",
    "Woop",
    "CVFit",
    "LinkedInLinkOpen",
    "LinkedInOutreach",
    "AppSetting",
    "Application",
    "ApplicationAnswer",
    "ApplicationResponse",
    "ApplicationEvent",
    "CVVersion",
    "Company",
    "CompanyAlias",
    "CompanyMergeDecision",
    "CompanyPage",
    "CompanySignal",
    "ContactAlert",
    "Contact",
    "CoverLetter",
    "ContactImport",
    "CopilotMessage",
    "CopilotThread",
    "DiscoveryRun",
    "EmailExample",
    "ExperienceHistory",
    "ExperienceItem",
    "FitScore",
    "Interview",
    "Job",
    "OutreachDraft",
    "ReminderAction",
    "ResearchRun",
    "SearchProfile",
    "ScoringRun",
    "ScoringTask",
    "SendLog",
    "SendQueue",
    "SendQueueItem",
    "SourceRun",
]
