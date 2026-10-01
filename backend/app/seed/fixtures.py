"""Mock data for the phase 0 UI shell. All companies and people are fictional."""

from dataclasses import dataclass, field

from app.services.contacts import (
    DEFAULT_LARGE_ORDER,
    DEFAULT_ROLE_RANKING,
    DEFAULT_SMALL_ORDER,
    DEFAULT_SMALL_THRESHOLD,
)
from app.services.outreach_check import DEFAULT_BANNED

# --------------------------------------------------------------------------------------------
# Companies: (name, domain, city/country hint). Contacts are generated per company below.
# --------------------------------------------------------------------------------------------
COMPANIES: dict[str, dict] = {
    "nimbus": {"name": "Nimbus Analytics S.L.", "domain": "nimbus-analytics.example"},
    "brume": {"name": "Brume AI", "domain": "brume.example"},
    "farol": {"name": "Farol Payments", "domain": "farolpay.example"},
    "veloce": {"name": "Veloce Logistics S.p.A.", "domain": "veloce.example"},
    "helio": {"name": "Helio Satellite", "domain": "heliosat.example"},
    "orbis": {"name": "Orbis Assurances", "domain": "orbis.example"},
    "quartzo": {"name": "Quartzo Data", "domain": "quartzo.example"},
    "sierra": {"name": "Sierra Grid", "domain": "sierragrid.example"},
    "lumiere": {"name": "Lumière Énergie SAS", "domain": "lumiere-energie.example"},
    "alameda": {"name": "Alameda Health", "domain": "alamedahealth.example"},
    "pixelfarm": {"name": "Pixelfarm Games", "domain": "pixelfarm.example"},
    "cantiere": {"name": "Cantiere Robotics", "domain": "cantiere.example"},
    "kelpie": {"name": "Kelpie", "domain": "kelpie.example"},
    "marea": {"name": "Marea Travel", "domain": "mareatravel.example"},
    "tessera": {"name": "Tessera Cloud", "domain": "tessera.example"},
    "ondina": {"name": "Ondina Media", "domain": "ondina.example"},
    "tramontana": {"name": "Grupo Tramontana", "domain": "tramontana.example"},
    "vertice": {"name": "Vértice Bank", "domain": "verticebank.example"},
}

