"""APInex asks for a daily check-in (HTTP 402, "Daily check-in required to use free models").

The client records it here when it sees one (`app_setting` key `apinex_status`), so Today and
Settings → Models can say so; the next successful APInex call (or "I checked in") clears it.
Nothing here calls APInex: scoring keeps failing over to Ollama and CV/summary requests fail
with the Retry panel, never in a loop.
"""

import logging
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models import AppSetting
from app.models.base import utcnow

KEY = "apinex_status"
CHECKIN_URL = "https://apinex.bond/airdrop?tab=quests"
log = logging.getLogger("jobhunter.apinex")
_needs: bool | None = None  # what this process last knew (None: not read yet)


def _engine() -> Engine:
    from app.db import engine

    return engine


def _write(engine: Engine, value: dict[str, Any]) -> None:
    with Session(engine) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
        if row is None:
            s.add(AppSetting(key=KEY, value=value))
        else:
            row.value = value
            s.add(row)
        s.commit()


def mark_checkin_needed(message: str, engine: Engine | None = None) -> None:
    global _needs
    _needs = True
    try:
        _write(engine or _engine(), {"needs_checkin": True, "seen_at": utcnow().isoformat(),
                                     "message": message[:300]})
    except Exception:  # noqa: BLE001 - a status note must never break the call that saw it
        log.exception("could not record the APInex check-in notice")


def clear(engine: Engine | None = None) -> None:
    global _needs
    _needs = False
    try:
        _write(engine or _engine(), {"needs_checkin": False})
    except Exception:  # noqa: BLE001
        log.exception("could not clear the APInex check-in notice")


def note_success(engine: Engine | None = None) -> None:
    """A real APInex answer arrived: whatever blocked it is over. Cheap after the first call."""
    if _needs is False:
        return
    eng = engine or _engine()
    with Session(eng) as s:
        row = s.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
        flagged = bool(row and (row.value or {}).get("needs_checkin"))
    if flagged:
        clear(eng)
    else:
        globals()["_needs"] = False


def state(s: Session) -> dict[str, Any]:
    row = s.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
    value = dict((row.value if row else {}) or {})
    return {"needs_checkin": bool(value.get("needs_checkin")), "seen_at": value.get("seen_at"),
            "message": value.get("message"), "url": CHECKIN_URL}
