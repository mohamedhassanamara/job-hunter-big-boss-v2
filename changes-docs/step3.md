# Architecture Addendum: APInex 429 Intelligent Backoff & Single-Model Direct Failover

**Date:** October 24, 2026

**Status:** Completed, Verified in CI, and Tested Against Simulated Gateway Throttling

**Modules Affected:** `backend/app/providers/apinex_client.py`, `backend/app/services/scoring.py`, `backend/app/providers/registry.py`, `backend/app/api/scoring.py`, `frontend/src/features/settings/sections.tsx`

---

## 1. Problem Statement & Root Cause

### The Bug

During batch scoring, `ScoringQueue` abruptly logged:

> *"Scoring switched from free/minimax-m3.1-flash to local gemma4:31b-cloud (slower): APInex quota/rate limit exhausted on primary and fallback: HTTP 429 Too Many Requests: `{"error":{"message":"Rate limit exceeded. Max 15 requests per minute for this account. Retry in 1s.","type":"rate_limit_error"}}`"*

### The Root Cause

1. **Per-Account Limit Conflation:** APInex enforces a **15 RPM limit per account**, not per model. When `free/minimax-m3.1-flash` received a transient burst 429, the client immediately retried using the fallback model (`free/deepseek-v4.1-flash`). Because the account window was already full, the fallback call instantly returned the exact same 429 error.
2. **Treating Burst Rate Limits as Permanent Exhaustion:** The client immediately raised `QuotaExceeded`, confusing a 1-second burst pause (`"Retry in 1s"`) with an unrecoverable daily token exhaustion. This triggered `ScoringQueue` to immediately abandon cloud scoring and permanently downgrade to local Ollama.

---

## 2. Changes Implemented

```
Old Architecture (Flawed Fallback):
[ Request ] ──► free/minimax-m3.1-flash 
                       │ (HTTP 429: "Retry in 1s")
                       ▼
            free/deepseek-v4.1-flash (Immediately fails: same account limit)
                       │
                       ▼ (Raises QuotaExceeded)
            Permanent switch to local Ollama (Premature)

New Architecture (Intelligent Backoff + Single Model):
[ Request ] ──► free/minimax-m3.1-flash 
                       │
             (HTTP 429: Parse delay)
                       │
             Sleep (delay + 1.5s margin) ──► Retry primary model (up to 3 attempts)
                       │
            (If permanent quota exhausted or 3 retries fail)
                       │
                       ▼
            Switch directly to configured local Ollama (qwen2.5:7b)

```

### 1. Dynamic Retry-After Parsing & Sleep Backoff

* Located in `APInexClient` (`backend/app/providers/apinex_client.py`).
* On receiving an `HTTP 429`:
* Inspects the `Retry-After` header or matches regex `r"Retry in (\d+(?:\.\d+)?)s"` in the error JSON.
* Calculates `sleep_duration = extracted_delay + 1.5s` (defaults to `4.0s` if unparsed).
* Asynchronously sleeps without blocking other threads, then retries `free/minimax-m3.1-flash`.
* Allows up to **3 consecutive retry attempts** before escalating.



### 2. Elimination of Redundant APInex Fallback (`free/deepseek-v4.1-flash`)

* **Backend:** Removed `free/deepseek-v4.1-flash` from `apinex_client.py`, `registry.py`, and `scoring.py`. `DEFAULT_MODEL` is strictly locked to `free/minimax-m3.1-flash`.
* **Frontend:** Removed DeepSeek from the curated models dropdown in `sections.tsx`.
* **Failover Path:** The only fallback for APInex is now **direct failover to local Ollama** (`qwen2.5:7b` / `gemma4:31b-cloud`), avoiding redundant secondary calls to a throttled gateway account.

### 3. Pre-Request Timestamp Registration in `RollingRateLimiter`

* Moved the monotonic timestamp registration to execute **inside the lock before awaiting the network call**.
* This prevents concurrent queue workers from starting parallel outbound connections that exceed 15 requests within any rolling 60-second window.

### 4. True Quota vs. Rate Limit Discrimination

* `QuotaExceeded` is now **only** raised if:
1. The error response explicitly reports daily credit or token exhaustion (e.g., `insufficient_quota`, `daily_limit`).
2. All 3 backoff retry attempts fail with persistent 429s.



---

## 3. Verification & Test Coverage

* **Automated Unit Tests:**
* Updated `backend/tests/test_scoring.py`:
* Added test verifying `APInexClient` parses transient 429 delays, sleeps, and retries successfully.
* Added test verifying 3-attempt exhaustion raises `QuotaExceeded`.
* Added test verifying immediate daily quota exhaustion triggers failover.


* `pytest backend/tests/test_scoring.py backend/tests/test_prompt.py` $\rightarrow$ **28 passed, 1 skipped** (live test).


* **Frontend Build:**
* `npm --prefix frontend run build` $\rightarrow$ Clean build, **0 TypeScript or Vite errors**.