# (company_key, [(full_name, title, source)])
CONTACTS: dict[str, list[tuple[str, str, str]]] = {
    "nimbus": [
        ("Lucía Ferrer", "Head of Data", "apollo_dump"),
        ("Javier Ortega", "Engineering Manager, Data Platform", "apollo_dump"),
        ("Marta Soler", "Talent Acquisition Lead", "apollo_dump"),
        ("Pablo Rius", "CTO", "apollo_dump"),
        ("Irene Campos", "Senior Recruiter", "apollo_dump"),
    ],
    "quartzo": [
        ("Inês Carvalho", "VP Engineering", "apollo_dump"),
        ("Tiago Moura", "ML Lead", "apollo_dump"),
        ("Rita Paiva", "People Partner", "apollo_dump"),
        ("Duarte Neves", "Staff Engineer", "apollo_dump"),
    ],
    "farol": [
        ("Beatriz Lopes", "Analytics Manager", "apollo_dump"),
        ("Miguel Rocha", "Director of Data", "apollo_dump"),
        ("Sofia Antunes", "Tech Recruiter", "apollo_dump"),
    ],
    "sierra": [
        ("Álvaro Méndez", "Data Engineering Lead", "apollo_dump"),
        ("Nuria Blanco", "HR Business Partner", "apollo_dump"),
        ("Carlos Vidal", "Head of Platform", "apollo_dump"),
        ("Elena Prats", "Recruiter", "apollo_dump"),
    ],
    "lumiere": [
        ("Camille Roux", "MLOps Lead", "found"),
        ("Hugo Lambert", "Head of Data & AI", "found"),
    ],
    "pixelfarm": [
        ("Jonas Weber", "Head of AI", "apollo_dump"),
        ("Clara Nilsson", "Engineering Director", "apollo_dump"),
        ("Aoife Byrne", "Talent Partner", "apollo_dump"),
        ("Matteo Galli", "Lead ML Engineer", "apollo_dump"),
    ],
    "kelpie": [
        ("Fiona MacLeod", "VP Data", "apollo_dump"),
        ("Arjun Mehta", "Staff Data Engineer", "apollo_dump"),
        ("Lena Hoffmann", "Head of Talent", "apollo_dump"),
        ("Owen Price", "CTO", "apollo_dump"),
        ("Sara Lindqvist", "Engineering Manager", "apollo_dump"),
    ],
    "marea": [
        ("Andrea Gil", "Head of Data Engineering", "apollo_dump"),
        ("Rubén Navarro", "Data Engineering Manager", "apollo_dump"),
        ("Laura Serra", "Talent Acquisition", "apollo_dump"),
        ("Óscar Pujol", "CTO", "apollo_dump"),
    ],
    "tessera": [
        ("Nadia Petrova", "Director of Applied AI", "found"),
        ("Tom Becker", "Platform Lead", "apollo_dump"),
        ("Yara Haddad", "Recruiting Manager", "apollo_dump"),
    ],
    "ondina": [
        ("Giulia Rinaldi", "Head of Data", "apollo_dump"),
        ("Paolo Conti", "Data Architect", "apollo_dump"),
        ("Chiara Fontana", "HR Manager", "apollo_dump"),
        ("Stefano Marino", "CTO", "apollo_dump"),
    ],
    "tramontana": [
        ("Jordi Puig", "Chief Data Officer", "apollo_dump"),
        ("Montse Riera", "BI Manager", "apollo_dump"),
        ("Xavier Font", "Talent Lead", "apollo_dump"),
    ],
    "vertice": [
        ("Ana Beltrán", "Head of ML", "apollo_dump"),
        ("Diego Herrera", "Data Engineering Manager", "apollo_dump"),
        ("Paula Moreno", "Recruiter", "apollo_dump"),
    ],
}


@dataclass
class JobFx:
    key: str
    source: str
    title: str
    company: str
    location: str
    country: str | None
    remote: str
    posted_days_ago: float
    score: int
    strengths: list[str]
    gaps: list[str]
    summary: str
    mission: str
    stack: list[str]
    stage: str = "new"
    route: str = "undecided"
    tier: str = "none"
    contact: int | None = None  # index into CONTACTS[company]
    salary: str | None = None
    close_reason: str | None = None
    duplicate_of: str | None = None
    days_in_stage: float = 0.5
    notes: str = ""
    extra: dict = field(default_factory=dict)


