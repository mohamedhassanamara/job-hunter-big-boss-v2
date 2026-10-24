#!/usr/bin/env python3
"""
APInex Model Evaluation Benchmark for Job Hunter v2 CV Tailoring & Plan Generation
Tests 10 free tier models (excluding jev-1.13) against candidate experience pool and job description.
Evaluates latency, token usage, JSON compliance, schema structure, and writing guide constraints.
Generates a comprehensive markdown report.
"""

import sys
import time
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List
import httpx

# 10 models from the FREE group (excluding free/jev-1.13)
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
]

BASE_URL = "https://apinex.bond/v1"

SYSTEM_PROMPT = """You are an expert technical resume writer and CV tailoring engine.
Follow the provided WRITING GUIDE, LAYOUT rules, FACTS rules, and EMPHASIS constraints strictly.

BANNED PHRASES:
Do not use any of the following phrases:
- "hands-on experience"
- "well suited"
- "strong foundation"
- "real-world applications"
- "production-ready"
- "brings experience"
- "passionate"
- "proven track record"
- "leveraging"

SUMMARY RULES:
- Exactly two full sentences with a clear grammatical subject.
- Sentence 1: state who the candidate is, professional years only in professional tracks (e.g. 3 years in mobile development).
- Sentence 2: concrete value brought to THIS role, naming at least one concrete item built from the pool. Subject must not be "I" (use e.g. "Recent work includes...", "Projects include..."). Never start with a bare verb like "Built..." or "Delivered...".
- Word count: around 45 words.
- No "I". No figures repeated in bullets. No certifications/internships mentioned in the summary.

ROLES & BULLETS:
- Adapt facts from the experience pool to align with the job description.
- Impact first, strong varied verbs.
- Strictly adhere to LAYOUT constraints:
  - Role 6 (Freelance): 3-4 adapted bullets.
  - Role 7 (E-Taalim): 2-3 adapted bullets.
  - Role 8 (Cynoia): 2-3 adapted bullets.
  - Role 9 (Cynapsys): 1-3 adapted bullets.
  - Projects: at most 2 projects (e.g. Project 13), 2-3 adapted bullets each.
  - Skills: at most 4 groups, up to 8 skills each.

Output strictly valid JSON conforming to this schema:
{
  "summary": "<two full sentences, ~45 words>",
  "roles": [
    {
      "id": <integer>,
      "title": "<string>",
      "org": "<string>",
      "bullets": [
        {
          "text": "<adapted bullet text>",
          "source_fact_index": "<string or int>"
        }
      ]
    }
  ],
  "projects": [
    {
      "id": <integer>,
      "title": "<string>",
      "bullets": [
        {
          "text": "<adapted bullet text>",
          "source_fact_index": "<string or int>"
        }
      ]
    }
  ],
  "skills": [
    {
      "category": "<string>",
      "skills": ["<string>"]
    }
  ]
}
Do not include any explanation or markdown wrapping outside the JSON object."""

