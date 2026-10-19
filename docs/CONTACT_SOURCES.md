# Contact sources (Phase 12)

How the **Find contact** button (Get contact step) gets a verified work email, what it costs, and
which sources are deliberately NOT used. Code: `services/contact_waterfall.py`,
`providers/contact_finders/`, `services/provider_quota.py`, `services/company_resolve.py`.

## The waterfall (one click, stops at the first verified email)

1. **Company cache.** Verified contacts already stored for the company (with their provenance) are
   returned at 0 credits. Providers already queried for the company within `providers.max_age_days`
   (default 90, Settings → Contacts) are skipped; "Ask the providers again" overrides.
2. **Hunter**: domain search (people, positions, email pattern, deliverability) at 1 credit.
3. **Prospeo** (key 1, then key 2): search by domain + role keywords (1 credit, emails masked), then
   enrich the best-ranked person with a verified email (1 credit, free when nothing is found).
4. **Apollo** (key 1, then key 2): people search is free and shows `has_email`; match reveals one
   email for about 1 credit. Free plans return only what the plan allows (the probe showed both
   endpoints working on both keys).
5. **Apify** `microworlds/leads-finder`: verified emails only, at most 5 leads, a hard $0.10 ceiling
   per run (about $0.001 start + $0.003 per lead).
6. **Local email pattern**: the company's pattern (Hunter's, or inferred from known emails at the
   domain: cached contacts, your Apollo CSV imports) builds the address of the best-ranked person,
   then a Hunter verifier call (0.5 credit) must say `valid`. Catch-all (`accept_all`), unknown and
   invalid results are shown but never used.
7. **Manual**: the Apollo extension flow in the same panel.

The first verified email ends the run; the top 3 by your ranking (Settings → Contacts, size-based
order) are shown with title, source (provider, key label, Actor) and verification status. The
"may have left" check (`contact_check.scan`) runs on every verified contact shown. A found contact
is saved on the company with `verified_at` empty: you still confirm "still there?" before drafting.

## Quotas and keys

- Per-key monthly counters (`provider_usage`, period `YYYY-MM`, so a new month starts at zero);
  Apify in dollars. A key is used only while `used + cost <= limit`.
- Before the first paid call of a click the app reads the real balances from Hunter, Prospeo and
  Apify (free account endpoints) and takes them over the local counts. Apollo has no balance endpoint
  on free plans: its limit is `providers.limits.apollo` (default 50) and its credits are counted
  locally.
- A key the provider refuses (401/403, suspended, banned) is **disabled** (`provider_key_state`),
  never retried, and flagged in Settings → Contacts and on Today; re-enable it from Settings. A key
  the provider says is out of credits is parked until the next month. A 429 skips the provider for
  this click (no retry loop). Paid calls are never retried.
- Every call is logged in `provider_call` (key label, endpoint, credits, dollars, result). Keys are
  only ever referred to by label (`prospeo#2`), never stored in the database or logged.

## Measured on the user's own keys (2026-10-19, free plans)

| Provider | Endpoint | Result | Cost |
|---|---|---|---|
| Hunter | domain-search / email-finder / email-verifier | all work; free plan limit+offset ≤ 10 | 1 / 1 / 0.5 credit (50 credits/month) |
| Prospeo ×2 | account (free), search-person, enrich-person | work on both keys | 1 / 1 credit (100 credits/month each) |
| Apollo ×2 | api_search, people/match | work on both keys; search has no emails | 0 / ~1 credit |
| Apify | microworlds/leads-finder | 3 verified leads with titles | $0.010 for 3 leads |
| Apify | boneswill/leads-generator | min 100 leads, half without email, no validation status | $0.20, rejected |
| Apify | peakydev/leads-scraper-ppe | one empty record | $0.10 start fee, rejected |
| Apify | code_crafter/leads-finder | empty result twice (needs permission approval first) | $0.02 per run, rejected |

## Company resolution (local, before any provider)

`services/company_resolve.py`: your typed domain → the company's stored domain → **People Data Labs
free company dataset** read with DuckDB (`data/pdl/companies.parquet`) → the listing / the
contacts' work-email domain (never a job board). Without the dataset only the last two work.

Getting the dataset (once, by you: PDL asks you to accept its terms and fill a short form):
1. Open https://www.peopledatalabs.com/company-dataset and submit the form (country, intended use).
2. Download the file (CSV, pipe-delimited or JSON). The October 2026 CSV was 5.4 GB, about 37 million
   rows, 24.5 million of them with a website.
3. `cd backend && .venv/bin/python scripts/pdl_to_parquet.py <path to the file>`: keeps the rows with a
   website and name, website, LinkedIn URL, size, industry and country (800 MB as zstd Parquet, about 20
   seconds). The name key is built in SQL (`company_resolve.name_key_sql`, kept equal to
   `normalize_company` by a test). A lookup takes about 20 ms.
   PDL can hold several companies with one name (Amo has 17): the one in the job's country, then the
   largest, wins, and the result says so. If it picks the wrong site, "Not the right domain?" in the Find
   contact card takes yours.
Licence: CC BY 4.0 (attribute People Data Labs). Quarterly updates.

## Excluded sources, and why

- **Scraped lead dumps** (e.g. Hugging Face lead datasets): the people never agreed to be
  contacted for this, provenance and freshness are unknown (stale or invented emails hurt the
  sender's reputation), and holding a bulk personal-data dump in a local DB creates GDPR duties
  (lawful basis, minimisation, deletion) that a single-user job search should not take on. The
  app only stores people it looked up for a specific job, with their provenance.
- **Emails harvested from GitHub commits**: commit emails are published for attribution, not for
  recruiting; harvesting them breaches GitHub's acceptable-use terms on scraping personal
  data for outreach, and they are mostly private or personal addresses (GDPR/ePrivacy).
- **Microsoft 365 and other login-endpoint email checks**: probing a company's sign-in or
  autodiscover endpoints to see whether a mailbox exists is unauthorised use of an authentication
  service (it looks like account enumeration, can trip the target's alerts and lock-outs, and is
  against the provider's terms). Verification goes through a verifier that is allowed to do it.
- Also never: scraping or automating LinkedIn (existing rule), disguising the client, or sending
  mail to an address no verifier called `valid`.

## Notes

- Apify Actors repackage third-party data (Apollo-like). They are the last paid step, cost-capped,
  and a contact they find keeps `found_by_actor` so you can see where it came from.
- Real runs go through `scripts/run_waterfall.py <application_id>` (standalone), not the dev server.
