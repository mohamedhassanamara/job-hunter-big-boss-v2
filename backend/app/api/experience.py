from fastapi import APIRouter, HTTPException, Response
from sqlmodel import col, select

from app.api.deps import EngineDep, SessionDep, get_or_404
from app.models import ExperienceItem
from app.models.enums import ExperienceKind
from app.schemas.experience import (
    ExperienceIn,
    ExperienceOut,
    ExperiencePatch,
    HistoryOut,
    ReorderIn,
)
from app.seed.test_cv import remove_test_cv
from app.services import experience_write

router = APIRouter(prefix="/experience", tags=["experience"])


def _out(i: ExperienceItem) -> ExperienceOut:
    return ExperienceOut.model_validate(i, from_attributes=True)


def _kind(value: str) -> ExperienceKind:
    try:
        return ExperienceKind(value)
    except ValueError as exc:
        raise HTTPException(422, f"Unknown kind {value}") from exc


@router.get("", response_model=list[ExperienceOut])
def list_items(session: SessionDep) -> list[ExperienceOut]:
    rows = session.exec(
        select(ExperienceItem).order_by(col(ExperienceItem.kind), col(ExperienceItem.position))
    ).all()
    return [_out(i) for i in rows]


@router.post("", response_model=ExperienceOut, status_code=201)
def create_item(body: ExperienceIn, session: SessionDep) -> ExperienceOut:
    data = body.model_dump()
    data["kind"] = _kind(body.kind)
    item = experience_write.create(session, data)
    session.commit()
    session.refresh(item)
    return _out(item)


@router.patch("/{item_id}", response_model=ExperienceOut)
def update_item(item_id: int, body: ExperiencePatch, session: SessionDep) -> ExperienceOut:
    item = get_or_404(session, ExperienceItem, item_id, "Experience item")
    data = body.model_dump(exclude_unset=True)
    if "kind" in data:
        data["kind"] = _kind(data["kind"])
    experience_write.update(session, item, data)
    session.commit()
    session.refresh(item)
    return _out(item)


@router.get("/{item_id}/history", response_model=list[HistoryOut])
def item_history(item_id: int, session: SessionDep) -> list[HistoryOut]:
    """Every change to this item's text, newest first, each undoable."""
    return [HistoryOut.model_validate(h, from_attributes=True)
            for h in experience_write.history(session, item_id)]


@router.post("/history/{history_id}/undo", response_model=ExperienceOut)
def undo_change(history_id: int, session: SessionDep) -> ExperienceOut:
    try:
        item = experience_write.undo(session, history_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    session.commit()
    session.refresh(item)
    return _out(item)


@router.delete("/placeholders", status_code=204)
def delete_placeholders(engine: EngineDep) -> Response:
    """Remove the test CV (items marked is_placeholder) and its test candidate profile."""
    remove_test_cv(engine)
    return Response(status_code=204)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, session: SessionDep) -> Response:
    item = get_or_404(session, ExperienceItem, item_id, "Experience item")
    experience_write.delete(session, item)
    session.commit()
    return Response(status_code=204)


@router.post("/reorder", response_model=list[ExperienceOut])
def reorder(body: ReorderIn, session: SessionDep) -> list[ExperienceOut]:
    kind = _kind(body.kind)
    items = {
        i.id: i
        for i in session.exec(select(ExperienceItem).where(ExperienceItem.kind == kind)).all()
    }
    if set(body.ids) != set(items):
        raise HTTPException(422, "ids must contain every item of this kind exactly once")
    for pos, id_ in enumerate(body.ids):
        items[id_].position = pos
        session.add(items[id_])
    session.commit()
    return list_items(session)
