# Migration & Architecture Changelog: Selective Rescoring, Adzuna Scraper Repair & Cross-Source Deduplication

**Date:** October 25, 2026

**Status:** Specification & Architecture Staged

**Modules Affected:** `backend/app/api/scoring.py`, `backend/app/services/scoring.py`, `backend/app/services/job_sources/`, `backend/app/services/dedup.py`, `backend/app/models/job.py`, `frontend/src/features/scoring/`, `frontend/src/features/job/`

---

## 1. Executive Summary & Problem Scope

Following the migrations of **Job Fit Scoring** (APInex MiniMax M3.1 Flash with 15 RPM throttling and direct Ollama failover), **CV Generation** (2-pass architecture, Source Sans Pro typography, and 98%–100% page fill), and **Cold Outreach v15** (visa disclaimer eradication and persona tailoring), three operational bottlenecks were identified in daily job discovery and queue management:

1. **Monolithic Rescoring Queue**:
* Any change to prompt rubrics or model setups triggered a coarse, all-or-nothing rescore across 4,000+ historical records.
* Under a strict 15 RPM gateway budget, an unsegmented rescore of 3,300+ jobs takes ~3.7 hours and consumes unnecessary quota on stale, non-target positions.


2. **Adzuna Scraper Ingestion Failure**:
* The Adzuna ingestion source ceased returning active listings or failed silently during aggregation runs due to missing country-specific routing parameters, outdated API key configuration, or unhandled 400/401 HTTP responses.


3. **Multi-Source Job Duplication**:
* Identical positions indexed across multiple channels (e.g., Adzuna, LinkedIn, Indeed, direct company career boards) were persisted as separate `Job` rows.
* This multiplied LLM scoring costs, created artificial queue bloat, distorted dashboard pipeline metrics, and cluttered the user review feed.



---

## 2. Technical Architecture & Module Specifications

```
Ingestion & Queue Architecture:
                                              
[ Adzuna API ] ──► (Country Base URL + Auth) ──┐
[ LinkedIn   ] ────────────────────────────────┼──► Deduplication Engine (Normalized Fingerprinting)
[ Other      ] ────────────────────────────────┘           │
                                                           ├── [ New Job ] ────► Create Canonical Job
                                                           └── [ Match Found ] ─► Append Source Badge & Upgrade Description
                                                                                       │
Selective Rescoring Architecture:                                                      ▼
[ UI Modal: Track / Date / Batch Filter ] ────────────────────────────────► Filtered SQL Query
                                                                                       │
                                                                                       ▼
                                                                     15 RPM Rolling Scoring Queue

```

---

### Step 1: Targeted & Segmented Rescoring Pipeline

#### A. Backend API & Filtered SQL Query (`backend/app/api/scoring.py` & `backend/app/services/scoring.py`)

* Replaced the unconditional bulk rescoring endpoint with a parameterized enqueue contract:
```python
class RescoreFilterRequest(BaseModel):
    track: str | None = None          # e.g., "mobile", "backend", "fullstack"
    since_days: int | None = None     # Filter jobs created/scraped within last N days
    limit: int | None = None          # Cap maximum jobs to queue in one batch
    only_unscored: bool = False       # Target only jobs missing a valid FitAssessment
    job_ids: list[int] | None = None  # Explicit target IDs

```


* **Query Builder**:
* Constructs dynamic SQL queries filtering `Job` rows where `status != 'dismissed'`.
* Applies indexed criteria on `job.track`, `job.created_at >= (now() - interval 'N days')`, and joins against `fit_assessment` to identify unassessed or outdated records.
* Enqueues only qualifying IDs directly into `ScoringQueue`, preventing non-target tracks (such as dismissed Java backend listings) from occupying rate-limited gateway slots.



#### B. Frontend Rescore Controls (`frontend/src/features/scoring/RescoreModal.tsx`)

* Replaced the generic "Rescore outdated jobs" button with an interactive modal:
* **Track Dropdown**: Filter by specific tracks (*"Mobile / Flutter"*, *"Backend"*, *"All Tracks"*).
* **Time Range Selector**: Presets for *Last 7 days*, *Last 30 days*, or *All time*.
* **Batch Ceiling**: User-selectable caps (25, 50, 100, or unlimited).
* **Quota Telemetry Estimate**: Computes queue ETA and estimated rate-limit usage (e.g., *"Queuing 45 jobs · ~3.0 min at 15 RPM"*).



---

### Step 2: Adzuna Job Source Diagnostic & Repair