USER_PROMPT = """WRITING GUIDE
Summary: two full sentences with a subject (never a fragment like "Brings…", never a figure as the subject like "3 years of experience spans…"), no "I", about 45 words. Sentence 1: who I am, with my years attached only to the tracks where my experience is professional. For a Data/AI job a move is welcome: say the professional years, then that the focus is now data (e.g. "Software engineer with 3 years of experience in mobile and backend development, now focused on data engineering."). Sentence 2: what I bring to THIS role, naming at least one concrete thing I built from the cited items (e.g. "a privacy-first resume parser on a local Mistral LLM", "a dbt/Airflow lakehouse for football data"); work in a track that is projects only is said to be projects (e.g. "Projects include an end-to-end dbt/Airflow lakehouse on DuckDB, plus local AI systems, built as personal and graduation projects."). The examples show the level of detail only: use your own facts and wording. Give sentence 2 a subject without "I" (e.g. "Recent work includes…", "Projects include…"), never a bare verb like "Built…" or "Delivered…". Vary the opening between CVs. No numbers that also appear in bullets, no certifications, no internships, no tool lists. In Data/AI summaries, state track years only when they are 2 or more; otherwise the total years, or no years at all.
Bullets: impact first (what I built and why it mattered), strong and varied verbs, one idea per bullet. Prefer bullets with concrete outcomes; skip generic ones ("collaborated in Agile sprints") unless nothing else fits.
Don't repeat the same fact in the summary, the skills and the bullets.
Human tone: natural phrasing, no keyword stuffing; not every bullet needs a metric.
Use the style exemplar for tone, bullet length and summary length (its content is already in the pool).
Never use these phrases: hands-on experience; well suited; strong foundation; real-world applications; production-ready; brings experience; passionate; proven track record; leveraging

STYLE EXEMPLAR (tone, summary length and bullet length only; its content is already in the pool)
{
 "summary": "Software and AI Engineer with over 2 years of experience developing robust data pipelines, scalable backend integrations, and mobile architectures. Proven expertise across batch ETL/ELT orchestration, local LLM systems, and high-performance Flutter applications.",
 "bullets": [
  "Architected custom Backend-for-Frontend (BFF) endpoints in Spring Boot to accelerate mobile API integration, reducing integration time by 40% and unblocking parallel development cycles.",
  "Shipped a full-stack sports management platform, managing mobile client releases to the App Store and Google Play while coordinating real-time backend synchronization.",
  "Spearheaded refactoring legacy code to Riverpod and GoRouter, eliminating 90% of critical bugs on core flows and reducing app size by 15%.",
  "Engineered 10+ custom Flutter screens and established a unit/widget testing culture achieving ~80% code coverage.",
  "Designed a privacy-first resume parsing engine using a local Mistral LLM, replacing external APIs to guarantee data confidentiality and cut operational costs.",
  "Programmed an AI pre-screen interview system using Whisper (STT) and Google TTS to conduct real-time automated candidate assessments."
 ]
}

LAYOUT (what code will show; rank facts with this in mind)
{"roles": {"6": "current: 3-4 bullets", "7": "long role: 2-3 bullets", "8": "long role: 2-3 bullets", "9": "graduation: 1-3 bullets"}, "projects": "at most 2 projects, 2-3 bullets each", "skills": "at most 4 groups, 8 skills each", "summary": "at most 2 sentences, about 45 words"}

FACTS (the only years claims allowed)
{"years": [{"label": "mobile development", "years": 3, "kind": "track"}, {"label": "software engineering", "years": 3, "kind": "total"}], "experience_by_track": [{"track": "Data/AI", "experience": "projects", "how": "personal projects and certifications"}, {"track": "Mobile", "experience": "professional"}, {"track": "Backend", "experience": "professional"}], "years_rule": "The years wording is professional software engineering experience (the professional tracks Mobile, Backend). Work in Data/AI is project-based; never claim professional years in it.", "honesty_tracks": [{"name": "Data/AI", "experience": "projects", "experience_note": "personal projects and certifications", "roles": [{"title": "Data Engineer"}, {"title": "AI Engineer"}]}, {"name": "Mobile", "experience": "professional", "experience_note": null, "roles": [{"title": "Flutter Developer"}, {"title": "Mobile Developer"}]}, {"name": "Backend", "experience": "professional", "experience_note": null, "roles": [{"title": "Backend Developer"}, {"title": "Python Developer"}]}]}

JOB
{
 "title": "Flutter developer for mobile apps (m/f/d)",
 "company": "Healy World GmbH",
 "location": "Charlottenburg, Berlin",
 "description": "JOB DESCRIPTION\n\nAt Healy, you’re not just an employee—you’re a co-creator.\n\nHealy World GmbH is an innovative and leading company in the health and wellness industry.\n\nWe’re growing, we’re shaping the future, we’re making a difference—and you can be a part of it! We offer an innovative and diverse work environment that’s constantly evolving. In Finance, Legal, Marketing, or Operations, you’ll have the opportunity to implement your ideas and make a real difference.\n\nDoes that sound exciting to you? Then join our international team at our location in Berlin! We’re looking for a:\n\nFlutter developer for mobile apps (m/f/d)\n\nYOUR TASKS\n• Development of cross-platform apps for iOS and Android based on Flutter\n• Active contribution to the app architecture and conception of new features\n• Continuous optimization of performance, code quality and user experience\n• Close cooperation with designers, product managers and backend developers\n• Independent implementation of modern UI/UX designs\n\nYOUR PROFILE\n• At least 2 years of professional experience in mobile app development with Flutter & Dart\n• Confident handling of state management (e.g. BLoC, Provider, Riverpod)\n• Experience in connecting REST APIs and WebSocket services\n• Good knowledge of app architecture (Clean Architecture, MVVM)\n• Experience with native development (iOS/Swift or Android/Kotlin) is an advantage\n• Quality awareness, clean code and experience with automated testing\n• Team player with very good communication skills in English (German is a plus)\n\nWHAT WE OFFER\n• A dynamic and international working environment in a growing company\n• Flat hierarchies and short decision-making paths\n• Flexible working hours and hybrid work model (home office / office in Berlin)\n• Modern hardware of your choice\n• Subsidized Deutschlandticket or corporate mobility allowance\n• Regular team events and open company culture\n\nHave we sparked your interest? We look forward to receiving your application!",
 "matched_track": "Mobile",
 "matched_role": "Flutter Developer",
 "strengths": [
  "Flutter and Dart",
  "API integration",
  "GitHub version control"
 ],
 "gaps": []
}

EMPHASIS FOR THIS TRACK
{"skill_groups": ["Mobile & Frontend", "Core Languages", "DevOps, Cloud & Release"], "tags": ["Flutter", "Riverpod", "Clean Architecture", "GoRouter", "Firebase (Auth, Crashlytics, Remote Config)"]}

EXPERIENCE POOL
{
 "summary_snippets": [],
 "roles": [
  {
   "id": 6,
   "title": "Full-Stack Developer",
   "org": "Freelance",
   "dates": "2024 – present",
   "facts": {
    "0": "Designed and delivered custom Flutter mobile applications and web dashboards end to end for international clients, taking features from initial concept through store deployment.",
    "1": "Developed RESTful backend APIs with Python (FastAPI) and Java (Spring Boot), integrating relational databases and third-party authentication services.",
    "2": "Set up deployment workflows using Docker containers and cloud infrastructure, ensuring reproducible environments and basic CI automation.",
    "3": "Collaborated directly with non-technical stakeholders to scope product requirements, manage release milestones and handle post-launch maintenance."
   },
   "tags": [
    "Flutter",
    "Dart",
    "Python",
    "FastAPI",
    "Java",
    "Spring Boot",
    "PostgreSQL",
    "Docker",
    "Git"
   ]
  },
  {
   "id": 7,
   "title": "Mobile Developer",
   "org": "E-Taalim",
   "dates": "2023 – 2024",
   "facts": {
    "0": "Built cross-platform mobile features in Flutter/Dart, implementing state management, offline storage and responsive UI components for thousands of daily learners.",
    "1": "Integrated real-time messaging, push notifications and audio streaming capabilities using Firebase Cloud Messaging and WebSocket connections.",
    "2": "Optimized application rendering performance and startup latency, reducing memory footprint across entry-level Android devices.",
    "3": "Worked closely with UI/UX designers and backend engineers in an Agile sprint cadence, contributing to code reviews and regression test coverage."
   },
   "tags": [
    "Flutter",
    "Dart",
    "Firebase",
    "REST APIs",
    "State Management",
    "Git",
    "Agile"
   ]
  },
  {
   "id": 8,
   "title": "Mobile Developer",
   "org": "Cynoia",
   "dates": "2022 – 2023",
   "facts": {
    "0": "Developed and maintained core modules of the Cynoia cross-platform mobile app using Flutter, including real-time chat, channel navigation and file previewing.",
    "1": "Implemented local SQLite caching and optimistic UI updates, maintaining consistent offline-first state during intermittent network conditions.",
    "2": "Refactored legacy navigation and state handling logic, resolving memory leaks and decreasing crash-free session rates below target thresholds.",
    "3": "Participated in automated build and deployment pipelines targeting Google Play Console and Apple App Store TestFlight distributions.",
   },
   "tags": [
    "Flutter",
    "Dart",
    "SQLite",
    "WebSockets",
    "Push Notifications",
    "CI/CD",
    "Git"
   ]
  },
  {
   "id": 9,
   "title": "End of Studies Project Intern",
   "org": "Cynapsys by Gfi / Inetum",
   "dates": "2021",
   "facts": {
    "0": "Built an internal reporting and notification mobile interface in Flutter connected to backend telemetry services for operational monitoring.",
    "1": "Implemented event ingestion adapters and data visualization widgets displaying real-time metrics, alerts and historical incident logs.",
    "2": "Co-authored technical documentation, architecture blueprints and user acceptance test suites as part of the formal graduation defense."
   },
   "tags": [
    "Flutter",
    "Dart",
    "REST APIs",
    "Data Visualization",
    "Git"
   ]
  }
 ],
 "projects": [
  {
   "id": 13,
   "title": "Cross-Platform Enterprise Field Service App",
   "org": null,
   "dates": "2023",
   "facts": {
    "0": "Engineered an offline-first mobile application in Flutter using Drift/SQLite for local persistence and background queue sync upon reconnection.",
    "1": "Designed modular architecture separating presentation, domain business rules and data repositories with automated BLoC state management.",
    "2": "Integrated camera scanning, PDF work order generation and biometric authentication using native platform channel plugins.",
    "3": "Published internal releases via Fastlane and GitHub Actions targeting Android and iOS staging environments."
   },
   "tags": [
    "Flutter",
    "Dart",
    "Drift",
    "SQLite",
    "BLoC",
    "Fastlane",
    "GitHub Actions",
    "Native Channels"
   ]
  }
 ],
 "skill_groups": [
  {
   "id": 15,
   "category": "Mobile Development",
   "skills": [
    "Flutter",
    "Dart",
    "Android (Java/Kotlin)",
    "iOS (Swift)",
    "Cross-platform Architecture",
    "BLoC",
    "Provider",
    "State Management"
   ]
  },
  {
   "id": 16,
   "category": "Backend Engineering & APIs",
   "skills": [
    "Python",
    "FastAPI",
    "Java",
    "Spring Boot",
    "RESTful APIs",
    "WebSockets",
    "Microservices",
    "SQLAlchemy"
   ]
  },
  {
   "id": 17,
   "category": "Databases & Storage",
   "skills": [
    "PostgreSQL",
    "MySQL",
    "SQLite",
    "MongoDB",
    "Redis",
    "DuckDB",
    "Qdrant"
   ]
  },
  {
   "id": 18,
   "category": "Cloud, DevOps & Tools",
   "skills": [
    "Docker",
    "Docker Compose",
    "Linux",
    "Git",
    "GitHub Actions",
    "CI/CD",
    "AWS (S3, EC2)",
    "Bash"
   ]
  },
  {
   "id": 19,
   "category": "Machine Learning & AI",
   "skills": [
    "LLMs",
    "LangChain",
    "Sentence Transformers",
    "Vector Databases",
    "Semantic Search",
    "Prompt Engineering",
    "Pandas",
    "NumPy"
   ]
  }
 ],
 "certifications": [
  {
   "id": 1,
   "name": "Data Engineer",
   "issuer": "DataCamp"
  },
  {
   "id": 2,
   "name": "Data Analyst with Python",
   "issuer": "DataCamp"
  }
 ],
 "education": [
  {
   "id": 4,
   "degree": "Master's Degree in Software Engineering",
   "school": "Higher Institute of Applied Sciences and Technology of Sousse"
  }
 ],
 "volunteering": []
}"""

