"""Local usage log: where the time goes during a batch (screens, key actions, waits, idle gaps).

Stored only in the real workspace's own database. Names are route patterns and action names
(validated), never page content, drafts, CV text or query strings. `build_report` is pure.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, col, delete, select

from app.models import Application, AppSetting, CVVersion, OutreachDraft, UsageEvent

KINDS = ("screen", "action", "wait", "idle")
DEFAULTS = {"enabled": True}
SESSION_GAP = timedelta(minutes=90)  # a longer silence starts a new session
IDLE_GAP = timedelta(minutes=5)  # no input for this long is an idle gap
MAX_BATCH = 200
MAX_MS = 24 * 3_600_000
NAME = re.compile(r"^[A-Za-z0-9_:/.?=\- ]{1,100}$")  # route patterns and action names only
REF_KINDS = ("job", "app", "cv", "draft")


def settings(s: Session) -> dict[str, bool]:
    row = s.exec(select(AppSetting).where(AppSetting.key == "usage_log")).first()
    stored = (row.value if row else {}) or {}
    return {"enabled": bool(stored.get("enabled", DEFAULTS["enabled"]))}


def _is_sandbox(s: Session) -> bool:
    from app.db import demo_engine

    return s.get_bind() is demo_engine


def _job_id(s: Session, ref_kind: str | None, ref_id: int | None) -> int | None:
    """The job an id points at (the client only knows job, application, CV or draft ids)."""
    if ref_kind is None or ref_id is None:
        return None
    if ref_kind == "job":
        return ref_id
    if ref_kind == "app":
        app = s.get(Application, ref_id)
    elif ref_kind == "cv":
        cv = s.get(CVVersion, ref_id)
        app = s.get(Application, cv.application_id) if cv else None
    else:
        draft = s.get(OutreachDraft, ref_id)
        app = s.get(Application, draft.application_id) if draft else None
    return app.job_id if app else None


def record(s: Session, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Store a batch. Nothing is stored when the log is off or in the tour sandbox; an invalid
    event is dropped, not stored in part."""
    enabled = settings(s)["enabled"] and not _is_sandbox(s)
    if not enabled:
        return {"enabled": settings(s)["enabled"], "stored": 0}
    stored = 0
    for e in events[:MAX_BATCH]:
        kind, name, screen = e.get("kind"), e.get("name"), e.get("screen")
        if kind not in KINDS or not isinstance(name, str) or not NAME.match(name):
            continue
        if screen is not None and (not isinstance(screen, str) or not NAME.match(screen)):
            continue
        ms = {}
        for field in ("duration_ms", "wall_ms"):
            v = e.get(field)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool)
                                  or not 0 <= v <= MAX_MS):
                ms = None
                break
            ms[field] = v
        at = e.get("at")
        try:
            when = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ms is None or when.tzinfo is None:
            continue
        ref_kind, ref_id = e.get("ref_kind"), e.get("ref_id")
        if ref_kind not in (*REF_KINDS, None) or (ref_id is not None and (
                not isinstance(ref_id, int) or isinstance(ref_id, bool))):
            continue
        s.add(UsageEvent(at=when, kind=kind, name=name, screen=screen,
                         job_id=_job_id(s, ref_kind, ref_id), **ms))
        stored += 1
    s.commit()
    return {"enabled": True, "stored": stored}


def clear(s: Session) -> int:
    n = len(s.exec(select(UsageEvent.id)).all())
    s.exec(delete(UsageEvent))  # type: ignore[call-overload]
    s.commit()
    return n


# ------------------------------------------------------------------------------------ report


def split_sessions(rows: list[UsageEvent]) -> list[list[UsageEvent]]:
    """Events (any order) grouped into sessions: a silence over 90 minutes starts a new one."""
    out: list[list[UsageEvent]] = []
    for r in sorted(rows, key=lambda r: r.at):
        if out and r.at - out[-1][-1].at <= SESSION_GAP:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def _secs(ms: int | None) -> float:
    return round((ms or 0) / 1000, 1)


