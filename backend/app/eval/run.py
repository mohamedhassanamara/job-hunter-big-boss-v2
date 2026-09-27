"""`make eval`: score every labeled job and report agreement with your Good/Maybe/No labels.

    python -m app.eval.run            # reuse cached scores when nothing changed
    python -m app.eval.run --fresh    # force new model calls for every labeled job
    python -m app.eval.run --limit 10

Reports are saved to data/eval/<timestamp>_<model>_p<prompt-version>.{md,json} and compared with
the previous report.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.config import DATA_DIR
from app.eval.metrics import LABELS, Item, bucket, summarize
from app.models import Company, Job
from app.providers.base import FitScorer
from app.services import scoring

DIMS = ("role_match", "skills_match", "seniority_fit", "location_eligibility",
        "language_requirements")
SHORT = {"role_match": "role", "skills_match": "skills", "seniority_fit": "seniority",
         "location_eligibility": "location", "language_requirements": "language"}


def run_eval(
    engine: Engine,
    scorer: FitScorer,
    *,
    fresh: bool = False,
    limit: int | None = None,
    out_dir: Path = DATA_DIR / "eval",
    echo: bool = True,
) -> tuple[dict, Path]:
    with Session(engine) as s:
        jobs = s.exec(
            select(Job).where(col(Job.user_label).is_not(None)).order_by(col(Job.labeled_at))
        ).all()
        if limit:
            jobs = jobs[:limit]
        ctx = scoring.load_context(s)
        companies = {c.id: c.name for c in s.exec(select(Company)).all()}
        labeled = [(j.id, j.title, companies.get(j.company_id, "?"), j.user_label) for j in jobs]
    if not labeled:
        raise SystemExit("No labeled jobs yet. Label some in Discover with 1 / 2 / 3.")

    items: list[Item] = []
    for n, (job_id, title, company, label) in enumerate(labeled, 1):
        started = time.monotonic()
        row = scoring.score_job(engine, job_id, scorer, force=fresh, ctx=ctx)
        wall = time.monotonic() - started
        seconds = (row.duration_ms / 1000) if row.duration_ms else wall
        items.append(Item(job_id, title, company, label, row.score, round(seconds, 1),
                          row.sub_scores or {}, row.summary, row.red_flags or [], row.confidence,
                          row.error))
        if echo:
            print(f"  [{n}/{len(labeled)}] {label:5} {str(row.score):>4}  {title[:60]}")

    good_t = int(ctx.scoring.get("good_threshold", 70))
    maybe_t = int(ctx.scoring.get("maybe_threshold", 45))
    summary = summarize(items, good_t, maybe_t)
    meta = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": scorer.model,
        "prompt_version": ctx.prompt_version,
        "weights": ctx.config.weights,
        "hard_flag_cap": ctx.config.hard_flag_cap,
        "thresholds": {"good": good_t, "maybe": maybe_t},
        "experience_version": ctx.experience_version,
        "fresh": fresh,
    }
    report = {"meta": meta, "summary": summary, "items": [i.__dict__ for i in items]}
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_model = scorer.model.replace(":", "-").replace("/", "-")
    version = ctx.prompt_version.split("/v")[-1]
    base = out_dir / f"{stamp}_{safe_model}_p{version}"
    previous = sorted(out_dir.glob("*.json"))
    base.with_suffix(".json").write_text(json.dumps(report, indent=1, default=str))
    base.with_suffix(".md").write_text(render_md(report, items, previous[-1] if previous else None))
    if echo:
        print(base.with_suffix(".md").read_text())
    return report, base.with_suffix(".md")


def render_md(report: dict, items: list[Item], previous: Path | None) -> str:
    meta, s = report["meta"], report["summary"]
    by_id = {i.job_id: i for i in items}
    lines = [
        f"# Scorer eval · {meta['model']} · {meta['prompt_version']}",
        "",
        f"{meta['created_at']} · {s['n']} labeled jobs "
        f"({', '.join(f'{k} {v}' for k, v in s['labels'].items())}) · failed {s['failed']}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Bucket accuracy (≥{meta['thresholds']['good']} Good, ≥{meta['thresholds']['maybe']} "
        f"Maybe) | {s['accuracy']} |",
        f"| Spearman (score vs label) | {s['spearman']} |",
        f"| Mean score · Good / Maybe / No | {s['mean_score']['good']} / "
        f"{s['mean_score']['maybe']} / {s['mean_score']['no']} |",
        f"| Seconds per job · avg / p90 | {s['avg_seconds']} / {s['p90_seconds']} |",
        "",
        f"Weights: {meta['weights']} · hard-flag cap {meta['hard_flag_cap']}",
    ]
    if previous:
        try:
            prev = json.loads(previous.read_text())
            ps = prev["summary"]
            lines += [
                "",
                f"**vs previous** ({prev['meta']['model']} · {prev['meta']['prompt_version']}, "
                f"{prev['meta']['created_at']}): accuracy {ps['accuracy']} → {s['accuracy']}, "
                f"spearman {ps['spearman']} → {s['spearman']}",
            ]
        except (ValueError, KeyError):
            pass
    lines += ["", "## Confusion (rows = your label, columns = score bucket)", "",
              "| label \\ bucket | good | maybe | no | failed |", "|---|---|---|---|---|"]
    for lab in LABELS:
        row = s["confusion"][lab]
        lines.append(f"| {lab} | {row['good']} | {row['maybe']} | {row['no']} | {row['failed']} |")
    lines += ["", "## Worst disagreements", ""]
    for job_id in s["worst"]:
        i = by_id[job_id]
        subs = " · ".join(
            f"{SHORT[d]} {i.sub_scores.get(d, {}).get('score', '?')}" for d in DIMS
        )
        lines += [
            f"### {i.title} ({i.company}), you said **{i.label}**, score **{i.score}** "
            f"({bucket(i.score, meta['thresholds']['good'], meta['thresholds']['maybe'])}, "
            f"confidence {i.confidence})",
            f"{subs}",
            f"> {i.summary}",
        ]
        for d in DIMS:
            sub = i.sub_scores.get(d) or {}
            if sub:
                mark = "" if sub.get("evidence_verified") else " (unverified quote)"
                lines.append(f"- **{SHORT[d]} {sub.get('score')}**: {sub.get('reason')}{mark}")
        for f in i.red_flags:
            lines.append(f"- flag {f.get('severity')}: {f.get('type')}: {f.get('text')}")
        lines.append("")
    failed = [i for i in items if i.score is None]
    if failed:
        lines += ["## Failures", ""] + [f"- {i.title}: {i.error}" for i in failed]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    from app.config import get_settings
    from app.db import engine
    from app.providers.registry import fit_scorer

    with Session(engine) as s:
        model = scoring.load_context(s).model
    scorer = fit_scorer(mock=get_settings().job_sources == "mock", model=model)
    health = getattr(scorer, "health", None)
    if health and not (h := health()).ok:
        raise SystemExit(h.message)
    run_eval(engine, scorer, fresh=args.fresh, limit=args.limit)


if __name__ == "__main__":
    main()
