# Branch review: `refactoring-with-gemini` vs `main`

Review date: 2026-10-26. Read-only review: no commits, no fixes applied, no Gemini or APInex calls, app not started, real DB never opened for writing.

**Scope note.** The branch has 5 commits (`git log main..HEAD`), but `changes-docs/step4.md` and `step5.md` describe work that exists only as **uncommitted changes** (25 modified files, 5 untracked: migration 0032, `RescoreModal.tsx`, two test files, `scripts/test_adzuna.py`). I reviewed `main` against the **working tree**, not only against `HEAD`. `git diff main...HEAD` alone would miss steps 4 and 5.

Conventions: `main` = commit `cd9ff7e`. "Baseline" = a clean `git archive main` export in the scratchpad, used to tell regressions from pre-existing failures.

---

## 1. Summary

1. Fit scoring moves from Gemini to the third-party APInex gateway (`free/minimax-m3.1-flash`) with a 15 RPM limiter, 429 backoff and failover to Ollama. Gemini is blocked for scoring.
2. The fit prompt is rewritten (v7) with a new output schema. `FitAssessment` gets an adapter for it.
3. CV generation gets a 2-pass APInex generator, a 98% fill target, larger bullet allowances and elastic LaTeX spacing.
4. Cold-email (applied mode) prompt is rewritten (v15). Visa, sponsorship and relocation text is banned by a regex, and the `constraint` field and location facts are removed from the model payload.
5. Letter, interview and rewrite models are decoupled from the CV model setting (`models.letter` etc.).
6. Selective rescoring: a filter API (track, days, limit, only unscored, job ids) and a `RescoreModal`.
7. Adzuna error handling.
8. Cross-source dedupe: a merged `sources`/`source_urls` model, a new dedupe key, and migration 0032.
9. Scripts and benchmarks: bulk-dismiss script (already run on the real DB on 2026-10-24), live-API verification scripts, two benchmark reports.
10. **Check results: 9 new test failures (1 more fails on `main` too), 39 new ruff errors, frontend `tsc`, oxlint, token guard and build pass. Migration 0032 round-trips on a copy.**

---

## 2. Documented changes vs code

Intent (one line each) and whether the code does what the doc says.

