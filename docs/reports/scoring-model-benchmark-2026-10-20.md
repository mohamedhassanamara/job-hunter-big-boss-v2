# Scoring model benchmark: 2026-10-20

Test only: nothing was written to the database, no setting or default model was changed. Scripts: read-only; raw responses in `docs/reports/raw/scoring-benchmark-2026-10-20/` (one JSON per run, plus `_meta.json` with the baseline).

**Prompt** `fit_score/v3` (the exact system + user prompt the app renders, 3 jobs), our `FitAssessment` JSON schema, temperature 0, every run. Scores are computed by the app's own `fit.build_record` (same arithmetic, evidence verification and flag caps as production).

**Baseline** = the stored `gemma4:31b-cloud` score of each job (no new call). Caveat: the baseline was written on 2026-10-14 against an older experience-pool version (`c19b26b20e9ec960`); the current one is `3812127ca20f8860`. Differences from the baseline therefore mix model differences with experience changes.

## Jobs

| Role | Job | Baseline (31b-cloud) | Why chosen |
|---|---|---|---|
| good | #3938 Full-Stack Engineer (Backend Leaning) - Creative Agents (ElevenLabs) | 94 | clearest fit in the DB (94): backend-leaning full-stack, remote, no flags |
| medium | #3935 Senior Data Engineer - Real time analytics (Aircall) | 62 | mid score (62): data-engineering role in France, full 4.9k-char listing |
| low | #3950 Data Collection Engineer ADAS (m/w/d) (Ceis Gmbh) | 21 | low score (21): ADAS data-collection role in Germany, full 2.9k-char listing |

All three have `description_level = full` (not snippets) and were scored under `fit_score/v3`.

## 1. Summary

Scores are `good / medium / low`. "Valid JSON" = parsed and schema-valid on the first model answer (no re-ask). Tokens = avg input / output / thinking. Evidence check = quoted evidence found in the job text, the experience pool, **or** the metadata lines the prompt shows (location with country code, remote type) (automatic, same matcher as the app: exact or ≥80% of words in order); the next column is job text only (what the app itself verifies). Retries = 429/500/503 retried with backoff.

| Model | Thinking | Valid JSON | Avg time (s) | Tokens in / out / think | Scores (good/med/low) | Ranking correct | Evidence ok (job, exp. or prompt metadata) | Evidence in job | Retries | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline gemma4:31b-cloud | – | – | – | – | 94 / 62 / 21 | yes | – | – | – | stored scores |
| gemini-3.8-flash | default | 3/3 | 91.1 | 4778 / 713 / 972 | 62 / 62 / 22 | no (tie) | 17/17 (100%) | 16/17 | 3 |  |
| gemini-3.8-flash | minimal | 1/1 | 179.0 | 4899 / 707 / 0 | 78 / – / – | n/a (missing runs) | 5/5 (100%) | 5/5 | 4 | 2 skipped |
| gemini-3.6-flash | default | 2/3 | 12.9 | 4726 / 572 / 1814 | 62 / – / 22 | n/a (missing runs) | 10/10 (100%) | 10/10 | 5 |  |
| gemini-3.6-flash | minimal | 1/1 | 4.2 | 4899 / 505 / 0 | 85 / – / – | n/a (missing runs) | 5/5 (100%) | 5/5 | 4 | 2 skipped |
| gemini-3.5-flash-lite | default | 3/3 | 3.0 | 4778 / 617 / 0 | 68 / 62 / 52 | yes | 16/16 (100%) | 13/16 | 0 |  |
| gemini-3.5-flash-lite | minimal | 3/3 | 2.4 | 4778 / 616 / 0 | 78 / 62 / 52 | yes | 16/16 (100%) | 12/16 | 0 |  |
| gemini-3.1-flash-lite | default | 3/3 | 3.6 | 4778 / 727 / 0 | 78 / 62 / 35 | yes | 19/19 (100%) | 17/19 | 0 |  |
| gemini-3.1-flash-lite | minimal | 3/3 | 4.6 | 4778 / 727 / 0 | 78 / 62 / 35 | yes | 19/19 (100%) | 17/19 | 0 |  |
| gemma-4-26b-a4b-it | default | 0/3 | – | 5538 / 766 / 0 | – / – / – | n/a (missing runs) | – | – | 1 |  |
| gemma-4-31b-it | default | 2/3 (+1 recoverable) | 83.1 | 5538 / 708 / 1333 | 97 / 70 / 15 | yes | 18/18 (100%) | 15/18 | 2 |  |

Minimal thinking on the lite models: the answers' thinking tokens are 0 in both modes, so the two modes are the same configuration there (any difference between their rows is run-to-run nondeterminism at temperature 0).

### Capacity (from the limits you gave and measured tokens)

jobs/min = min(RPM, TPM ÷ avg input tokens per job); input tokens are what TPM counts. jobs/day = min(RPD, jobs/min × 1440). "1,000 jobs" is the rate-limit-bound time; the quota column is the days of RPD it needs. Retries after 429/503 probably also consume RPD.

| Model | RPM | TPM | RPD | Avg input tok | Avg total tok | Max jobs/min | Max jobs/day | 1,000 jobs at that rate | Quota for 1,000 jobs | Avg latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini-3.8-flash | 5 | 250K | 20 | 4808 | 6249 | 5.0 | 20 | 3.3 h | 50 day(s) | 113 |
| gemini-3.6-flash | 5 | 250K | 20 | 4783 | 6542 | 5.0 | 20 | 3.3 h | 50 day(s) | 10 |
| gemini-3.5-flash-lite | 15 | 250K | 500 | 4778 | 5394 | 15.0 | 500 | 67 min | 2 day(s) | 3 |
| gemini-3.1-flash-lite | 15 | 250K | 500 | 4778 | 5505 | 15.0 | 500 | 67 min | 2 day(s) | 4 |
| gemma-4-26b-a4b-it | 30 | 16K | 14,400 | 5538 | 6048 | 2.9 | 4,160 | 5.8 h | 1 day | 68 |
| gemma-4-31b-it | 30 | 16K | 14,400 | 5538 | 7579 | 2.9 | 4,160 | 5.8 h | 1 day | 80 |

Latency matters on top of limits: the Flash models need concurrency to reach 5 jobs/min when a call takes 80-100 s.

### Evidence quotes that were NOT found (automatic check)

None: every quoted evidence string was found in the listing, the experience pool or the prompt's metadata lines.


## 2. Per job, side by side with the baseline

### Good fit: #3938 Full-Stack Engineer (Backend Leaning) - Creative Agents (ElevenLabs)

