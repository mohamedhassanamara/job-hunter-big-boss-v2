"""A clearly-marked TEST CV for the real workspace (the user asked for one to try scoring
before entering their real experience). Every item is `is_placeholder=True`, the UI warns about
it, and "Remove test data" (DELETE /api/experience/placeholders) deletes exactly these items.

    python -m app.seed.test_cv            # load (replaces previous test items)
    python -m app.seed.test_cv --remove   # remove test items only
"""

import argparse
from datetime import date

from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select

from app.models import AppSetting, ExperienceItem
from app.services.experience_write import writing

TEST_PROFILE = {
    "full_name": "Test Candidate",
    "email": "",
    "based_in": "City, Country",
    "work_authorization": "needs_sponsorship",
    "languages": [
        {"language": "Arabic", "level": "Native"},
        {"language": "French", "level": "C1"},
        {"language": "English", "level": "C1"},
        {"language": "Spanish", "level": "A2"},
    ],
    "years_experience": 2.5,
    "headline": (
        "Software engineer (~2.5 years, mobile and backend) moving into Data & AI Engineering, "
        "with hands-on data pipeline and LLM projects."
    ),
    "is_placeholder": True,
}


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


TEST_ITEMS: list[dict] = [
    {
        "kind": "job", "title": "Backend Software Engineer", "org": "Fintech startup (test)",
        "location": "City, Country", "start_date": "2024-01-01", "end_date": None,
        "summary": "Python backend for a payments product; owns the analytics data feeds.",
        "bullets": [
            "Built REST APIs in FastAPI and PostgreSQL serving ~50k daily requests",
            "Wrote Airflow DAGs moving transaction data into a BigQuery warehouse",
            "Containerised services with Docker and deployed them on AWS ECS",
            "Added data-quality checks that cut broken reports by half",
        ],
        "tags": ["python", "fastapi", "postgresql", "airflow", "bigquery", "sql", "docker",
                 "aws", "etl"],
    },
    {
        "kind": "job", "title": "Mobile Developer", "org": "Digital agency (test)",
        "location": "City, Country", "start_date": "2022-09-01", "end_date": "2023-12-31",
        "summary": "Flutter and Kotlin apps for retail and media clients.",
        "bullets": [
            "Shipped 5 Flutter apps to the App Store and Google Play",
            "Designed the analytics event schema and Firebase pipelines for client dashboards",
            "Integrated REST and GraphQL APIs; mentored one junior developer",
        ],
        "tags": ["flutter", "kotlin", "firebase", "rest-api", "graphql", "mobile"],
    },
    {
        "kind": "project", "title": "RAG assistant over internal docs", "org": "Personal project (test)",
        "location": None, "start_date": "2025-03-01", "end_date": None,
        "summary": "Question answering over PDFs with citations.",
        "bullets": [
            "Chunking + embeddings in pgvector, retrieval with reranking",
            "Runs locally with Ollama or with a hosted LLM API; FastAPI backend",
            "Evaluation set of 60 questions to compare retrieval settings",
        ],
        "tags": ["llm", "rag", "pgvector", "langchain", "ollama", "python", "evaluation"],
    },
    {
        "kind": "project", "title": "Streaming analytics pipeline", "org": "Personal project (test)",
        "location": None, "start_date": "2024-10-01", "end_date": "2025-01-31",
        "summary": "Real-time metrics from a simulated e-commerce event stream.",
        "bullets": [
            "Kafka → Spark Structured Streaming → Delta Lake, orchestrated with Airflow",
            "Dashboards in Metabase on top of the aggregated tables",
        ],
        "tags": ["kafka", "spark", "streaming", "delta-lake", "airflow"],
    },
    {
        "kind": "project", "title": "dbt analytics model on BigQuery", "org": "Personal project (test)",
        "location": None, "start_date": "2024-06-01", "end_date": "2024-08-31",
        "summary": None,
        "bullets": [
            "Staging → marts model for an open e-commerce dataset with dbt tests and docs",
        ],
        "tags": ["dbt", "bigquery", "sql", "data-modeling"],
    },
    {
        "kind": "project", "title": "Churn prediction service", "org": "Course project (test)",
        "location": None, "start_date": "2023-03-01", "end_date": "2023-05-31",
        "summary": None,
        "bullets": ["scikit-learn model tracked with MLflow, served with FastAPI"],
        "tags": ["ml", "scikit-learn", "mlflow", "fastapi"],
    },
    {
        "kind": "skill", "title": "Data engineering", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["python", "sql", "airflow", "dbt", "spark", "kafka", "postgresql", "bigquery"],
    },
    {
        "kind": "skill", "title": "AI / ML", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["llm", "rag", "langchain", "pgvector", "ollama", "scikit-learn", "mlflow"],
    },
    {
        "kind": "skill", "title": "Backend & mobile", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["fastapi", "django", "flutter", "kotlin", "rest-api"],
    },
    {
        "kind": "skill", "title": "Cloud & tooling", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["aws", "gcp", "docker", "git", "ci-cd", "linux"],
    },
    {
        "kind": "education", "title": "Engineering degree in Computer Science",
        "org": "Engineering school (test)", "location": "Country",
        "start_date": "2017-09-01", "end_date": "2022-06-30", "summary": None,
        "bullets": ["Final project: recommendation engine for a local e-commerce site"],
        "tags": [],
    },
]


def remove_test_cv(engine: Engine) -> int:
    with writing(), Session(engine) as s:
        items = s.exec(select(ExperienceItem).where(col(ExperienceItem.is_placeholder))).all()
        n = len(items)
        s.exec(delete(ExperienceItem).where(col(ExperienceItem.is_placeholder)))  # type: ignore[call-overload]
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).first()
        if row and row.value.get("is_placeholder"):
            from app.seed.fixtures import SETTINGS

            row.value = dict(SETTINGS["profile"])
            s.add(row)
        s.commit()
        return n


def load_test_cv(engine: Engine) -> int:
    remove_test_cv(engine)
    with writing(), Session(engine) as s:
        for i, item in enumerate(TEST_ITEMS):
            s.add(
                ExperienceItem(
                    **{**item, "start_date": _d(item["start_date"]), "end_date": _d(item["end_date"])},
                    position=100 + i,
                    is_placeholder=True,
                )
            )
        row = s.exec(select(AppSetting).where(AppSetting.key == "profile")).first()
        if row is None:
            row = AppSetting(key="profile", value={})
        row.value = dict(TEST_PROFILE)
        s.add(row)
        s.commit()
    return len(TEST_ITEMS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    from app.db import engine

    if args.remove:
        print(f"Removed {remove_test_cv(engine)} test experience items")
    else:
        print(f"Loaded {load_test_cv(engine)} TEST experience items (marked placeholder)")


if __name__ == "__main__":
    main()
