"""Read-only: the usage log as a report per session (time per screen, route changes, longest
waits, idle gaps), for the real workspace.

    .venv/bin/python scripts/usage_report.py            # the latest session
    .venv/bin/python scripts/usage_report.py --last 3   # the last three sessions
    .venv/bin/python scripts/usage_report.py --json
"""

import argparse
import json

from sqlmodel import Session

from app.db import engine
from app.services import usage


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--last", type=int, default=1, help="how many sessions (default 1)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    with Session(engine) as s:
        found = usage.reports(s, last=args.last)
    if not found:
        print("No usage recorded yet (Settings → Data → Usage log must be on).")
    elif args.json:
        print(json.dumps(found, indent=2))
    else:
        print("\n\n".join(usage.format_report(r) for r in found))


if __name__ == "__main__":
    main()