| Sub-score | baseline 31b-cloud | gemini-3.8-flash (default) | gemini-3.8-flash (minimal) | gemini-3.6-flash (default) | gemini-3.6-flash (minimal) | gemini-3.5-flash-lite (default) | gemini-3.5-flash-lite (minimal) | gemini-3.1-flash-lite (default) | gemini-3.1-flash-lite (minimal) | gemma-4-31b-it (default) |
|---|---|---|---|---|---|---|---|---|---|---|
| role_match | 10 | 5 | 10 | 5 | 10 | 5 | 5 | 5 | 5 | 10 |
| skills_match | 8 | 5 | 5 | 5 | 5 | 7 | 10 | 10 | 10 | 9 |
| seniority_fit | 10 | 5 | 5 | 5 | 10 | 5 | 5 | 10 | 10 | 10 |
| location_eligibility | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 5 | 5 | 10 |
| language_requirements | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| **final score** | 94 | 62 | 78 | 62 | 85 | 68 | 78 | 78 | 78 | 97 |
| red flags | none | none | none | none | none | none | none | none | none | none |

No valid score: gemma-4-26b-a4b-it (default). See the errors in the raw files.

<details><summary><b>baseline gemma4:31b-cloud</b>: score 94</summary>

- **role_match = 10**: The job is for a backend-leaning full-stack engineer, which aligns with the candidate's target role of Backend Engineer and their experience in both backend and mobile/frontend.  
  evidence: “backend-leaning full-stack engineer” ✓
- **skills_match = 8**: The candidate has strong overlap in backend skills (Spring Boot, Python, REST APIs), asynchronous processing (Airflow, MQTT), and specific AI agent experience (LLMs, Mistral, prompt-based systems).  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 10**: The job does not specify a minimum number of years of experience and focuses on evidence of shipped products, which the candidate has (3 years total).  
  evidence: (none)
- **location_eligibility = 10**: The job is explicitly remote and states that they prioritize talent over location.  
  evidence: “We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The job is in English and the candidate has full professional proficiency in English.  
  evidence: (none)
- **strengths**: AI agent development (Mistral, LLMs) | Full-stack delivery (Spring Boot, Flutter) | Asynchronous pipelines (Airflow, Docker)
- **gaps**: No explicit mention of MCP integrations | Limited experience with multimodal generation
- **summary**: The candidate is a strong fit for this remote role, combining professional backend experience with a proven track record of building AI-driven agents and shipping full-stack products.

</details>

<details><summary><b>gemini-3.8-flash (default)</b>: score 62</summary>

- **role_match = 5**: The role is a backend-leaning full-stack position combining backend infrastructure and customer-facing agent integrations, which is adjacent to pure backend engineering.  
  evidence: “We are looking for a backend-leaning full-stack engineer to help build the next generation of Creative Agents at ElevenLabs.” ✓
- **skills_match = 5**: The candidate has practical experience with LLMs, FastAPI, and APIs, but lacks professional experience with WebSockets, MCP integrations, and running large-scale asynchronous generation pipelines.  
  evidence: “Familiarity with HTTP, WebSockets and asynchronous workers will help you build reliable communication between services and recover from failures.” ✓
- **seniority_fit = 5**: The company does not use standard job titles or state required years of experience, making the seniority expectation ambiguous, though they look for proven end-to-end ownership.  
  evidence: “Impact not job titles: We don’t have job titles. Instead, it’s about the impact you have. No task is above or beneath you.” ✓
- **location_eligibility = 10**: The position is fully remote and explicitly states a global-first policy prioritizing talent regardless of location.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The role is conducted in English, which the candidate speaks at a full professional working proficiency.  
  evidence: “Find more English Speaking Jobs in Switzerland on Arbeitnow” ✓
- **strengths**: Hands-on AI and LLM project experience | API development with FastAPI and Spring Boot | Cross-stack mobile and backend development
- **gaps**: Production experience with WebSockets and async workers | Model Context Protocol (MCP) integrations | Limited professional backend track tenure
- **summary**: A globally remote role open to backend-focused AI engineering, but demanding strong end-to-end agent production experience beyond the candidate's current background.

</details>

<details><summary><b>gemini-3.8-flash (minimal)</b>: score 78</summary>

- **role_match = 10**: The role is a backend-leaning engineering role focusing heavily on backend systems and agent infrastructure, fitting the Backend track.  
  evidence: “We are looking for a backend-leaning full-stack engineer to help build the next generation of Creative Agents at ElevenLabs.” ✓
- **skills_match = 5**: The candidate has built agent/LLM pipelines and APIs, but lacks deep experience operating large-scale production distributed systems, WebSockets, and asynchronous worker infrastructure.  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 5**: The job does not state a specific number of years, but expects exceptional engineering with autonomous end-to-end ownership of complex distributed systems, which is mid-to-senior level compared to candidate's 1 year in backend.  
  evidence: “Evidence of independent, end-to-end ownership and confidence working across the stack, including frontend delivery when needed.” ✓
- **location_eligibility = 10**: The company states a global team and that they prioritize talent over location, with a fully remote work mode and remote stipends.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The posting is in English and requires clear communication; the candidate speaks full professional English.  
  evidence: “Good product judgement, clear communication and enthusiasm for creative agents.” ✓
- **strengths**: Hands-on experience with LLMs and AI agent integrations | API development with FastAPI and Spring Boot | Full-stack delivery experience across mobile and backend
- **gaps**: Operating production systems at scale with asynchronous workers | WebSockets and real-time streaming protocols | Deep professional backend experience beyond 1 year
- **summary**: Globally open remote role with a solid agent/backend match, though the engineering rigor and scale demanded may stretch the candidate's backend seniority.

</details>

<details><summary><b>gemini-3.6-flash (default)</b>: score 62</summary>

- **role_match = 5**: The job is a backend-leaning full-stack role, which represents a mixed role combining backend engineering with frontend responsibilities.  
  evidence: “We are looking for a backend-leaning full-stack engineer to help build the next generation of Creative Agents” ✓
- **skills_match = 5**: The candidate has relevant experience with Python, FastAPI, Spring Boot, and LLM agent orchestration, but lacks proven experience with asynchronous workers and production cloud storage.  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 5**: The job posting does not state a specific year requirement or seniority level, making the seniority fit unclear for a candidate with 1 year in the track.  
  evidence: “We care about evidence of exceptional engineering: products you have shipped, difficult problems you have solved, and systems you have owned.” ✓
- **location_eligibility = 10**: The job is fully remote and explicitly states that location is not a barrier.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The job is written in English and requires no additional languages; the candidate has full professional proficiency in English.  
  evidence: (none)
- **strengths**: Python & FastAPI backend APIs | LLM & AI agent orchestration | Full-stack development
- **gaps**: Only 1 year focused backend experience | Asynchronous job processing | Cloud infrastructure management
- **summary**: A good remote opportunity matching the candidate's backend and AI project experience, though full-stack expectations and unspecified seniority requirements create moderate gaps.

</details>

<details><summary><b>gemini-3.6-flash (minimal)</b>: score 85</summary>