| # | Change in changes-docs | Intent / why | Files | Implemented | Notes |
|---|---|---|---|---|---|
| 1.1 | step1: Gemini key-pool ban, switch scoring to APInex | Google suspended the project for key pooling; reseller gateways burn quota too fast | `providers/apinex_client.py`, `registry.py`, `api/scoring.py`, `model_choice.py` | **yes** | Client is sync + async, not only async as the doc says. Guards exist in all three places. See issues H1, M2. |
| 1.2 | step1: 15 RPM rolling limiter | Avoid gateway 429s | `apinex_client.py` `RollingRateLimiter` | **yes** | Per-process only. The scripts (`verify_*`, `test_2pass_*`) run in a second process and get their own window. |
| 1.3 | step1: Ollama failover on `QuotaExceeded` | No cloud dependency during outages | `services/scoring.py`, `seed.py` | **yes** | The doc says `qwen2.5:7b`. The real DB still has `gemma4:31b-cloud` as fallback. The code default is `qwen2.5:7b`. |
| 1.4 | step1: fit prompt v7, visa realism, weighting | Stop penalising non-EU candidates | `prompts/fit_score.md`, `versions.json`, `providers/base.py` | **partly** | The v7 prompt dropped `flag_checks` and `core_requirements`, so the hard cap (35) and core-requirement cap (60) can never fire. See issue H2. |
| 1.5 | step1: Settings dropdowns, APInex status badge | UI sync | `sections.tsx`, `ScoringTodayCard.tsx` | **yes** | The doc lists `free/deepseek-v4.1-flash` in the dropdown. Step 3 removed it, and the code agrees with step 3. |
| 1.6 | step1: tests and live run | Verification | `tests/test_scoring.py`, `scripts/verify_apinex.py` | **partly** | `scripts/verify_apinex.py` imports `PRIMARY_MODEL`/`FALLBACK_MODEL`, which no longer exist. It would fail on import (L2). |
| 2.1 | step2: 2-pass CV generator | Avoid JSON crashes on one big call | `providers/apinex_cv.py` | **partly** | The code exists and works from scripts. It is **not reachable from the app**. See issue H3. |
| 2.2 | step2: `fill_min` 0.96, allowances 5/4/3/4 | Fill the page | `cv_rules.py`, `cv.config.yaml`, `cv_build.py` | **partly** | Allowances match. The doc says 0.96, but the code uses **0.98** in three places. |
| 2.3 | step2: graduated shrink, micro-spacing | Avoid project-drop avalanche | `cv_build.py`, `cv_render.py`, `cv.tex.j2` | **yes** | `fit_to_page` also silently injects every pool project when the plan has none (M5). |
| 2.4 | step2: elastic LaTeX | Distribute vertical glue | `cv.tex.j2`, `templates/reference/cv.tex` | **yes** | Default branch equals the reference. `test_cv_render` passes. |
| 3.1 | step3: 429 backoff, single model | The 429 came from a per-account limit | `apinex_client.py`, `scoring.py` | **yes** | |
| 3.2 | step3: pre-request timestamp in limiter | No bursts | `apinex_client.py` | **yes** | |
| 4.1 | step4: outreach v15, visa ban, persona prompt | Stop the emails apologising for visa status | `prompts/outreach.md`, `applied_check.py`, `outreach.py`, `base.py` | **partly** | Works as described, but breaks project rules and tests. See issues B1, H4, M6. |
| 4.2 | step4: "154/154 passed" | Verification | tests | **no** | `test_email_eval` and `test_no_personal_data` fail on the working tree. |
| 5.1 | step5: selective rescoring (API, modal) | Don't rescore 3,300 jobs | `api/scoring.py`, `services/scoring.py`, `RescoreModal.tsx` | **partly** | Works, but weakens the open-jobs rule. See issue H5. The doc says `frontend/src/features/scoring/RescoreModal.tsx` and `job.track`/`fit_assessment`, but the real file is `components/app/RescoreModal.tsx` and the column is `matched_track`/`FitScore`. |
| 5.2 | step5: Adzuna repair | Source returned nothing | `providers/sources/adzuna.py`, `scripts/test_adzuna.py` | **yes** | The doc says `services/job_sources/adzuna.py` and `httpx.AsyncClient`. The real file is `providers/sources/adzuna.py` and it uses `PoliteClient`. Endpoints were already per-country on `main`. 401/429 handling, skipping jobs with no id/url, and the config check are new. No tests for the new branches (L4). |
| 5.3 | step5: dedupe fingerprint, `sources`, `source_urls` | One row per real job | `dedupe.py`, `ingest.py`, `models/job.py`, migration 0032, 5 frontend files | **partly** | Works for new ingest only. See issues H6, H7. The doc says `canonical_job_id` and `services/dedup.py`. Neither exists. The existing `duplicate_of_id` is kept. |
| 5.4 | step5: "Status: Specification & Architecture Staged" | n/a | | | The doc calls itself a spec, but the code is implemented. The "Adzuna live verification" claim can't be checked offline. |

---

## 3. Undocumented changes

Files changed that no doc mentions (committed or uncommitted):