BANNED_PHRASES = [
    "hands-on experience",
    "well suited",
    "strong foundation",
    "real-world applications",
    "production-ready",
    "brings experience",
    "passionate",
    "proven track record",
    "leveraging"
]

def analyze_cv_output(parsed: Dict[str, Any]) -> Dict[str, Any]:
    summary = parsed.get("summary", "")
    words = summary.split()
    word_count = len(words)
    
    # Check banned phrases
    banned_found = []
    summary_lower = summary.lower()
    for bp in BANNED_PHRASES:
        if bp in summary_lower:
            banned_found.append(bp)
            
    # Check roles count and bullet counts
    roles = parsed.get("roles", [])
    roles_summary = {}
    for r in roles:
        rid = str(r.get("id"))
        b_count = len(r.get("bullets", []))
        roles_summary[rid] = b_count
        for b in r.get("bullets", []):
            b_text = b.get("text", "") if isinstance(b, dict) else str(b)
            for bp in BANNED_PHRASES:
                if bp in b_text.lower() and bp not in banned_found:
                    banned_found.append(bp)

    projects = parsed.get("projects", [])
    projects_summary = {str(p.get("id")): len(p.get("bullets", [])) for p in projects}

    skills = parsed.get("skills", [])
    skills_count = len(skills)

    return {
        "word_count": word_count,
        "banned_found": banned_found,
        "roles_summary": roles_summary,
        "projects_summary": projects_summary,
        "skills_groups_count": skills_count,
        "summary_text": summary
    }

