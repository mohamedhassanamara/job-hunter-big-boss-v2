"""Sample data lives ONLY in the tour sandbox (data/demo.db). The real DB gets no fake data.

    python -m app.seed.seed               # rebuild the tour sandbox from fixtures
    python -m app.seed.seed --defaults    # real DB: add profile + settings if missing
    python -m app.seed.seed --erase-real  # real DB: erase everything but the defaults
"""

import argparse
import unicodedata
import zlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, delete
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401
from app.models import (
    Application,
    ApplicationEvent,
    AppSetting,
    Company,
    Contact,
    CVVersion,
    ExperienceItem,
    FitScore,
    Job,
    OutreachDraft,
    SearchProfile,
    SendQueue,
    SendQueueItem,
    SourceRun,
)
from app.models.enums import (
    CVStatus,
    DraftStatus,
    EventKind,
    QueueItemStatus,
    QueueStatus,
    RunStatus,
    Source,
    Stage,
)
from app.providers.base import ContactSnapshot, JobSnapshot
from app.providers.registry import cv_generator, email_drafter
from app.seed import fixtures as fx
from app.services.dedupe import dedupe_key, normalize_company
from app.services.experience import experience_snapshots
from app.services.pipeline import stage_label

SOURCE_NAMES = {
    "adzuna": "Adzuna",
    "remotive": "Remotive",
    "arbeitnow": "Arbeitnow",
    "wttj": "Welcome to the Jungle",
}
FORWARD = [Stage.new, Stage.shortlisted, Stage.cv_ready, Stage.ready, Stage.done, Stage.interview]


def _clear(session: Session) -> None:
    for table in reversed(SQLModel.metadata.sorted_tables):
        session.exec(delete(table))  # type: ignore[call-overload]


def _stage_path(stage: Stage, close_reason: str | None) -> list[Stage]:
    if stage == Stage.closed:
        if close_reason == "dismissed":
            return [Stage.new, Stage.closed]
        return [*FORWARD[:5], Stage.closed]
    return FORWARD[: FORWARD.index(stage) + 1]