- **`backend/app/seed/seed.py` `ensure_defaults`**: rewrites stored `models.scoring` from Gemini to APInex at startup, and **breaks adding new default settings** (issue B2).
- **`model_choice.claude_model`** and `models.letter/interview/rewrite` (`api/letters.py`, `api/interview.py`, `api/copilot.py`, `fixtures.py`). This is a sound fix: without it a `free/*` CV model would reach `claude -p`. It needs a doc line.
- **`gemini_keys.py`**: daily cap raised 200 to 500. `CLAUDE.md` text was edited to match (issue H8).
- **`counts()` in `services/scoring.py`**: now excludes closed jobs, so Today/Discover totals change.
- **`_scope_ids` special case for `scope="unscored"`** and `force=True` for `unscored`/`outdated` (issue H5).
- **`GET /jobs` default `hide_duplicates=True`** and source filter now matches `sources[]`.
- **`FitAssessment` model validator**, `AppliedEmailPlan` `extra="ignore"`, `evidence` default `""` (`providers/base.py`).
- **Company-name matching** in `applied_check`/`outreach_check` now accepts the normalised company name.
- **`cv_service.generate(generator=None)`** defaults to APInex.
- **Frontend**: the "stale scores" notice and `RescoreConfirmDialog` usage were removed (the dialog file is now dead code). `ScoringProgress.tsx` can no longer start "Rescore stale".
- **`CLAUDE.md`**: Gemini cap edit plus an added "Suggested fixes" paragraph.
- **Scripts and docs**: `backend/scripts/bulk_dismiss_java_jobs.py` (committed in `f869281`; a backup `jobhunter-before-before-bulk-dismiss-java-20261024-212813.db` shows it was run on the real DB), `backend/scripts/verify_98_fullness.py`, `test_2pass_generation.py`, `test_adzuna.py`, `scripts/verify_apinex.py`, `benchmarks/*`, `docs/AI_ACTIONS_CATALOG.md` (412 lines), `.env.example` (`APINEX_API_KEY`), `config.py` (`apinex_api_key`), `pyproject.toml` (E501 ignore for the client).

### Diff size by area (main vs working tree, +/-)

| Area | Files | Lines |
|---|---|---|
| Backend app (providers, services, api, models, schemas, seed) | ~32 | ~+1,760 / -190 (apinex_client 418, apinex_cv 370 new) |
| Migrations | 1 (untracked) | +62 |
| Prompts | 3 (`fit_score.md`, `outreach.md`, `versions.json`) | +64 / -73 |
| Tests | 7 modified, 2 new | +328 / -40, plus ~150 in new files |
| Frontend | 11 | ~+215 / -45 (`RescoreModal.tsx` new) |
| Templates / settings | 4 | +18 / -9 |
| Scripts and benchmarks | 7 | ~+2,350 (reports are 1,100 of it) |
| Docs | `changes-docs` x5, `AI_ACTIONS_CATALOG.md`, `CLAUDE.md`, `.env.example` | ~+800 |

`git diff main...HEAD` alone: 51 files, +4,939 / -272. Working tree vs `main`: 69 files, +5,601 / -326.

---

## 4. Issues

### Blocker

**B1. Branch breaks the "no personal data in source" rule; `test_no_personal_data` fails.**
`backend/app/prompts/outreach.md:27` hardcodes the candidate's full name in the applied-mode system prompt. The same prompt also bakes in this candidate's stack (Flutter/Riverpod/BLoC/Drift/"~80% code coverage") as persona guidance (lines 33-36).
- What goes wrong: personal data lives in source. The model is also told to emphasise "~80% code coverage" and specific tools whether or not the cited pool items say so, which is an invented-facts risk that the verifier then has to catch. The project rule also says examples set tone only and prompts must not carry wording or personal facts.
- Fix: remove the name (the code already supplies `candidate.name`). Make persona guidance generic ("match the recipient's domain, using only cited pool items"). Bump to v16 if the text changes.

