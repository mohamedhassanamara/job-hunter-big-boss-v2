# Migration & Architecture Changelog: 2-Pass CV Generation & Elastic Layout Engine

**Date:** October 24, 2026

**Status:** Completed, Verified in CI, and Validated Live on Production Applications

**Modules Affected:** `backend/app/providers/apinex_cv.py`, `backend/app/services/cv_build.py`, `backend/app/services/cv_rules.py`, `backend/app/services/cv_render.py`, `templates/default/cv.tex.j2`

---

## 1. Executive Summary & Root Cause Analysis

### Background & Failure Modes of the Legacy Pipeline

* **JSON Syntax Crashes on Monolithic Generation:** The previous generation flow attempted to produce the entire CV—the 2-sentence summary, all role metadata, adapted bullet points for every role, project records, and 4 skill groups—in a single continuous LLM call (~1,200+ completion tokens). Benchmark evaluation showed that fast models (such as `deepseek-v4.1-flash` and `muse-spark-1.3`) failed with unrecoverable JSON parsing syntax errors (`char 3838`, `char 3893`) due to buffer cut-offs or malformed trailing brackets.
* **Premature 88% Exit Condition:** `DEFAULT_STRUCTURE["fill_min"]` in `cv_rules.py` was hardcoded to `0.88`. Even though template configs stated `0.92`, the fitting loop evaluated `0.88` first and stopped the moment a document reached 88.1% vertical height. This intentionally left 12% of the page blank at the bottom.
* **The Allowance Ceiling Trap:** In `cv_rules.py:allowance()`, upper bounds (`hi`) for bullets were capped too strictly (current role: max 4; past roles: max 3; projects: max 2). Once all entries reached their maximums, the `grow()` function found 0 candidates and halted expansion, even when 10% of the page remained empty.
* **Coarse Project-Dropping Avalanche:** When an initial draft slightly overflowed page 1 (e.g., 1.019 pages = ~1-2 lines on page 2), the shrink loop dropped an entire project at once. This removed ~5 lines simultaneously, collapsing page fill straight down to ~90%. Because 90% was greater than the 88% target floor, the engine stopped without refilling the void with role bullets.
* **Static LaTeX Spacing:** `cv.tex.j2` used static point values (`titlespacing 6pt/4pt`, `itemsep 1.5pt`) combined with `\raggedbottom`, forbidding the LaTeX engine from distributing vertical glue across sections.

---

## 2. Architectural Changes & Implementation Details

```
Legacy Pipeline (Monolithic):
[ Job + Pool ] ──> Single LLM Pass (~1,200 tokens) ──> Rigid Allowance Cap (hi: 4/3/2) ──> Early Exit at 88% ──> ~89-91% Fill (Empty Bottom)

New Pipeline (2-Pass Elastic):
[ Job + Pool ] 
      │
      ├─► Pass 1: Selection Planner (APInex MiniMax M3.1 Flash, ~300 tokens) ──> Preserves Timeline & Roles
      │
      └─► Pass 2: Polish Engine (Grounded Summary + Impact Bullets)
                │
                ▼
      Expanded Headroom (hi: 5/4/4) ──► Elastic LaTeX Glue (\titlespacing, \itemsep) ──► Target: 96%–100% Fill

```

### Step 1: 2-Pass Generation Engine (`backend/app/providers/apinex_cv.py`)

Implemented `APInexCVGenerator` utilizing `free/minimax-m3.1-flash`:

* **Pass 1: Structure & Selection Planner:**
* Inputs: Job description, track emphasis tags, and candidate master experience pool.
* Responsibility: Selects which roles to emphasize, prioritizes source fact indices, selects up to 3 relevant projects, and groups up to 4 skill categories.
* Guarantee: Enforces timeline continuity by maintaining every professional role from the pool. Runs in ~2.0 seconds with a compact ~300-token output, completely eliminating JSON syntax crashes.


* **Pass 2: Summary & Bullet Text Polisher:**
* Inputs: Only the chosen facts from Pass 1, writing guide, style exemplar, and job requirements.
* Generates the two-sentence summary strictly grounded in professional track facts:
* *Sentence 1:* Target title + professional track years.
* *Sentence 2:* Concrete systems built from pool items (grammatical subject without "I", no bare verbs, zero banned buzzwords).
* Generates an alternative `summary_short_sentences` (~20 words) for tight pages.


