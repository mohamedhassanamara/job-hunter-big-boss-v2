# Scoring benchmark follow-up: 20 jobs, 2 models (2026-10-20)

Test only: nothing was written to the database, no setting or default changed. Prompt `fit_score/v3`, current experience pool (`3812127ca20f8860`), temperature 0, our JSON schema, the same rendered prompt for both models. Raw responses: `docs/reports/raw/followup-2026-10-20/`.

**How the 20 jobs were chosen.** Full descriptions only (> 1,500 chars, not duplicates), 7 from the top of the stored scores, 6 from the middle, 7 from the bottom, mixing tracks (Data/AI, Backend, Mobile) and sources (arbeitnow, boards, remotive, linkedin). Only 175 of 5,319 jobs have a full description, 158 of them from arbeitnow, so the sample leans arbeitnow. "Stored score" is each job's latest OK score, which comes from `gemma4:31b-cloud` (older ones from `gemma4:12b`) under an older experience pool; it is a reference, not ground truth. Note that 35 is a cap value, so many stored scores tie at 35.

Gemini 3.1 Flash-Lite used the native JSON schema; Gemma 4 31B rejects it, so it got the schema in the prompt (as the app does for Ollama cloud). "Valid after app parse" additionally accepts what the app's own `strip_fence` + `_unwrap_properties` accepts.

## 1. Reliability and speed

| Metric | 3.1-flash-lite | gemma-4-31b-it |
|---|---|---|
| Jobs run | 20 | 20 |
| Valid JSON on first try | 20/20 | 0/20 |
| Valid after the app's parse | 20/20 | 20/20 |
| Retries (429/500/503) | 0 across 0 jobs | 13 across 7 jobs (500, 503) |
| Jobs with no answer | 0 | 0 |
| Time per job (s): mean / median / max | 11.6 / 10.4 / 24.7 | 82.3 / 84.5 / 113.4 |
| Tokens per job: input / output / thinking | 4715 / 701 / 0 | 5475 / 704 / 1279 |
| Evidence quotes found (job, experience or prompt metadata) | 134/139 | 120/121 |
| Evidence quotes found in the listing text alone | 114/139 | 104/121 |

Wall time includes my rate limiter's pauses; the per-job times above are the API call only.

## 2. Do the two models agree?

Jobs with a score from both models: **20/20**.

| Pair | Spearman ρ | Kendall τ-b | Mean abs. score diff |
|---|---|---|---|
| 3.1-flash-lite vs gemma-4-31b-it | 0.50 | 0.40 | 16.8 |
| 3.1-flash-lite vs stored score | 0.35 | 0.28 | 19.1 |
| gemma-4-31b-it vs stored score | 0.66 | 0.52 | 11.5 |

Spearman uses average ranks for ties; with 20 jobs and several tied scores, read ρ as approximate.

### All 20 jobs

| Job | Title (company) | Track / source | Stored | 3.1-flash-lite | gemma-4-31b-it |
|---|---|---|---|---|---|
| #1914 | Location Data engineer (Amo) | Data/AI / arbeitnow | 94 | 35 | 100 * |
| #794 | Data Analytics Engineer (They/She/He) (Delivery Hero (talabat)) | Data/AI / boards | 90 | 85 | 79 * |
| #2410 | Data Engineer (Mentor Talent Acquisition) | Data/AI / linkedin | 86 | 35 | 68 * |
| #765 | AI Engineer (m/w/d) (Nerdware) | Data/AI / arbeitnow | 82 | 35 | 35 * |
| #5139 | Software Engineer, AI Coding Tasks (Askable) | Data/AI / remotive | 82 | 85 | 100 * |
| #3943 | O&M Data Engineer – Munich (Fixed Term 2 years) (Sungrow Europe - Welcome trave) | Data/AI / arbeitnow | 78 | 62 | 52 * |
| #3924 | Senior Data Engineer (x/f/m) (Doctolib) | Data/AI / arbeitnow | 76 | 35 | 70 * |
| #1921 | Senior Data Engineer - BeReal (BeReal) | Data/AI / arbeitnow | 68 | 35 | 70 * |
| #1927 | Senior Backend Engineer - Scoring & Computation Engine (m/f/d) (Statista) | Backend / arbeitnow | 66 | 62 | 62 * |
| #2431 | Senior AI Engineer, Agents and Platform (f/m/d) (Xu De) | Data/AI / arbeitnow | 62 | 62 | 66 * |
| #5319 | Senior ML Backend Engineer - Search & Recommendations (Salla) | Data/AI / boards | 62 | 48 | 56 * |
| #3923 | Python Engineer – Web Crawling & Data Extraction (m/f/d) (Certivity) | Data/AI / arbeitnow | 55 | 35 | 78 * |
| #797 | Senior AI Quality Engineer (Foodics) | Data/AI / boards | 54 | 48 | 55 * |
| #2427 | Propulsion Data & Modeling Engineer (The Exploration Company) | Data/AI / arbeitnow | 38 | 32 | 32 * |
| #1913 | Backend Engineer (Go) (Prelude) | Backend / arbeitnow | 35 | 35 | 35 * |
| #2418 | Senior Fullstack Engineer — Mobile Healthcare Platform (Snke) | Mobile / arbeitnow | 35 | 70 | 35 * |
| #2441 | Data Engineer Kubernetes (m/w/d) (citema systems GmbH) | Data/AI / arbeitnow | 35 | 35 | 35 * |
| #5316 | Analytics Engineer II (Delivery Hero (talabat)) | Data/AI / boards | 35 | 62 | 79 * |
| #3921 | Sr. Technical Program Manager (TPM) - AI Programs, Vinted Engineering (Vinteden) | Data/AI / arbeitnow | 32 | 32 | 24 * |
| #2409 | Senior Principal Software Engineer, Vertica (Ladders) | - / linkedin | 25 | 10 | 25 * |