**B2. `ensure_defaults` no longer persists newly added default settings.**
`backend/app/seed/seed.py:905-921`. When a `models` row exists, which is always on a real DB, the `elif missing: s.commit()` branch is skipped, so keys added to the session are rolled back. Reproduced on a temp DB: after deleting the `generation` key and calling `ensure_defaults`, it is **not** restored. `tests/test_workspace.py::test_ensure_defaults_adds_new_setting_keys_without_overwriting` fails with `KeyError: 'scoring'`.
- Impact: any future new settings key silently never reaches an existing workspace, and the app then reads missing settings. The current real DB has all keys, so it is latent today.
- Fix: commit whenever `missing` is non-empty or the models row changed (for example `changed = bool(missing)`, set it in the migration branch, `if changed: s.commit()`).

**B3. The branch breaks 9 tests that pass on `main`, and 39 ruff errors.** See section 5. A branch that fails its own offline suite shouldn't merge. Step 4's "154/154 passed" is not true of the working tree (`test_email_eval` is missing its eval record, `test_no_personal_data` fails).

### High

**H1. Third-party gateway gets personal and profile data, with no privacy guard and no daily cap.**
`apinex_client.py:176`, `apinex_cv.py` passes `request.pool`, `request.job`, `request.facts`, `request.guide` to `apinex.bond`, an unknown reseller on a "free" tier. The Gemini path has `gemini_generate.check_private` (refuses profile email, phone digits, link URLs) and the APInex path has nothing equivalent. The scoring prompt also sends the full experience text.
- Also: unlike the single-key Gemini mode there is **no daily cap**. `discovery.py:274` `enqueue_never_scored()` can start scoring automatically after each discovery run (`scoring.py:646`), bounded only by 15 RPM (~900 requests/hour). Step 1 itself records 2-4x token multipliers on these gateways.
- Fix: reuse `check_private` in `APInexClient` before every request. Add an APInex daily cap, paused state and no-auto-start rule matching the Gemini ones. Decide explicitly whether the experience pool may go to this vendor.

**H2. Fit prompt v7 silently disables the hard-flag and core-requirement caps, and breaks the "a score is never defaulted" rule.**
- `prompts/fit_score.md` v7 no longer asks for `flag_checks` or `core_requirements`. `FitAssessment` defaults them to empty (`base.py:155-156`), so `fit.py`'s hard cap (35) and core-requirement cap (60) can never fire for APInex scores.
- `base.py:181,195`: missing dimensions get `score: 5` and a missing/invalid score becomes 5. Scores >10 are divided by 10. Evidence defaults to `""` (`SubScore.evidence`).
- The model is asked for `overall_score` and `verdict`; they are stored but ignored. The project rule is not to ask the model for the final number.
- The prompt asserts an immigration claim as fact ("self-file ... EU Blue Card upon signing") that is not true for many roles. This is the same location-rule area `fit.requirement_stated` guards (a `requirement_stated`-style rule is gone).
- Fix: keep v6's `flag_checks`/`core_requirements` sections and only soften the location rubric. Reject a response with a missing dimension (`ScoringFailed`) instead of defaulting to 5. Drop `overall_score`/`verdict` from the schema.

**H3. The 2-pass CV generator is unreachable from the app, and its settings are inconsistent.**
- The real DB has `models.cv = gemini-3.5-flash-lite` (checked on the copy). `model_choice.check` (`model_choice.py:78`) **rejects** any CV/email model that is not `gemini-*`/`claude-*`, and the Settings CV dropdown has no APInex option. The only paths to `APInexCVGenerator` are `cv_service.generate(generator=None)` (`cv_service.py:244`), `DEFAULT_APINEX` when no model is stored, and the scripts. Step 2's "live on production" only holds for those scripts.
- If a `free/...` model is ever stored (a DB edit), `model_choice.choice` returns provider `apinex` for the **email** task too. `registry.email_drafter` has no APInex branch and falls through to `ClaudeEmailDrafter("free/…")`, which sends a non-Claude model name to `claude -p` (violates "a model name reaches only its own provider").
- Fix: decide whether APInex is a CV option. If yes, extend `check` plus the dropdown, and make `choice` apply `apinex` only to `cv`. If no, remove the dead paths.

