from fastapi import APIRouter

from app.api import (
    applications,
    contacts,
    cv,
    discovery,
    experience,
    jobs,
    outreach,
    settings,
    today,
)

router = APIRouter()


@router.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (today, jobs, applications, cv, outreach, experience, contacts, settings, discovery):
    router.include_router(module.router)
