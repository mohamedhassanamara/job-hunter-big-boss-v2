"""Contact providers: credits per key (and Apify spend) this month, the call log, and a free
sync with the providers' own account endpoints. Never makes a paid call."""

from fastapi import APIRouter, HTTPException
from sqlmodel import col, select

from app.api.deps import SessionDep, WorkspaceDep
from app.models import ProviderCall
from app.schemas.providers import KeyStatusOut, ProviderCallOut, ProvidersOut
from app.services import provider_quota as quota

router = APIRouter(tags=["providers"])


def _out(session: SessionDep) -> ProvidersOut:
    keys = quota.status(session)
    calls = session.exec(select(ProviderCall).order_by(col(ProviderCall.id).desc()).limit(25)).all()
    warnings = [f"{k.label} is disabled: {k.disabled_reason}" for k in keys if k.disabled]
    warnings += [f"{k.label} has no credits left this month"
                 for k in keys if not k.disabled and k.remaining <= 0]
    return ProvidersOut(
        keys=[KeyStatusOut(**k.__dict__) for k in keys],
        recent_calls=[ProviderCallOut(
            provider=c.provider, key_label=c.key_label, endpoint=c.endpoint, credits=c.credits,
            cost_usd=c.cost_usd, ok=c.ok, result=c.result, created_at=c.created_at)
            for c in calls],
        max_age_days=quota.settings(session)["max_age_days"],
        spend_usd=round(sum(k.used for k in keys if k.provider == "apify"), 4),
        warnings=warnings)


@router.get("/providers/status", response_model=ProvidersOut)
def providers_status(session: SessionDep) -> ProvidersOut:
    return _out(session)


@router.post("/providers/sync", response_model=ProvidersOut)
def providers_sync(session: SessionDep, workspace: WorkspaceDep) -> ProvidersOut:
    """Read the real limits and usage from Hunter, Prospeo and Apify (free account endpoints)."""
    if workspace != "demo":
        quota.sync_remote(session)
        session.commit()
    return _out(session)


@router.post("/providers/{provider}/{label}/enable", response_model=ProvidersOut)
def enable_key(provider: str, label: str, session: SessionDep) -> ProvidersOut:
    if provider not in quota.PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    quota.enable(session, provider, label)
    session.commit()
    return _out(session)
