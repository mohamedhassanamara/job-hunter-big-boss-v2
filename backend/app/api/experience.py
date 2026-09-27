from fastapi import APIRouter, HTTPException, Response
from sqlmodel import col, func, select

from app.api.deps import EngineDep, SessionDep, get_or_404
from app.models import ExperienceItem
from app.models.enums import ExperienceKind
from app.schemas.experience import ExperienceIn, ExperienceOut, ExperiencePatch, ReorderIn
from app.seed.test_cv import remove_test_cv

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
    kind = _kind(body.kind)
    last = session.exec(
        select(func.max(ExperienceItem.position)).where(ExperienceItem.kind == kind)
    ).one()
    item = ExperienceItem(**body.model_dump(), position=(last or 0) + 1)
    item.kind = kind
    session.add(item)
    session.commit()
    session.refresh(item)
    return _out(item)


@router.patch("/{item_id}", response_model=ExperienceOut)
def update_item(item_id: int, body: ExperiencePatch, session: SessionDep) -> ExperienceOut:
    item = get_or_404(session, ExperienceItem, item_id, "Experience item")
    data = body.model_dump(exclude_unset=True)
    if "kind" in data:
        data["kind"] = _kind(data["kind"])
    for key, value in data.items():
        setattr(item, key, value)
    item.is_placeholder = False  # once edited, it's the user's own data
    session.add(item)
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
    session.delete(get_or_404(session, ExperienceItem, item_id, "Experience item"))
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
