from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # The real workspace. Only the user's own data lives here.
    database_url: str = f"sqlite:///{DATA_DIR / 'jobhunter.db'}"
    # Sandbox used by guided tours (sample data only; reset at every tour start).
    demo_database_url: str = f"sqlite:///{DATA_DIR / 'demo.db'}"
    # Dev aid: delay every /api response to exercise skeleton states in the UI.
    mock_latency_ms: int = 0
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Job sources. `mock` swaps every source for the offline MockJobSource (tests, demos).
    job_sources: Literal["real", "mock"] = "real"
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    # Public, search-only key the Welcome to the Jungle site ships to every browser.
    wttj_algolia_app_id: str = "CSEKHVMS53"
    wttj_algolia_key: str = "4bd8f6215d0cc52b26430765769e65a0"
    # Optional contact appended to the User-Agent sent to job sources.
    discovery_contact: str = ""
    log_dir: Path = DATA_DIR / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