def build_report(rows: list[UsageEvent]) -> dict[str, Any]:
    """One session: time per screen, switches (overall and per job), longest waits, idle gaps."""
    rows = sorted(rows, key=lambda r: r.at)
    screens = [r for r in rows if r.kind == "screen"]
    per_screen: dict[str, dict[str, Any]] = {}
    for r in screens:
        d = per_screen.setdefault(r.name, {"screen": r.name, "visits": 0, "active_s": 0.0,
                                           "wall_s": 0.0})
        d["visits"] += 1
        d["active_s"] = round(d["active_s"] + _secs(r.duration_ms), 1)
        d["wall_s"] = round(d["wall_s"] + _secs(r.wall_ms), 1)
    switches = sum(1 for a, b in zip(screens, screens[1:], strict=False) if a.name != b.name)
    # screens visited per job: how many route changes each job cost
    by_job: dict[int, list[UsageEvent]] = defaultdict(list)
    for r in screens:
        if r.job_id is not None:
            by_job[r.job_id].append(r)
    jobs = [{"job_id": j, "screens": len(v), "distinct": len({x.name for x in v}),
             "active_s": round(sum(_secs(x.duration_ms) for x in v), 1)}
            for j, v in by_job.items()]
    jobs.sort(key=lambda j: -j["active_s"])
    waits = sorted((r for r in rows if r.kind == "wait"), key=lambda r: -(r.duration_ms or 0))
    wait_by_name: dict[str, dict[str, Any]] = {}
    for r in waits:
        d = wait_by_name.setdefault(r.name, {"name": r.name, "count": 0, "total_s": 0.0})
        d["count"] += 1
        d["total_s"] = round(d["total_s"] + _secs(r.duration_ms), 1)
    idle = [r for r in rows if r.kind == "idle"]
    acts = [r for r in rows if r.kind == "action"]
    action_gaps = [{"from": a.name, "to": b.name,
                    "minutes": round((b.at - a.at).total_seconds() / 60, 1), "at": a.at.isoformat()}
                   for a, b in zip(acts, acts[1:], strict=False) if b.at - a.at > IDLE_GAP]
    first, last = rows[0].at, rows[-1].at
    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
        "wall_minutes": round((last - first).total_seconds() / 60, 1),
        "active_minutes": round(sum(_secs(r.duration_ms) for r in screens) / 60, 1),
        "screen_visits": len(screens),
        "screen_switches": switches,
        "per_screen": sorted(per_screen.values(), key=lambda d: -d["active_s"]),
        "per_job": jobs[:20],
        "actions": dict(Counter(r.name for r in acts)),
        "waits_total_s": round(sum(_secs(r.duration_ms) for r in waits), 1),
        "longest_waits": [{"name": r.name, "seconds": _secs(r.duration_ms), "screen": r.screen,
                           "job_id": r.job_id, "at": r.at.isoformat()} for r in waits[:10]],
        "waits_by_name": sorted(wait_by_name.values(), key=lambda d: -d["total_s"])[:10],
        "idle_gaps": [{"minutes": round((r.duration_ms or 0) / 60000, 1), "at": r.at.isoformat()}
                      for r in sorted(idle, key=lambda r: -(r.duration_ms or 0))],
        "action_gaps_over_5_min": action_gaps,
    }


def reports(s: Session, last: int | None = None) -> list[dict[str, Any]]:
    """Every session's report, oldest first (the last `last` when given)."""
    rows = list(s.exec(select(UsageEvent).order_by(col(UsageEvent.at))).all())
    found = [build_report(group) for group in split_sessions(rows)]
    return found[-last:] if last else found


def format_report(r: dict[str, Any]) -> str:
    """The report as plain text (scripts/usage_report.py)."""
    lines = [f"Session {r['start']} -> {r['end']}  ({r['wall_minutes']} min wall, "
             f"{r['active_minutes']} min active on screens)",
             f"  {r['screen_visits']} screen visits, {r['screen_switches']} route changes, "
             f"{r['waits_total_s']} s waiting on slow requests", "", "  Time per screen (active):"]
    for d in r["per_screen"]:
        lines.append(f"    {d['screen']:<34} {d['active_s']:>7.0f} s active  "
                     f"{d['wall_s']:>7.0f} s wall  {d['visits']:>3} visits")
    if r["actions"]:
        done = ", ".join(f"{k} x{v}" for k, v in sorted(r["actions"].items()))
        lines += ["", f"  Key actions: {done}"]
    if r["per_job"]:
        lines += ["", "  Screens per job (most time first):"]
        lines += [f"    job {j['job_id']}: {j['screens']} screen visits "
                  f"({j['distinct']} distinct), {j['active_s']:.0f} s" for j in r["per_job"][:10]]
    if r["longest_waits"]:
        lines += ["", "  Longest waits:"]
        lines += [f"    {w['seconds']:>6.1f} s  {w['name']}  on {w['screen'] or '?'}"
                  + (f" (job {w['job_id']})" if w["job_id"] else "") + f"  at {w['at']}"
                  for w in r["longest_waits"]]
    if r["idle_gaps"] or r["action_gaps_over_5_min"]:
        lines += ["", "  Idle gaps over 5 minutes (no input):"]
        lines += [f"    {g['minutes']} min at {g['at']}" for g in r["idle_gaps"][:10]]
        lines += ["  Gaps over 5 minutes between key actions:"]
        lines += [f"    {g['minutes']} min between {g['from']} and {g['to']} (from {g['at']})"
                  for g in r["action_gaps_over_5_min"][:10]]
    return "\n".join(lines)
