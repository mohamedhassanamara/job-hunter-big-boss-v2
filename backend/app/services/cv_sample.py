"""Fictional sample content used to validate and preview CV templates. Every section and header
field is filled so a template's handling of all of them is exercised. Nobody real."""

from app.services.cv_render import (
    CVCertification,
    CVDocument,
    CVEducation,
    CVLink,
    CVProfile,
    CVProject,
    CVRole,
    CVSkillGroup,
)

SAMPLE_PROFILE = CVProfile(
    full_name="Alex Sample",
    location="Lisbon, Portugal",
    phone="+351 000 000 000",
    email="alex.sample@example.com",
    links=[
        CVLink(type="linkedin", label="linkedin.com/in/alex-sample",
               url="https://linkedin.com/in/alex-sample"),
        CVLink(type="github", label="github.com/alex-sample", url="https://github.com/alex-sample"),
        CVLink(type="portfolio", label="alexsample.dev", url="https://alexsample.dev"),
    ],
)

SAMPLE_DOCUMENT = CVDocument(
    summary=(
        "Software engineer with 3 years of experience building data pipelines, APIs and mobile "
        "apps. Comfortable from ingestion to dashboards, with a focus on tests & reliability."
    ),
    skills=[
        CVSkillGroup(category="Languages", items=["Python", "SQL", "Kotlin", "TypeScript"]),
        CVSkillGroup(category="Data", items=["Airflow", "dbt", "PostgreSQL", "Spark"]),
        CVSkillGroup(category="Tools", items=["Docker", "Git", "GitHub Actions", "Linux"]),
    ],
    roles=[
        CVRole(title="Software Engineer", org="Example Analytics", location="Lisbon, Portugal",
               start="Jan 2024", end="Present", bullets=[
                   "Built batch pipelines in Airflow and dbt that load 2M rows/day into Postgres.",
                   "Cut dashboard latency by 35% by adding incremental models and indexes.",
                   "Introduced data tests (100+ checks) and on-call runbooks for the team.",
               ]),
        CVRole(title="Backend Developer", org="Sample Apps Ltd", location="Porto, Portugal",
               start="Sep 2022", end="Dec 2023", bullets=[
                   "Designed REST APIs in FastAPI serving 20k daily users with 99.9% uptime.",
                   "Migrated a monolith to 4 services with Docker & CI, halving release time.",
               ]),
    ],
    projects=[
        CVProject(name="Open Data Lakehouse", stack=["Python", "DuckDB", "dbt"],
                  label="Personal project", bullets=[
                      "Modelled 5 years of public transport data into a star schema with tests.",
                  ]),
    ],
    certifications=[
        CVCertification(name="Cloud Data Engineer", issuer="Example Academy",
                        credential_id="EX-12345", url="https://example.com/cert/EX-12345"),
    ],
    education=[
        CVEducation(school="Example University", degree="BSc Computer Science",
                    location="Lisbon, Portugal", start="Sep 2018", end="Jun 2022"),
    ],
    volunteering=[
        CVRole(title="Mentor", org="Code Club", location="Lisbon, Portugal", start="2021",
               end="Present", bullets=["Mentor 5 students a year through their first project."]),
    ],
)
