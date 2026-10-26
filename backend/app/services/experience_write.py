"""The only way to change the text of your experience pool.

Your pool is your own words: no automated process may edit it (generation, scoring, imports of
other data, seeds of the real workspace…). Everything that writes an `ExperienceItem` text field
goes through this module, which records the item as it was in `experience_history` (so every
change can be undone). A `before_flush` guard enforces it at runtime: any other write to those
fields, or a delete, raises `PoolWriteError`. `tests/test_pool_protected.py` checks both the guard
and that no other module writes pool text.

Who may call it: the Experience screen (`api/experience.py`, source "user"), the explicit master
document import (source "master_import"), and Undo. Sample-data seeds (the tour sandbox, the test
CV) run inside `writing()`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from typing import Any

from sqlalchemy import event, inspect
from sqlmodel import Session, col, func, select

from app.models import ExperienceHistory, ExperienceItem

# Everything the CV/letters/emails can quote or rely on. Position and the placeholder flag are
# layout/bookkeeping and stay free (reordering is not a text edit).
TEXT_FIELDS = ("kind", "title", "org", "location", "start_date", "end_date", "date_label",
               "summary", "bullets", "tags", "tracks", "url", "credential_id", "is_active")

_allowed: ContextVar[bool] = ContextVar("pool_write_allowed", default=False)


class PoolWriteError(RuntimeError):
    pass


@contextmanager
def writing() -> Iterator[None]:
    """Mark the enclosed code as an explicit, user-authorised pool write (the gateway itself,
    and sample-data seeds)."""
    token = _allowed.set(True)
    try:
        yield
    finally:
        _allowed.reset(token)


@event.listens_for(Session, "before_flush")
def _guard(session: Session, _ctx: Any, _instances: Any) -> None:
    if _allowed.get():
        return
    for obj in session.dirty:
        if isinstance(obj, ExperienceItem):
            state = inspect(obj)
            changed = [f for f in TEXT_FIELDS if state.attrs[f].history.has_changes()]
            if changed:
                raise PoolWriteError(
                    f"Experience text is only edited from the Experience screen "
                    f"(tried to change {', '.join(changed)} of item {obj.id}).")
    for obj in session.deleted:
        if isinstance(obj, ExperienceItem):
            raise PoolWriteError("Experience items are only deleted from the Experience screen.")


def snapshot(item: ExperienceItem) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in TEXT_FIELDS:
        v = getattr(item, f)
        out[f] = v.isoformat() if isinstance(v, date) else (list(v) if isinstance(v, list) else
                                                           str(v) if f == "kind" else v)
    return out


def _restore(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for f in ("start_date", "end_date"):
        if isinstance(out.get(f), str):
            out[f] = date.fromisoformat(out[f])
    return out


def _log(s: Session, item_id: int, action: str, source: str, before: dict[str, Any],
         after: dict[str, Any], note: str | None) -> ExperienceHistory:
    row = ExperienceHistory(item_id=item_id, action=action, source=source, before=before,
                            after=after, note=note)
    s.add(row)
    return row


def create(s: Session, data: dict[str, Any], *, source: str = "user", note: str | None = None,
           item_id: int | None = None) -> ExperienceItem:
    with writing():
        last = s.exec(select(func.max(ExperienceItem.position)).where(
            ExperienceItem.kind == data["kind"])).one()
        item = ExperienceItem(**{**_restore(data), "position": data.get("position",
                                                                        (last or 0) + 1)})
        if item_id is not None:
            item.id = item_id
        s.add(item)
        s.flush()
        _log(s, item.id, "created", source, {}, snapshot(item), note)
    return item


def update(s: Session, item: ExperienceItem, changes: dict[str, Any], *, source: str = "user",
           action: str = "edited", note: str | None = None) -> ExperienceItem:
    """Apply `changes`; when any text field actually changes, record the previous version."""
    with writing():
        before = snapshot(item)
        for key, value in _restore(changes).items():
            setattr(item, key, value)
        after = snapshot(item)
        if before != after:
            item.is_placeholder = False  # once edited, it's the user's own data
            _log(s, item.id, action, source, before, after, note)
        s.add(item)
        s.flush()
    return item


def archive(s: Session, item: ExperienceItem, *, source: str = "user",
            note: str | None = None) -> ExperienceItem:
    """Inactive: kept (and restorable) but never used for CVs, scoring, letters or emails."""
    return update(s, item, {"is_active": False}, source=source, action="archived", note=note)


def delete(s: Session, item: ExperienceItem, *, source: str = "user") -> None:
    with writing():
        _log(s, item.id, "deleted", source, snapshot(item), {}, None)
        s.delete(item)
        s.flush()


def history(s: Session, item_id: int) -> list[ExperienceHistory]:
    return list(s.exec(select(ExperienceHistory).where(ExperienceHistory.item_id == item_id)
                       .order_by(col(ExperienceHistory.id).desc())))


def undo(s: Session, history_id: int) -> ExperienceItem:
    """Put the item back as it was before that change (itself recorded, so Undo can be undone)."""
    row = s.get(ExperienceHistory, history_id)
    if row is None:
        raise LookupError("History entry not found")
    item = s.get(ExperienceItem, row.item_id)
    if row.action == "created":
        if item is None:
            raise LookupError("Item no longer exists")
        return archive(s, item, source="undo", note=f"undo of #{row.id}")
    if row.action == "deleted":
        return create(s, {**row.before, "kind": row.before["kind"]}, source="undo",
                      note=f"undo of #{row.id}", item_id=row.item_id)
    if item is None:
        raise LookupError("Item no longer exists")
    return update(s, item, dict(row.before), source="undo", action="undo",
                  note=f"undo of #{row.id}")