JOBS: list[JobFx] = [
    JobFx(
        key="nimbus-sde", source="adzuna", title="Senior Data Engineer",
        company="nimbus", location="Madrid, Spain", country="ES", remote="hybrid",
        posted_days_ago=0.4, score=91, salary="€60k–72k",
        strengths=["5+ years building Spark and dbt pipelines", "Airflow orchestration at scale",
                   "Data modelling for analytics teams"],
        gaps=["Listing asks for Kafka Streams; experience is with Flink"],
        summary="Very strong match: core stack and seniority line up.",
        mission="builds the analytics layer that 400+ retailers use to price and stock products",
        stack=["Spark", "dbt", "Airflow", "Snowflake", "Kafka", "AWS"],
        tier="imported", contact=0,
    ),
    JobFx(
        key="brume-llm", source="wttj", title="AI Engineer, LLM Platform",
        company="brume", location="Paris, France", country="FR", remote="hybrid",
        posted_days_ago=1.2, score=88, salary="€65k–80k",
        strengths=["Built a production RAG service", "Evaluation harnesses for LLM features",
                   "Python + FastAPI services"],
        gaps=["French is a plus for client meetings"],
        summary="Strong match on LLM platform work; language is a soft gap.",
        mission="gives legal teams an AI assistant that drafts and reviews contracts",
        stack=["Python", "LangGraph", "pgvector", "FastAPI", "Kubernetes", "GCP"],
    ),
    JobFx(
        key="farol-ae", source="remotive", title="Analytics Engineer",
        company="farol", location="Porto, Portugal (Remote)", country="PT", remote="remote",
        posted_days_ago=2.0, score=76,
        strengths=["dbt expert-level modelling", "Stakeholder-facing analytics work"],
        gaps=["Looker specifically; experience is with Metabase and Superset",
              "Payments domain is new"],
        summary="Good match; BI tooling differs.",
        mission="processes card payments for 30k small merchants across Iberia",
        stack=["dbt", "BigQuery", "Looker", "Fivetran", "Python"],
        tier="imported", contact=0,
    ),
    JobFx(
        key="veloce-mle", source="adzuna", title="Machine Learning Engineer",
        company="veloce", location="Milan, Italy", country="IT", remote="onsite",
        posted_days_ago=3.1, score=58,
        strengths=["Solid Python and data pipelines for features"],
        gaps=["Heavy on computer vision", "Onsite 5 days in Milan", "Italian required"],
        summary="Fair: ML infra overlaps, but CV focus and onsite are gaps.",
        mission="optimizes last-mile delivery routes for 2M parcels a day",
        stack=["PyTorch", "OpenCV", "Kubeflow", "Azure"],
    ),
    JobFx(
        key="helio-dpe", source="remotive", title="Data Platform Engineer",
        company="helio", location="Remote (EU)", country=None, remote="remote",
        posted_days_ago=1.8, score=84,
        strengths=["Platform ownership: CI/CD, IaC, observability", "Terraform on AWS",
                   "Streaming ingestion"],
        gaps=["Satellite telemetry domain"],
        summary="Strong platform match, fully remote.",
        mission="turns satellite telemetry into insights for climate researchers",
        stack=["Terraform", "AWS", "Kafka", "Iceberg", "Trino", "Python"],
        stage="shortlisted", tier="to_get", days_in_stage=1.0,
    ),
    JobFx(
        key="nimbus-sde-dup", source="arbeitnow", title="Senior Data Engineer (m/f/d)",
        company="nimbus", location="Madrid, Spain", country="ES", remote="hybrid",
        posted_days_ago=0.9, score=91,
        strengths=["5+ years building Spark and dbt pipelines"], gaps=[],
        summary="Duplicate of the Adzuna listing.",
        mission="builds the analytics layer that 400+ retailers use to price and stock products",
        stack=["Spark", "dbt", "Airflow", "Snowflake"],
        duplicate_of="nimbus-sde", tier="imported", contact=0,
    ),
    JobFx(
        key="orbis-bi", source="wttj", title="Junior BI Developer",
        company="orbis", location="Paris, France", country="FR", remote="onsite",
        posted_days_ago=4.5, score=38,
        strengths=["SQL fundamentals"],
        gaps=["Junior role, well below current level", "Power BI / SSRS stack",
              "French fluency required"],
        summary="Weak: seniority and stack mismatch.",
        mission="modernizes reporting for a 120-year-old insurance group",
        stack=["Power BI", "SQL Server", "SSIS"],
    ),
    JobFx(
        key="quartzo-llm", source="arbeitnow", title="LLM Engineer",
        company="quartzo", location="Lisbon, Portugal", country="PT", remote="remote",
        posted_days_ago=5.0, score=86, salary="€55k–70k",
        strengths=["Fine-tuning and evaluation pipelines", "Retrieval and reranking in production",
                   "Strong Python engineering"],
        gaps=["Rust nice-to-have"],
        summary="Strong match on applied LLM engineering.",
        mission="builds document-understanding APIs for European banks",
        stack=["Python", "vLLM", "Ray", "Postgres", "AWS"],
        stage="shortlisted", route="cold_email", tier="imported", contact=1,
        days_in_stage=0.8,
    ),
    JobFx(
        key="sierra-gcp", source="adzuna", title="Data Engineer (GCP)",
        company="sierra", location="Madrid, Spain", country="ES", remote="hybrid",
        posted_days_ago=6.0, score=72,
        strengths=["BigQuery and Dataflow pipelines", "Energy-market data experience"],
        gaps=["GCP Professional Data Engineer cert preferred"],
        summary="Good match; certification is a nice-to-have.",
        mission="forecasts grid demand for renewable energy producers",
        stack=["BigQuery", "Dataflow", "Composer", "Terraform", "Python"],
        stage="cv_ready", route="cold_email", tier="imported", contact=0, days_in_stage=0.6,
    ),
    JobFx(
        key="lumiere-mlops", source="wttj", title="MLOps Engineer",
        company="lumiere", location="Lyon, France", country="FR", remote="hybrid",
        posted_days_ago=7.0, score=69,
        strengths=["Model serving and monitoring", "Kubernetes + Argo"],
        gaps=["MLflow at scale", "French for internal docs"],
        summary="Good: infra match, some tooling gaps.",
        mission="predicts energy consumption for 3M households",
        stack=["MLflow", "Kubernetes", "Argo", "Python", "Azure"],
        stage="cv_ready", route="cold_email", tier="found", contact=0, days_in_stage=1.5,
    ),
    JobFx(
        key="alameda-sae", source="arbeitnow", title="Senior Analytics Engineer",
        company="alameda", location="Barcelona, Spain", country="ES", remote="hybrid",
        posted_days_ago=8.0, score=81,
        strengths=["Senior dbt modelling", "Data quality frameworks", "Healthcare data (HL7) once"],
        gaps=[],
        summary="Strong match; no contact found, so apply on the web.",
        mission="helps 200 clinics cut patient waiting times",
        stack=["dbt", "Snowflake", "Dagster", "Python"],
        stage="ready", route="web_apply", tier="none", days_in_stage=1.1,
    ),
    JobFx(
        key="pixelfarm-ai", source="remotive", title="AI Engineer",
        company="pixelfarm", location="Remote (Europe)", country=None, remote="remote",
        posted_days_ago=9.0, score=79,
        strengths=["LLM-powered product features", "Event pipelines for game telemetry"],
        gaps=["Unity experience is a plus"],
        summary="Good: AI product focus with data depth.",
        mission="uses generative AI to build living NPCs in mobile games",
        stack=["Python", "OpenAI API", "Redis", "ClickHouse", "GCP"],
        stage="ready", route="cold_email", tier="imported", contact=0, days_in_stage=0.4,
    ),
    JobFx(
        key="cantiere-de", source="adzuna", title="Data Engineer",
        company="cantiere", location="Turin, Italy", country="IT", remote="onsite",
        posted_days_ago=10.0, score=64,
        strengths=["Time-series pipelines", "Python + Spark"],
        gaps=["Onsite in Turin", "ROS/robotics data formats"],
        summary="Fair: solid data fit, location is a gap.",
        mission="builds autonomous robots for construction sites",
        stack=["Spark", "Delta Lake", "Databricks", "Python"],
        stage="ready", route="web_apply", tier="none", days_in_stage=2.2,
        extra={"good_to_know": "Candidates must already have the right to work in the EU; we are unable to sponsor visas. Fluent Italian is required for daily work on site."},
    ),
    JobFx(
        key="kelpie-staff", source="arbeitnow", title="Staff Data Engineer",
        company="kelpie", location="Remote (EU timezones)", country=None, remote="remote",
        posted_days_ago=11.0, score=83, salary="€85k–100k",
        strengths=["Technical leadership on data platforms", "Lakehouse migrations",
                   "Mentoring engineers"],
        gaps=["Staff scope: prior title was Senior"],
        summary="Strong match; a step up in scope.",
        mission="builds the carbon accounting platform used by 900 companies",
        stack=["Databricks", "Delta Lake", "dbt", "Terraform", "AWS"],
        stage="ready", route="cold_email", tier="imported", contact=0, days_in_stage=0.3,
    ),
    JobFx(
        key="marea-stream", source="adzuna", title="Data Engineer, Streaming",
        company="marea", location="Barcelona, Spain", country="ES", remote="hybrid",
        posted_days_ago=13.0, score=74,
        strengths=["Flink + Kafka streaming", "Travel search data volumes"],
        gaps=["Scala preferred"],
        summary="Good: streaming match.",
        mission="prices 5M hotel nights a day in real time",
        stack=["Flink", "Kafka", "Scala", "AWS"],
        stage="done", route="cold_email", tier="imported", contact=0, days_in_stage=9.0,
    ),
    JobFx(
        key="tessera-applied", source="wttj", title="Applied AI Engineer",
        company="tessera", location="Remote (EU)", country=None, remote="remote",
        posted_days_ago=14.0, score=87,
        strengths=["Agents + tool use in production", "Evaluation-driven development",
                   "Data platform background"],
        gaps=[],
        summary="Strong match on applied AI.",
        mission="lets platform teams query their cloud estate in plain language",
        stack=["Python", "Claude API", "Postgres", "Temporal", "AWS"],
        stage="interview", route="cold_email", tier="found", contact=0, days_in_stage=2.0,
        notes="First call with Nadia went well. Technical interview Thursday 10:00.",
    ),
    JobFx(
        key="marea-de", source="remotive", title="Data Engineer",
        company="marea", location="Barcelona, Spain", country="ES", remote="hybrid",
        posted_days_ago=0.7, score=70,
        strengths=["Same data stack as the streaming role"],
        gaps=["Already in contact with this company"],
        summary="Good match, but you already reached out to Marea Travel.",
        mission="prices 5M hotel nights a day in real time",
        stack=["Spark", "Airflow", "AWS"],
        tier="imported", contact=1,
    ),
    JobFx(
        key="veloce-bi", source="adzuna", title="BI Engineer",
        company="veloce", location="Milan, Italy", country="IT", remote="hybrid",
        posted_days_ago=20.0, score=55,
        strengths=["SQL and warehousing"], gaps=["Tableau-heavy", "Italian required"],
        summary="Fair.",
        mission="optimizes last-mile delivery routes for 2M parcels a day",
        stack=["Tableau", "Snowflake", "SQL"],
        stage="closed", route="web_apply", close_reason="rejected", days_in_stage=3.0,
    ),
    JobFx(
        key="orbis-bigdata", source="wttj", title="Big Data Engineer (Hadoop)",
        company="orbis", location="Paris, France", country="FR", remote="onsite",
        posted_days_ago=6.5, score=47,
        strengths=["Spark"], gaps=["Legacy Hadoop/Hive stack", "Onsite, French required"],
        summary="Weak: legacy stack.",
        mission="modernizes reporting for a 120-year-old insurance group",
        stack=["Hadoop", "Hive", "Spark", "Cloudera"],
        stage="closed", close_reason="dismissed", days_in_stage=1.0,
        extra={"good_to_know": "This position requires professional fluency in French. No visa sponsorship is available."},
    ),
    JobFx(
        key="brume-llm-dup", source="adzuna", title="AI Engineer - LLM Platform",
        company="brume", location="Paris, France", country="FR", remote="hybrid",
        posted_days_ago=1.0, score=88,
        strengths=["Built a production RAG service"], gaps=[],
        summary="Duplicate of the Welcome to the Jungle listing.",
        mission="gives legal teams an AI assistant that drafts and reviews contracts",
        stack=["Python", "LangGraph", "pgvector"],
        duplicate_of="brume-llm",
    ),
]