async def test_single_model(client: httpx.AsyncClient, model_name: str) -> Dict[str, Any]:
    print(f"[*] Testing CV generation on {model_name}...")
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
        "analysis": {},
        "error": None,
        "raw_response": ""
    }

    try:
        response = await client.post(
            "/chat/completions",
            json=payload,
            timeout=120.0
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
        result["analysis"] = analyze_cv_output(parsed)
        print(f"[+] {model_name} finished in {result['duration_sec']}s (Words in summary: {result['analysis']['word_count']}, Roles: {len(result['analysis']['roles_summary'])})")

    except json.JSONDecodeError as e:
        result["error"] = f"Invalid JSON generated: {str(e)}"
        result["status"] = "PARTIAL_JSON_ERROR"
        print(f"[!] {model_name} returned non-JSON response in {result['duration_sec']}s")
    except Exception as e:
        result["duration_sec"] = round(time.perf_counter() - start_time, 2)
        result["error"] = str(e)
        print(f"[-] {model_name} failed: {str(e)}")

    return result

def generate_report(results: List[Dict[str, Any]], filename: str = "cv_benchmark_report.md"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = [
        "# APInex Free-Tier Models CV Generation Benchmark Report",
        f"**Generated at:** {now}",
        f"**Total models tested:** {len(results)} (excluding `free/jev-1.13`)",
        "",
        "## 1. Summary Comparison",
        "",
        "| Model | Status | Latency (s) | Prompt Tokens | Output Tokens | Total Tokens | Summary Words | Banned Words Found | JSON Valid |",
        "|---|---|---:|---:|---:|---:|---:|:---:|:---:|",
    ]

    for r in results:
        status_badge = "OK" if r["status"] == "SUCCESS" else "FAIL"
        json_badge = "Yes" if r["json_valid"] else "No"
        analysis = r.get("analysis", {})
        words = str(analysis.get("word_count", "-"))
        banned = ", ".join(analysis.get("banned_found", [])) if analysis.get("banned_found") else "None"
        
        lines.append(
            f"| `{r['model']}` | **{status_badge}** | {r['duration_sec']}s | "
            f"{r['prompt_tokens']} | {r['completion_tokens']} | {r['total_tokens']} | "
            f"{words} | {banned} | {json_badge} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Structural & Layout Adherence",
        "",
        "| Model | Roles Extracted (Bullets per ID) | Projects Extracted | Skill Groups |",
        "|---|---|---|---|",
    ])

    for r in results:
        if r["status"] == "SUCCESS":
            analysis = r.get("analysis", {})
            roles_str = ", ".join([f"Role {k}: {v}b" for k, v in analysis.get("roles_summary", {}).items()])
            proj_str = ", ".join([f"Proj {k}: {v}b" for k, v in analysis.get("projects_summary", {}).items()])
            skills_count = f"{analysis.get('skills_groups_count', 0)} groups"
            lines.append(f"| `{r['model']}` | {roles_str} | {proj_str} | {skills_count} |")
        else:
            lines.append(f"| `{r['model']}` | - | - | - |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Generated Summaries Review",
        ""
    ])

    for r in results:
        lines.append(f"### Model: `{r['model']}`")
        if r["status"] == "SUCCESS":
            analysis = r.get("analysis", {})
            lines.append(f"> \"{analysis.get('summary_text', '')}\"")
            lines.append(f"- **Word count**: {analysis.get('word_count')} words (Target: ~45 words)")
            lines.append(f"- **Banned words check**: {analysis.get('banned_found') or 'Clean'}")
        else:
            lines.append(f"- **Failed with error**: `{r['error']}`")
        lines.append("\n---\n")

    lines.extend([
        "",
        "## 4. Full Raw Model Responses",
        ""
    ])

    for r in results:
        lines.append(f"### Raw Output: `{r['model']}`")
        if r["raw_response"]:
            lines.append("```json" if r["json_valid"] else "```text")
            lines.append(r["raw_response"])
            lines.append("```")
        lines.append("\n---\n")

    report_content = "\n".join(lines)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print(f"\n[✓] CV Benchmark finished! Full report written to: {filename}")

async def main():
    print("=" * 60)
    print(" APInex Free Tier Model Benchmark for CV Generation")
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
            await asyncio.sleep(1.0)

    generate_report(results)

if __name__ == "__main__":
    asyncio.run(main())