def seed(engine: Engine, *, empty: bool = False) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    with Session(engine) as s:
        _clear(s)

        profile = SearchProfile(**fx.SEARCH_PROFILE)
        s.add(profile)
        for key, value in fx.SETTINGS.items():
            s.add(AppSetting(key=key, value=value))
        queue = SendQueue(status=QueueStatus.idle if empty else QueueStatus.paused)
        s.add(queue)
        s.flush()

        if empty:
            s.commit()
            return

        # Discovery runs: today (07:00-ish) and yesterday for every source.
        runs: dict[str, SourceRun] = {}
        for day_offset in (1, 0):
            for i, src in enumerate(Source):
                started = (now - timedelta(days=day_offset)).replace(hour=5, minute=i * 2)
                failed = day_offset == 0 and src == Source.wttj
                run = SourceRun(
                    source=src,
                    profile_id=profile.id,
                    started_at=started,
                    finished_at=started + timedelta(seconds=40 + i * 7),
                    status=RunStatus.partial if failed else RunStatus.success,
                    fetched_count=[34, 12, 21, 18][i],
                    new_count=[3, 2, 2, 1][i] if day_offset == 0 else [4, 1, 3, 2][i],
                    duplicate_count=[1, 0, 1, 0][i],
                    error="Rate limited after page 3 (18 of ~30 listings fetched)"
                    if failed
                    else None,
                )
                s.add(run)
                runs[src] = run
        s.flush()

        companies: dict[str, Company] = {}
        for key, c in fx.COMPANIES.items():
            company = Company(
                name=c["name"],
                normalized_name=normalize_company(c["name"]),
                domain=c["domain"],
                website=f"https://{c['domain']}",
            )
            s.add(company)
            companies[key] = company
        s.flush()

        contacts: dict[str, list[Contact]] = {}
        for key, people in fx.CONTACTS.items():
            contacts[key] = []
            for full_name, title, source in people:
                first, last = full_name.split(" ", 1)
                slug = unicodedata.normalize("NFKD", f"{first}.{last}".lower().replace(" ", ""))
                slug = slug.encode("ascii", "ignore").decode()
                contact = Contact(
                    company_id=companies[key].id,
                    full_name=full_name,
                    title=title,
                    email=f"{slug}@{fx.COMPANIES[key]['domain']}",
                    linkedin_url=f"https://linkedin.com/in/{slug.replace('.', '-')}",
                    source=source,
                    imported_batch="apollo-2026-09-01.csv" if source == "apollo_dump" else None,
                )
                s.add(contact)
                contacts[key].append(contact)
        s.flush()

        for i, item in enumerate(fx.EXPERIENCE):
            s.add(
                ExperienceItem(
                    **{
                        **item,
                        "start_date": date.fromisoformat(item["start_date"])
                        if item["start_date"]
                        else None,
                        "end_date": date.fromisoformat(item["end_date"])
                        if item["end_date"]
                        else None,
                    },
                    position=i,
                )
            )
        s.flush()
        experience = experience_snapshots(s)

        jobs: dict[str, Job] = {}
        apps: dict[str, Application] = {}
        for jf in fx.JOBS:
            company = companies[jf.company]
            posted = now - timedelta(days=jf.posted_days_ago)
            discovered = posted + timedelta(hours=2)
            job = Job(
                source=jf.source,
                external_id=f"{jf.source}-{zlib.crc32(jf.key.encode()) % 10_000_000}",
                source_run_id=runs[jf.source].id,
                url=f"https://example.com/{jf.source}/jobs/{jf.key}",
                title=jf.title,
                company_id=company.id,
                location=jf.location,
                country=jf.country,
                remote_type=jf.remote,
                description=fx.job_description(jf, company.name),
                salary_text=jf.salary,
                posted_at=posted,
                discovered_at=discovered,
                dedupe_key=dedupe_key(company.name, jf.title, jf.country),
                duplicate_of_id=jobs[jf.duplicate_of].id if jf.duplicate_of else None,
            )
            s.add(job)
            s.flush()
            jobs[jf.key] = job
            s.add(
                FitScore(
                    job_id=job.id,
                    profile_id=profile.id,
                    score=jf.score,
                    strengths=jf.strengths,
                    gaps=jf.gaps,
                    summary=jf.summary,
                    model="ollama:qwen2.5:7b (mock)",
                    created_at=discovered + timedelta(minutes=5),
                )
            )

            contact = contacts[jf.company][jf.contact] if jf.contact is not None else None
            stage = Stage(jf.stage)
            stage_changed = min(now - timedelta(days=jf.days_in_stage), now)
            stage_changed = max(stage_changed, discovered + timedelta(hours=1))
            application = Application(
                job_id=job.id,
                stage=stage,
                route=jf.route,
                contact_id=contact.id if contact else None,
                contact_tier=jf.tier,
                close_reason=jf.close_reason,
                notes=jf.notes,
                stage_changed_at=stage_changed,
                applied_at=None,
                created_at=discovered,
                updated_at=stage_changed,
            )
            s.add(application)
            s.flush()
            apps[jf.key] = application

            # Timeline: discovered → each stage along the path, spread evenly in time.
            s.add(
                ApplicationEvent(
                    application_id=application.id,
                    kind=EventKind.discovered,
                    message=f"Discovered on {SOURCE_NAMES[jf.source]}"
                    + (f" · fit {jf.score}" if not jf.duplicate_of else " · flagged as duplicate"),
                    at=discovered,
                )
            )
            if contact:
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.contact_resolved,
                        message=f"Contact found: {contact.full_name} ({contact.title})",
                        payload={"tier": jf.tier},
                        at=discovered + timedelta(minutes=8),
                    )
                )
            path = _stage_path(stage, jf.close_reason)
            steps = list(zip(path, path[1:], strict=False))
            for n, (src, dst) in enumerate(steps, start=1):
                at = discovered + (stage_changed - discovered) * (n / len(steps))
                if dst == Stage.done:
                    application.applied_at = at
                    if company.contacted_at is None:
                        company.contacted_at = at
                message = f"Moved to {stage_label(dst, jf.route)}"
                if dst == Stage.closed:
                    message = (
                        "Dismissed"
                        if jf.close_reason == "dismissed"
                        else f"Closed ({(jf.close_reason or '').replace('_', ' ')})"
                    )
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.stage_change,
                        from_stage=src,
                        to_stage=dst,
                        message=message,
                        at=at,
                    )
                )
            if jf.notes:
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.note,
                        message="Note updated",
                        at=stage_changed + timedelta(hours=1),
                    )
                )
        s.flush()

        # CVs: every application past `shortlisted` has an approved CV; one shortlisted job
        # has a draft waiting for review; Lumière has a superseded v1.
        gen = cv_generator()
        for key, application in apps.items():
            job = jobs[key]
            snapshot = JobSnapshot(
                title=job.title, company=companies[fx_company(key)].name,
                description=job.description,
            )
            path = _stage_path(Stage(application.stage), application.close_reason)
            needs_approved = Stage.cv_ready in path
            needs_draft = key == "quartzo-llm"
            if not (needs_approved or needs_draft):
                continue
            content = gen.generate(snapshot, experience).model_dump()
            base_at = application.stage_changed_at - timedelta(hours=3)
            versions: list[tuple[int, CVStatus]] = []
            if key == "lumiere-mlops":
                versions = [(1, CVStatus.superseded), (2, CVStatus.approved)]
            elif needs_approved:
                versions = [(1, CVStatus.approved)]
            else:
                versions = [(1, CVStatus.draft)]
            for version, status in versions:
                s.add(
                    CVVersion(
                        application_id=application.id,
                        version=version,
                        content=content,
                        tex=None,
                        pdf_path=None,
                        page_count=1,
                        status=status,
                        generator_model="claude-sonnet-5 (mock)",
                        created_at=base_at + timedelta(minutes=version * 20),
                        updated_at=base_at + timedelta(minutes=version * 20),
                    )
                )
                s.add(
                    ApplicationEvent(
                        application_id=application.id,
                        kind=EventKind.cv_generated,
                        message=f"CV v{version} generated",
                        at=base_at + timedelta(minutes=version * 20),
                    )
                )
                if status == CVStatus.approved:
                    s.add(
                        ApplicationEvent(
                            application_id=application.id,
                            kind=EventKind.cv_approved,
                            message=f"CV v{version} approved",
                            at=base_at + timedelta(minutes=version * 20 + 15),
                        )
                    )

        # Outreach drafts + queue.
        drafter = email_drafter()
        plan = [
            ("sierra-gcp", DraftStatus.draft, None),
            ("lumiere-mlops", DraftStatus.rejected, None),
            ("lumiere-mlops", DraftStatus.draft, None),
            ("pixelfarm-ai", DraftStatus.queued, QueueItemStatus.pending),
            ("kelpie-staff", DraftStatus.queued, QueueItemStatus.pending),
            ("marea-stream", DraftStatus.sent, QueueItemStatus.sent),
            ("tessera-applied", DraftStatus.sent, QueueItemStatus.sent),
        ]
        position = 0
        for key, status, item_status in plan:
            application = apps[key]
            job = jobs[key]
            contact = s.get(Contact, application.contact_id)
            assert contact is not None
            result = drafter.draft(
                JobSnapshot(title=job.title, company=companies[fx_company(key)].name),
                ContactSnapshot(full_name=contact.full_name, title=contact.title),
                None,
            )
            created = application.stage_changed_at - timedelta(hours=1)
            draft = OutreachDraft(
                application_id=application.id,
                contact_id=contact.id,
                subject=result.subject,
                body=result.body,
                status=status,
                model="claude-haiku-4-5 (mock)",
                edited=key == "kelpie-staff",
                created_at=created,
                updated_at=created,
            )
            if status == DraftStatus.rejected:
                draft.subject = f"Quick question about the {job.title} role"
                draft.created_at = draft.updated_at = created - timedelta(hours=5)
            s.add(draft)
            s.flush()
            s.add(
                ApplicationEvent(
                    application_id=application.id,
                    kind=EventKind.draft_created,
                    message=f"Email draft created for {contact.full_name}",
                    at=draft.created_at,
                )
            )
            if item_status is not None:
                position += 1
                pending = item_status == QueueItemStatus.pending
                sent_at = application.applied_at if not pending else None
                s.add(
                    SendQueueItem(
                        queue_id=queue.id,
                        draft_id=draft.id,
                        position=position,
                        status=item_status,
                        scheduled_at=None if pending else sent_at,
                        sent_at=sent_at,
                    )
                )
                if not pending:
                    s.add(
                        ApplicationEvent(
                            application_id=application.id,
                            kind=EventKind.sent,
                            message=f"Email sent to {contact.email}",
                            at=(sent_at or now) + timedelta(minutes=1),
                        )
                    )
        s.commit()


