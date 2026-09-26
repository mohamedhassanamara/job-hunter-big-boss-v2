import os
import tempfile
from pathlib import Path

# Point the app at a throwaway DB *before* any app module creates its engine.
_tmp = Path(tempfile.mkdtemp(prefix="jobhunter-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["MOCK_LATENCY_MS"] = "0"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def _migrate() -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    _migrate()


@pytest.fixture()
def seeded(migrated_db: None) -> None:
    from app.db import engine
    from app.seed.seed import seed

    seed(engine)


@pytest.fixture()
def client(seeded: None) -> TestClient:
    from app.main import app

    return TestClient(app)
