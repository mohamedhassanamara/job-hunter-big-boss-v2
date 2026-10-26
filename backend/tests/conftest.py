import os
import tempfile
from pathlib import Path

# Point the app at a throwaway DB *before* any app module creates its engine.
_tmp = Path(tempfile.mkdtemp(prefix="jobhunter-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["DEMO_DATABASE_URL"] = f"sqlite:///{_tmp / 'demo.db'}"
os.environ["MOCK_LATENCY_MS"] = "0"
os.environ["JOB_SOURCES"] = "mock"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SEND_WORKER_ENABLED"] = "false"
os.environ["GENERATION_WORKER_ENABLED"] = "false"
os.environ["SMTP_APP_PASSWORD"] = ""
os.environ["APINEX_API_KEY"] = ""  # no gateway key in tests
os.environ["HUNTER_API_KEY"] = ""  # .env may hold a real key: tests never use it
for _name in ("HUNTER_API_KEYS", "PROSPEO_API_KEYS", "APOLLO_API_KEYS", "APIFY_TOKEN",
              "GEMINI_API_KEYS", "GEMINI_API_KEY"):
    os.environ[_name] = ""

# Rendered CVs, letters and uploads go to the throwaway folder too, never into data/.
from app.services import cover_letter as _cover_letter  # noqa: E402
from app.services import cv_service as _cv_service  # noqa: E402
from app.services.motivation import files as _motivation_files  # noqa: E402

_cv_service.CV_DIR = _tmp / "cv"
_cover_letter.LETTER_DIR = _tmp / "letters"
_motivation_files.ROOT = _tmp / "motivation"

import socket  # noqa: E402

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


_real_connect = socket.socket.connect


def _guarded_connect(self: socket.socket, address: object) -> None:
    host = address[0] if isinstance(address, tuple) else address
    if host not in ("127.0.0.1", "localhost", "::1") and not str(host).startswith("/"):
        raise RuntimeError(f"Tests must not use the network (tried to connect to {host})")
    _real_connect(self, address)


@pytest.fixture(scope="session", autouse=True)
def no_network() -> None:
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]


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
