"""Import data/import/master_experience.md into the real pool (explicit, after a preview).

    .venv/bin/python scripts/import_master.py            # dry run: what would change, nothing written
    .venv/bin/python scripts/import_master.py --apply    # backs up the DB first, then writes

Mapping of document entries to existing pool ids and suggested tags: data/import/master_mapping.json.
Every write goes through services/experience_write (history + undo).
"""

import argparse
import json
import sys
from pathlib import Path

from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import engine  # noqa: E402
from app.models import AppSetting  # noqa: E402
from app.services import master_import  # noqa: E402
from app.services.contacts_import import backup_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    items = master_import.parse((ROOT / "data/import/master_experience.md").read_text())
    mapping = json.loads((ROOT / "data/import/master_mapping.json").read_text())
    with Session(engine) as s:
        todo = master_import.plan(s, items, mapping)
        for row in todo["rows"]:
            it = row["entry"]
            print(f"{'replace #' + str(row['item_id']) if row['item_id'] else 'NEW':>12}  "
                  f"{it['kind']:<13} {it.get('org') or '':<30} {it['title']}")
        for old in todo["archive"]:
            print(f"{'archive #' + str(old.id):>12}  {old.kind:<13} {old.org or '':<30} {old.title}")
        if not args.apply:
            print("\nDry run: nothing written. Re-run with --apply.")
            return
        print("\nBackup:", backup_db(engine, "master-import"))
        counts = master_import.apply(s, items, mapping)
        row = s.exec(select(AppSetting).where(AppSetting.key == "cv")).first()
        if row is not None and mapping.get("track_emphasis"):
            value = dict(row.value)
            emphasis = dict(value.get("track_emphasis") or {})
            for track, spec in mapping["track_emphasis"].items():
                emphasis.setdefault(track, spec)  # never overwrite your own choices
            value["track_emphasis"] = emphasis
            row.value = value
            s.add(row)
        s.commit()
        print("Done:", counts)


if __name__ == "__main__":
    main()
