# Migration & Architecture Changelog: Job Fit Scoring Engine

**Date:** October 24, 2026

**Status:** Completed & Verified in Production Pipeline

**Module:** `backend/app/services/scoring.py`, `backend/app/providers/`, `backend/app/prompts/`

---

## 1. Executive Summary & Root Cause Analysis

### Background & Failure of Initial Setup

* **Google Cloud Free-Tier Key Pooling Failure:** The original scoring architecture relied on rotating multiple free Google AI Studio keys (`gemini-3.5-flash-lite`) via `gemini_keys.py` to handle 70+ daily job evaluations. Google's automated anti-abuse heuristics detected concurrent/sequential requests originating from identical client IPs running the same prompt body across multiple unbilled projects, flagging the pattern as quota evasion and suspending the Google Cloud project.


* **Reseller Quota & Token Multiplier Reality:** Third-party gateway tiers advertising 3M tokens/day were evaluated. Analysis revealed models had $\times 2$ to $\times 4$ token consumption multipliers. Scoring 70 jobs plus generating 30 CVs consumed between 1.2M and 1.8M raw tokens, which scaled to 3.6M–5.4M counted tokens under $\times 3$ tiers, running the quota dry midday.


* **Rubric Bias Against Foreign Applicants:** Prompt version 6 (`prompts/fit_score.md`) heavily penalized non-EU candidates targeting European positions, assigning location scores of 15–20/100 and triggering premature disqualifications under the mistaken assumption that every EU role requires rigid corporate legal sponsorship (like US H-1B or UK licences).



---

## 2. Benchmark & Model Selection

A live evaluation benchmark was executed across 11 free-tier models on the APInex gateway using an identical candidate profile and production job description (Healy World GmbH Flutter Developer).

### Benchmark Results Overview

| Model | Status | Latency | Tokens (In/Out) | Multiplier | Score / Verdict | JSON Valid | Key Evaluator Finding |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **`free/minimax-m3.1-flash`** | **OK**

| **3.19s**

| 2,982 / 555

| **$\times 2$ (Cheapest)**

| **72 / `apply**`

| **Yes**

| **Top Pick.** Correctly distinguished between needing a visa vs. employer legal sponsorship. Cleanest token efficiency.

|
| `free/deepseek-v4.1-flash` | **OK**

| 2.92s

| 2,984 / 409

| $\times 3$

| 78 / `maybe`

| Yes

| Highly accurate reasoning, but carries higher token burn. Selected as fallback.

|
| `free/glm-5.3-flash` | **OK**

| 2.71s

| 2,988 / 421

| $\times 3$

| 78 / `maybe`

| Yes

| Fastest response time, but penalized location too severely (15/100).

|
| `free/gemini-3.8-flash` | **OK**

| 3.30s

| 2,979 / 510

| $\times 3$

| 78 / `maybe`

| Yes

| Solid output, but lower gateway uptime history (96.1%).

|
| `free/glm-5.3-flashx` | **OK**

| 4.43s

| 2,989 / 476

| $\times 3$

| 82 / `apply`

| Yes

| Hallucinated German immigration law (claimed Flutter is barred from the shortage list).

|
| `free/jev-1.13` | **FAIL**

| 0.19s

| 0 / 0

| $\times 2$

| - / `-`

| No

| Rejected with HTTP 400 (requires non-standard `/v1/decisions` endpoint).

|

---

## 3. Implementation Details

### Step 1: Resilient Client Adapter (`app/providers/apinex_client.py`)

* Created an asynchronous client communicating directly with `[https://apinex.bond/v1/chat/completions](https://apinex.bond/v1/chat/completions)`.
* **Primary Model:** `free/minimax-m3.1-flash`.


* **Fallback Model:** `free/deepseek-v4.1-flash`.


* Implemented automatic response sanitization (stripping `json ... ` fences) and JSON parse verification.
* Configured automated fallback: if the primary model returns a non-200 status code, invalid JSON, or times out (>60s), the request immediately reroutes to the fallback model.

### Step 2: Strict Rolling 15 RPM Rate Limiter