REMOTE_LINE = {
    "remote": "This is a fully remote role within European time zones.",
    "hybrid": "Hybrid: 2 days a week in the office, the rest remote.",
    "onsite": "This role is based in our office.",
}


def job_description(j: JobFx, company_name: str) -> str:
    stack = ", ".join(j.stack)
    return f"""## About {company_name}
{company_name} {j.mission}. We're a product-led team that values ownership, clear writing, and shipping small increments.

## The role
As our next {j.title}, you'll join a small team that owns the data and AI foundations behind our product. {REMOTE_LINE[j.remote]}

## What you'll do
- Design, build, and operate reliable pipelines and services using {stack}
- Partner with product and analytics to turn ambiguous questions into well-modelled data
- Improve observability, testing, and cost efficiency across the platform
- Mentor teammates and contribute to technical decisions and RFCs

## What we're looking for
- Several years of hands-on experience in a similar role
- Strong Python and SQL; comfort with {j.stack[0]} and {j.stack[1]}
- Experience running production systems end to end
- Clear communication in English

## Nice to have
- Experience with {j.stack[-1]}
- Prior work in a scale-up environment

## What we offer
Competitive salary{f" ({j.salary})" if j.salary else ""}, learning budget, flexible hours, and 25 days of holiday.{f"{chr(10)}{chr(10)}## Good to know{chr(10)}{j.extra['good_to_know']}" if j.extra.get('good_to_know') else ""}"""


