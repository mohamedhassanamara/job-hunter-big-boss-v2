#!/usr/bin/env python3
"""Standalone verification script for APInex Gateway Fit Scoring."""

import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_dir))

from app.config import get_settings
from app.providers.apinex_client import APInexClient, PRIMARY_MODEL, FALLBACK_MODEL
from app.providers.base import FitAssessment, JobSnapshot
from app.services import fit
from app.services.prompt import load_prompt


def main() -> None:
    api_key = os.environ.get("APINEX_API_KEY") or getattr(get_settings(), "apinex_api_key", "")
    print(f"Checking APINEX_API_KEY... {'Found' if api_key else 'Missing'}")
    if not api_key:
        print("Error: APINEX_API_KEY must be set in environment or .env file.")
        sys.exit(1)

    print(f"Base URL: https://apinex.bond/v1")
    print(f"Primary model: {PRIMARY_MODEL}")
    print(f"Fallback model: {FALLBACK_MODEL}")

    client = APInexClient(api_key=api_key)
    prompt = load_prompt("fit_score")
    print(f"Loaded prompt: {prompt.name} (version {prompt.version})")

    # Sample listing: German backend engineer role with no explicit visa bans
    job_text = """
Title: Senior Python Engineer
Company: CloudScale GmbH
Location: Berlin, Germany
Work mode: Hybrid (2 days in Berlin office)

About the role:
We are looking for a Senior Python Engineer to design and scale our distributed event-driven systems.
Requirements:
- 5+ years of experience with Python, FastAPI or Django, and asynchronous architectures.
- Experience with PostgreSQL, Redis, and message queues (Kafka or RabbitMQ).
- Strong understanding of Docker and containerized deployments.
- Fluency in English (working language of our international engineering team). German is a plus.
- We support relocation and standard visa sponsorship (EU Blue Card) for international hires.
"""

    user_prompt = f"""
CANDIDATE
Headline: Senior Backend Engineer
Based in: Casablanca, Morocco
Nationality: Moroccan
Work authorization: needs employer visa sponsorship (not EU citizen)
Target countries: Germany, France, Netherlands (or remote)
Languages: English (Native), French (Full professional)
Years of experience (total): 6

TRACK
Track: Backend
Track roles: Python Backend Engineer, Senior Backend Engineer
Years in this track: 6
Matched role: Senior Python Engineer

EXPERIENCE
- [work] Senior Python Engineer, FinTech Corp (2021 - Present)
  Architected high-throughput payment processing APIs in FastAPI and PostgreSQL.
  Skills: Python, FastAPI, PostgreSQL, Docker, Redis

JOB
{job_text}
"""

    print("\nExecuting fit score evaluation via APInex Gateway...")
    raw_json = client.complete_sync(prompt.system, user_prompt)
    print("\n--- Raw JSON Response ---")
    print(json.dumps(raw_json, indent=2))

    print("\nValidating into FitAssessment Pydantic model...")
    assessment = FitAssessment.model_validate(raw_json)
    print(f"Overall score: {assessment.overall_score}")
    print(f"Verdict: {assessment.verdict}")
    print(f"Disqualifying flags: {assessment.disqualifying_flags}")
    print(f"Role match subscore: {assessment.role_match.score}/10")
    print(f"Location eligibility subscore: {assessment.location_eligibility.score}/10")
    print(f"Summary: {assessment.summary}")

    print("\nComputing database record with build_record arithmetic...")
    config = fit.ScoringConfig.from_settings(
        {"weights": {"location_eligibility": 0.20}},
        {"work_authorization": "needs_sponsorship", "nationality": "Moroccan",
         "languages": [{"language": "English", "level": "Native"}]}
    )
    record = fit.build_record(
        assessment,
        job_text=job_text,
        description_level="full",
        remote_type="hybrid",
        config=config,
        experience_text="6 years Python and backend engineering experience.",
        job_title="Senior Python Engineer",
    )
    print(f"Final calculated score: {record['score']}/100")
    hard_flags = [f for f in record["red_flags"] if f.get("severity") == "hard"]
    print(f"Hard red flags: {len(hard_flags)}")
    assert len(hard_flags) == 0, f"Expected 0 hard red flags, got: {hard_flags}"
    assert record["sub_scores"]["location_eligibility"]["score"] >= 8, (
        f"Location eligibility should be >= 8, got {record['sub_scores']['location_eligibility']['score']}"
    )

    print("\n Verification Successful: EU listing without explicit ban is NOT disqualified.")


if __name__ == "__main__":
    main()
