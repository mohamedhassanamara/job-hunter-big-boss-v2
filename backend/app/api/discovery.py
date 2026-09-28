from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, col, select

from app.api.deps import EngineDep, SessionDep, WorkspaceDep
from app.models import DiscoveryRun, SourceRun
from app.models.enums import RunStatus, Source
from app.providers.registry import job_sources, unsupported_countries
from app.schemas.settings import (
    DiscoveryRunOut,
    DiscoveryStarted,
    DiscoveryStatus,
    SampleJob,
    SourceInfo,
    SourceRunOut,
    SourceTestResult,
)
from app.services import discovery, scoring
from app.services.ingest import SOURCE_NAMES

router = APIRouter(tags=["discovery"])


def run_out(r: SourceRun) -> SourceRunOut:
    return SourceRunOut.model_validate(r, from_attributes=True)


def discovery_run_out(session: Session, run: DiscoveryRun) -> DiscoveryRunOut:
    srs = session.exec(
        select(SourceRun).where(SourceRun.discovery_run_id == run.id).order_by(col(SourceRun.id))
    ).all()
    return DiscoveryRunOut(
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        totals=run.totals,
        sources=[run_out(sr) for sr in srs],
    )


@router.post("/discovery/run", response_model=DiscoveryStarted, status_code=202)
def start_discovery(
    session: SessionDep, engine: EngineDep, workspace: WorkspaceDep,
    ignore_cooldown: Annotated[list[str] | None, Query()] = None,
) -> DiscoveryStarted:
    """`ignore_cooldown=adzuna` runs that source now even inside its cooldown (a manual,
    one-off decision, e.g. after changing roles; the source's own rate limits still apply)."""
    # The tour sandbox never touches the network.
    sources = job_sources(discovery.enabled_sources(session), mock=workspace == "demo" or None)
    if not sources:
        raise HTTPException(422, "Every source is disabled. Enable one in Settings → Sources.")
    for src, impl in sources.items():
        if src in (ignore_cooldown or []):
            impl.cooldown_hours = 0  # type: ignore[misc]  # this instance only
    try:
        queue = scoring.workspace_queue(workspace)
        # Additive discovery: only jobs that have never been scored enter the queue.
        run_id = discovery.start_run_in_background(
            engine, sources, on_jobs=lambda ids: discovery.after_discovery(engine, ids, queue)
        )
    except discovery.RunInProgress as exc:
        raise HTTPException(409, str(exc)) from exc
    return DiscoveryStarted(run_id=run_id)


@router.get("/discovery/status", response_model=DiscoveryStatus)
def discovery_status(session: SessionDep) -> DiscoveryStatus:
    run = session.exec(
        select(DiscoveryRun)
        .where(DiscoveryRun.trigger != "test")
        .order_by(col(DiscoveryRun.started_at).desc())
    ).first()
    return DiscoveryStatus(
        running=discovery.is_running(),
        run=discovery_run_out(session, run) if run else None,
    )


@router.get("/sources", response_model=list[SourceInfo])
def list_sources(session: SessionDep, workspace: WorkspaceDep) -> list[SourceInfo]:
    enabled = set(discovery.enabled_sources(session))
    impls = job_sources(list(Source), mock=workspace == "demo" or None)
    _, profile = discovery.active_profile(session)
    out = []
    for src, impl in impls.items():
        last = session.exec(
            select(SourceRun)
            .where(
                SourceRun.source == src,
                col(SourceRun.status).not_in([RunStatus.pending, RunStatus.skipped]),
            )
            .order_by(col(SourceRun.started_at).desc())
        ).first()
        hint = discovery.prepare_source(session, impl).configured()
        wait = discovery.cooldown_remaining(session, impl)
        out.append(
            SourceInfo(
                source=src,
                name=SOURCE_NAMES[src],
                enabled=src in enabled,
                configured=hint is None,
                config_hint=hint,
                cooldown_hours=impl.cooldown_hours,
                cooldown_remaining_minutes=int(wait.total_seconds() // 60) + 1 if wait else None,
                last_run=run_out(last) if last else None,
                unsupported_countries=unsupported_countries(src, profile.locations),
            )
        )
    return out


def _sample(job, reason: str | None = None) -> SampleJob:  # noqa: ANN001
    return SampleJob(
        title=job.title, company=job.company, location=job.location,
        remote_type=job.remote_type, url=job.url, reason=reason,
    )


@router.post("/sources/{source}/test", response_model=SourceTestResult)
def test_source(source: Source, engine: EngineDep, workspace: WorkspaceDep) -> SourceTestResult:
    impl = job_sources([source], mock=workspace == "demo" or None)[source]
    try:
        result, requests, warnings = discovery.test_source(engine, impl)
    except (discovery.RunInProgress, discovery.SourceCoolingDown) as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"{SOURCE_NAMES[source]} failed: {exc}") from exc
    return SourceTestResult(
        source=source,
        fetched=len(result.kept) + len(result.dropped),
        kept=len(result.kept),
        filtered=len(result.dropped),
        requests=requests,
        reasons=result.reason_counts(),
        warnings=warnings,
        kept_samples=[_sample(j) for j in result.kept[:10]],
        filtered_samples=[_sample(d.job, d.reason) for d in result.dropped[:15]],
    )