# --------------------------------------------------------------------------------------------
# Master experience
# --------------------------------------------------------------------------------------------
EXPERIENCE: list[dict] = [
    {
        "kind": "job", "title": "Senior Data Engineer", "org": "Northwind Mobility",
        "location": "Madrid, Spain", "start_date": "2022-03-01", "end_date": None,
        "summary": "Tech lead for the data platform team (5 engineers).",
        "bullets": [
            "Re-modelled 140+ core pipelines in dbt, cutting warehouse spend by 35%",
            "Built a Kafka → Flink streaming layer serving real-time pricing at 20k events/s",
            "Designed a RAG service over internal docs used weekly by 2,000 employees",
            "Introduced data contracts and CI tests, reducing broken dashboards by 70%",
            "Mentored 3 engineers to mid/senior level",
        ],
        "tags": ["spark", "dbt", "airflow", "kafka", "flink", "snowflake", "aws", "llm", "rag",
                 "leadership"],
    },
    {
        "kind": "job", "title": "Data Engineer", "org": "Kappa Retail Group",
        "location": "Barcelona, Spain", "start_date": "2019-06-01", "end_date": "2022-02-28",
        "summary": "Owned ingestion and modelling for e-commerce analytics.",
        "bullets": [
            "Migrated on-prem Hadoop jobs to Spark on EMR, 4x faster nightly loads",
            "Built Airflow DAGs for 60+ sources with SLA alerting",
            "Delivered a demand-forecasting feature store used by 3 ML teams",
        ],
        "tags": ["spark", "airflow", "aws", "python", "sql", "feature-store"],
    },
    {
        "kind": "job", "title": "Junior Data Analyst", "org": "Solstice Labs",
        "location": "Lisbon, Portugal", "start_date": "2017-09-01", "end_date": "2019-05-31",
        "summary": None,
        "bullets": [
            "Automated weekly KPI reporting with Python, saving 10 hours a week",
            "Built the first Metabase dashboards for sales and ops",
        ],
        "tags": ["python", "sql", "metabase"],
    },
    {
        "kind": "project", "title": "Open-source dbt test pack", "org": "GitHub",
        "location": None, "start_date": "2023-01-01", "end_date": None,
        "summary": "Reusable dbt tests for data contracts.",
        "bullets": ["1.2k stars, used by 300+ projects", "Maintainer and release manager"],
        "tags": ["dbt", "open-source", "data-quality"],
    },
    {
        "kind": "project", "title": "LLM evaluation harness", "org": "Side project",
        "location": None, "start_date": "2024-04-01", "end_date": None,
        "summary": "Offline eval framework for RAG pipelines.",
        "bullets": [
            "Scores retrieval and answer quality across 5 model providers",
            "Runs locally with Ollama or remotely with hosted APIs",
        ],
        "tags": ["llm", "rag", "evaluation", "python", "ollama"],
    },
    {
        "kind": "project", "title": "Real-time bike availability predictor",
        "org": "Hackathon (1st place)", "location": None, "start_date": "2021-10-01",
        "end_date": "2021-10-03", "summary": None,
        "bullets": ["Streaming features + gradient boosting, served via FastAPI"],
        "tags": ["ml", "streaming", "fastapi"],
    },
    {
        "kind": "skill", "title": "Data engineering", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["spark", "dbt", "airflow", "kafka", "flink", "dagster", "iceberg", "sql"],
    },
    {
        "kind": "skill", "title": "AI / LLM engineering", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["llm", "rag", "evaluation", "langgraph", "pgvector", "ollama", "fine-tuning"],
    },
    {
        "kind": "skill", "title": "Cloud & infrastructure", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["aws", "gcp", "terraform", "kubernetes", "docker", "ci-cd"],
    },
    {
        "kind": "skill", "title": "Languages", "org": None, "location": None,
        "start_date": None, "end_date": None, "summary": None, "bullets": [],
        "tags": ["python", "sql", "typescript", "english-c2", "spanish-c1", "french-b1"],
    },
    {
        "kind": "education", "title": "MSc Data Science", "org": "Universidad Politécnica",
        "location": "Madrid, Spain", "start_date": "2015-09-01", "end_date": "2017-07-31",
        "summary": None, "bullets": ["Thesis: streaming anomaly detection"], "tags": [],
    },
    {
        "kind": "volunteering", "title": "Mentor", "org": "Women in Data Madrid",
        "location": "Madrid, Spain", "start_date": "2022-01-01", "end_date": None,
        "summary": None,
        "bullets": ["Mentor 4 career switchers a year through their first data pipeline project"],
        "tags": ["mentoring", "sql", "python"],
    },
    {
        "kind": "certification", "title": "AWS Certified Data Engineer, Associate",
        "org": "Amazon Web Services", "location": None, "start_date": "2024-02-01",
        "end_date": None, "summary": None, "bullets": [], "tags": ["aws"],
    },
]

