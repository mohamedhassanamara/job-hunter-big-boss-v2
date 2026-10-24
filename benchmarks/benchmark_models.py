#!/usr/bin/env python3
"""
APInex Model Evaluation Benchmark for Job Hunter v2 Fit Scoring
Tests free tier models against a standardized candidate profile and job listing.
Outputs metrics (latency, input/output tokens, JSON validity, score) and generates a Markdown report.
"""

import os
import sys
import time
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List
import httpx

# List of FREE group models from APInex dashboard
MODELS = [
    "free/muse-spark-1.3",
    "free/deepseek-v4.1-flash",
    "free/glm-5.3-flash",
    "free/minimax-m3.1-flash",
    "free/glm-5.3",
    "free/gemini-3.8-flash",
    "free/deepseek-v4-pro-0813",
    "free/gpt-6-luna",
    "free/glm-5.3-flashx",
    "free/mimo-v2.6-pro",
    "free/jev-1.13",
]

BASE_URL = "https://apinex.bond/v1"

SYSTEM_PROMPT = """You are a rigorous, objective job fit evaluator for technical roles.
Evaluate the candidate against the job description across 5 dimensions:
1. role_match: Does the job title/responsibilities align with the candidate's track?
2. skills_match: Are core required frameworks, languages, and technical proficiencies met?
3. seniority_fit: Does the candidate's experience level match requirements without being under/over-qualified?
4. location_eligibility: Can the candidate legally work here considering visa, remote policy, and country?
5. language_requirements: Does the candidate meet required/working languages?

Output strictly a valid JSON object matching this schema:
{
  "overall_score": <integer 0-100>,
  "verdict": "<apply | maybe | skip>",
  "disqualifying_flags": [<string>],
  "dimensions": {
    "role_match": {"score": <0-100>, "reason": "<string>"},
    "skills_match": {"score": <0-100>, "reason": "<string>"},
    "seniority_fit": {"score": <0-100>, "reason": "<string>"},
    "location_eligibility": {"score": <0-100>, "reason": "<string>"},
    "language_requirements": {"score": <0-100>, "reason": "<string>"}
  },
  "key_strengths": [<string>],
  "critical_gaps": [<string>],
  "summary": "<short 2-sentence summary>"
}
Do not include any explanation or markdown formatting outside the JSON object."""