_KEY_TO_COMPANY = {j.key: j.company for j in fx.JOBS}


def fx_company(job_key: str) -> str:
    return _KEY_TO_COMPANY[job_key]


def migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["embedded"] = True
    command.upgrade(cfg, "head")


def reset_sandbox() -> None:
    """Rebuild the tour sandbox (data/demo.db) from fixtures. Never touches the real DB."""
    from app.config import get_settings
    from app.db import demo_engine

    migrate(get_settings().demo_database_url)
    seed(demo_engine)


def ensure_defaults(engine: Engine) -> None:
    """Give a brand-new real workspace its search profile and settings. Idempotent: never
    overwrites or adds data once a profile exists."""
    with Session(engine) as s:
        if s.exec(select(SearchProfile)).first() is not None:
            return
    seed(engine, empty=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sandbox", action="store_true", help="rebuild the tour sandbox (default)")
    group.add_argument("--erase-real", action="store_true",
                       help="ERASE the real workspace (keeps only profile + settings defaults)")
    group.add_argument("--defaults", action="store_true",
                       help="add profile + settings to the real DB if it has none")
    args = parser.parse_args()
    from app.db import engine

    if args.erase_real:
        seed(engine, empty=True)
        print("Real workspace erased (profile + settings defaults kept)")
    elif args.defaults:
        ensure_defaults(engine)
        print("Real workspace defaults ensured")
    else:
        reset_sandbox()
        print("Tour sandbox rebuilt (data/demo.db)")


if __name__ == "__main__":
    main()