SETTINGS: dict[str, dict] = {
    "sources": {"adzuna": True, "remotive": True, "arbeitnow": True, "wttj": True,
                "boards": True, "bayt": True},
    # After applying (Settings → Tracking): follow-up reminders and the ghosting suggestion.
    "tracking": {"followup_days": [7, 14], "ghost_after_days": 30},
    # CV (Settings → CV and Templates). track_emphasis: track name → {skill_groups, tags}.
    "cv": {"default_template": "default", "filename_pattern": "{full_name}_CV_{company}.pdf",
           "track_emphasis": {}},
    # Company job boards (Settings → Sources). Starter list: Gulf/MENA employers whose public
    # boards were verified on 2026-09-27; edit freely. ats: greenhouse|lever|ashby|workable|
    # smartrecruiters, token: the company's board id in that ATS.
    "company_boards": {
        "boards": [
            {"ats": "smartrecruiters", "token": "DeliveryHero", "company": "Delivery Hero (talabat)"},
            {"ats": "greenhouse", "token": "tamara", "company": "Tamara"},
            {"ats": "greenhouse", "token": "careem", "company": "Careem"},
            {"ats": "greenhouse", "token": "hala", "company": "Hala"},
            {"ats": "workable", "token": "bayutdubizzle", "company": "dubizzle / Bayut"},
            {"ats": "workable", "token": "salla", "company": "Salla"},
            {"ats": "workable", "token": "foodics", "company": "Foodics"},
            {"ats": "ashby", "token": "ziina", "company": "Ziina"},
            {"ats": "ashby", "token": "LeanTech", "company": "Lean Technologies"},
            {"ats": "ashby", "token": "thndr", "company": "Thndr"},
        ]
    },
    "models": {
        # Cloud first; a usage limit switches the rest of a run to the local fallback.
        "scoring": {"provider": "ollama", "model": "gemma4:31b-cloud", "fallback": "gemma4:12b",
                    "cloud_concurrency": {"min": 1, "start": 4, "max": 4},
                    "local_concurrency": 2},
        "cv": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "email": {"provider": "anthropic", "model": "claude-haiku-4-5"},
    },
    "smtp": {"address": "", "from_name": "", "interval_minutes": 15, "max_per_queue": 20},
    "schedule": {"enabled": True, "time": "07:00"},
    "lookup": {"daily_cap": 10},
    # Cold emails: signature (empty fields use Settings → Candidate), opt-out, lint rules.
    "outreach": {"signature": {"name": "", "title": "", "email": "", "phone": "",
                               "photo_path": ""},
                 "sign_off": "Best regards,",
                 "opt_out": "If this isn't relevant for you, just let me know and I won't "
                            "follow up.",
                 "banned_phrases": DEFAULT_BANNED, "max_words": 150, "language": "auto"},
    # LinkedIn (Settings → LinkedIn): note length (free account: 200), daily requests, reminders,
    # and the gap between an email and a LinkedIn request to the same person.
    "linkedin": {"note_max_chars": 200, "daily_requests": 10, "followup_days": 5, "gap_days": 3},
    # Who to write to first at a company (Settings → Contacts). Edits re-rank every contact.
    "contacts": {"role_ranking": DEFAULT_ROLE_RANKING, "small_order": DEFAULT_SMALL_ORDER,
                 "large_order": DEFAULT_LARGE_ORDER,
                 "small_company_threshold": DEFAULT_SMALL_THRESHOLD, "verify_days": 30},
    # The candidate, as the fit scorer sees them (edited in Settings → Candidate).
    "profile": {
        "full_name": "",
        "email": "",
        "phone": "",
        "total_years_override": None,  # replaces the years computed from role dates (CVs)
        "links": [],  # [{"type": "linkedin|github|portfolio|other", "label": "", "url": ""}]
        "based_in": "",
        "nationality": "",
        "work_authorization": "needs_sponsorship",  # needs_sponsorship | eu_authorized
        "languages": [],  # [{"language": "English", "level": "C1"}]
        "years_experience": 0,
        "headline": "",
    },
    # How the 0-100 fit score is computed from the LLM's 0-10 sub-scores (Settings → Scoring).
    "scoring": {
        "weights": {
            "role_match": 0.30,
            "skills_match": 0.30,
            "seniority_fit": 0.15,
            "location_eligibility": 0.15,
            "language_requirements": 0.10,
        },
        "hard_flag_cap": 35,
        "concurrency": 1,
        "good_threshold": 70,
        "maybe_threshold": 45,
    },
}