- **role_match = 10**: The job is for a backend-leaning full-stack engineer building production agents and backend systems, which aligns with the candidate's target track roles.  
  evidence: “We are looking for a backend-leaning full-stack engineer to help build the next generation of Creative Agents” ✓
- **skills_match = 5**: The candidate has strong backend (Spring Boot, Python, FastAPI) and AI/Agent/LLM experience (RAG, Mistral, prompts, orchestration), but lacks explicit exposure to multimodal media production tools or WebSockets.  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 10**: The role specifies no required years of experience, focusing instead on evidence of shipped products and engineering ability. Candidate's 1 year in track and 3 years overall fit mid-level expectations.  
  evidence: “We care about evidence of exceptional engineering: products you have shipped, difficult problems you have solved, and systems you have owned.” ✓
- **location_eligibility = 10**: The position is fully remote with no geographic restrictions stated, explicitly emphasizing prioritizing talent over location.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The job text is in English and requires clear communication in English, which the candidate speaks at a full professional level.  
  evidence: “Good product judgement, clear communication and enthusiasm for creative agents.” ✓
- **strengths**: Python and FastAPI backend skills | Agent and LLM orchestration experience | End-to-end full-stack shipping experience
- **gaps**: Limited experience with WebSockets and async workers | No direct experience with Model Context Protocol (MCP) | No explicit multimodal generation background
- **summary**: The candidate is a strong fit for this fully remote backend-leaning role, bringing solid backend and agent/LLM development experience.

</details>

<details><summary><b>gemini-3.5-flash-lite (default)</b>: score 68</summary>

- **role_match = 5**: The job is a Full-Stack Engineer role leaning towards backend, which partially overlaps with backend developer roles.  
  evidence: “We are looking for a backend-leaning full-stack engineer to help build the next generation of Creative Agents at ElevenLabs.” ✓
- **skills_match = 7**: The candidate has experience with backend systems, APIs, Python, and LLM agent development, matching several requirements.  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 5**: The job does not state a specific seniority level, but requires evidence of exceptional engineering and independent ownership.  
  evidence: “We care about evidence of exceptional engineering: products you have shipped, difficult problems you have solved, and systems you have owned.” ✓
- **location_eligibility = 10**: The job is fully remote and explicitly states global team priority.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: No specific secondary language is required, and the candidate has full professional English.  
  evidence: (none)
- **strengths**: LLM agent development | Python backend engineering | API design
- **gaps**: Full-stack production experience | Multimodal generation experience
- **summary**: This is a remote full-stack engineering role focusing on creative AI agents at ElevenLabs, which aligns well with the candidate's backend and AI project background.

</details>

<details><summary><b>gemini-3.5-flash-lite (minimal)</b>: score 78</summary>

- **role_match = 5**: The candidate targets backend roles, and the job is for a full-stack engineer with a backend leaning, which is an adjacent role.  
  evidence: “We are looking for a backend-leaning full-stack engineer to help build the next generation of Creative Agents at ElevenLabs.” ✓
- **skills_match = 10**: The candidate has strong backend and AI engineering skills including APIs, asynchronous processing, LLMs, and agent workflows.  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 5**: The candidate has 1 year of professional experience in the track plus previous internships, whereas the job asks for evidence of exceptional engineering and production ownership without a strict year count.  
  evidence: “We care about evidence of exceptional engineering: products you have shipped, difficult problems you have solved, and systems you have owned.” ✓
- **location_eligibility = 10**: The job is remote and the company explicitly states they are a global team prioritizing talent over location.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The job requires English, which the candidate speaks at a full professional level.  
  evidence: (none)
- **strengths**: Backend engineering | LLMs and AI agents | API and asynchronous systems
- **gaps**: Years of professional track experience | Frontend delivery at scale
- **summary**: This is a good role match for a backend-leaning full-stack engineer with strong AI skills, though the candidate's junior seniority level may be a hurdle against more experienced applicants.

</details>

<details><summary><b>gemini-3.1-flash-lite (default)</b>: score 78</summary>

- **role_match = 5**: The job is for a full-stack engineer with a backend focus, which overlaps with the candidate's backend engineering experience.  
  evidence: “We are looking for a backend-leaning full-stack engineer” ✓
- **skills_match = 10**: The candidate has strong experience in backend systems, APIs, and AI/LLM agent development, which aligns perfectly with the job requirements.  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 10**: The job does not specify a minimum number of years, and the candidate's experience in building and shipping production systems is relevant.  
  evidence: “We care about evidence of exceptional engineering: products you have shipped, difficult problems you have solved, and systems you have owned.” ✓
- **location_eligibility = 5**: The job is remote and global, but does not explicitly state visa sponsorship policies for non-residents.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The job is in English, and the candidate has full professional proficiency in English.  
  evidence: (none)
- **strengths**: Backend systems architecture | AI/LLM agent development | Full-stack ownership
- **gaps**: Limited professional experience (3 years) | No explicit mention of visa sponsorship
- **summary**: The candidate is a strong match for this role due to their hands-on experience with backend systems, AI agent development, and end-to-end product ownership.

</details>

<details><summary><b>gemini-3.1-flash-lite (minimal)</b>: score 78</summary>

Identical text to gemini-3.1-flash-lite (default).
</details>

