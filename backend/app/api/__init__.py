from fastapi import APIRouter

from app.api import (
    applications,
    contacts,
    copilot,
    cv,
    discovery,
    experience,
    jobs,
    letters,
    outreach,
    research,
    scoring,
    settings,
    studio,
    today,
    tracking,
)

router = APIRouter()


@router.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (
    today, jobs, tracking, applications, cv, letters, copilot, outreach, experience, contacts,
    settings, discovery, scoring, studio, research,
):
    router.include_router(module.router)