USER_PROMPT = """CANDIDATE
Headline: Software engineer with 3 years of experience in mobile and backend development, moving into data and AI through personal projects, a graduation project and certifications.
Based in: Tunis, Tunisia
Nationality: Tunisian
Work authorization: needs employer visa sponsorship to work in the target countries (not a citizen or resident of the EU or the Gulf states)
Target countries: Spain, Portugal, France, Italy, Germany, Belgium, United Arab Emirates, Qatar, Bahrain, Kuwait, Jordan, Turkey (or remote)
Languages: Arabic (Native), English (Full professional), French (Full professional), Spanish (Limited working)
Years of experience (total): 3

TRACK (the candidate's target field this job matched)
Track: Mobile
Track roles: Flutter Developer, Flutter Engineer, Mobile Developer, Mobile Engineer, Cross-platform Developer
Years in this track: 3.0
Matched role: Flutter Developer

EXPERIENCE
- [certification] Data Engineer, DataCamp
  Skills: data-engineering
- [certification] Data Analyst with Python, DataCamp
  Skills: python, data-analysis, pandas
- [certification] Associate Data Engineer in Python, DataCamp
  Skills: python, sql, data-modeling, data-pipelines
- [education] Master's Degree in Software Engineering, Higher Institute of Applied Sciences and Technology of Sousse (2019 – 2024)
  Software engineering, algorithms, distributed systems, software architecture.
- [education] Scientific Baccalaureate, Secondary School (2019)
- [job] Full-Stack Developer, Freelance (2024 – present)
  Independent development of web, mobile and backend applications for direct clients.
  • Designed and delivered custom Flutter mobile applications and web dashboards end to end for international clients, taking features from initial concept through store deployment.
  • Developed RESTful backend APIs with Python (FastAPI) and Java (Spring Boot), integrating relational databases and third-party authentication services.
  • Set up deployment workflows using Docker containers and cloud infrastructure, ensuring reproducible environments and basic CI automation.
  • Collaborated directly with non-technical stakeholders to scope product requirements, manage release milestones and handle post-launch maintenance.
  Skills: Flutter, Dart, Python, FastAPI, Java, Spring Boot, PostgreSQL, Docker, Git
- [job] Mobile Developer, E-Taalim (2023 – 2024)
  Cross-platform mobile application for online learning and student engagement.
  • Built cross-platform mobile features in Flutter/Dart, implementing state management, offline storage and responsive UI components for thousands of daily learners.
  • Integrated real-time messaging, push notifications and audio streaming capabilities using Firebase Cloud Messaging and WebSocket connections.
  • Optimized application rendering performance and startup latency, reducing memory footprint across entry-level Android devices.
  • Worked closely with UI/UX designers and backend engineers in an Agile sprint cadence, contributing to code reviews and regression test coverage.
  Skills: Flutter, Dart, Firebase, REST APIs, State Management, Git, Agile
- [job] Mobile Developer, Cynoia (2022 – 2023)
  All-in-one team collaboration platform combining chat, email, video and project management.
  • Developed and maintained core modules of the Cynoia cross-platform mobile app using Flutter, including real-time chat, channel navigation and file previewing.
  • Implemented local SQLite caching and optimistic UI updates, maintaining consistent offline-first state during intermittent network conditions.
  • Refactored legacy navigation and state handling logic, resolving memory leaks and decreasing crash-free session rates below target thresholds.
  • Participated in automated build and deployment pipelines targeting Google Play Console and Apple App Store TestFlight distributions.
  Skills: Flutter, Dart, SQLite, WebSockets, Push Notifications, CI/CD, Git
- [job] End of Studies Project Intern, Cynapsys by Gfi / Inetum (2021)
  Graduation project focused on real-time event monitoring and mobile dashboard reporting.
  • Built an internal reporting and notification mobile interface in Flutter connected to backend telemetry services for operational monitoring.
  • Implemented event ingestion adapters and data visualization widgets displaying real-time metrics, alerts and historical incident logs.
  • Co-authored technical documentation, architecture blueprints and user acceptance test suites as part of the formal graduation defense.
  Skills: Flutter, Dart, REST APIs, Data Visualization, Git
- [project] Smart Home Sensor Streaming & Analytics Pipeline (2024)
  End-to-end streaming data pipeline ingesting IoT telemetry to power real-time anomaly detection and operational dashboards.
  • Built an event ingestion pipeline using Python and Apache Kafka producing synthetic telemetry across multiple simulated sensor topics.
  • Processed unbounded data streams with PySpark Streaming and Spark Structured Streaming, computing rolling aggregations and detecting threshold breaches.
  • Landed raw and aggregated metrics into a Delta Lake storage tier orchestrated by Apache Airflow DAGs for reliable daily partitioning.
  • Surfaced real-time pipeline status and sensor health through a lightweight Streamlit dashboard backed by DuckDB queries.
  Skills: Python, Apache Kafka, Apache Spark, PySpark, Delta Lake, Apache Airflow, Docker, DuckDB, Streamlit
- [project] E-Commerce Clickstream & Orders Lakehouse (2024)
  Batch and near-real-time ELT pipeline modeling raw transactional logs into Medallion architecture analytical layers.
  • Ingested simulated clickstream JSON logs and relational order tables from PostgreSQL into an Amazon S3 object storage raw zone.
  • Implemented Medallion architecture (Bronze/Silver/Gold) transformations using dbt and Snowflake, producing Kimball-style dimensional models.
  • Enforced schema contracts and data freshness checks using Great Expectations test suites integrated into GitHub Actions CI workflows.
  • Documented data lineage, transformation DAGs and dimensional dictionaries within dbt docs and automated markdown catalogs.
  Skills: Python, SQL, PostgreSQL, Snowflake, dbt, Amazon S3, Great Expectations, GitHub Actions
- [project] Multilingual Resume Parsing & Semantic Matching Engine (2024)
  Information extraction and semantic retrieval engine matching technical job descriptions to candidate profiles.
  • Built an extraction pipeline using Python, PyMuPDF and regular expressions parsing semi-structured CV documents in English and French into structured JSON schemas.
  • Generated dense vector representations of parsed skills and job requirements using open-source sentence transformers (all-MiniLM-L6-v2).
  • Implemented hybrid search combining lexical BM25 matching with vector similarity indexing in Qdrant for semantic ranking.
  • Deployed the retrieval service as an asynchronous FastAPI application with automated unit testing and containerized packaging.
  Skills: Python, FastAPI, Sentence Transformers, Qdrant, BM25, Docker, PyMuPDF
- [project] Cross-Platform Enterprise Field Service App (2023)
  Production-grade offline-first mobile application for field technicians managing maintenance work orders and assets.
  • Engineered an offline-first mobile application in Flutter using Drift/SQLite for local persistence and background queue sync upon reconnection.
  • Designed modular architecture separating presentation, domain business rules and data repositories with automated BLoC state management.
  • Integrated camera scanning, PDF work order generation and biometric authentication using native platform channel plugins.
  • Published internal releases via Fastlane and GitHub Actions targeting Android and iOS staging environments.
  Skills: Flutter, Dart, Drift, SQLite, BLoC, Fastlane, GitHub Actions, Native Channels
- [skill] Data Engineering & Big Data
  Skills: Apache Spark, PySpark, Apache Kafka, Apache Airflow, dbt, Delta Lake, Snowflake, Hadoop, Hive
- [skill] Mobile Development
  Skills: Flutter, Dart, Android (Java/Kotlin), iOS (Swift), Cross-platform Architecture, BLoC, Provider, State Management
- [skill] Backend Engineering & APIs
  Skills: Python, FastAPI, Java, Spring Boot, RESTful APIs, WebSockets, Microservices, SQLAlchemy
- [skill] Databases & Storage
  Skills: PostgreSQL, MySQL, SQLite, MongoDB, Redis, DuckDB, Qdrant
- [skill] Cloud, DevOps & Tools
  Skills: Docker, Docker Compose, Linux, Git, GitHub Actions, CI/CD, AWS (S3, EC2), Bash
- [skill] Machine Learning & AI
  Skills: LLMs, LangChain, Sentence Transformers, Vector Databases, Semantic Search, Prompt Engineering, Pandas, NumPy

JOB
Title: Flutter developer for mobile apps (m/f/d)
Company: Healy World GmbH
Location: Charlottenburg, Berlin (DE)
Work mode: unknown
Description (full listing):
<<<
JOB DESCRIPTION

At Healy, you’re not just an employee—you’re a co-creator.

Healy World GmbH is an innovative and leading company in the health and wellness industry.

We’re growing, we’re shaping the future, we’re making a difference—and you can be a part of it! We offer an innovative and diverse work environment that’s constantly evolving. In Finance, Legal, Marketing, or Operations, you’ll have the opportunity to implement your ideas and make a real difference.

Does that sound exciting to you? Then join our international team at our location in Berlin! We’re looking for a:

Flutter developer for mobile apps (m/f/d)

YOUR TASKS
- Development of cross-platform apps for iOS and Android based on Flutter
- Active contribution to the app architecture and conception of new features
- Continuous optimization of performance, code quality and user experience
- Close cooperation with designers, product managers and backend developers
- Independent implementation of modern UI/UX designs

YOUR PROFILE
- At least 2 years of professional experience in mobile app development with Flutter & Dart
- Confident handling of state management (e.g. BLoC, Provider, Riverpod)
- Experience in connecting REST APIs and WebSocket services
- Good knowledge of app architecture (Clean Architecture, MVVM)
- Experience with native development (iOS/Swift or Android/Kotlin) is an advantage
- Quality awareness, clean code and experience with automated testing
- Team player with very good communication skills in English (German is a plus)

WHAT WE OFFER
- A dynamic and international working environment in a growing company
- Flat hierarchies and short decision-making paths
- Flexible working hours and hybrid work model (home office / office in Berlin)
- Modern hardware of your choice
- Subsidized Deutschlandticket or corporate mobility allowance
- Regular team events and open company culture

Have we sparked your interest? We look forward to receiving your application!
>>>"""

