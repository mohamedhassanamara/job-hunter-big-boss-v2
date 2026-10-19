"""Run the contact waterfall for one application from the command line (REAL providers and
credits, real workspace). Real generations run standalone, never through the dev server.

    .venv/bin/python scripts/run_waterfall.py <application_id> [--domain acme.com] [--requery]
"""

import argparse

from sqlmodel import Session

from app.db import engine
from app.models import Application, Company, Job
from app.providers import registry
from app.providers.contact_finders import Cost, Search
from app.services import contact_waterfall, provider_quota


class Skipped:
    def __init__(self, provider: str, unit: str):
        self.provider, self.unit = provider, unit

    def search(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
        return Search([], Cost())

    def reveal(self, key, cand):  # noqa: ANN001, ANN201
        return cand, Cost()

    def verify(self, key, email):  # noqa: ANN001, ANN201
        return "unknown", Cost()

ap = argparse.ArgumentParser()
ap.add_argument("application_id", type=int)
ap.add_argument("--domain")
ap.add_argument("--requery", action="store_true")
ap.add_argument("--skip", default="", help="providers to leave out, e.g. hunter,prospeo (tests the later steps)")
args = ap.parse_args()

with Session(engine) as s:
    app = s.get(Application, args.application_id)
    job = s.get(Job, app.job_id)
    company = s.get(Company, job.company_id)
    fs = registry.contact_finders(mock=False)
    for name in filter(None, args.skip.split(",")):
        fs[name] = Skipped(name, fs[name].unit)
    out = contact_waterfall.run(s, app, requery=args.requery, domain=args.domain, mock=False,
                                finders=fs)
    s.commit()
    print(f"# application {app.id}: {job.title} @ {company.name}")
    print(f"domain: {out.domain} ({out.domain_source}); found_by: {out.found_by}; "
          f"from_cache: {out.from_cache}")
    for st in out.steps:
        spent = f"  [{st.credits:g} credits, ${st.usd:.3f}]" if st.credits or st.usd else ""
        print(f"  - {st.provider:8} {st.status:12} {st.key_label or '':11} {st.detail}{spent}")
    print(f"TOTAL: {out.credits:g} credits, ${out.usd:.3f}")
    for c in out.candidates:
        flag = "VERIFIED" if c["verified"] else "not used"
        print(f"  * {c['full_name']} | {c['title']} | {c['email'] or '-'} | {flag} "
              f"| via {c['provider']} {c['key_label'] or ''} | {c['note']} {c['alerts'] or ''}")
    print("keys now:", [(k.label, f"{k.remaining:g} {k.unit} left", "DISABLED" if k.disabled else "")
                        for k in provider_quota.status(s)])
