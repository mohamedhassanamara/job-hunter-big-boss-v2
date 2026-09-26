from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.db import Workspace, engine_for, get_session, workspace_of

SessionDep = Annotated[Session, Depends(get_session)]
WorkspaceDep = Annotated[Workspace, Depends(workspace_of)]


def get_engine(workspace: WorkspaceDep) -> Engine:
    return engine_for(workspace)


EngineDep = Annotated[Engine, Depends(get_engine)]


def get_or_404[T: SQLModel](
    session: Session, model: type[T], id_: int, label: str | None = None
) -> T:
    obj = session.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{label or model.__name__} {id_} not found")
    return obj