**H4. Removing the constraint sentence conflicts with the project's honesty rule for job-linked emails.**
`applied_check.py:61,169,240,253`, `outreach.py` `logistics()`, `base.py` `AppliedEmailPlan`. Project rule (CLAUDE.md "Cold email", memory "email rules"): a constraint is stated **once, plainly**, only when the listing states a requirement the candidate doesn't meet, and the checks warn, not block.
- What goes wrong now: if a listing says "must be EU-resident", the email can never say anything, and `visa_disclaimer_banned` is an **error** on *any* occurrence of `sponsor\w*`, `relocat\w*`, `visa`, so a legitimate company fact ("we sponsor a conference", "relocation tech") blocks approval and triggers the retry loop. English only: German/French equivalents (Arbeitserlaubnis, titre de séjour) are not matched, so the ban is inconsistent across languages.
- The verifier's `Based in / Work authorization / Relocation` FACTS lines (`verifier.py:138-146`) can now never populate, but CLAUDE.md still documents them.
- This is a deliberate product change, but it reverses a documented rule. Either update CLAUDE.md and the memory notes, or keep the stated-once constraint for listings that explicitly require it.
- Fix: scope the regex to the model-written parts (`opening`, `experience`, `ask`), not the whole assembled text and signal, and downgrade it to a warning when the listing itself states a location requirement (`listing_states_location`).

**H5. The rescore filters bypass the "open jobs only" rule and the scope.**
- `api/scoring.py:131-135` (`scope == "unscored"`) only excludes closed-stage jobs, so jobs hidden by location filters, duplicates, and jobs from paused sources are included. `api/scoring.py:211` then passes `only_open=False` for `unscored`.
- `services/scoring.py:438`: when `job_ids` is given, the query uses `id IN job_ids` **instead of** intersecting with the scope's ids, so `scope="outdated"` plus `job_ids=[…]` rescoring any job, closed or not, bypasses scope and openness.
- `force` is now true for `unscored`/`outdated`, which re-spends calls on jobs that already have current scores.
- The modal's default batch cap is 50, so the Settings button labelled "Rescore every job" actually queues at most 50 unless the user changes it.
- Fix: run `open_jobs.split_open` last on every path except `scope="jobs"`. Intersect `job_ids` with the scope. Label the Settings button honestly or default `limit` to "all" for `scope=all`.

**H6. The dedupe key was changed without backfill and now conflates different countries.**
`dedupe.py:50` drops the country from the key and the key format changes from `company|title|country` to `company::title`.
- On the copy of the real DB, **all 5,536** stored keys use the old format and **none** use the new one, so new ingests will not match any existing job by key (only by `apply_url`). The 1,375 existing duplicate rows stay as separate rows with `sources = NULL`.
- 72 company+title groups in the real DB span more than one country (for example the same title at one company in Berlin and Dubai). Under the new key those become one job, and the second location's URL is merged away.
- The legal-suffix set now strips `technologies`, `solutions`, `holding`, `co`, `ab`, `oy`, `kg`, so "Acme Solutions" and "Acme Technologies" collapse to one company (`dedupe.py:7`).
- Fix: keep country in the key. Add a data migration that recomputes keys for existing rows. Review the suffix list (keep real suffixes only).

**H7. Migration 0032 is lossy, was applied without a backup, and merges data it can't undo.**
`alembic/versions/0032_job_sources_and_urls.py`. The real DB is **already at 0032**, and the newest backup is `jobhunter-before-before-bulk-dismiss-java-20261024-212813.db` (a day older than the migration), so no backup was taken before it ran. The migration overwrites the parent's `description` with a duplicate's longer one. `downgrade()` only drops columns, so that text is not restored.
- Result on the copy: upgrade → downgrade → re-upgrade works; 4,161 rows have `sources`, 1,375 (the duplicates) are NULL, and 149 parents are multi-source.
- Fix: back up first (`contacts_import.backup_db`, as the bulk-dismiss script does). Put that into the `make migrate` path, or document the manual step. Give the duplicate rows `sources` too, or document why they stay NULL.

