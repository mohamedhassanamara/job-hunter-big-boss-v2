"""The master document import: verbatim text, dates as written, history, archive, idempotence."""

from datetime import date

from sqlmodel import Session, select

from app.db import engine
from app.models import ExperienceHistory, ExperienceItem
from app.services import experience_write, master_import

DOC = """# Someone — Master Document[cite: 1]

## Contact Information
- **Email:** x@example.com[cite: 1]

## Target Profile Summaries
- **Focus:** Over 2 years of everything[cite: 1]

## Education
- **Some University** — Paris, France[cite: 1]
  - *Engineering Degree* | Sep 2020 – June 2025[cite: 1]
  - **Core Coursework:** Algorithms, Databases[cite: 1]
- **Baccalauréat** | 2020[cite: 1]
  - **Score:** 16/20[cite: 1]

## Technical Skills (ATS-Optimized Inventory)
- **Languages:** Python, SQL[cite: 1]
- **AI:** LLMs (Mistral 7B, Ollama), RAG[cite: 1]

## Professional Experience
### Acme — Software Engineer
*Paris, France | Sep 2025 – Present*[cite: 1]

- Built a thing in Spring Boot, cutting latency by 40%[cite: 1].
- Wrote tests with Mockito[cite: 1].

## Technical Projects
### Lakehouse
*Python, dbt, Airflow*[cite: 1]

- Ingested 140K+ records[cite: 1].
- Designed a star schema[cite: 1].

## Volunteering & Leadership Experience
- **Club — Instructor (2022 – Present):** Taught Flutter[cite: 1].
- **Branch — Webmaster (07/2023 – 05/2024):** Managed the site[cite: 1].

## Certifications
- **Data Engineer** — DataCamp *(ID: ABC123)*[cite: 1]

## Languages
"""


def test_parse_is_verbatim_apart_from_citation_markers() -> None:
    items = {(i["kind"], i["key"]): i for i in master_import.parse(DOC)}
    job = items[("job", "Acme")]
    assert job["bullets"] == ["Built a thing in Spring Boot, cutting latency by 40%.",
                              "Wrote tests with Mockito."]
    assert job["date_label"] == "Sep 2025 – Present" and job["start_date"] == date(2025, 9, 1)
    assert job["end_date"] is None and job["location"] == "Paris, France"
    edu = items[("education", "Some University")]
    assert edu["date_label"] == "Sep 2020 – June 2025" and edu["end_date"] == date(2025, 6, 30)
    assert edu["bullets"] == ["Core Coursework: Algorithms, Databases"]
    bac = items[("education", "Baccalauréat")]
    assert bac["org"] is None and bac["date_label"] == "2020" and bac["start_date"] is None
    assert items[("project", "Lakehouse")]["tags"] == ["Python", "dbt", "Airflow"]
    assert items[("skill", "AI")]["tags"] == ["LLMs (Mistral 7B, Ollama)", "RAG"]
    assert items[("volunteering", "Branch")]["date_label"] == "07/2023 – 05/2024"
    assert items[("certification", "DataCamp")]["credential_id"] == "ABC123"
    assert not any("Contact" in i["key"] or "Focus" in str(i) for i in items.values())
    assert "[cite" not in str(items)


def test_apply_replaces_archives_and_is_idempotent(seeded: None) -> None:
    items = master_import.parse(DOC)
    with Session(engine) as s:
        old_job = s.exec(select(ExperienceItem).where(ExperienceItem.kind == "job")).first()
        others = [i.id for i in s.exec(select(ExperienceItem)).all()
                  if i.kind in ("job", "project", "education", "certification", "volunteering",
                                "skill") and i.id != old_job.id]
        old_bullets, old_id = list(old_job.bullets), old_job.id
        mapping = {"match": {"job|Acme": old_id}}
        counts = master_import.apply(s, items, mapping)
        s.commit()
        assert counts["updated"] >= 1 and counts["updated"] + counts["created"] == len(items)
        assert counts["archived"] >= len(others) - 2  # same title+org entries are kept
        s.refresh(old_job)
        assert old_job.bullets[0].startswith("Built a thing") and old_job.summary is None
        assert old_job.date_label == "Sep 2025 – Present" and old_job.is_active
        hist = experience_write.history(s, old_id)
        assert hist[0].source == "master_import" and hist[0].before["bullets"] == old_bullets
        archived = s.get(ExperienceItem, others[0])
        assert archived.is_active is False and archived.bullets  # kept, not deleted
        n = len(s.exec(select(ExperienceHistory)).all())
        again = master_import.apply(s, items, mapping)
        s.commit()
        assert again["updated"] == 0 and again["created"] == 0 and again["archived"] == 0
        assert len(s.exec(select(ExperienceHistory)).all()) == n  # nothing new logged
