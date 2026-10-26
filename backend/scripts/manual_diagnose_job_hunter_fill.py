"""Report only: which current CV drafts carry a given project, and whether the new fill order
(roles first, project relevance gate; `cv_build.fill_order` / `project_gate`) would change them.

    .venv/bin/python scripts/manual_diagnose_job_hunter_fill.py --live [--out docs/reports/x.md]
        --role-org "<company of the role to check>" [--project "Job Hunter"]

Opens data/jobhunter.db READ-ONLY (sqlite `mode=ro`), makes no model call, compiles nothing, and
regenerates nothing. Relevance comes from what the plan stored: the project entry's own
relevance, `plan.extras_rated` (kept since the new fill) and `plan.fill_log` (leftovers that were
tried). A bullet the model never rated shows "not rated".
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "jobhunter.db"
MIN_REL, OTHER_TRACK_REL = 7, 9  # the defaults of cv.structure; the saved settings are read below


def settings(c: sqlite3.Connection) -> tuple[int, int, int]:
    row = c.execute("select value from app_setting where key = 'cv'").fetchone()
    structure = (json.loads(row[0]).get("structure") or {}) if row else {}
    return (int(structure.get("project_min_relevance", MIN_REL)),
            int(structure.get("project_other_track_relevance", OTHER_TRACK_REL)),
            int(structure.get("projects_max", 3)))


def shown_bullets(plan: dict, overrides: dict, fit: dict, item_id: int) -> set[int]:
    """Source indexes on the CV for a role: the best `count` plan bullets (generic last), plus
    force_in minus force_out (the same rule as cv_build._visible)."""
    entry = next((r for r in plan["roles"] if r["item_id"] == item_id), None)
    if entry is None:
        return set()
    count = int((fit.get("counts") or {}).get(f"role:{item_id}", 0))
    ranked = sorted(entry["bullets"], key=lambda b: (b.get("strength", 3) <= 1, b["priority"]))
    shown = {b["source_index"] for b in ranked[:count]}
    prefix = f"role:{item_id}:"
    shown |= {int(k[len(prefix):]) for k in overrides.get("force_in", []) if k.startswith(prefix)}
    shown -= {int(k[len(prefix):]) for k in overrides.get("force_out", []) if k.startswith(prefix)}
    return shown


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="read the real workspace (read-only)")
    ap.add_argument("--project", default="Job Hunter")
    ap.add_argument("--role-org", required=True, help="company of the role whose bullets to check")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not args.live:
        sys.exit("This reads the real database (read-only). Re-run with --live.")

    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    min_rel, other_rel, projects_max = settings(c)
    items = {r[0]: {"title": r[1], "org": r[2], "kind": r[3], "tags": json.loads(r[4] or "[]"),
                    "bullets": json.loads(r[5] or "[]"), "active": bool(r[6])}
             for r in c.execute("select id, title, org, kind, tags, bullets, is_active "
                                "from experience_item")}
    has_tracks = "tracks" in [r[1] for r in c.execute("pragma table_info(experience_item)")]
    project_id = next((i for i, v in items.items() if v["kind"] == "project"
                       and args.project.lower() in v["title"].lower()), None)
    role_id = next((i for i, v in items.items() if v["kind"] == "job"
                    and args.role_org.lower() in (v["org"] or "").lower()
                    and v["active"]), None)
    if project_id is None or role_id is None:
        sys.exit(f"Project {args.project!r} or role at {args.role_org!r} not found in the pool.")
    tags = items[project_id]["tags"]
    track_tags = (json.loads(c.execute("select tracks from experience_item where id = ?",
                                       (project_id,)).fetchone()[0] or "[]") if has_tracks else [])

    tracks_note = (", ".join(track_tags) if track_tags else
                   "not set" if has_tracks else "not set (migration 0037 not applied)")
    latest: dict[int, tuple] = {}
    for row in c.execute("select id, application_id, version, status, plan, overrides, fill "
                         "from cv_version where status != 'superseded' order by version"):
        latest[row[1]] = row  # the newest non-superseded version of each application
    lines = [f"# Diagnostic: {items[project_id]['title']} in current CV drafts",
             "", "Report only: nothing regenerated, no model call, database opened read-only.", "",
             f"Rules read from settings: project minimum relevance {min_rel}, other-track "
             f"{other_rel}, projects max {projects_max}. Project tags: "
             f"{', '.join(tags) or 'none'}; track tags: "
             f"{tracks_note}.",
             "", "| App | Job | Track | Project in CV | Its relevance | Added by | "
             f"Left-out bullets of {items[role_id]['org']} (relevance) | New order |",
             "|---|---|---|---|---|---|---|---|"]
    changed = unknown = total = 0
    for app_id, (_v, _a, _n, status, plan_json, ov_json, _fill) in sorted(latest.items()):
        if status != "draft":
            continue
        blob = json.loads(plan_json or "{}")
        plan, fit = blob.get("plan") or {}, blob.get("fit") or {}
        overrides = json.loads(ov_json or "{}")
        in_plan = next((p for p in plan.get("projects", []) if p["item_id"] == project_id), None)
        key = f"project:{project_id}"
        forced = key in overrides.get("force_in", [])
        count = int((fit.get("counts") or {}).get(key, 0))
        if not ((in_plan and count > 0) or forced):
            continue
        total += 1
        job = c.execute("select j.title, co.name, j.matched_track from application a "
                        "join job j on j.id = a.job_id "
                        "left join company co on co.id = j.company_id "
                        "where a.id = ?", (app_id,)).fetchone() or ("?", "?", "")
        rated = {(e["kind"], e["item_id"], e.get("source_index")): e["relevance"]
                 for e in plan.get("extras_rated", [])}
        tried = {(e.get("kind"), e.get("item_id"), e.get("source_index")): e
                 for e in plan.get("fill_log", []) if "item_id" in e}
        fill_entry = tried.get(("project", project_id, None))
        if forced and not in_plan:
            added_by, rel = "you (forced in)", None
        elif fill_entry and fill_entry.get("result") == "added":
            added_by, rel = "fill (rated leftover)", fill_entry["relevance"]
        else:
            added_by, rel = "the model's own plan", in_plan["relevance"] if in_plan else None
        shown = shown_bullets(plan, overrides, fit, role_id)
        left = []
        for idx, _text in enumerate(items[role_id]["bullets"]):
            if idx in shown:
                continue
            r = tried.get(("role", role_id, idx), {}).get("relevance", rated.get(
                ("role", role_id, idx)))
            left.append(f"#{idx + 1} ({r if r is not None else 'not rated'})")
        if added_by.startswith("fill"):
            blocked = rel is not None and (rel < min_rel or any(
                (t := tried.get(("role", role_id, i))) and t.get("result") == "skipped"
                and t.get("reason") in ("did not fit one page", "no gain")
                and t["relevance"] >= rel for i in range(len(items[role_id]["bullets"]))))
            verdict = "would change: not added" if blocked else "no change"
            changed += bool(blocked)
        elif added_by.startswith("you"):
            verdict = "no change (your force-in wins)"
        else:
            verdict = ("no change: the project is in the model's own plan, not added by the "
                       "fill (the gate only governs fill)")
            if left:
                unknown += 1
        lines.append(f"| {app_id} | {job[0]} @ {job[1]} | {job[2] or '-'} | yes | "
                     f"{rel if rel is not None else 'not rated'} | {added_by} | "
                     f"{', '.join(left) or 'none'} | {verdict} |")
    lines += ["", f"{total} current drafts include the project; {changed} would change under the "
              f"new fill order; {unknown} keep it only because the model put it in its own plan "
              "while role bullets were left out (outside what the fill order controls)."]
    report = "\n".join(lines)
    print(report)
    if args.out:
        (ROOT / args.out).write_text(report + "\n")


if __name__ == "__main__":
    main()