`*` = not valid as returned, accepted by the app's parse.

## 3. Top 10 by each model, side by side

Ties are broken by job id; a score shown twice means those jobs tie. Only the 20 jobs of this sample are ranked, so "top 10" means the top half of the sample.

| # | 3.1-flash-lite | gemma-4-31b-it |
|---|---|---|
| 1 | **85** #794 Data Analytics Engineer (They/She/He) (Delivery Hero (talabat), stored 90 | **100** #1914 Location Data engineer (Amo), stored 94 ◦ |
| 2 | **85** #5139 Software Engineer, AI Coding Tasks (Askable), stored 82 | **100** #5139 Software Engineer, AI Coding Tasks (Askable), stored 82 |
| 3 | **70** #2418 Senior Fullstack Engineer — Mobile Healthcare Plat (Snke), stored 35 ◦ | **79** #794 Data Analytics Engineer (They/She/He) (Delivery Hero (talabat), stored 90 |
| 4 | **62** #1927 Senior Backend Engineer - Scoring & Computation En (Statista), stored 66 | **79** #5316 Analytics Engineer II (Delivery Hero (talabat), stored 35 |
| 5 | **62** #2431 Senior AI Engineer, Agents and Platform (f/m/d) (Xu De), stored 62 | **78** #3923 Python Engineer – Web Crawling & Data Extraction ( (Certivity), stored 55 ◦ |
| 6 | **62** #3943 O&M Data Engineer – Munich (Fixed Term 2 years) (Sungrow Europe - Welco), stored 78 ◦ | **70** #1921 Senior Data Engineer - BeReal (BeReal), stored 68 ◦ |
| 7 | **62** #5316 Analytics Engineer II (Delivery Hero (talabat), stored 35 | **70** #3924 Senior Data Engineer (x/f/m) (Doctolib), stored 76 ◦ |
| 8 | **48** #797 Senior AI Quality Engineer (Foodics), stored 54 ◦ | **68** #2410 Data Engineer (Mentor Talent Acquisit), stored 86 ◦ |
| 9 | **48** #5319 Senior ML Backend Engineer - Search & Recommendati (Salla), stored 62 ◦ | **66** #2431 Senior AI Engineer, Agents and Platform (f/m/d) (Xu De), stored 62 |
| 10 | **35** #765 AI Engineer (m/w/d) (Nerdware), stored 82 ◦ | **62** #1927 Senior Backend Engineer - Scoring & Computation En (Statista), stored 66 |

◦ = job is in this model's top 10 but not the other's. Overlap between the two top 10s: **5/10**. Overlap with the stored-score top 10: 3.1-flash-lite 6/10, gemma-4-31b-it 8/10.

<details><summary>Reasons for the 3.1-flash-lite top 5</summary>

- **#794 Data Analytics Engineer (They/She/He)** → 85: The candidate is a strong technical match for the role, but the lack of existing work authorization for Spain and the location requirement make them ineligible for this specific position.  
  strengths: Strong SQL and Python proficiency | Hands-on LLM and automation experience | Collaborative engineering practices  
  gaps: Limited years of experience in the data track | Requires visa sponsorship for Spain | No prior professional experience with Looker  
  flags: must_be_based_in (soft)
- **#5139 Software Engineer, AI Coding Tasks** → 85: The candidate is a strong technical fit for this remote task-based role, possessing the required programming skills and experience with AI tools, though they will need to demonstrate their ability to curate high-quality coding tasks.  
  strengths: Strong Python proficiency | Experience with automated testing | Familiarity with AI/LLM workflows  
  gaps: Limited experience in open-source contributions | No prior experience creating AI evaluation benchmarks  
  flags: none