async def test_single_model(client: httpx.AsyncClient, model_name: str) -> Dict[str, Any]:
    print(f"[*] Testing {model_name}...")
    start_time = time.perf_counter()
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    
    result = {
        "model": model_name,
        "status": "FAILED",
        "duration_sec": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "json_valid": False,
        "score": None,
        "verdict": None,
        "error": None,
        "raw_response": ""
    }

    try:
        response = await client.post(
            "/chat/completions",
            json=payload,
            timeout=90.0
        )
        duration = time.perf_counter() - start_time
        result["duration_sec"] = round(duration, 2)
        
        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
            print(f"[-] {model_name} failed with HTTP {response.status_code}")
            return result

        data = response.json()
        usage = data.get("usage", {})
        result["prompt_tokens"] = usage.get("prompt_tokens", 0)
        result["completion_tokens"] = usage.get("completion_tokens", 0)
        result["total_tokens"] = usage.get("total_tokens", 0)

        content = data["choices"][0]["message"]["content"]
        result["raw_response"] = content
        
        # Parse JSON
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.startswith("```"):
            clean_content = clean_content[3:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        parsed = json.loads(clean_content)
        result["json_valid"] = True
        result["status"] = "SUCCESS"
        result["score"] = parsed.get("overall_score")
        result["verdict"] = parsed.get("verdict")
        print(f"[+] {model_name} completed in {result['duration_sec']}s (Score: {result['score']}, Verdict: {result['verdict']})")

    except json.JSONDecodeError as e:
        result["error"] = f"Invalid JSON generated: {str(e)}"
        result["status"] = "PARTIAL_JSON_ERROR"
        print(f"[!] {model_name} returned non-JSON response in {result['duration_sec']}s")
    except Exception as e:
        result["duration_sec"] = round(time.perf_counter() - start_time, 2)
        result["error"] = str(e)
        print(f"[-] {model_name} failed: {str(e)}")

    return result

def generate_report(results: List[Dict[str, Any]], filename: str = "scoring_benchmark_report.md"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = [
        "# APInex Free-Tier Models Scoring Benchmark Report",
        f"**Generated at:** {now}",
        f"**Total models tested:** {len(results)}",
        "",
        "## 1. Summary Comparison",
        "",
        "| Model | Status | Latency (s) | Prompt Tokens | Output Tokens | Total Tokens | Score | Verdict | JSON Valid |",
        "|---|---|---:|---:|---:|---:|---:|---|:---:|",
    ]

    for r in results:
        status_badge = "OK" if r["status"] == "SUCCESS" else "FAIL"
        json_badge = "Yes" if r["json_valid"] else "No"
        score_val = str(r["score"]) if r["score"] is not None else "-"
        verdict_val = str(r["verdict"]) if r["verdict"] is not None else "-"
        lines.append(
            f"| `{r['model']}` | **{status_badge}** | {r['duration_sec']}s | "
            f"{r['prompt_tokens']} | {r['completion_tokens']} | {r['total_tokens']} | "
            f"{score_val} | `{verdict_val}` | {json_badge} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Detailed Responses & Error Logs",
        ""
    ])

    for r in results:
        lines.append(f"### Model: `{r['model']}`")
        lines.append(f"- **Status**: {r['status']}")
        lines.append(f"- **Execution Time**: {r['duration_sec']}s")
        lines.append(f"- **Tokens**: Prompt: {r['prompt_tokens']} | Completion: {r['completion_tokens']} | Total: {r['total_tokens']}")
        
        if r["error"]:
            lines.append(f"- **Error / Issue**: `{r['error']}`")
        
        if r["raw_response"]:
            lines.append("\n**Model Response Output:**")
            lines.append("```json" if r["json_valid"] else "```text")
            lines.append(r["raw_response"])
            lines.append("```")
        lines.append("\n---\n")

    report_content = "\n".join(lines)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print(f"\n[✓] Benchmark finished! Full report written to: {filename}")

async def main():
    print("=" * 60)
    print(" APInex Free Tier Model Benchmark for Fit Scoring")
    print("=" * 60)
    
    api_key = input("Enter your APInex API key: ").strip()
    if not api_key:
        print("Error: API key is required.")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    results = []
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers) as client:
        for model in MODELS:
            res = await test_single_model(client, model)
            results.append(res)
            # Short courtesy pause between calls
            await asyncio.sleep(1.0)

    generate_report(results)

if __name__ == "__main__":
    asyncio.run(main())