**H8. Gemini cap loosened against the "conservative caps" rule.**
`gemini_keys.py:45` daily cap 200 → 500 (and the CLAUDE.md text changed with it). CV and email still use Gemini, and the cap is the account-review protection. This needs an explicit decision, not a side edit. Fix: revert to 200, or record the reason in CLAUDE.md.

**H9. `bulk_dismiss_java_jobs.py` bypasses `pipeline.transition` and also closes jobs far along the pipeline.**
`backend/scripts/bulk_dismiss_java_jobs.py:105,121`. CLAUDE.md says `services/pipeline.py` is the only place that changes `application.stage`. The script sets `stage = closed` directly. `to_dismiss` is every target whose stage is not `closed`, so it would also close jobs in `shortlisted`, `cv_ready`, `ready`, `applied`, or later stages. It also treats an empty `matched_track` as backend. The backup name shows it already ran on 2026-10-24. Fix: audit what it closed (the `application_event` rows with message `Dismissed: Excluded track: Java backend`), and rewrite it to call `pipeline.transition` and skip anything past `new`/`shortlisted`.

### Medium

**M1. `scripts/` that use the real DB and live APIs live next to normal scripts.** `scripts/verify_98_fullness.py`, `test_2pass_generation.py` open the real `engine` with hardcoded application ids (1621, 1622) and call the live gateway (`cv_service.generate` writes CV versions). Names starting with `test_` invite someone to run them as tests. Rename them (`manual_*`) or require an explicit `--apply`/`--live` flag.

**M2. `APInex` routing by substring.** `registry.py:58-60,85-88`, `model_choice.py`, `scoring.is_cloud`, `scoring.py estimate_seconds`, the API: `"minimax" in model`, `"deepseek" in model`, `model == "apinex"`. `deepseek` is routed to APInex for CV but not for scoring. One helper (`is_apinex(model)`) would remove the six copies and the inconsistency. The scoring path hardcodes an estimate of 4.0 seconds per job for any APInex model.

**M3. Scoring fallback now defaults to `qwen2.5:7b` in code** (`services/scoring.py load_context`, `seed.py`), but the user's memory notes and the real DB use gemma. If `qwen2.5:7b` isn't pulled, a 429 streak degrades to a `blocked` queue. `/scoring/health` for an APInex model doesn't check that the fallback exists.

**M4. `APInexCVGenerator` fabricates a summary fallback.** `apinex_cv.py:239,365`. If the model returns no summary, it substitutes the first pool snippet, or the literal text `"Software engineer."` cited to pool id 1 (which may not be a snippet). CLAUDE.md says summary checks never swap in a fallback. Raise `CVGenerationFailed` instead.

**M5. Pass 1 plan is cosmetic, and `fit_to_page` injects projects.** `apinex_cv.py:108` appends every fact index the model left out, so selection and ordering are nominal. `cv_build.py:360-388`: if the plan has no projects, `fit_to_page` adds **every** pool project with 2+ facts after `cv_check` has run (unchecked, original text, relevance 6). CLAUDE.md says structure decisions are in code and "never filler". Fix: do it in `cv_rules`/`layout`, before checks, and cap by `projects_max`.

**M6. Applied prompt hard-limits and wording changes.** `outreach.md` v15 says "strictly between 80 and 130 words" while the code warns outside 90-170 (`applied_check`). The prompt tells the model the greeting is a returned part ("greeting") though the schema/code build it. Required for the eval record anyway (B-level issue below): `make eval-emails` was not run for v15, and `test_the_current_email_prompt_was_run_against_the_regression_set` fails.