- **#2418 Senior Fullstack Engineer — Mobile Healthcare Platform** → 70: While the candidate's technical stack is a strong match for the role, they lack the required seniority and the necessary work authorization to work onsite in Germany.  
  strengths: Flutter mobile development | Backend and API integration | CI/CD and testing automation  
  gaps: Senior-level experience | Local work authorization in Germany | Healthcare interoperability standards (FHIR/HL7)  
  flags: must_be_based_in (soft); seniority_mismatch (soft)
- **#1927 Senior Backend Engineer - Scoring & Computation Engine (m/f/d)** → 62: The candidate is a talented junior engineer with relevant technical skills, but does not meet the senior experience requirements or the location/work authorization criteria for this role.  
  strengths: Python and FastAPI | Data engineering pipelines | Testing and clean architecture  
  gaps: Years of experience | Computation engine design | German work authorization  
  flags: seniority_mismatch (soft); must_be_based_in (soft)
- **#2431 Senior AI Engineer, Agents and Platform (f/m/d)** → 62: The candidate is a strong junior-to-mid-level AI engineer, but does not meet the senior-level experience requirements or the location/work authorization criteria for this role.  
  strengths: LLM and RAG development | Python and FastAPI | Agentic workflow experience  
  gaps: Insufficient years of experience | Lack of work authorization in Germany | Need for onsite presence in Berlin  
  flags: seniority_mismatch (soft); must_be_based_in (soft)

</details>

<details><summary>Reasons for the gemma-4-31b-it top 5</summary>

- **#1914 Location Data engineer** → 100: Excellent match; the candidate has the exact core data stack requested (dbt, DuckDB) and the company explicitly provides the visa sponsorship and relocation needed for the candidate to move to Paris.  
  strengths: dbt | DuckDB | Python/SQL  
  gaps: Spark | BigQuery/ClickHouse  
  flags: none
- **#5139 Software Engineer, AI Coding Tasks** → 100: The candidate is an excellent fit, possessing the required software engineering seniority and a strong AI background to create high-quality coding tasks for model training.  
  strengths: Proficiency in Python, Java, and C++ | Experience with Docker, Linux, and Git | Hands-on experience building LLM-based systems  
  gaps: No explicit mention of public open-source contributions  
  flags: none
- **#794 Data Analytics Engineer (They/She/He)** → 79: The candidate is a strong technical match with the required SQL, Python, and LLM skills, though they are slightly under the requested years of professional data experience and will require visa sponsorship for Spain.  
  strengths: Python and SQL proficiency | Extensive LLM and AI implementation experience | Hands-on with dbt and Apache Airflow  
  gaps: Professional experience with Looker | Experience with Google Cloud Platform (GCP) | Professional years of experience in Analytics Engineering  
  flags: none
- **#5316 Analytics Engineer II** → 79: The candidate has the exact technical stack required for the role but lacks the minimum 3 years of professional experience in data modeling.  
  strengths: Proficiency in dbt | Python and SQL skills | Experience with CI/CD and Git  
  gaps: Professional experience with dbt (mostly project-based) | Enterprise cloud data warehouse experience (e.g., Snowflake, BigQuery)  
  flags: none
- **#3923 Python Engineer – Web Crawling & Data Extraction (m/f/d)** → 78: The candidate meets the general seniority and Python requirements and possesses valuable LLM and backend skills, but lacks the specific expertise in large-scale web crawling and anti-bot measures required for this role.  
  strengths: Python | LLM-assisted extraction | Java/Spring Boot  
  gaps: Large-scale web scraping | Anti-bot defenses | GCP/Azure production experience  
  flags: none

</details>

## 4. Observations

**Caveats.** 20 jobs is a small sample. The stored scores are another LLM's output (`gemma4:31b-cloud`), from the same model family as `gemma-4-31b-it`, so agreement with them is partly expected and is not ground truth. Judge the two top 10s above with your own eyes.

**Reliability.**
- `gemini-3.1-flash-lite`: 20/20 valid on the first try with the native schema, no retries, no errors, 11.6 s mean per job (max 24.7 s). It was run with 4 jobs in flight under 15 RPM.
- `gemma-4-31b-it`: **0/20 valid as returned.** Every answer came in a Markdown fence and/or wrapped as `{"properties": ...}` (in the earlier 3-job test only 1 of 3 did). All 20 are accepted by the app's existing `strip_fence` + `_unwrap_properties`, so it works with the app's current parsing, but a stricter parser would reject all of them. 82 s mean per job, 13 retries on 7 jobs (HTTP 500/503), and about 1,280 thinking tokens per job.

**Agreement.** The two models agree only moderately (Spearman 0.50, mean score difference 16.8 points) and the top 10s share 5 of 10 jobs. `gemma-4-31b-it` is closer to the stored scores (ρ 0.66, top-10 overlap 8/10) than `gemini-3.1-flash-lite` (ρ 0.35, 6/10).

