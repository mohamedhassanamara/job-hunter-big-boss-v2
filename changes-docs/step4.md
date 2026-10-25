# Architecture & Engineering Changelog: Cold Outreach Overhaul (v15)

**Date:** October 24, 2026

**Status:** Completed, Verified in CI, and Validated Live on Production Applications

**Modules Affected:** `backend/app/prompts/outreach.md`, `backend/app/providers/base.py`, `backend/app/services/applied_check.py`, `backend/app/services/outreach.py`, `backend/app/services/outreach_check.py`

---

## 1. Executive Summary & Root Cause Analysis

### Background & Failure Modes of Legacy Pipeline

* **Unprompted Visa Apology Disclaimers:** Prompt version 14 (`prompts/outreach.md`) and the Pydantic schema `AppliedEmailPlan` contained a dedicated `constraint` field. The prompt explicitly instructed the model: *"Offer the way out kindly ('if that rules me out, I understand')."* Simultaneously, `services/outreach.py:logistics()` unconditionally injected the candidate's residency (`Tunis, Tunisia`) and work authorization status into the LLM payload. As a result, drafts frequently volunteered premature sponsorship requests and defensive caveats.
* **Passive Severity Handling:** In `services/applied_check.py`, unrequested location disclaimers were classified only as `severity="warning"`. Because warnings do not halt draft persistence, emails containing self-disqualifying statements bypassed quality gates.
* **Missing Recipient Persona Adaptation:** The legacy prompt instructed the model to evaluate only the job posting when selecting facts. Consequently, drafts sent to platform, OEM, and backend engineering managers used entry-level UI phrasing (*"built mobile interfaces across many screens"*) rather than discussing API contracts, offline sync, Clean Architecture, or platform telemetry.

---

## 2. Technical Implementation Details

```
Legacy Pipeline:
[ Candidate Logistics (Visa: Yes) ] ──► Gemini 3.5 Flash ──► Constraint Block ("If that rules me out...") ──► Warning Only ──► Sent to User

New Pipeline (v15):
[ Sanitized Logistics (Languages only) ]
                  │
[ Recipient Title + Job Description ] ──► Gemini 3.5 Flash (v15 Prompt)
                                                  │
                                                  ▼
                                      AppliedEmailPlan (Constraint Stripped)
                                                  │
                                                  ▼
                          Deterministic Regex Guard (_VISA_DISCLAIMER_WORDS)
                                                  │
                      ┌───────────────────────────┴───────────────────────────┐
                      ▼                                                       ▼
            [ Visa Mention Found ]                                  [ Clean Pass ]
                      │                                                       │
           Blocking Error (Auto-Retry)                                Body Assembly & DB Persistence

```

### Step 1: Schema Deprecation & Sanitization (`backend/app/providers/base.py`)

* In `AppliedEmailPlan`:
* Deprecated and removed `constraint: str` and `constraint_quote: str` from the LLM JSON schema.
* Added `model_config = ConfigDict(extra="ignore")` and a backward-compatible `@property def constraint(self) -> str: return ""` to prevent breaking queries against historical records.



### Step 2: Body Assembly & Blocking Deterministic Checks (`backend/app/services/applied_check.py`)

* **Body Assembly:** Updated `body()` to concatenate only:

$$\text{greeting} + \text{opening} + \text{experience} + \text{ask}$$



The deprecated constraint field is completely omitted from the rendered text.
* **Hard Regex Guard:** Added strict scanner `_VISA_DISCLAIMER_WORDS`:
```python
_VISA_DISCLAIMER_WORDS = re.compile(
    r"\b(?:visas?|sponsorship|sponsor\w*|work authori[sz]ation|work permit|right to work|rules me out|relocat\w*)\b",
    re.I
)

```


Any occurrence in `plan.opening`, `plan.experience`, or the assembled body emits a blocking `violation("visa_disclaimer_banned", ..., severity="error")`, automatically triggering the retry loop.
* **Banned Phrases:** Added `"rules me out"` to `DEFAULT_BANNED` in `app/services/outreach_check.py`.

### Step 3: Payload Sanitization (`backend/app/services/outreach.py`)

* Updated `logistics(pool)` to return strictly `{"languages": langs}`.
* Completely removed `based_in`, `work_authorization`, and `relocation` from the LLM prompt payload in `applied_request()` and `intro_request()`.

### Step 4: Persona-Aware Prompt Overhaul (`backend/app/prompts/outreach.md` v15)

* Bumped version to `version: 15` and registered hash `"e00b50e7e16b7126"` in `versions.json`.
* **Persona Guidance Matrix:** Instructed the model to dynamically pivot based on `CONTACT.title`:
* **Mobile Lead / Frontend:** Emphasize Flutter/Dart architecture, state management (Riverpod/BLoC), clean code, memory leak elimination, and app store delivery.
* **OEM / Platform / Backend / Systems Lead:** Emphasize robust API integration, WebSocket sync, offline-first caching (Drift/SQLite), and native platform channels (Swift/Kotlin).
* **Engineering Manager / Director:** Emphasize end-to-end feature ownership, automated testing culture (~80% code coverage), and reducing integration time.
* **CTO / Founder:** Emphasize shipping production apps from concept through store release and performance optimization.


* **Negative Constraints:** Explicitly banned vague tutorial phrasing (*"across many screens"*, *"connected to backend services"*) and strictly prohibited any mention of visas or relocation.

---

## 3. Test Verification & Empirical Results

### Automated Regression Suite

Ran the complete outreach and prompt test suites:

```bash
backend/.venv/bin/pytest backend/tests/test_outreach.py backend/tests/test_applied_email.py backend/tests/test_prompt.py backend/tests/test_intro_email.py backend/tests/test_email_route.py backend/tests/test_email_step_v2.py

```

* **Result:** **154 / 154 passed** in 43.01s.

### Live Production Execution (Application 894 - Nextlane)

Executed live draft generation addressing **Tonny Svensson** (`Senior Engineering Manager`):

* **Model:** `gemini-3.5-flash-lite` (via official Generative AI API).
* **Prompt Version:** `outreach/v15`.
* **Output:**
* Clean engineering tone highlighting Riverpod, Clean Architecture, and store deployments.
* **0 visa or sponsorship mentions.**
* **0 blocking violations.**



---

With **Job Fit Scoring** (APInex MiniMax + 15 RPM throttling + direct Ollama failover), **CV Generation** (2-pass architecture + elastic LaTeX + 98% fullness target), and **Cold Outreach** (v15 prompt + visa ban + persona adaptation) all implemented and passing tests, the core pipelines are updated.