#### A. Country-Specific Route & Authentication Validation (`backend/app/services/job_sources/adzuna.py`)

* **Endpoint Architecture**:
* Adzuna requires localized endpoints based on job country:
* Germany: `[https://api.adzuna.com/v1/api/jobs/de/search/1](https://api.adzuna.com/v1/api/jobs/de/search/1)`
* United Kingdom: `[https://api.adzuna.com/v1/api/jobs/gb/search/1](https://api.adzuna.com/v1/api/jobs/gb/search/1)`
* France: `[https://api.adzuna.com/v1/api/jobs/fr/search/1](https://api.adzuna.com/v1/api/jobs/fr/search/1)`


* Fixed endpoint string formatting to dynamically route queries according to the target market instead of issuing requests against a single global host.


* **Credentials & Configuration**:
* Enforced validation of `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` from `app/config.py` and `.env`.
* Added proactive checking: if credentials are empty or missing, log a structured warning and bypass the crawler gracefully without interrupting global source ingestion.


* **Error Handling & Resilience**:
* Wrapped HTTP calls in `httpx.AsyncClient` with explicit status inspection:
* `HTTP 401 / 403`: Logs authentication errors and halts the Adzuna worker.
* `HTTP 400`: Logs exact validation response (e.g., malformed parameter, unsupported country code).
* `HTTP 429`: Implements exponential backoff before retrying.





---

### Step 3: Cross-Source Job Deduplication & Grouping

#### A. Deterministic Normalization & Fingerprinting (`backend/app/services/dedup.py`)

Implemented a two-stage normalization algorithm to identify identical listings across different scraping channels:

1. **Company Name Canonicalization**:
* Lowercase and strip punctuation.
* Strip legal corporate entities: `gmbh`, `ag`, `ltd`, `inc`, `corp`, `sarl`, `sl`, `bv`, `sa`, `llc`.
* Standardize whitespace (e.g., `"Bloomwell Group GmbH"` $\to$ `"bloomwell group"`).


2. **Job Title Normalization**:
* Lowercase and strip punctuation.
* Remove gender markers and regional tags: `(m/w/d)`, `(all genders)`, `(f/m/d)`, `m/f/d`, `hybrid`, `remote`, `full-time`.
* Standardize engineering titles (e.g., `"Senior Flutter Developer (m/w/d) - Remote"` $\to$ `"senior flutter developer"`).


3. **Fingerprint Signature**:

$$\text{fingerprint} = \text{SHA256}(\text{norm\_company} \mathbin{\Vert} \text{"\:\:"} \mathbin{\Vert} \text{norm\_title})$$


* Supplementary check: Normalizes and compares clean direct application URLs or exact text similarity on job description openings.



#### B. Database Schema & Source Grouping (`backend/app/models/job.py`)

* Added source aggregation metadata to the `Job` model:
* `sources: list[str]` (stores unique providers, e.g., `["adzuna", "linkedin"]`).
* `source_urls: dict[str, str]` (maps provider names to their respective application/portal URLs).
* `canonical_job_id: int | None` (optional foreign key for multi-record clustering).


* **Ingestion Merge Logic**:
* When an incoming job matches an existing active listing:
1. Do **not** create a new `Job` row.
2. Do **not** enqueue a redundant scoring run.
3. Append the new source name and URL to `job.sources` and `job.source_urls`.
4. If the newly scraped description contains higher character length or richer Markdown formatting than the stored record, update `job.description` with the fuller text.





#### C. Frontend Multi-Source Grouping (`frontend/src/features/job/JobCard.tsx`)

* Updated the job list and card views to render multi-source origin badges:
* Badges for each indexing source: `[Adzuna]`, `[LinkedIn]`, `[Direct Board]`.
* Clicking an individual source badge opens that specific platform's listing URL in a new tab.
* Prevents duplicate entries from cluttering the main review dashboard and application pipeline.



---

## 3. Verification & Operational Safeguards

1. **Selective Enqueue Test**:
* Verified that triggering a rescore for `track="mobile"` only queues mobile listings and leaves backend/dismissed jobs untouched.


2. **Adzuna Live Verification**:
* Validated that queries against `[https://api.adzuna.com/v1/api/jobs/de/](https://api.adzuna.com/v1/api/jobs/de/)` return HTTP 200, parse cleanly into the ingestion pipeline, and populate source metadata correctly.


3. **Deduplication Test**:
* Verified that ingesting identical test listings from two distinct providers results in a single canonical database record displaying both source badges.ch