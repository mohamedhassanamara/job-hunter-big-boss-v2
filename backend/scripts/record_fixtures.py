"""Record one real (trimmed) response per source as an offline test fixture.

    .venv/bin/python scripts/record_fixtures.py arbeitnow remotive wttj adzuna

Makes real network requests: run it by hand, never from tests.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.base import ProfileSpec  # noqa: E402
from app.seed.fixtures import SEARCH_PROFILE  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sources"
KEEP = 30  # items per fixture: enough variety, small file


def relevant_first(items: list[dict], title_key: str) -> list[dict]:
    """Keep a mix: role-looking titles first (so mappers see realistic data), then the rest."""
    words = ("data", "machine learning", "ml", "ai", "analytics", "engineer")
    hit = [i for i in items if any(w in str(i.get(title_key, "")).lower() for w in words)]
    rest = [i for i in items if i not in hit]
    return (hit[: KEEP // 2] + rest)[:KEEP]


def main(names: list[str]) -> None:
    profile = ProfileSpec(**{k: v for k, v in SEARCH_PROFILE.items() if k != "name"})
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        if name == "arbeitnow":
            from app.providers.sources.arbeitnow import ArbeitnowSource

            first_page_only = profile.model_copy(update={"max_age_days": 0})
            payload = ArbeitnowSource().fetch_payloads(first_page_only)[0]
            payload["data"] = relevant_first(payload["data"], "title")
        elif name == "remotive":
            from app.providers.sources.remotive import RemotiveSource

            # One request only: Remotive asks for <= 4 requests/day.
            payload = RemotiveSource(categories=["data"], limit=KEEP).fetch_payloads(profile)[0]
        else:
            raise SystemExit(f"unknown source {name}")
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        print(f"wrote {path.relative_to(OUT.parents[2])}")


if __name__ == "__main__":
    main(sys.argv[1:])
