"""One silent discovery + scoring pass on the real workspace, scored by a LOCAL model.

Runs outside the dev server (no toasts: the frontend watcher only reacts to runs it saw
start) and writes results only. The model override lives in this process: Settings → Models is
never changed, and every score stores the model that produced it.

    .venv/bin/python scripts/silent_discovery.py --prepare-turkey   # Turkey in Settings (once)
    .venv/bin/python scripts/silent_discovery.py --run [--model gemma4:12b]
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, col, func, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import (  # noqa: E402
    AppSetting,
    FitScore,
    Job,
    ScoringTask,
    SearchProfile,
    SourceRun,
)
from app.models.enums import FitStatus, RunTrigger  # noqa: E402
from app.providers.registry import job_sources  # noqa: E402
from app.services import discovery, scoring  # noqa: E402
from app.services.contacts_import import backup_db  # noqa: E402

TURKEY_GEO_ID = "102105699"  # unverified: confirm it in Settings → LinkedIn


def prepare_turkey() -> None:
    print("backup:", backup_db(engine, "turkey"))
    with Session(engine) as s:
        profile = s.exec(select(SearchProfile).where(SearchProfile.is_active)).one()
        if "TR" not in profile.locations:
            profile.locations = [*profile.locations, "TR"]
            s.add(profile)
        row = s.exec(select(AppSetting).where(AppSetting.key == "linkedin")).one()
        value = dict(row.value)
        geos = dict(value.get("geo_ids") or {})
        geos.setdefault("TR", {"id": TURKEY_GEO_ID, "verified": False})
        row.value = {**value, "geo_ids": geos}
        s.add(row)
        s.commit()
        print("locations:", profile.locations, "| TR geoId:", geos["TR"])


def run(model: str) -> None:
    with Session(engine) as s:
        before = s.exec(select(func.max(Job.id))).one() or 0
        sources = job_sources(discovery.enabled_sources(s), mock=False)
        print("sources:", [x.value for x in sources])
    queue = scoring.queue_for(engine, mock=False)
    queue.model_override = model  # this process only
    print("backup:", backup_db(engine, "silent-discovery"))
    started = time.monotonic()
    run_id = discovery.run_discovery(
        engine, sources, RunTrigger.manual,
        on_jobs=lambda ids: discovery.after_discovery(engine, ids, queue),
    )
    print(f"discovery done in {time.monotonic() - started:.0f}s (run {run_id})")
    time.sleep(2)
    while queue._alive():  # noqa: SLF001 (script: wait for the worker threads)
        time.sleep(5)
    report(run_id, before, model, time.monotonic() - started)


def resume(model: str, before: int) -> None:
    """Score the jobs that still have no score, with the local model (this process only)."""
    queue = scoring.queue_for(engine, mock=False)
    queue.model_override = model
    started = time.monotonic()
    print("enqueued:", queue.enqueue_never_scored(trigger="resume-local"))
    time.sleep(2)
    while queue._alive():  # noqa: SLF001
        time.sleep(5)
    report(None, before, model, time.monotonic() - started)


def report(run_id: int | None, before: int, model: str, elapsed: float) -> None:
    with Session(engine) as s:
        print("\n== sources ==")
        for sr in s.exec(select(SourceRun).where(SourceRun.discovery_run_id == run_id)):
            note = f" | {sr.error}" if sr.error else ""
            warns = (sr.details or {}).get("warnings") or []
            print(f"{sr.source!s:12} {sr.status!s:8} fetched={sr.fetched_count} "
                  f"new={sr.new_count} dup={sr.duplicate_count}{note} {warns}")
        jobs = s.exec(select(Job).where(Job.id > before)).all()
        ids = [j.id for j in jobs]
        print(f"\n== new jobs: {len(jobs)} ==")
        by_country = Counter(j.country or "unknown" for j in jobs)
        print("per country:", dict(by_country.most_common()))
        print("Turkey:", by_country.get("TR", 0))
        by_source = Counter(str(j.source) for j in jobs)
        print("per source:", dict(by_source))
        cross = Counter((str(j.source), j.country or "unknown") for j in jobs)
        print("source x country:", {f"{a}/{b}": n for (a, b), n in sorted(cross.items())})
        scores = s.exec(select(FitScore).where(col(FitScore.job_id).in_(ids))).all() if ids else []
        latest: dict[int, FitScore] = {}
        for sc in sorted(scores, key=lambda x: x.id):
            latest[sc.job_id] = sc
        ok = [x for x in latest.values() if x.status == FitStatus.ok]
        failed = [x for x in latest.values() if x.status == FitStatus.failed]
        unscored = len(ids) - len(latest)
        print(f"\n== scoring ({model}) ==")
        tasks = s.exec(select(ScoringTask).where(col(ScoringTask.job_id).in_(ids))).all() \
            if ids else []
        task_failed = [t for t in tasks if str(t.status) == "failed"]
        print(f"scored ok: {len(ok)} | failed: {len(failed) + len(task_failed)} | "
              f"not scored: {unscored}")
        for t in task_failed[:10]:
            print("  failed task, job", t.job_id, "-", (t.error or "")[:120])
        print("models stored:", dict(Counter(x.model for x in latest.values())))
        secs = [x.duration_ms / 1000 for x in ok if x.duration_ms]
        if secs:
            print(f"avg seconds per scored job: {sum(secs) / len(secs):.1f}")
        for x in failed[:10]:
            print("  failed job", x.job_id, "-", (x.error or "")[:120])
        print(f"total elapsed: {elapsed / 60:.1f} min")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare-turkey", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--after-job", type=int, default=4117, help="first run's highest old job id")
    ap.add_argument("--model", default="gemma4:12b")
    args = ap.parse_args()
    if args.prepare_turkey:
        prepare_turkey()
    if args.run:
        run(args.model)
    if args.resume:
        resume(args.model, args.after_job)