# Tour sandbox only (seed.py): a fictional candidate header for sample CVs.
SANDBOX_CANDIDATE = {
    "full_name": "Alex Sample", "based_in": "Lisbon, Portugal", "phone": "+351 000 000 000",
    "email": "alex.sample@example.com",
    "links": [{"type": "linkedin", "label": "", "url": "https://linkedin.com/in/alex-sample"},
              {"type": "github", "label": "", "url": "https://github.com/alex-sample"}],
}

SEARCH_PROFILE = {
    "name": "Data / AI Engineering, South EU + remote",
    # Tour sandbox sample only; the real workspace's roles come from Settings → Search profile.
    "roles": ["Data Engineer", "AI Engineer", "ML Engineer", "Analytics Engineer",
              "Flutter Developer", "Mobile Developer"],
    "tracks": [
        {"name": "Data/AI", "years_experience": 2.5, "roles": [
            {"title": "Data Engineer"}, {"title": "AI Engineer"}, {"title": "ML Engineer"},
            {"title": "Analytics Engineer"},
        ]},
        {"name": "Mobile", "years_experience": 2.5, "roles": [
            {"title": "Flutter Developer"}, {"title": "Mobile Developer"},
        ]},
    ],
    "keywords": ["spark", "dbt", "airflow", "kafka", "llm", "rag", "python", "aws", "gcp"],
    # Title keywords that are never relevant. No seniority words by default: every level stays
    # visible and the user decides what to pursue.
    "excluded_keywords": [
        "intern", "internship", "stage", "stagiaire", "alternance", "alternant", "apprenti",
        "apprentice", "working student", "werkstudent", "praktikum", "becario", "tirocinio",
        "estagio",
    ],
    # Defaults for a fresh workspace only; the user edits them in Settings → Search profile.
    "locations": ["FR", "ES", "IT", "PT", "DE", "BE", "AE", "QA", "BH", "KW", "JO"],
    "remote_policy": "remote_ok",
    "remote_scope": "anywhere",
    "min_fit_score": 65,
    "max_age_days": 30,
}
