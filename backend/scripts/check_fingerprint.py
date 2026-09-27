"""Compare the current DB against a saved score fingerprint (data/backups/scores-before-*.json).

    .venv/bin/python scripts/check_fingerprint.py ../data/backups/scores-before-0005.json

Exit code 1 if a fingerprinted job changed (score row, score, status, model, prompt, label, stage).
"""

import json
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "jobhunter.db"
QUERY = """
select j.id, f.id, f.score, f.status, f.model, f.prompt_version, j.user_label, a.stage,
       (select count(*) from fit_score g where g.job_id = j.id)
from job j
left join fit_score f on f.id = (select id from fit_score g where g.job_id = j.id
                                 order by created_at desc, id desc limit 1)
left join application a on a.job_id = j.id
"""
KEYS = ("fit_id", "score", "status", "model", "prompt", "label", "stage", "fit_rows")


def main(path: str) -> int:
    before = json.loads(Path(path).read_text())
    now = {str(r[0]): dict(zip(KEYS, r[1:], strict=True))
           for r in sqlite3.connect(DB).execute(QUERY)}
    changed = [(k, before[k], now.get(k)) for k in before if now.get(k) != before[k]]
    new = [k for k in now if k not in before]
    print(f"fingerprinted: {len(before)} · unchanged: {len(before) - len(changed)} · "
          f"changed/missing: {len(changed)} · new jobs: {len(new)} "
          f"(scored: {sum(1 for k in new if now[k]['fit_id'])})")
    for k, a, b in changed[:10]:
        print(f"  job {k}: {a} -> {b}")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
