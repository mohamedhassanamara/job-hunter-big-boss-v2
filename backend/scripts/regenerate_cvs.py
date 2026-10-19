"""Regenerate every current CV draft with the current pool and tailoring rules (real Claude calls,
run from a standalone script: dev-server reloads kill the subprocess).

    .venv/bin/python scripts/regenerate_cvs.py [--only APP_ID ...] [--dry]

Drafts are superseded by a new draft. An approved version is never changed: it gets a corrected
draft next to it for you to approve. Applications whose CV was already sent (locked) are skipped.
"""

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, col, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine  # noqa: E402
from app.models import AppSetting, CVVersion  # noqa: E402
from app.models.enums import CVStatus  # noqa: E402
from app.providers.registry import cv_generator  # noqa: E402
from app.services import cv_service, verifier  # noqa: E402


def targets(s: Session) -> list[int]:
    rows = s.exec(select(CVVersion).where(col(CVVersion.status).in_(
        [CVStatus.draft, CVStatus.approved])).order_by(CVVersion.application_id)).all()
    locked = {v.application_id for v in s.exec(select(CVVersion)).all() if v.locked_at}
    return sorted({v.application_id for v in rows} - locked)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int, nargs="*")
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()
    with Session(engine) as s:
        apps = args.only or targets(s)
        row = s.exec(select(AppSetting).where(AppSetting.key == "models")).first()
        model = ((row.value if row else {}).get("cv") or {}).get("model") or "claude-sonnet-5"
        check = verifier.for_workspace(s, "real")
    print("applications:", apps, "| generator:", model, "| verifier:", check.model)
    if args.dry:
        return
    gen = cv_generator(mock=False, model=model)
    for app_id in apps:
        try:
            v = cv_service.generate(engine, app_id, gen, verifier=check)
        except Exception as exc:  # noqa: BLE001
            print(f"app {app_id}: FAILED {exc}")
            continue
        t = (v.plan or {}).get("tailoring") or {}
        errors = [x for x in v.violations if x["severity"] == "error"]
        print(f"app {app_id}: v{v.version} pages={v.page_count} fill={v.fill} "
              f"adapted={t.get('adapted')} original={t.get('original')} "
              f"refused={len(t.get('fallbacks') or [])} verifier={(t.get('verifier') or {}).get('status')} "
              f"errors={len(errors)} warnings={len(v.violations) - len(errors)}")
        for x in errors:
            print("   ERROR", x["where"], "-", x["message"])


if __name__ == "__main__":
    main()