* Adapts bullet points to highlight outcomes and action verbs while keeping lengths within $\pm 15\%$ of source facts and preserving all metrics and tool names.
* Assembles the validated `CVPlanDraft` and returns a clean `CVPlan`.



### Step 2: Allowance Ceilings & Fullness Target Tuning (`cv_rules.py`)

* **Retargeted Minimum Fill:** Raised `fill_min` from `0.88` to **`0.96`** across `DEFAULT_STRUCTURE` and `templates/default/cv.config.yaml`.
* **Summary Ceiling:** Increased `summary_max_words` from `45` to `48` to allow natural sentence structure without truncation.
* **Expanded Section Allowances (`hi` Headroom):**
* `current`: Expanded to `[3, 5]` bullets (previously `[3, 4]`).
* `long_role`: Expanded to `[2, 4]` bullets (previously `[2, 3]`).
* `projects_max`: Expanded to `3` projects (previously `2`).
* `project_bullets`: Expanded to `[2, 4]` bullets (previously `[2, 3]`).


* *Impact:* The `grow()` function now has headroom to add 2–4 high-impact lines whenever a document is sitting in the 89%–94% range.

### Step 3: Fitting Loop Refinement (`cv_build.py`)

* **Target Enforcement:** Updated `fit_to_page()` to resolve `target = max(0.96, float(lay.rules.get("fill_min") or template.min_fill))`.
* **Graduated `shrink()` Progression:**
* Minor overflows ($< 3.0$ lines) no longer drop projects immediately.
* The engine first attempts switching to `short_summary` (~2 lines saved) and pruning single bullets from lower-priority roles.
* Projects are only dropped if bullet pruning across roles has already reached minimum thresholds (`lo`).


* **Micro-Spacing Fallback:**
* Added `micro_spacing: bool` to `FitState` and `cv_render.py:render_tex()`.
* If all roles and projects reach their `hi` ceiling and the page is between 90% and 95%, `state.micro_spacing = True` activates, prompting LaTeX to expand spacing into the 96%–100% target range.



### Step 4: Elastic LaTeX Typography (`templates/default/cv.tex.j2`)

* **Removed `\raggedbottom`:** Permitted the LaTeX rendering engine to balance vertical glue evenly across sections instead of pooling unused white space at the bottom.
* **Elastic Section Spacing:**
```latex
\titlespacing*{\section}{0pt}{5pt plus 2pt minus 1pt}{3pt plus 1pt minus 1pt}

```


* **Elastic Item & List Separation:**
```latex
\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0pt, label={}, itemsep=4pt plus 2pt minus 1pt, topsep=2pt plus 1pt]}
\newcommand{\resumeItemListStart}{\begin{itemize}[leftmargin=14pt, itemsep=1.5pt plus 1pt minus 0.5pt, topsep=2pt plus 1pt minus 1pt, parsep=0pt]}

```


* **Dynamic Micro-Spacing Branch:** When `micro_spacing` is flagged by the fitting loop, section spacing expands to `6pt plus 3pt minus 1pt` and bullet spacing expands to `2.2pt plus 1.5pt minus 0.5pt`.

---

## 3. Test Verification & Empirical Results

### Automated Test Suite Run

Executed full test suite via `backend/.venv/bin/python3 -m pytest backend/tests/test_cv*.py`:

* **Result:** **109 / 109 tests passed**.
* Covered modules: `test_cv.py`, `test_cv_claims.py`, `test_cv_fit.py`, `test_cv_render.py`, `test_cv_rules.py`, `test_cv_summary.py`.

### Empirical Re-Fitting on Real Applications

Historical CVs in the database that previously suffered from underfill were re-compiled through the new fitting loop:

* **CV 9 (App 1073):** Previously `0.906` (90.6%) $\longrightarrow$ **`0.972` (97.2% fill, exactly 1 page)**.
* **CV 10 (App 1132):** Previously `0.935` (93.5%) $\longrightarrow$ **`0.969` (96.9% fill, exactly 1 page)**.

### Live End-to-End Generation Test (`scripts/test_2pass_generation.py`)

Executed full 2-pass generation with `free/minimax-m3.1-flash` on Application 1622:

* **Status:** Success (Draft v2 generated).
* **Generator:** `free/minimax-m3.1-flash` via APInex Gateway.
* **Passes Required:** 1 fit pass.
* **PyMuPDF Geometry Verification:**
* Physical Page Count: **Exactly 1**.
* Physical Text Fill: **97.78%**.
* Zero dropped numbers, zero banned phrases, zero LaTeX compilation errors.

