#!/usr/bin/env python3
"""Bulk dismiss pure Java backend positions from jobhunter.db.

Criteria:
- Track: Backend (or related backend category)
- Title/Description: title ILIKE '%Java%' OR title ILIKE '%Spring%' OR description ILIKE '%Java Developer%'
- Exclude: Hybrid Flutter/Mobile/Android/Dart jobs (preserved and never dismissed)
- Action:
  - Transition application to Stage.closed, CloseReason.dismissed
  - Note: 'Excluded track: Java backend'
  - Cancel any active scoring or generation tasks
  - Safely backup database before execution
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlmodel import Session, col, select

from app.db import engine_for
from app.models import Application, ApplicationEvent, GenerationTask, Job, ScoringTask
from app.models.base import utcnow
from app.models.enums import CloseReason, EventKind, ScoringTaskStatus, Stage
from app.services.contacts_import import backup_db


def is_protected_mobile_hybrid(title: str, matched_track: str | None) -> bool:
    """Check if job mentions Flutter, Mobile, Android, or Dart."""
    keywords = ("flutter", "mobile", "android", "dart")
    title_lower = (title or "").lower()
    track_lower = (matched_track or "").lower()
    return any(k in title_lower for k in keywords) or any(k in track_lower for k in keywords)


def is_java_backend(title: str, description: str, matched_track: str | None) -> bool:
    """Check if job is a Java/Spring backend position."""
    track_lower = (matched_track or "").lower()
    # Track must be backend or related
    if "backend" not in track_lower and track_lower != "":
        return False

    title_lower = (title or "").lower()
    desc_lower = (description or "").lower()

    matches_java_signal = (
        "java" in title_lower
        or "spring" in title_lower
        or "java developer" in desc_lower
        or "développeur java" in desc_lower
        or "developpeur java" in desc_lower
        or "ingenieur java" in desc_lower
        or "ingénieur java" in desc_lower
    )
    return matches_java_signal


def run_bulk_dismiss(dry_run: bool = False) -> None:
    engine = engine_for("real")

    if not dry_run:
        backup_path = backup_db(engine, "before-bulk-dismiss-java")
        print(f"Database backed up to: {backup_path}")
    else:
        print("[DRY RUN] No backup created, no database modifications will be committed.")

    now = utcnow()
    DISMISS_REASON_TEXT = "Excluded track: Java backend"

    with Session(engine) as session:
        # Load all jobs with their applications
        jobs = session.exec(select(Job)).all()
        job_map = {j.id: j for j in jobs}

        apps = session.exec(select(Application)).all()

        target_jobs: list[tuple[Job, Application]] = []
        protected_jobs: list[Job] = []

        for app in apps:
            job = job_map.get(app.job_id)
            if not job:
                continue

            # First test if it matches Java backend signal
            if is_java_backend(job.title, job.description, job.matched_track):
                if is_protected_mobile_hybrid(job.title, job.matched_track):
                    protected_jobs.append(job)
                else:
                    target_jobs.append((job, app))

        print(f"\n--- Analysis ---")
        print(f"Total jobs evaluated: {len(jobs)}")
        print(f"Protected mobile/flutter hybrid jobs: {len(protected_jobs)}")
        for pj in protected_jobs:
            print(f"  [PROTECTED] ID: {pj.id} | Title: {pj.title} | Track: {pj.matched_track}")

        print(f"\nTarget Java backend jobs to dismiss: {len(target_jobs)}")

        # Partition into already closed vs newly dismissed
        already_closed = [item for item in target_jobs if item[1].stage == Stage.closed]
        to_dismiss = [item for item in target_jobs if item[1].stage != Stage.closed]

        print(f"  Already closed: {len(already_closed)}")
        print(f"  To be dismissed now: {len(to_dismiss)}")

        if dry_run:
            print("\n[DRY RUN complete - no changes made]")
            return

        target_job_ids = [j.id for j, _ in target_jobs]
        target_app_ids = [a.id for _, a in target_jobs]

        # 1. Update applications
        dismissed_count = 0
        for job, app in to_dismiss:
            prev_stage = app.stage
            app.stage = Stage.closed
            app.close_reason = CloseReason.dismissed
            app.stage_changed_at = now
            if DISMISS_REASON_TEXT not in (app.notes or ""):
                app.notes = f"{DISMISS_REASON_TEXT}. {app.notes}".strip()
            session.add(app)

            # Record event
            event = ApplicationEvent(
                application_id=app.id,
                kind=EventKind.stage_change,
                from_stage=prev_stage,
                to_stage=Stage.closed,
                message=f"Dismissed: {DISMISS_REASON_TEXT}",
                at=now,
            )
            session.add(event)
            dismissed_count += 1

        # Also update notes on already-closed jobs if not present
        for job, app in already_closed:
            if app.close_reason == CloseReason.dismissed and DISMISS_REASON_TEXT not in (app.notes or ""):
                app.notes = f"{DISMISS_REASON_TEXT}. {app.notes}".strip()
                session.add(app)

        # 2. Cancel scoring tasks for these jobs
        scoring_tasks = session.exec(
            select(ScoringTask).where(
                col(ScoringTask.job_id).in_(target_job_ids),
                col(ScoringTask.status).in_([ScoringTaskStatus.queued, ScoringTaskStatus.in_progress]),
            )
        ).all()
        for st in scoring_tasks:
            st.status = ScoringTaskStatus.cancelled
            st.finished_at = now
            st.last_error = DISMISS_REASON_TEXT
            session.add(st)

        # 3. Cancel generation tasks for these applications
        gen_tasks = session.exec(
            select(GenerationTask).where(
                col(GenerationTask.application_id).in_(target_app_ids),
                col(GenerationTask.status).in_(["queued", "running"]),
            )
        ).all()
        for gt in gen_tasks:
            gt.status = "cancelled"
            gt.finished_at = now
            gt.error = DISMISS_REASON_TEXT
            session.add(gt)

        session.commit()

        print(f"\n--- Execution Results ---")
        print(f"Successfully dismissed: {dismissed_count} applications")
        print(f"Scoring tasks cancelled: {len(scoring_tasks)}")
        print(f"Generation tasks cancelled: {len(gen_tasks)}")
        print(f"Database update complete.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run_bulk_dismiss(dry_run=dry)
