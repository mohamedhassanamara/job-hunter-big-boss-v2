# Prompt v5 verification against Claude's blind ratings (2026-10-20)

Read-only: **no database writes**. Prompt `fit_score/v5` (registered) through the app's own path (`scoring.render`, 15,000-character limit, `fit.build_record` with the experience text), `gemini-3.5-flash-lite`, no thinking, native JSON schema, temperature 0, current experience pool. Reference: Claude's saved blind ratings in `docs/reports/raw/judgment-test/claude.json` (for #765, the rating with the full listing). Each job was run 3 times to show run-to-run noise; run 1 is the primary comparison. Raw: `docs/reports/raw/v5-verification/`.

**Caveat on the reference:** Claude's ratings were made with the draft v5 prompt, which has no `core_requirements` and no cap; the registered v5 adds both. Claude's 61 and 64 on #3923 and #1913 are therefore not capped, while v5's cap is 60.

## Result

| Job | Claude | v5 run 1 | run 2 | run 3 | Difference (run 1) |
|---|---|---|---|---|---|
| #765 AI Engineer, Nerdware (German C1, 6,908-char listing) | 35 | **35** | 35 | 35 | +0 |
| #2418 Senior Fullstack Mobile Healthcare, Snke | 67 | **62** | 66 | 62 | -5 |
| #1914 Location Data Engineer, Amo | 90 | **91** | 94 | 91 | +1 |
| #3923 Python Engineer, Web Crawling, Certivity | 61 | **60** | 60 | 60 | -1 |
| #1913 Backend Engineer (Go), Prelude | 64 | **60** | 60 | 60 | -4 |

**Mean absolute difference from Claude: 2.2 (run 1)**, 2.0 and 2.2 (runs 2 and 3); 2.1 using each job's 3-run mean. For comparison, in the judgment test (draft v5, no cap, #765 truncated) the best lite configuration was 5.0 (4.6 with the full listing).

## Do #1913, #3923 and #765 land where Claude put them?

| Job | Claude | v5 (3 runs) | Why |
|---|---|---|---|
| #765 German C1 | 35 | 35 / 35 / 35 | The C1 line is now in the prompt (it was cut before). All 3 runs raise a hard `language_required` flag on it, which caps at 35. |
| #3923 Web Crawling | 61 | 60 / 60 / 60 | Core requirement `Web Scraping at Scale` is missing, its quote is verified, so the score is capped at 60 in all 3 runs (the weighted score alone was about 73-88 in the judgment test). |
| #1913 Go Backend | 64 | 60 / 60 / 60 | Core requirement `Go` is missing and verified, capped at 60 in all 3 runs (82 on one config before). |

All three land where Claude put them, within 4 points, and the two capped jobs sit exactly at the cap, 1 and 4 points under Claude's uncapped 61 and 64.

## Core requirements the model raised

| Job | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| #765 AI Engineer | LLM / Generative AI (covered); Cloud Development (missing, counts) | LLM Applications (covered); Cloud Development (AWS/Azure) (missing, counts) | LLM & Generative AI Applications (covered); Cloud Development (AWS/Azure) (missing, counts); German Language C1 (missing, counts) |
| #2418 Senior Fullstack Mobile Healthcare | Mobile development (covered); Backend development (covered) | Mobile development (covered); Backend and frontend spanning experience (covered) | Mobile development (covered); Backend services (covered) |
| #1914 Location Data Engineer | SQL and large-scale datasets (covered); Modern data technologies (DBT, DuckDB, Spark) (covered); Data pipelines (covered) | SQL and Large Datasets (covered); Modern Data Technologies (covered); Data Pipelines (covered) | SQL and large datasets (covered); Modern data technologies (DBT, DuckDB, Spark) (covered) |
| #3923 Python Engineer | Web Scraping at Scale (missing, counts); Python (covered) | Python (covered); Web scraping at scale (missing, counts) | Python (covered); Web Scraping at Scale (missing, counts) |
| #1913 Backend Engineer (Go) | Go (missing, counts) | Go (missing, counts); Distributed Systems (covered) | Go (missing, counts) |

No false cap on the two jobs Claude rates well (#1914: 91, 94, 91; #2418: 62, 66, 62: no missing core requirement raised).

## Sub-scores, run 1

| Job | role_match | skills_match | seniority_fit | location_eligibility | language_requirements |
|---|---|---|---|---|---|
| #765 AI Engineer Claude | 9 | 5 | 3 | 8 | 0 |
| #765 AI Engineer v5 | 10 | 4 | 2 | 8 | 0 |
| #2418 Senior Fullstack Mobile Healthcare Claude | 6 | 6 | 6 | 8 | 10 |
| #2418 Senior Fullstack Mobile Healthcare v5 | 5 | 6 | 5 | 8 | 10 |
| #1914 Location Data Engineer Claude | 10 | 7 | 9 | 10 | 10 |
| #1914 Location Data Engineer v5 | 10 | 7 | 10 | 10 | 10 |
| #3923 Python Engineer Claude | 4 | 5 | 8 | 8 | 10 |
| #3923 Python Engineer v5 | 10 | 7 | 10 | 8 | 10 |
| #1913 Backend Engineer (Go) Claude | 8 | 3 | 6 | 8 | 10 |
| #1913 Backend Engineer (Go) v5 | 10 | 2 | 10 | 8 | 10 |

## Cost and reliability

All 15 answers were valid JSON as returned, with 0 thinking tokens; 3 retries; time per job 30 s median (max 99 s); input 5456 tokens and output 655 tokens per job on average.

## Notes and risks

- **Five jobs, three runs each.** Good enough to show the mechanism works and is stable (the scores of a job differ by at most 4 points across runs); not enough to show how often the cap fires wrongly.
- **Generic requirements can over-trigger.** On #765 the model also listed `Cloud Development (AWS/Azure)` as a missing core requirement (counted; your pool has Terraform and LocalStack S3 but no AWS or Azure in production), and in one run `German Language C1`. Here the hard flag decides anyway, but on a job without a hard flag a generic item like cloud could cap at 60. This is the thing to watch in the first day's rescore (the report in step 7 counts capped jobs and lists the requirements).
- **#2418** lands at 62-66 against Claude's 67, a little low in two of three runs; no cap involved.
- The cap and the check are in code and tested; `missing_core_cap` is a setting (Settings → Scoring, 100 = off).
