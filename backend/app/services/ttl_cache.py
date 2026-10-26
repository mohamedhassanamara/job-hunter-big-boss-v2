"""A tiny per-database cache for the counts behind the shell's polled requests (Today, scoring
status): a few seconds is enough to turn "every screen polls a full-table count" into one query
per window. Keyed by the database engine, so the real workspace and the sandbox never mix.

Writers that change what the counts say (stage changes, new jobs, finished scores) call `clear`,
so a click is never followed by a stale number; the TTL only bounds what clear can't see."""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

TTL_SECONDS = 4.0
_lock = threading.Lock()
_store: dict[tuple[int, str], tuple[float, Any]] = {}


def cached[T](engine: Engine, name: str, fn: Callable[[], T], ttl: float = TTL_SECONDS) -> T:
    key, now = (id(engine), name), time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    value = fn()  # computed outside the lock: two racing requests may both compute, harmlessly
    with _lock:
        _store[key] = (time.monotonic() + ttl, value)
    return value


def clear(engine: Engine | None = None) -> None:
    """Forget everything for one database (or all)."""
    with _lock:
        for key in [k for k in _store if engine is None or k[0] == id(engine)]:
            del _store[key]


@event.listens_for(Session, "after_commit")
def _forget_on_commit(session: Session) -> None:
    """Any committed write may change a count: the next read recomputes it."""
    try:
        clear(session.get_bind())  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 (a session bound to something else: nothing to forget)
        logging.getLogger(__name__).debug("cache not cleared", exc_info=True)
