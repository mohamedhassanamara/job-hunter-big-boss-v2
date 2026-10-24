"""Verification script: Verify >= 98% page fullness and 1 page on Application 1621 and 1622."""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf
from sqlmodel import Session, select
from app.db import engine
from app.models import Application, CVVersion, Job, Company
from app.services import cv_service
from app.providers.base import CVPlan
from app.services.cv_pool import load_pool
from app.providers.apinex_cv import APInexCVGenerator


def measure_pdf(pdf_path: str) -> tuple[int, float]:
    with pymupdf.open(pdf_path) as doc:
        pages = doc.page_count
        first_top = min((b[1] for b in doc[0].get_text("blocks")), default=0.0)
        bottom = max((b[3] for b in doc[pages - 1].get_text("blocks")), default=0.0)
        usable = max(1.0, doc[pages - 1].rect.height - 2 * first_top)
        fill = (bottom - first_top) / usable
        return pages, fill


def verify_app(app_id: int, fresh_generate: bool = False) -> None:
    with Session(engine) as s:
        app = s.get(Application, app_id)
        job = s.get(Job, app.job_id) if app else None
        company = s.get(Company, job.company_id) if job else None
        comp_name = company.name if company else "Unknown"
        title = job.title if job else "Unknown"
        print(f"\n==================================================")
        print(f"Verifying Application {app_id}: {comp_name} - {title}")
        print(f"==================================================")

    if fresh_generate:
        print(f"Running fresh 2-Pass CV Generation for App {app_id}...")
        generator = APInexCVGenerator(model="free/minimax-m3.1-flash")
        version = cv_service.generate(engine, app_id, generator=generator)
    else:
        # Re-render latest version
        with Session(engine) as s:
            pool = load_pool(s)
            v = s.exec(select(CVVersion).where(CVVersion.application_id == app_id).order_by(CVVersion.version.desc())).first()
            assert v is not None, f"No CV version found for app {app_id}"
            plan = CVPlan.model_validate(v.plan["plan"])
            cv_service._save_render(s, v, plan, pool, v.template, dict(v.overrides or {}), None)
            s.add(v)
            s.commit()
            s.refresh(v)
            version = v

    print(f"Render result: Version v{version.version}, pages={version.page_count}, fill={version.fill}")
    assert version.pdf_path and Path(version.pdf_path).exists(), f"PDF not found: {version.pdf_path}"
    
    pages, fill = measure_pdf(version.pdf_path)
    print(f"PyMuPDF Physical Measurements:")
    print(f"  Physical Pages: {pages}")
    print(f"  Physical Fill:  {round(fill * 100, 2)}% ({fill:.4f})")
    print(f"  Target:         >= 98.00%")
    
    assert pages == 1, f"Expected 1 page, got {pages}"
    assert fill >= 0.98, f"Expected physical fill >= 0.98 (98%), got {fill:.4f} ({round(fill * 100, 2)}%)"
    print(f"PASSED: App {app_id} successfully achieved {round(fill * 100, 2)}% vertical page fullness on exactly 1 page!")


def main() -> None:
    # 1. Test re-rendering existing plans for 1621 and 1622
    print("PHASE 1: Verifying Existing Plan Re-renders with 98% Retargeting...")
    verify_app(1621, fresh_generate=False)
    verify_app(1622, fresh_generate=False)

    # 2. Test fresh 2-Pass generation for 1622
    print("\nPHASE 2: Verifying Fresh 2-Pass Generation for Application 1622...")
    verify_app(1622, fresh_generate=True)

    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
