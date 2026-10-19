"""Turn the downloaded People Data Labs free company dataset into data/pdl/companies.parquet.

    .venv/bin/python scripts/pdl_to_parquet.py data/import/free_company_dataset.csv   (or .json)

Keeps only companies with a website: name, website, linkedin_url, size, industry, country, plus a
folded `name_key` (the same rule as services/dedupe.normalize_company, written in SQL so DuckDB
streams the 5 GB file without a Python callback) for fast exact lookups
(services/company_resolve.py). Dataset: CC BY 4.0, https://www.peopledatalabs.com/company-dataset
"""

import sys
from pathlib import Path

import duckdb

from app.config import DATA_DIR
from app.services.company_resolve import name_key_sql

src = Path(sys.argv[1]).expanduser().resolve()
out = DATA_DIR / "pdl" / "companies.parquet"
out.parent.mkdir(parents=True, exist_ok=True)
name_key = name_key_sql("name")
reader = ("read_json_auto" if src.suffix in (".json", ".jsonl", ".ndjson")
          else "read_csv(?, all_varchar=true, ignore_errors=true)")
con = duckdb.connect()
con.execute("SET preserve_insertion_order=false")
con.execute(f"""
    COPY (SELECT name, website, linkedin_url, size, industry, country, {name_key} AS name_key
          FROM {reader}
          WHERE website IS NOT NULL AND website <> '' AND name IS NOT NULL
          ORDER BY name_key) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
""", [str(src)])
n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(out)]).fetchone()[0]
print(f"{n} companies with a website -> {out} ({out.stat().st_size / 1e6:.0f} MB)")