**Why the lite model diverges: hard-flag caps.** A hard red flag caps the final score at 35. `gemini-3.1-flash-lite` raised a hard flag on 9 of 20 jobs (13 flags), `gemma-4-31b-it` on 5 of 20 (8 flags). Several of the lite model's flags are backed by a real quote that does not support the claim, and the app marks them "verified" because the quote exists in the listing:
- #1914 (stored 94): all five sub-scores are 10, then capped to 35 by `must_be_based_in` with the quote "we work together onsite 5 days a week". (Gemma gave it 100.)
- #3924 (stored 76): `must_be_based_in` with the quote "Paris" (just the location word). Gemma gave 70.
- #1921 (stored 68): `must_be_based_in` with "Wellness activities in our Paris office". Gemma gave 70.
- #765: `work_authorization_required` with the quote "Remote & Home-Office innerhalb Deutschlands", which says nothing about work authorization.
- #3923: `must_be_based_in` with "A vibrant in-office culture in Munich". Gemma gave 78.
Gemma also has weak ones: #765 `language_required` with "Wir suchen erfahrene AI Engineers", and #2418 `must_be_based_in` with "hybrid work model within Germany" (arguably relevant).
This is a property of the flag pipeline, not only of one model: the check proves a quote exists, not that it supports the flag. It also affects the stored scores: **1,975 of the 5,319 stored scores (37%) are exactly 35**, the cap value. I have not verified how many of those come from unsupported flags. It is worth checking before any model becomes the single source for Discover, because it decides which jobs reach your top 10 more than the sub-scores do.

**Evidence quotes.** 134/139 (lite) and 120/121 (gemma) quotes were found in the listing, the experience pool or the prompt's metadata lines; the few not found are paraphrases or translations of the listing ("Die gesamte Stellenanzeige ist auf Deutsch verfasst", "The entire job posting is written in German") or restated candidate facts, not invented text. In the listing text alone: 114/139 and 104/121.

**Other score behaviour.** Gemma gave 100 to two jobs (#1914, #5139) with no flags, so the top of its ranking has ties. The lite model put a Senior Fullstack Mobile Healthcare role (#2418, stored 35) at 70 and third; gemma capped it at 35 for the "hybrid within Germany" flag.

## 5. How long to rescore everything with one bulk model

- Discover holds **5,319 jobs, of which 3,999 are not duplicates**. Cross-source duplicates get a copy of the score without a model call, so about **4,000 calls** are needed. Only 144 of those have full descriptions; 3,004 are Adzuna snippets (avg 495 chars) and 851 are summaries.
- **`gemini-3.1-flash-lite` at 500/day:** 3,999 ÷ 500 = **8.0 days** with nothing else using the quota and no retries; about 9 days with a 5% allowance for retries and quota used by tests (I used 32 lite requests today). New jobs compete for the same 500: discovery has averaged about 167 new non-duplicate jobs/day since 2026-09-26 (bursty: 1,820 on 09-27, 1,025 on 10-12, 835 on 10-19), which leaves about 333/day for the backlog, so roughly **12 days** until Discover is entirely one model. RPM and TPM are not the limit (15 RPM and 250K TPM allow thousands per day); one day's 500 calls take about 35-40 minutes of running.
- **`gemma-4-31b-it`, for comparison:** it is limited by TPM (16K) rather than RPD (14,400). At about 5.5k input tokens a full listing allows about 2.9 jobs/min. Snippet jobs are shorter (my estimate, not measured: about 3.5k input tokens, about 3.9 jobs/min), so the backlog is **about 15-23 hours of running, roughly 1 day**, with about 4 calls in flight because of 80 s latency, plus retries. It would share that TPM with the "Rate with Gemini" button.
- Until the pass finishes, Discover mixes models. Scoring best-first (by stored score) would make the top of Discover consistent after the first 1-2 days.

## 6. What I would do next (nothing below is built)

Item 3 (making `gemini-3.1-flash-lite` the bulk scorer and `gemma-4-31b-it` the per-job button, with the queue-for-tomorrow and copy-paste fallbacks) is waiting for your approval. Based on this follow-up I would not approve it as specified yet:
1. The lite model changes your top 10 mainly through unsupported hard flags. Either fix the flag check first (a hard flag should need a quote that actually states the requirement, which touches `services/fit.py` and probably the prompt, so it needs a prompt version bump and an eval), or choose `gemma-4-31b-it` for bulk, where the backlog is about 1 day instead of 8-12.
2. If you still want the lite model as bulk, I need three answers: the day boundary for the 500 RPD reset (Google resets at midnight Pacific), whether "queue the rest for tomorrow" should keep Discover partly on the old scores, and whether the Ollama-cloud fallback is a one-click choice you make per run.
