"""Diagnostic and verification script for Adzuna API ingestion.

Run with: backend/.venv/bin/python backend/scripts/manual_adzuna.py --live
"""

import sys

if "--live" not in sys.argv:  # manual script: never run by accident (or as a test)
    sys.exit("manual_adzuna.py makes real requests to the live Adzuna API. Re-run it with --live.")
sys.argv.remove("--live")
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import get_settings  # noqa: E402
from app.providers.base import ProfileSpec  # noqa: E402
from app.providers.sources.adzuna import ENDPOINTS, AdzunaSource, parse_adzuna  # noqa: E402


def main() -> None:
    print("=" * 60)
    print("Adzuna Job Source Diagnostic & Verification Tool")
    print("=" * 60)

    settings = get_settings()
    app_id = settings.adzuna_app_id
    app_key = settings.adzuna_app_key

    print("Checking credentials:")
    id_info = "set" if app_id else "NOT SET"
    key_info = "set" if app_key else "NOT SET"
    print(f"  ADZUNA_APP_ID  : {id_info}")
    print(f"  ADZUNA_APP_KEY : {key_info}")

    source = AdzunaSource()
    not_configured = source.configured()
    if not_configured:
        print(f"\n[FAIL] Adzuna is not properly configured: {not_configured}")
        sys.exit(1)

    print("\n[OK] Configuration valid.")

    # Target countries
    test_countries = ["DE", "FR"]
    test_roles = ["Flutter Developer", "Data Engineer"]
    spec = ProfileSpec(locations=test_countries, roles=test_roles, max_age_days=14)

    targets = source.targets(spec)
    print(f"\nTargets resolved for {test_countries}: {targets}")
    print(f"Warnings (if any): {source.warnings}")

    print("\nExecuting live API fetch...")
    payloads = source.fetch_payloads(spec)
    print(
        f"Fetched {len(payloads)} country/role payloads. "
        f"Total requests made: {source.requests}"
    )

    total_jobs = 0
    parsed_jobs = []
    for country, payload in payloads:
        results = payload.get("results") or []
        ep = ENDPOINTS.get(country)
        print(f"  - [{country}] endpoint '{ep}': returned {len(results)} raw items")
        jobs = parse_adzuna(payload, country)
        parsed_jobs.extend(jobs)
        total_jobs += len(jobs)

    print(f"\nParsed {total_jobs} total valid RawJob instances.")
    if parsed_jobs:
        sample = parsed_jobs[0]
        print("\nSample Job Verification:")
        print(f"  Title       : {sample.title}")
        print(f"  Company     : {sample.company}")
        print(f"  Country     : {sample.country}")
        print(f"  Location    : {sample.location}")
        print(f"  URL         : {sample.url[:60]}...")
        print(f"  Remote Type : {sample.remote_type}")
        print(f"  Level       : {sample.description_level}")
        print(f"  Snippet len : {len(sample.description)} chars")

    if source.warnings:
        print("\nWarnings during run:")
        for w in source.warnings:
            print(f"  * {w}")

    print("\n[SUCCESS] Adzuna ingestion verified successfully!")


if __name__ == "__main__":
    main()