**M7. `ScoringTodayCard`/`ScoringProgress`/`RescoreModal` UI gaps.** `RescoreConfirmDialog.tsx` is dead code. "Rescore stale" is no longer reachable from Discover, so experience-change staleness has no entry point except Settings → "Rescore all". `RescoreModal` has no "See how it works" `TourButton` or tour entry (CLAUDE.md requires one per feature). The sandbox preview path wasn't checked. No shortcut conflicts found (the modal registers no keys).

**M8. Test isolation.** `tests/test_granular_rescore.py` and `tests/test_dedupe_merge.py` write to the shared session DB with fixed `external_id`s and don't clean up, so test order can change other tests' counts (not proven; the 9 failures above reproduce in isolation and are caused by the changes, not by order). `conftest.py` blanks the other providers' keys but not `APINEX_API_KEY`. The socket guard blocks it anyway, and the live test needs `APINEX_LIVE=1`.

### Low

- **L1.** `ruff`: `apinex_cv.py` (24), `applied_check.py` (4), `outreach.py` (2), `cv_build.py` (2), and others (E501/SIM). `main` was clean. `make lint` fails.
- **L2.** `scripts/verify_apinex.py:14` imports names that no longer exist, so the script crashes on import.
- **L3.** `scripts/test_adzuna.py` prints the first 4 characters of the Adzuna id and key. Print only "set / not set".
- **L4.** New Adzuna branches (401, 429, skipped items) have no tests. Mapper tests against recorded fixtures are still the project norm.
- **L5.** `ingest()` merge path does not append to `stats.job_ids`, and does not reset `fit` staleness when it replaces a description with a longer one, so the displayed score may reflect the shorter text.
- **L6.** `hide_duplicates` default flipped to `True` for `GET /jobs` with no mention. Old duplicate rows are now hidden by default.
- **L7.** Docs: `CLAUDE.md`, `docs/SPEC.md`, `docs/DATA_MODEL.md` don't mention APInex, `sources`/`source_urls`, `models.letter`, or the rescore filters. The project requires keeping them updated. `CLAUDE.md`'s scoring section still describes Gemini scoring.
- **L8.** `changes-docs` path/name mismatches (section 2, rows 5.1-5.3) and the 0.96 vs 0.98 fill target will confuse the next reviewer.

### Rules checked and found **intact**

- Experience pool: no new writer. `apinex_cv.py` only reads; `tests/test_pool_protected.py` passes.
- Send gate (`send_queue`, `verifier.send_gate`): untouched. The verifier changed only by `.get()` guards.
- Secrets: no key, token or password values found in code, docs, tests or fixtures (pattern scan; `.env` is git-ignored and `git ls-files` lists no `.env` or `.db`). The `.env` has `APINEX_API_KEY=` present as a name only; I did not read its value.
- `claude -p` isolation/subscription check: untouched. Letter/interview/rewrite now read their own model key, so a `free/*` or `gemini-*` model can't reach `claude -p` from those three paths.
- Gemini: no scoring path left (`registry`, API, `check`). The "no probe or startup call" rule holds. `scoring_health` for an APInex model only reads config.
- Honesty: `honesty.violations` is still called on emails. Years tied to projects tracks are still enforced.
- UI: token guard passes; `RescoreModal` has loading, error and empty states.

---

## 5. Check results

All run offline: tests use a temp DB and a network-blocking socket guard (`tests/conftest.py`); the migration ran on a sqlite online-backup copy placed in the scratchpad.

