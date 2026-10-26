from fastapi import APIRouter

from app.api import (
    applications,
    claim_fixes,
    confirmation,
    contacts,
    copilot,
    cv,
    discovery,
    experience,
    generation,
    get_contact,
    interview,
    jobs,
    letters,
    linkedin,
    motivation,
    outreach,
    providers,
    research,
    scoring,
    settings,
    studio,
    today,
    tracking,
    usage,
)

router = APIRouter()


@router.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (
    today, jobs, tracking, applications, cv, letters, copilot, outreach, experience, contacts,
    settings, discovery, scoring, studio, research, get_contact, linkedin, motivation,
    providers, interview, confirmation, generation, claim_fixes, usage,
):
    router.include_router(module.router)
