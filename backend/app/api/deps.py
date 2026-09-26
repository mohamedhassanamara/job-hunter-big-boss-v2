from typing import Annotated

from fastapi import Depends, HTTPException
from sqlmodel import Session, SQLModel

from app.db import get_session

SessionDep = Annotated[Session, Depends(get_session)]


def get_or_404[T: SQLModel](
    session: Session, model: type[T], id_: int, label: str | None = None
) -> T:
    obj = session.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{label or model.__name__} {id_} not found")
    return obj