| Check | Result |
|---|---|
| `pytest -q` (full backend) | **10 failed, 1058 passed, 1 skipped** (277 s). The skip is the live APInex test, which needs `APINEX_LIVE=1`. |
| Same failing tests on a clean `main` export | 9 pass on `main` and fail on the branch; **1 fails on both** (`test_motivation::test_a_sent_email_alone_does_not_move_the_streak_by_default`, `assert 2 == (0 + 1)`, pre-existing). |
| `ruff check app tests` | **39 errors** (`main`: 0). 24 of them in `apinex_cv.py`; the rest are E501/SIM in 6 other files. |
| `tsc -b` | pass |
| `npm run lint` (oxlint) | pass, no warnings printed |
| `scripts/check-tokens.sh` | pass |
| `npm run build` | pass (bundle 1.3 MB, same size warning class as before) |
| Migration 0032 on a COPY of the real DB (5,536 jobs, 1,375 duplicates) | The copy was already at 0032. Downgrade to `afe287de393c` removed both columns, re-upgrade restored them: 4,161 rows backfilled, 1,375 NULL, 149 multi-source. Single head `0032`, no numbering conflict with `main` (`main` head is `afe287de393c`). No pre-migration backup exists (H7). |

The 9 branch-only failures:

| Test | Cause |
|---|---|
| `test_api::test_seed_shape` | Sandbox no longer produces 2 duplicate rows: `ingest` merges instead (the test expects the old behaviour). |
| `test_linkedin::test_import_scores_only_that_job_dedupes_and_saves_the_hiring_team` | The test builds a duplicate through `dedupe_key(name, title, "PT")` and expects `duplicate_of`. The key semantics changed. It ends in `NoResultFound`. |
| `test_email_eval::test_the_current_email_prompt_was_run_against_the_regression_set` | outreach v15 has no `eval_log.json` entry (`make eval-emails` not run). |
| `test_gemini::test_quota_endpoint_single_key_cap_and_rescore_preview_in_days` | Expects provider `gemini`, gets `apinex` (scoring model changed). Tests need updating. |
| `test_gemini::test_the_quota_endpoint_has_nothing_to_say_for_other_models` | Expects `other`, gets `apinex`. |
| `test_gemini::test_continue_with_and_key_enable_endpoints` | `KeyError: 'paused'` (same cause as above). |
| `test_queue::test_quota_limit_switches_the_run_to_local` | `KeyError: 'free/minimax-m3.1-flash'` (the test's fake scorers are keyed by the old default model). |
| `test_workspace::test_ensure_defaults_adds_new_setting_keys_without_overwriting` | Real bug B2. |
| `test_no_personal_data` | Real bug B1. |

I did not run: `make eval`, `make eval-emails`, `make eval-verifier`, any script in `scripts/` (they call live APIs or open the real DB), `make seed`, or `make dev`.

---

## 6. Questions for you

1. **APInex for CV (H3).** Is the 2-pass APInex generator meant to be selectable in Settings, or only a script experiment? Today the stored `models.cv` is still Gemini and Settings can't switch it.
2. **Third-party data (H1).** Are you comfortable sending the experience pool and job text to `apinex.bond`? If yes, should it get the same private-data guard and a daily cap as Gemini?
3. **Visa ban (H4).** Is "never mention visa, sponsorship or relocation, even when the listing requires it" the new rule? That reverses the documented stated-once constraint, and CLAUDE.md and the memory notes would need updating.
4. **Fit prompt (H2).** Was dropping `flag_checks` and `core_requirements` intended, with the hard and core caps accepted as lost? Or should v7 keep them and only soften the location rubric?
5. **Gemini cap (H8).** Was 200 → 500 deliberate?
6. **Fill target.** Is 0.98 the intended target (code), or 0.96 (step2 doc)?
7. **Dedupe (H6).** Should the same title at the same company in different countries stay as separate jobs? Should I-or-you backfill the old keys and the 1,375 duplicate rows?
8. **Bulk dismiss (H9).** Did the 2026-10-24 run close anything past `New`? The backup `jobhunter-before-before-bulk-dismiss-java-20261024-212813.db` lets you check.
9. **Motivation test.** It also fails on `main`. Known?
10. **Doc status.** `changes-docs/step5.md` says "Specification & Architecture Staged" but the code exists. Is it finished, and should the file names in it be corrected for the next reviewer?
