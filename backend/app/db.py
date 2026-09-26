from collections.abc import Iterator
from typing import Literal

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.config import DATA_DIR, get_settings

Workspace = Literal["real", "demo"]
WORKSPACE_HEADER = "X-Workspace"


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine


# The real workspace: only the user's own data.
engine = make_engine(get_settings().database_url)
# The tour sandbox: sample data, rebuilt from fixtures at every tour start.
demo_engine = make_engine(get_settings().demo_database_url)


def workspace_of(request: Request) -> Workspace:
    return "demo" if request.headers.get(WORKSPACE_HEADER, "").lower() == "demo" else "real"


def engine_for(workspace: Workspace) -> Engine:
    return demo_engine if workspace == "demo" else engine


def get_session(request: Request) -> Iterator[Session]:
    with Session(engine_for(workspace_of(request))) as session:
        yield session