<details><summary><b>gemma-4-31b-it (default) [recovered by the app's unwrap, not valid as returned]</b>: score 97</summary>

- **role_match = 10**: The job is for a backend-leaning full-stack engineer, which aligns perfectly with the candidate's background in backend development and mobile frontend.  
  evidence: “backend-leaning full-stack engineer” ✓
- **skills_match = 9**: The candidate has strong overlap in backend skills (FastAPI, Spring Boot, PostgreSQL), AI agent development (LLMs, RAG, Mistral, LLaMA), and full-stack delivery (Flutter).  
  evidence: “Strong backend engineering skills, experience operating production systems, and sound fundamentals in APIs, cloud infrastructure, storage and asynchronous processing.” ✓
- **seniority_fit = 10**: The job does not specify a minimum number of years or a senior title, and the candidate's 3 years of experience is appropriate for a general engineer role.  
  evidence: (none)
- **location_eligibility = 10**: The company explicitly states they prioritize talent over location and operate as a global team.  
  evidence: “Global team: We prioritize your talent, not your location.” ✓
- **language_requirements = 10**: The job is in English, and the candidate has full professional proficiency.  
  evidence: (none)
- **strengths**: LLM and Agent development (Mistral, LLaMA, RAG) | Backend proficiency (FastAPI, Spring Boot, Airflow) | Full-stack delivery (Flutter)
- **gaps**: Experience with multimodal generation | Scale of production systems operated
- **summary**: An excellent match given the candidate's specific experience building AI agents and their ability to work across the full stack.

</details>

### Medium fit: #3935 Senior Data Engineer - Real time analytics (Aircall)

| Sub-score | baseline 31b-cloud | gemini-3.8-flash (default) | gemini-3.5-flash-lite (default) | gemini-3.5-flash-lite (minimal) | gemini-3.1-flash-lite (default) | gemini-3.1-flash-lite (minimal) | gemma-4-31b-it (default) |
|---|---|---|---|---|---|---|---|
| role_match | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| skills_match | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| seniority_fit | 0 | 0 | 0 | 0 | 0 | 0 | 5 |
| location_eligibility | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| language_requirements | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| **final score** | 62 | 62 | 62 | 62 | 62 | 62 | 70 |
| red flags | must_be_based_in (soft); seniority_mismatch (soft) | seniority_mismatch (soft) | seniority_mismatch (soft) | must_be_based_in (soft); seniority_mismatch (soft) | must_be_based_in (soft); seniority_mismatch (soft) | must_be_based_in (soft); seniority_mismatch (soft) | must_be_based_in (soft) |

No valid score: gemini-3.8-flash (minimal), gemini-3.6-flash (default), gemini-3.6-flash (minimal), gemma-4-26b-a4b-it (default). See the errors in the raw files.

<details><summary><b>baseline gemma4:31b-cloud</b>: score 62</summary>

- **role_match = 10**: The core responsibilities are exactly that of a Data Engineer, focusing on data pipelines and analytics platforms.  
  evidence: “Senior Data Engineer to join our growing Engineering Team” ✓
- **skills_match = 5**: The candidate has experience with Python, SQL, Airflow, S3, and star schema modeling, but lacks the specific real-time streaming stack (Kafka, Flink, Pinot) and Scala required for this senior role.  
  evidence: “AWS (Kinesis,Kafka, s3, DMS, Glue, EMR, EKS, Redshift, Spectrum), Apache Pinot, Apache Flink and Airflow.” ✓
- **seniority_fit = 0**: The job requires 5+ years of programming experience and 3+ years in real-time analytics; the candidate has only 1 year in the data track and 3 years total experience.  
  evidence: “5+ years experience with a modern programming language such as Scala, Python, Go, Typescript” ✓
- **location_eligibility = 5**: The job is onsite in Paris, and the candidate is based in Tunisia and requires visa sponsorship, which is not explicitly offered in the text. (Adjusted to unknown: the listing doesn't state this requirement.)  
  evidence: “Paris Office (FR)
Work mode: onsite” ✗ (not in listing)
- **language_requirements = 10**: The job is listed as an English-speaking role in France, and the candidate has full professional English and French skills.  
  evidence: “Find more English Speaking Jobs in France on Arbeitnow” ✓
- **strengths**: Python and SQL | Airflow and S3 | Star schema modeling
- **gaps**: Real-time streaming (Kafka/Flink) | Scala experience | Senior-level professional experience
- **summary**: The candidate is a junior-to-mid level engineer who lacks the required seniority and specific real-time streaming expertise for this onsite senior role in Paris.
- **red flag** must_be_based_in (soft): Onsite role in Paris  
  evidence: “Paris Office (FR)
Work mode: onsite”
- **red flag** seniority_mismatch (soft): Requires 5+ years experience; candidate has 3 total/1 in track  
  evidence: “5+ years experience with a modern programming language”

</details>

<details><summary><b>gemini-3.8-flash (default)</b>: score 62</summary>

- **role_match = 10**: The role is specifically for a Data Engineer focusing on real-time analytics, perfectly matching the candidate's Data/AI track.  
  evidence: “We are looking for an engaged and passionate Senior Data Engineer to join our growing Engineering Team.” ✓
- **skills_match = 5**: The candidate has Python, SQL, Airflow, and data modeling experience, but lacks exposure to near real-time streaming technologies like Flink, Kafka, Pinot, and production AWS services.  
  evidence: “AWS (Kinesis,Kafka, s3, DMS, Glue, EMR, EKS, Redshift, Spectrum), Apache Pinot, Apache Flink and Airflow.” ✓
- **seniority_fit = 0**: The position is a Senior role requiring 5+ years of programming experience and 3+ years in real-time analytics, which exceeds the candidate's 1.0 year in this track by at least 4 years.  
  evidence: “5+ years experience with a modern programming language such as Scala, Python, Go, Typescript” ✓
- **location_eligibility = 5**: The role is on-site in France (a target country), but the listing does not state whether visa sponsorship is provided or if existing work authorization is required.  
  evidence: “Paris Office (FR)” ✗ (not in listing)
- **language_requirements = 10**: The job description is in English and mentions being an English-speaking job in France; the candidate is fluent in both English and French.  
  evidence: “Find more English Speaking Jobs in France on Arbeitnow” ✓
- **strengths**: Python and SQL proficiency | Data pipeline orchestration with Airflow | Dimensional modeling and star schema experience
- **gaps**: Near real-time streaming tools (Kafka, Flink, Pinot) | Senior-level production experience (requires 5+ years) | AWS big data ecosystem (Redshift, Glue, EMR)
- **summary**: While the role fits the candidate's target Data Engineer track and language profile, it is a senior position requiring 5+ years of experience and real-time streaming expertise that the candidate currently lacks.
- **red flag** seniority_mismatch (soft): Seniority well above the candidate: 5+ years experience with a modern programming language such as Scala, Python, Go, Typescript  
  evidence: “5+ years experience with a modern programming language such as Scala, Python, Go, Typescript”

</details>

<details><summary><b>gemini-3.5-flash-lite (default)</b>: score 62</summary>

- **role_match = 10**: The role is a Senior Data Engineer, which directly aligns with the Data Engineer track role.  
  evidence: “We are looking for an engaged and passionate Senior Data Engineer to join our growing Engineering Team.” ✓
- **skills_match = 5**: The candidate has experience with Python, SQL, and Airflow, but lacks the requested 5+ years of programming experience, Scala, AWS streaming/big data tools, and Kafka production background.  
  evidence: “Write clean scalable code using Scala / python / SQL and test and deploy applications and systems” ✓
- **seniority_fit = 0**: The job asks for a Senior Data Engineer with 5+ years of experience with a modern programming language and 3+ years in near real-time analytics, whereas the candidate has only 1 year of experience in the track.  
  evidence: “Senior Data Engineer - Real time analytics” ✓
- **location_eligibility = 5**: The job is located in the Paris Office (FR), and while France is in the candidate's target countries, the listing does not explicitly state visa sponsorship.  
  evidence: “Location: Paris Office (FR)” ✗ (not in listing)
- **language_requirements = 10**: The job is in English and requires no specific local language that the candidate does not speak.  
  evidence: “Find more English Speaking Jobs in France on Arbeitnow” ✓
- **strengths**: Python | SQL | Apache Airflow
- **gaps**: Scala | AWS big data stack | Seniority level (5+ years experience required)
- **summary**: This is a senior-level data engineering role requiring extensive big data and streaming experience that exceeds the candidate's current 1 year of track experience.
- **red flag** seniority_mismatch (soft): Seniority well above the candidate: Senior Data Engineer  
  evidence: “Senior Data Engineer”

</details>

<details><summary><b>gemini-3.5-flash-lite (minimal)</b>: score 62</summary>

- **role_match = 10**: The job is a Data Engineer role, which directly matches the track role of Data Engineer.  
  evidence: “Senior Data Engineer - Real time analytics” ✓
- **skills_match = 5**: The candidate has experience with Python, SQL, and Apache Airflow, but lacks the required 5+ years of programming experience and AWS real-time stack like Kafka and Flink.  
  evidence: “Python / sql / Apache Airflow” ✓
- **seniority_fit = 0**: The job requires a Senior level with 5+ years of experience in a modern programming language and 3+ years in near real-time analytics, while the candidate has only 1 year in the track and 3 years total experience.  
  evidence: “Senior Data Engineer - Real time analytics” ✓
- **location_eligibility = 5**: The job is onsite in Paris, France, and the posting does not mention visa sponsorship.  
  evidence: “Paris Office (FR)” ✗ (not in listing)
- **language_requirements = 10**: The job is in English and the candidate has full professional English proficiency.  
  evidence: (none)
- **strengths**: Python | SQL | Apache Airflow
- **gaps**: Seniority level | Kafka and real-time streaming stack | 5+ years programming experience
- **summary**: The candidate matches the Data Engineer role conceptually, but is too junior for this senior position and requires relocation/visa for an onsite role in Paris.
- **red flag** must_be_based_in (soft): Requires living in a specific place: Paris Office (FR)  
  evidence: “Paris Office (FR)”
- **red flag** seniority_mismatch (soft): Seniority well above the candidate: Senior Data Engineer  
  evidence: “Senior Data Engineer”

</details>

<details><summary><b>gemini-3.1-flash-lite (default)</b>: score 62</summary>

- **role_match = 10**: The job is for a Data Engineer, which is one of the target roles in the candidate's track.  
  evidence: “we are looking for an engaged and passionate Senior Data Engineer” ✓
- **skills_match = 5**: The candidate has experience with Python, SQL, and Airflow, but lacks the required 5+ years of experience and specific expertise in the heavy AWS/Kafka/Flink stack mentioned.  
  evidence: “AWS (Kinesis,Kafka, s3, DMS, Glue, EMR, EKS, Redshift, Spectrum), Apache Pinot, Apache Flink and Airflow.” ✓
- **seniority_fit = 0**: The job is a Senior role requiring 5+ years of experience, while the candidate has only 3 years total and 1 year in the data track.  
  evidence: “5+ years experience with a modern programming language” ✓
- **location_eligibility = 5**: The job is onsite in Paris, France. The candidate is based in Tunisia and requires visa sponsorship, which is not explicitly offered in the text.  
  evidence: “Paris Office (FR)” ✗ (not in listing)
- **language_requirements = 10**: The job is in English, which the candidate speaks at a full professional level.  
  evidence: “Find more English Speaking Jobs in France on Arbeitnow” ✓
- **strengths**: Python and SQL proficiency | Experience with Apache Airflow | Data pipeline project experience
- **gaps**: Insufficient years of experience | Lack of senior-level expertise | No experience with Kafka/Flink/AWS stack
- **summary**: The candidate is a junior engineer who does not meet the senior-level experience requirements or the location/visa needs for this onsite role in Paris.
- **red flag** must_be_based_in (soft): Requires living in a specific place: Paris Office (FR)  
  evidence: “Paris Office (FR)”
- **red flag** seniority_mismatch (soft): Seniority well above the candidate: 5+ years experience with a modern programming language  
  evidence: “5+ years experience with a modern programming language”

</details>

<details><summary><b>gemini-3.1-flash-lite (minimal)</b>: score 62</summary>

Identical text to gemini-3.1-flash-lite (default).
</details>

<details><summary><b>gemma-4-31b-it (default)</b>: score 70</summary>

- **role_match = 10**: The job is for a Senior Data Engineer, which aligns perfectly with the candidate's target role of Data Engineer within the Data/AI track.  
  evidence: “We are looking for an engaged and passionate Senior Data Engineer to join our growing Engineering Team.” ✓
- **skills_match = 5**: The candidate has experience with Python, SQL, Airflow, and star schema modeling (via dbt), but lacks the specific real-time streaming tools (Kafka, Flink, Pinot) and AWS Redshift experience required.  
  evidence: “AWS (Kinesis,Kafka, s3, DMS, Glue, EMR, EKS, Redshift, Spectrum), Apache Pinot, Apache Flink and Airflow.” ✓
- **seniority_fit = 5**: The job asks for 3+ years in real-time analytics and 5+ years in a modern programming language; the candidate has 1 year in the track and 3 years total experience, creating a gap of 2-4 years.  
  evidence: “3+ years experience with near real-time analytics” ✓
- **location_eligibility = 5**: The job is onsite in Paris, France (a target country), but there is no mention of visa sponsorship for a candidate who requires it.  
  evidence: “Paris Office (FR)” ✗ (not in listing)
- **language_requirements = 10**: The job is in English and located in France; the candidate is fluent in both English and French.  
  evidence: “Find more English Speaking Jobs in France on Arbeitnow” ✓
- **strengths**: Python and SQL | Apache Airflow | Star schema modeling
- **gaps**: Real-time analytics experience | AWS Redshift | Scala
- **summary**: The candidate possesses the core data engineering toolkit but lacks the seniority and specialized real-time streaming experience required for this senior-level role.
- **red flag** must_be_based_in (soft): Requires living in a specific place: Paris Office (FR)  
  evidence: “Paris Office (FR)”

</details>

### Low fit: #3950 Data Collection Engineer ADAS (m/w/d) (Ceis Gmbh)

| Sub-score | baseline 31b-cloud | gemini-3.8-flash (default) | gemini-3.6-flash (default) | gemini-3.5-flash-lite (default) | gemini-3.5-flash-lite (minimal) | gemini-3.1-flash-lite (default) | gemini-3.1-flash-lite (minimal) | gemma-4-31b-it (default) |
|---|---|---|---|---|---|---|---|---|
| role_match | 0 | 0 | 0 | 5 | 5 | 5 | 5 | 0 |
| skills_match | 2 | 0 | 0 | 5 | 5 | 5 | 5 | 0 |
| seniority_fit | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| location_eligibility | 0 | 5 | 5 | 5 | 5 | 0 | 0 | 0 |
| language_requirements | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **final score** | 21 | 22 | 22 | 52 | 52 | 35 | 35 | 15 |
| red flags | language_required (hard); must_be_based_in (hard) | language_required (soft) | language_required (soft) | must_be_based_in (soft); language_required (soft) | must_be_based_in (soft); language_required (soft) | language_required (soft); must_be_based_in (hard) | language_required (soft); must_be_based_in (hard) | language_required (hard); must_be_based_in (hard) |

No valid score: gemini-3.8-flash (minimal), gemini-3.6-flash (minimal), gemma-4-26b-a4b-it (default). See the errors in the raw files.

<details><summary><b>baseline gemma4:31b-cloud</b>: score 21</summary>

- **role_match = 0**: The job is a hardware-centric data collection role for ADAS involving test-track activities and sensor integration, not a Data Engineering role focused on pipelines, ETL, or AI software development.  
  evidence: “Integration verschiedener Systeme, Kameras und Sensoren, einschließlich dGPS und Ground Truth (GT), in Prototypen und Serienfahrzeuge.” ✓
- **skills_match = 2**: The candidate has basic Linux knowledge and general technical education, but lacks the specific ADAS, automotive sensor integration, and electronics skills required.  
  evidence: “Grundkenntnisse in Linux sind von Vorteil.” ✓
- **seniority_fit = 10**: The job asks for a technical degree or comparable experience, which the candidate possesses.  
  evidence: “Abgeschlossenes technisches Studium oder vergleichbare Berufserfahrung im ADAS-Bereich.” ✓
- **location_eligibility = 0**: The job is onsite in Munich and requires a valid European driver's license, which the candidate (based in Tunisia) does not have.  
  evidence: “Gültiger europäischer Führerschein” ✓
- **language_requirements = 0**: The job requires fluent German and English; the candidate does not speak German.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.” ✓
- **strengths**: Technical degree | Linux basics
- **gaps**: German language | European driver's license | ADAS/Automotive experience
- **summary**: The candidate is a software/data engineer, whereas this is a hardware-focused automotive data collection role requiring German fluency and a European driver's license.
- **red flag** language_required (hard): Requires fluent German  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.”
- **red flag** must_be_based_in (hard): Requires European driver's license  
  evidence: “Gültiger europäischer Führerschein”

</details>

<details><summary><b>gemini-3.8-flash (default)</b>: score 22</summary>

- **role_match = 0**: The role is an automotive field/hardware testing position focused on vehicle sensor integration, test-track operations, and ADAS data logging rather than data platform or AI engineering.  
  evidence: “Betreuung und Koordination von Test-Track-Aktivitäten sowie Pflege des aktuellen Aufgabenstatus nach definierten Prozessen und in den entsprechenden Tools” ✓
- **skills_match = 0**: The position requires automotive protocols (CAN, FlexRay), ADAS experience, vehicle sensor hardware integration, and a European driving license, none of which the candidate possesses.  
  evidence: “Kenntnisse von Kommunikationsprotokollen wie CAN, FlexRay oder Ethernet sind von Vorteil.” ✓
- **seniority_fit = 10**: The role accepts a completed technical degree or equivalent initial experience, which matches an entry- to mid-level profile.  
  evidence: “Abgeschlossenes technisches Studium oder vergleichbare Berufserfahrung im ADAS-Bereich.” ✓
- **location_eligibility = 5**: The position is on-site in Munich, Germany (a target country), but makes no statement regarding visa sponsorship or work permit eligibility.  
  evidence: “Reisebereitschaft von bis zu 30 % innerhalb Deutschlands und Europas.” ✓
- **language_requirements = 0**: The posting strictly requires fluent German, which the candidate does not speak.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.” ✓
- **strengths**: Technical engineering degree | Basic Linux familiarity
- **gaps**: No German language skills | Lack of ADAS and automotive protocols (CAN, FlexRay) | No European driving license
- **summary**: This role is a poor fit as it requires fluent German and focuses on on-site automotive test-track and hardware data collection rather than software/data engineering.
- **red flag** language_required (soft): Requires a language: Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.”

</details>

<details><summary><b>gemini-3.6-flash (default)</b>: score 22</summary>

- **role_match = 0**: The role focuses on automotive test track coordination, hardware mounting, and sensor integration for ADAS systems, which belongs to automotive test engineering rather than data engineering.  
  evidence: “Integration verschiedener Systeme, Kameras und Sensoren, einschließlich dGPS und Ground Truth (GT), in Prototypen und Serienfahrzeuge.” ✓
- **skills_match = 0**: The candidate lacks experience in ADAS systems, CAN/FlexRay protocols, automotive electronics, and field data collection on test tracks.  
  evidence: “Abgeschlossenes technisches Studium oder vergleichbare Berufserfahrung im ADAS-Bereich.” ✓
- **seniority_fit = 10**: The posting asks for a relevant technical degree or comparable experience without requiring senior or principal years of experience.  
  evidence: “Abgeschlossenes technisches Studium oder vergleichbare Berufserfahrung im ADAS-Bereich.” ✓
- **location_eligibility = 5**: The job is located in Germany (a target country), but the listing does not state whether visa sponsorship is available.  
  evidence: “Zum Einsatz bei einem unserer Kunden suchen wir zum 01.11.2026 einen Data Collection Engineer ADAS (m/w/d)” ✓
- **language_requirements = 0**: The posting explicitly requires fluent German, which the candidate does not speak.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.” ✓
- **strengths**: Technical degree in software engineering | Python and data handling skills | Experience with testing and validation pipelines
- **gaps**: Lack of German language proficiency | No ADAS or automotive electronics experience | Lacks a valid European driver's license
- **summary**: This automotive field engineering role requires fluent German, an EU driver's license, and ADAS hardware experience, making it a poor fit for the candidate.
- **red flag** language_required (soft): Requires a language: Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.”

</details>

<details><summary><b>gemini-3.5-flash-lite (default)</b>: score 52</summary>

- **role_match = 5**: The role is ADAS Data Collection Engineering involving test-tracks and sensor data handling, which is adjacent to the Data Engineer track.  
  evidence: “Data Collection Engineer ADAS (m/w/d)” ✓
- **skills_match = 5**: The candidate has Linux and Python background and general engineering degree, but lacks specific automotive ADAS experience and CAN/FlexRay protocols.  
  evidence: “Grundkenntnisse in Linux sind von Vorteil.” ✓
- **seniority_fit = 10**: The candidate has 3 years of total experience which fits well with the general profile requirements.  
  evidence: (none)
- **location_eligibility = 5**: The job requires working onsite in Munich, Germany, and the candidate needs visa sponsorship and does not live in Germany. (Adjusted to unknown: the listing doesn't state this requirement.)  
  evidence: “Location: München (DE)” ✗ (not in listing)
- **language_requirements = 0**: The job requires fluent German and English, but the candidate does not speak German.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.” ✓
- **strengths**: Linux | Engineering degree | Python
- **gaps**: German language | ADAS experience | CAN/FlexRay protocols
- **summary**: This job is not a good fit because it is an onsite role in Munich requiring fluent German language skills and physical presence, which does not match the candidate's location or language profile.
- **red flag** must_be_based_in (soft): Requires living in a specific place: Location: München (DE)  
  evidence: “Location: München (DE)”
- **red flag** language_required (soft): Requires a language: Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.”

</details>

<details><summary><b>gemini-3.5-flash-lite (minimal)</b>: score 52</summary>

- **role_match = 5**: The role involves data handling and sensor data collection for ADAS, which touches upon data engineering tasks within an automotive context.  
  evidence: “Data Collection Engineer ADAS (m/w/d)” ✓
- **skills_match = 5**: The candidate has Linux and some general technical skills, but lacks the specific ADAS domain experience, vehicle prototyping, and communication protocols like CAN or FlexRay.  
  evidence: “Grundkenntnisse in Linux sind von Vorteil.” ✓
- **seniority_fit = 10**: The job does not state a high seniority level and aligns well with the candidate's total years of experience.  
  evidence: (none)
- **location_eligibility = 5**: The job is onsite in Munich, Germany, and the candidate is based in Tunisia requiring visa sponsorship while the listing does not offer sponsorship. (Adjusted to unknown: the listing doesn't state this requirement.)  
  evidence: “München (DE)” ✗ (not in listing)
- **language_requirements = 0**: The job explicitly requires fluent German and English, but the candidate does not speak German.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.” ✓
- **strengths**: Linux | Python | Data pipelines
- **gaps**: German language fluency | ADAS domain experience | Automotive protocols (CAN/FlexRay)
- **summary**: This position is not a good fit because it requires fluent German, onsite presence in Munich, and automotive ADAS experience that the candidate lacks.
- **red flag** must_be_based_in (soft): Requires living in a specific place: München (DE)  
  evidence: “München (DE)”
- **red flag** language_required (soft): Requires a language: Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.”

</details>

<details><summary><b>gemini-3.1-flash-lite (default)</b>: score 35</summary>

- **role_match = 5**: The role is focused on data collection and sensor integration for ADAS, which is adjacent to data engineering but involves significant hardware and test-track work.  
  evidence: “Umgang mit Daten, einschließlich Upload, Validierung der hochgeladenen Daten sowie Korrektur und Anpassung bis zur Übergabe der fertigen Daten.” ✓
- **skills_match = 5**: The candidate has strong software and data pipeline skills, but lacks the specific automotive/ADAS hardware and sensor integration experience required.  
  evidence: “Integration verschiedener Systeme, Kameras und Sensoren, einschließlich dGPS und Ground Truth (GT), in Prototypen und Serienfahrzeuge.” ✓
- **seniority_fit = 10**: The job does not specify a seniority level, and the candidate's 3 years of experience are sufficient for an engineering role.  
  evidence: (none)
- **location_eligibility = 0**: The job is onsite in Munich, Germany, and the candidate is based in Tunisia and requires visa sponsorship, which is not offered.  
  evidence: “Zum Einsatz bei einem unserer Kunden suchen wir zum 01.11.2026 einen Data Collection Engineer ADAS (m/w/d)” ✓
- **language_requirements = 0**: The job requires fluent German, which the candidate does not speak.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.” ✓
- **strengths**: Python data pipelines | Software engineering fundamentals | FastAPI and backend development
- **gaps**: Fluent German language | Automotive/ADAS sensor experience | Local work authorization in Germany
- **summary**: The candidate is a strong software engineer with emerging data skills, but is not a fit due to the requirement for fluent German, onsite presence in Munich, and lack of specific automotive sensor experience.
- **red flag** language_required (soft): Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.”
- **red flag** must_be_based_in (hard): Zum Einsatz bei einem unserer Kunden suchen wir zum 01.11.2026 einen Data Collection Engineer ADAS (m/w/d)  
  evidence: “Zum Einsatz bei einem unserer Kunden suchen wir zum 01.11.2026 einen Data Collection Engineer ADAS (m/w/d)”

</details>

<details><summary><b>gemini-3.1-flash-lite (minimal)</b>: score 35</summary>

Identical text to gemini-3.1-flash-lite (default).
</details>

<details><summary><b>gemma-4-31b-it (default)</b>: score 15</summary>

- **role_match = 0**: The job is a hardware-centric test and data collection role for autonomous driving (ADAS), involving test-track coordination and sensor integration, which is entirely different from the software-focused Data Engineering roles in the candidate's track.  
  evidence: “Integration verschiedener Systeme, Kameras und Sensoren, einschließlich dGPS und Ground Truth (GT), in Prototypen und Serienfahrzeuge.” ✓
- **skills_match = 0**: The candidate lacks the core requirements: ADAS experience, a European driver's license, and knowledge of automotive communication protocols (CAN, FlexRay).  
  evidence: “Kenntnisse von Kommunikationsprotokollen wie CAN, FlexRay oder Ethernet sind von Vorteil.” ✓
- **seniority_fit = 10**: The job requires a technical degree or comparable experience, which the candidate possesses.  
  evidence: “Abgeschlossenes technisches Studium oder vergleichbare Berufserfahrung im ADAS-Bereich.” ✓
- **location_eligibility = 0**: The role is onsite in Munich and explicitly requires a valid European driver's license, which the candidate (based in Tunisia) does not have.  
  evidence: “Gültiger europäischer Führerschein” ✓
- **language_requirements = 0**: The job requires fluent German, which the candidate does not speak.  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.” ✓
- **strengths**: Technical degree | Linux basics
- **gaps**: German language | European driver's license | ADAS/Automotive experience
- **summary**: The candidate is entirely unsuitable for this role as it is a hardware-focused ADAS test engineering position requiring fluent German and a European driver's license, whereas the candidate is a software engineer based in Tunisia.
- **red flag** language_required (hard): Requires fluent German  
  evidence: “Fließende Englisch- und Deutschkenntnisse in Wort und Schrift.”
- **red flag** must_be_based_in (hard): Onsite in Munich and requires European driver's license  
  evidence: “Gültiger europäischer Führerschein”

</details>


## 3. Observations

**Read this first: the sample is 3 jobs, so everything below is indicative, not proof.** Also: (a) the baseline was scored against an older experience pool; (b) temperature 0 is not deterministic here (`gemini-3.5-flash-lite` gave 68 vs 78 on the same job with identical settings and 0 thinking tokens); (c) some runs are missing because of 503s and your RPD limits (see below).

**What did not run, and why**
- `gemini-3.8-flash`, minimal thinking: only the *good* job ran. I stopped at 11 attempts to stay inside the ~12 requests/day you had left; 503 retries use attempts. `medium` and `low` are not run.
- `gemini-3.6-flash`: default/medium never got an answer (5 × 503, gave up); minimal/medium and minimal/low were skipped by my 18-attempt guard (20 RPD) after 9 more 503s. Those cells can be completed after the quota resets.
- Minimal thinking: `gemini-3.6-flash` accepted `thinkingLevel: "minimal"`; `gemini-3.8-flash` rejected it and accepted `thinkingBudget: 0` (both then report 0 thinking tokens). On the two lite models thinking is already 0 by default, so "default" and "minimal" are the same setting there.
- Gemma has no thinking switch in the API (it still produced ~1,150-1,530 thinking tokens on 31b).

**Reliability**
- Gemini models accept our JSON schema natively (`responseJsonSchema`) and were schema-valid on the first answer in every run that returned: 100% of the 12 lite runs, 3/3 for 3.8 default, 3/3 for the 3.6 runs that returned.
- `gemini-3.8-flash` and `gemini-3.6-flash` returned 503 "high demand" often: 3.8 had 7 retries across 4 answers (one minimal call also hit my 300 s read timeout, and the successful call still took 179 s); 3.6 had 14 retries across 3 answers, and one job never got through. The lite models had zero errors.
- Both Gemma models reject the native schema (HTTP 400 "invalid argument"), so I fell back to the schema-in-the-prompt path the app already uses for Ollama cloud. They also returned HTTP 500 "internal error" intermittently (retried).
- `gemma-4-31b-it`: valid as returned on 2/3 jobs. The third (good) came back in a code fence wrapped as `{"properties": {...}}`; the app's existing `strip_fence` + `_unwrap_properties` accepts it, so I scored it and marked it "recovered" in the per-job section.
- `gemma-4-26b-a4b-it`: 0/3 usable: one truncated JSON (unclosed object), one empty `MALFORMED_RESPONSE`, one wrong shape (4 schema errors). Not viable in this setup.

**Speed.** Lite models answered in 2-6 s. `gemini-3.6-flash` 12-14 s with default thinking (1.6-2.0k thinking tokens) and ~4 s minimal. `gemini-3.8-flash` 80-98 s default (and 179 s minimal under load): too slow for anything interactive at this load. `gemma-4-31b-it` 75-91 s; `gemma-4-26b-a4b-it` 12-23 s when it answered.

**Evidence (anti-hallucination) check.** Every quoted evidence string was found in the listing, the experience pool, or the metadata lines the prompt itself shows (e.g. `Paris Office (FR)`, `onsite`; these are not in the listing text, so the app's job-only check would count them as unverified; that is the difference between the two evidence columns). So no model invented quotes.
But a verbatim quote is not the same as a *supported claim*, and this is where the cheaper models are weaker:
- `gemini-3.1-flash-lite` on the low job (#3950): said the candidate "requires visa sponsorship, which is not offered" and raised a **hard** `must_be_based_in` flag. The listing never mentions visas or sponsorship (I checked), and the quote it attached ("Zum Einsatz bei einem unserer Kunden suchen wir zum 01.11.2026 einen Data Collection Engineer ADAS") says nothing about location requirements. The quote exists, so the automatic check passes it, yet the flag is unsupported. `gemini-3.8-flash` correctly said the listing makes no statement on visas for the same job.
- `gemini-3.5-flash-lite` gave the low job 52 (baseline 21) by rating role and skills 5 ("adjacent to the Data Engineer track") for a hardware test-track ADAS role; the larger models and the baseline gave 0.
- Reasons from the lite models are generic ("aligns perfectly with ... requirements", skills 10 on the good job with no gap named). The thinking models name concrete gaps: `gemini-3.8-flash` "lacks professional experience with WebSockets, MCP integrations, and running large-scale asynchronous generation pipelines", `gemini-3.6-flash` "lacks explicit exposure to multimodal media production tools or WebSockets".

**Scores vs baseline (94 / 62 / 21)**
- `gemma-4-31b-it` is closest overall: 97 / 70 / 15, correct ranking, spread 82 (baseline 73), and reasons that read like the baseline's (same hardware-vs-software and licence reasoning on the low job). It is the same model family as the baseline.
- The Flash/Lite models under-score the good job (62-85) and compress the range. `gemini-3.8-flash` default: 62 / 62 / 22: **good and medium tie, so the ranking fails**. `gemini-3.6-flash` default: 62 / – / 22. The 3.8 and 3.6 models are the closest on the low job (22), as are 3.1-lite (35) and Gemma 31b (15); 3.5-lite is far (52).
- `gemini-3.6-flash` minimal gave the good job 85, the closest Gemini result to 94, but it is one run.
- Models that ranked good > medium > low: `gemini-3.5-flash-lite` (both modes), `gemini-3.1-flash-lite` (both modes), `gemma-4-31b-it`. The good/low spread of the lite models is only 16-43 points vs 73 for the baseline, so they discriminate weakly.


## 4. Recommendation

Two caveats apply to both choices: this is 3 jobs, and the only evidence for "closest to the baseline" is agreement with another LLM's scores, not with your own judgment. Before changing any default, run `make eval` on your labeled jobs with the candidate model.

**Bulk scoring: keep `gemma4:31b-cloud` (Ollama) as it is.** If you want a free Gemini-side option for bulk, the only candidate from this test is `gemma-4-31b-it`:
- closest to the baseline (97 / 70 / 15, correct ranking, evidence grounded, reasons comparable);
- the only free model with enough quota: 14,400 RPD. The binding limit is TPM (16K ÷ ~5.5k input tokens ≈ 2.9 jobs/min ≈ 4,100 jobs/day, so 1,000 jobs ≈ 5.8 h), and with ~80 s latency it needs about 4 jobs in flight;
- it needs the schema-in-prompt path, `_unwrap_properties`, and retries on HTTP 500; it was valid as returned on 2 of 3 jobs, so expect some retries or failures. Do not use `gemma-4-26b-a4b-it` (0/3 usable).
- Not for bulk: `gemini-3.8-flash` / `gemini-3.6-flash` (20 RPD is 1,000 jobs in 50 days, plus 503s); the lite models (fast, 500 RPD = 2 days per 1,000 jobs, but they under-rate good jobs, one over-rated a low job at 52, and one raised an unsupported *hard* flag, which in our arithmetic caps the score).

**Per-job "Rate with Gemini" button: `gemini-3.6-flash`, with a fallback to `gemma-4-31b-it`.**
- One job per click suits 20 RPD, and 12-14 s (default thinking) or ~4 s (minimal) is acceptable for a button; 3.8-flash at 80-180 s is not.
- Its reasoning is specific and its evidence was grounded; it matched the baseline on the low job (22 vs 21) and with minimal thinking came closest on the good job (85).
- Weak points: 503s are common (14 retries in this test and one job that never answered), so the button needs a retry with backoff and a visible fallback to `gemma-4-31b-it`; and with default thinking it scored the good job 62.
- Use it as a **second opinion shown next to the stored score, never written over it**. Minimal vs default thinking is unsettled: the minimal runs for medium and low are missing, so I would not pick one until those two cells are run after the quota resets (say so and I'll complete them).