To prevent queue bursts from overwhelming the gateway and triggering `HTTP 429` errors:

* Implemented a thread-safe and async-safe sliding-window rate limiter using `asyncio.Lock` and a `collections.deque` tracking request timestamps.
* Enforced a hard limit of **15 requests per 60-second window** across all parallel workers. Any excess requests asynchronously sleep until the oldest timestamp exits the window.
* Backs off on HTTP 429 and raises `QuotaExceeded` only if both APInex primary and fallback models fail.

### Step 3: Hard-Locking Gemini Out of the Scoring Engine

To prevent any accidental calls to Google Cloud APIs from legacy configurations:

1. **Registry Guard (`app/providers/registry.py`):**
```python
if model.startswith("gemini-"):
    raise ValueError("Gemini is deprecated for scoring")

```


2. **API Endpoint Guard (`app/api/scoring.py`):**
```python
if model.startswith("gemini-"):
    raise HTTPException(400, "Gemini is deprecated for scoring")

```


3. **Settings Guard (`app/services/model_choice.py`):**
* Validates incoming settings payloads and rejects any attempt to persist a `gemini-*` model for scoring with an HTTP 422 error.



### Step 4: True Local Fallback to Ollama

* Integrated `QuotaExceeded` handling into `ScoringQueue` in `app/services/scoring.py`.
* When APInex quota or gateway connectivity is exhausted, the queue logs a warning and shifts subsequent scoring tasks to the configured local/cloud Ollama model (defaulting to `qwen2.5:7b` / `gemma4:31b-cloud`).


* Directly instantiates `OllamaFitScorer` pointing to `http://localhost:11434/api/chat`, ensuring zero dependencies on external cloud APIs during quota outages.



### Step 5: Overhaul of the Scoring Rubric (`app/prompts/fit_score.md` v7)

Updated the prompt to version 7 and refreshed the body hash in `versions.json`:

* **Visa Realism:** Explicitly instructed the model that non-EU candidates targeting EU countries (Germany, France, Spain, Belgium) self-file their work permits (e.g., EU Blue Card) upon signing an employment contract. The model only flags location disqualifications if the job explicitly states: *"Must already possess valid local work authorization at the time of application"* or requires defense/security clearance.
* **Weighting Balance:** Mandatory technical requirements are scored strictly under `skills_match`, while "nice-to-haves" / "pluses" (such as German for an English-speaking role) are evaluated as bonus points rather than deductions.
* **Schema Integrity:** Preserved the 0–10 sub-score range expected by `FitCard.tsx` and the database while retaining `overall_score` (0–100) and `verdict` (`apply`, `maybe`, `skip`).

### Step 6: Frontend & UI State Synchronization

* **Settings Page (`sections.tsx`):** Replaced free-form text inputs with curated `<Select>` dropdowns featuring APInex models (`free/minimax-m3.1-flash`, `free/deepseek-v4.1-flash`, `free/gpt-6-luna`, `free/glm-5.3-flash`, `free/mimo-v2.6-pro`) and Ollama models.


* **Scoring Card (`ScoringTodayCard.tsx`):** Completely removed the legacy Google Cloud quota alert card (`"Gemini: single key, accounts under review..."`). Replaced it with the APInex status badge: `APInex Gateway · 15 RPM throttle active · Ollama fallback ready`.



---

## 4. Test Verification & Operational Status

1. **Automated Unit Tests:**
* Ran `pytest backend/tests/test_prompt.py backend/tests/test_scoring.py`.
* All 27 unit tests passed, including `test_gemini_is_hard_deprecated_for_scoring`.


2. **Frontend Build:**
* Ran `npm --prefix frontend run build`. Clean compile with zero TypeScript or Vite errors.


3. **Live Execution (`scripts/verify_apinex.py`):**
* Confirmed live scoring through `[https://apinex.bond/v1](https://apinex.bond/v1)` using `free/minimax-m3.1-flash`.


* Latency clocked at ~3.2 seconds, returning valid JSON with no premature visa disqualifications for European targets.