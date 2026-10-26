"""Test script: End-to-end 2-pass CV generation using APInex (free/minimax-m3.1-flash)."""

import sys

if "--live" not in sys.argv:  # manual script: never run by accident (or as a test)
    sys.exit("manual_2pass_generation.py opens the REAL database (application 1622), writes a CV draft and calls the live APInex gateway. Re-run it with --live.")
sys.argv.remove("--live")
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf
from sqlmodel import Session
from app.db import engine
from app.models import Application, CVVersion
from app.providers.apinex_cv import APInexCVGenerator
from app.services import cv_service


def main() -> None:
    # Use application 1622 (Healy World - Flutter developer)
    app_id = 1622
    print(f"Starting 2-Pass CV Generation for Application {app_id}...")
    
    generator = APInexCVGenerator(model="free/minimax-m3.1-flash")
    version = cv_service.generate(engine, app_id, generator=generator)
    
    print("\nGeneration Completed:")
    print(f"  Version: v{version.version}")
    print(f"  Status: {version.status}")
    print(f"  Generator Model: {version.generator_model}")
    print(f"  Pages: {version.page_count}")
    print(f"  Fill: {version.fill} ({round((version.fill or 0) * 100, 1)}%)")
    print(f"  Fit Passes: {version.fit_passes}")
    print(f"  PDF Path: {version.pdf_path}")
    print(f"  Violations count: {len(version.violations or [])}")

    # Inspect PDF directly with PyMuPDF
    if version.pdf_path and Path(version.pdf_path).exists():
        with pymupdf.open(version.pdf_path) as doc:
            pages = doc.page_count
            first_top = min((b[1] for b in doc[0].get_text("blocks")), default=0.0)
            bottom = max((b[3] for b in doc[pages - 1].get_text("blocks")), default=0.0)
            usable = max(1.0, doc[pages - 1].rect.height - 2 * first_top)
            measured_fill = (bottom - first_top) / usable
            print(f"\nPyMuPDF Direct Verification:")
            print(f"  Physical Page Count: {pages}")
            print(f"  Physical Text Fill: {round(measured_fill * 100, 2)}%")
            assert pages == 1, f"Expected 1 page, got {pages}"
            assert measured_fill >= 0.98, f"Expected fill >= 0.98, got {measured_fill}"
            print("SUCCESS: Resulting CV is exactly 1 page and fills >= 98% of the page!")


if __name__ == "__main__":
    main()
