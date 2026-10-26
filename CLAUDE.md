# Job Hunter v2

A local, single-user web app for my Data/AI Engineering job search (Europe + Gulf targets set in Settings, or remote). It discovers jobs,
scores fit, resolves contacts, generates a tailored one-page LaTeX CV, and drafts cold emails or routes
the job to manual web apply. I review everything before anything is sent.

**Read before working:** `docs/SPEC.md` (screens, flow, states), `docs/DATA_MODEL.md` (tables, stage
transitions), `docs/DESIGN.md` (tokens and UI rules). Keep them updated when behavior changes.

## How to run

```bash
make setup     # first time: uv venv (Python 3.12) + pip deps, npm install, migrate, seed
make dev       # API on :8000 (docs at /docs) + web on :5173, Ctrl-C stops both
make seed      # rebuild the tour sandbox (data/demo.db); sample data lives ONLY there
make reset     # ERASE the real workspace (keeps profile + settings defaults)
make migrate   # alembic upgrade head (alembic/env.py first backs the DB up when a migration is pending)
make test      # backend pytest (never calls a model or the network)
make eval      # score your labeled jobs with the real model; report in data/eval/ (ARGS="--fresh")
make lint      # ruff + tsc + oxlint + design-token guard
make build     # frontend production build
```
Dev aids: `MOCK_LATENCY_MS=1500 make dev` slows every API response (check skeletons). Stopping only the
backend shows error states. `JOB_SOURCES=mock` swaps every job source for the offline mock.
Scripts named `manual_*` touch the real DB or live APIs and refuse to run without `--live`. Secrets and keys go in `.env` (see `.env.example`): `ADZUNA_APP_ID/KEY`, optional `WTTJ_ALGOLIA_KEY`.

## Real data vs sample data (non-negotiable)

- `data/jobhunter.db` is the user's **real** workspace: never seed fixtures into it. A fresh DB gets only
  the search profile and settings defaults (`ensure_defaults` at startup).
- `data/demo.db` is the **tour sandbox**, rebuilt from `app/seed/fixtures.py` at every tour start
  (`POST /api/sandbox/reset`). Requests with `X-Workspace: demo` use it (`db.get_session`), and the
  sandbox always uses mock job sources. The scheduler only touches the real DB.
- Every new feature ships with a real empty state (plus a "See how it works" `TourButton`) and a short
  per-feature tour in `features/tours/tours.ts`, anchored with `data-tour="…"` attributes.

## Job sources (backend/app/providers/sources/)

- Each source has a class (`fetch`, `configured()`, `cooldown_hours`, `requests`) plus a **pure `parse_*`
  mapper**. HTTP always goes through `providers/http.PoliteClient`.
- Mapper tests run offline against real responses in `backend/tests/fixtures/sources/`, recorded with
  `.venv/bin/python scripts/record_fixtures.py <source>` (manual; makes real requests). The test suite
  blocks the network. The Adzuna fixture is synthetic until keys exist, so re-record it.
- Gulf coverage: `boards.py` (public ATS APIs; company list = `app_setting.company_boards`, handed to the source by
  `discovery.prepare_source` via `settings_key`/`apply_settings`; one failing board is a warning, all failing fails
  the source) and `bayt.py` (public country search pages only, 3s spacing, 6h cooldown; robots.txt disallows
  `/en/jobs/…-jobs/` and `filters[`, never request those).
- One listing per real job: `job.sources` / `job.source_urls` (migration 0032) hold every source and URL; `ingest` merges a job whose `dedupe_key` (or apply URL) already exists into the canonical row instead of adding one (`duplicate_of_id` stays for rows that were duplicates before; `GET /jobs` hides them by default); a LinkedIn import merges the same way. The key is company::title::country (`dedupe.py`, real legal suffixes only); migration 0033 (`services/listing_merge.backfill`, data only; optional `DEDUPE_ORIGINALS_DB` = a pre-0032 backup) recomputed every key and gave each main listing its duplicates' sources/URLs. The main listing keeps its own description unless it is a snippet (< 1,500 chars) and another source has the full listing (`should_take_description`); a changed description marks the latest score stale (`mark_score_stale`), never rescores. Adzuna: 401 stops the run with a warning, 429 keeps the batches fetched so far (`PoliteClient` errors carry the last HTTP status).
- Orchestration lives in `services/discovery.py`: lock (one run), per-source isolation, cooldown, and a filter
  report into `source_run.details` plus `data/logs/discovery.log`. Pre-filter rules are in `services/prefilter.py`
  (never filter seniority by default), idempotent upsert and dedupe in `services/ingest.py`.
Python is managed by `uv` (`uv python install 3.12`). The venv is `backend/.venv`. The DB is `data/jobhunter.db`.
The Vite dev server proxies `/api` → `http://localhost:8000`.

## Architecture

```
frontend (Vite/React/TS) ──/api──▶ FastAPI routers ──▶ services (domain logic) ──▶ SQLModel/SQLite
                                                   └──▶ providers (interfaces) ──▶ mock | real impls
```

- **Routers** (`backend/app/api/`) are thin. They validate input, call services, and return schemas from `app/schemas/`.
  Never return table models directly.
- **Services** (`backend/app/services/`) own the rules: stage transitions (`pipeline.py`, the only place
  that changes `application.stage` and it always writes an `application_event`), dedupe keys (`dedupe.py`),
  Today aggregation (`today.py`).
- **Providers** (`backend/app/providers/base.py`) are Protocols: `JobSource`, `FitScorer`, `CVGenerator`,
  `CVRenderer`, `EmailDrafter`, `Mailer`. `registry.py` returns implementations. Phase 0 uses `mock/` only.
  FitScorer=APInex (`providers/apinex_client.py`, Ollama fallback), CVGenerator=APInex 2-pass (`providers/apinex_cv.py`; Gemini `providers/gemini_generate.py` or Claude Code headless `providers/claude_cv.py` selectable); rendering is `services/cv_render.py`
  (Jinja + latexmk + PyMuPDF). Planned: Mailer=Gmail SMTP.
- **Migrations:** every model change needs a new Alembic revision (`alembic revision --autogenerate -m "..."`,
  then review it). SQLite needs `render_as_batch=True` (already configured).
- **Frontend data:** TanStack Query only, with no ad-hoc fetch in components. The client is in `src/lib/api.ts`, types
  in `src/lib/types.ts` (these mirror `app/schemas`, so keep them in sync), and query/mutation hooks in `src/lib/queries/`.
  Mutations invalidate the related keys and toast on success or error.

## Folder layout

```
backend/app/{main,config,db}.py
backend/app/models/      SQLModel tables (one module per aggregate) + enums.py
backend/app/schemas/     API DTOs
backend/app/api/         routers, mounted under /api
backend/app/services/    domain logic
backend/app/providers/   base.py, registry.py, mock/
backend/app/seed/        fixtures.py + seed.py (python -m app.seed.seed)
backend/alembic/         migrations
backend/tests/           pytest (fresh temp DB per session)
frontend/src/styles/     tokens.css (raw values) + index.css (Tailwind @theme mapping)
frontend/src/components/ui/   shadcn primitives (restyled to tokens)
frontend/src/components/app/  shared app components (badges, states, shell, panels)
frontend/src/features/<screen>/  one folder per screen
frontend/src/hooks/      useHotkeys, useListKeyboard, …
frontend/src/lib/        api client, types, queries, formatting utils
docs/                    SPEC, DATA_MODEL, DESIGN
```

## Frontend building blocks (reuse before writing new ones)

- `hooks/useSearchParamState`: filters, tabs and selection live in the URL (`?job=`, `?view=`, `?tab=`).
- `hooks/useListKeyboard`: j/k/Enter plus action keys. It tracks the selection in a ref because keys can
  arrive faster than re-renders, so read the *live* selection in handlers, not render-time state.
- `hooks/useHotkeys`: global keys and `g x` sequences. Shortcuts are skipped in inputs and while a dialog/menu is open.
- `hooks/useTriageActions`: shortlist/dismiss with an Undo toast (8s). `components/app/CloseDialog`: close reasons.
- `hooks/useDiscoveryAction` starts a run. `DiscoveryWatcher` (in the shell) turns finished runs into toasts,
  and `DiscoveryProgress` is the strip shown while running.
- `components/app/tour/*`: TourProvider (switches `lib/api` to the sandbox workspace), TourOverlay,
  TourStrip, TourButton.
- `components/app/badges`: Stage/Fit/Source/Remote/ContactTier/Tone badges. `states`: EmptyState/ErrorState/SkeletonRows.
- `components/app/job-cards`: FitCard, ContactCard, JobFlags. `Prose` renders listing markdown safely. `TagInput`.
- Autosave pattern (notes, CV, drafts): local state, a 700ms debounced mutation, and a "Saving… / All changes saved" label.

## Fit scoring (backend/app/services/scoring.py, fit.py; providers/ollama.py)

- The LLM only returns sub-scores, reasons, evidence and flags (`FitAssessment`). **All arithmetic is in `services/fit.py`**:
  weights, the hard-flag cap (verified quotes only), evidence verification, confidence. Don't ask the model for the final number.
- `score_job` never raises for model problems by default (stores `status=failed`); the queue calls it with
  `store_failures=False` and handles the typed errors itself. A score is never defaulted.
- Hard flags (the score cap) need a quote that states the requirement itself: `fit.requirement_stated` checks the quote's wording per flag type and downgrades the rest to soft with a `severity_note` (prompt v4). An office, a city, on-site/hybrid or perks never cap a score; `recompute` applies the same rule to stored flags.
- Prompt v5 adds `core_requirements` (the role's primary language/stack or central skill, with a quote and `missing`). A missing one caps the score softly (`scoring.missing_core_cap`, default 60) only when `fit.evaluate_core` verifies its quote in the listing and the experience text doesn't name it; the lower of the hard (35) and soft caps wins; `recompute` reapplies the stored verdict. Listings go in whole up to 15,000 chars (`fit.truncate_description` drops boilerplate sections above that, never requirement/language sections); the Ollama scorer's `num_ctx` is 16,384.
- Core-requirement verdicts are derived, not stored once: `fit.judge_core` (missing + verified quote + not named in the experience text + not generic tooling from `scoring.never_cap_on` unless the title names it) runs at scoring AND in `recompute_all`, so a rule, cap or list change never needs a rescore.
- **APInex gateway** (`providers/apinex_client.py`, `providers/apinex_models.is_apinex`, `APINEX_API_KEY`): the scoring model (`models.scoring`, default `free/minimax-m3.1-flash`) and the CV model (`models.cv`) can be APInex; **nothing else may**. `is_apinex(model)` (`free/*`, `minimax*`, `apinex`) is the only routing check; email, letters, interview, rewrite, confirm, verifier and everything on `claude -p` reject it before any call (`apinex_models.reject`, `model_choice.check`, `ClaudeCVGenerator.__init__`). One process-wide 15 RPM rolling limiter, 429 backoff, `QuotaExceeded` → the Ollama fallback (`models.scoring.fallback`, default `qwen2.5:7b`). Fit prompt v7 asks for `dimensions` only: it does not ask for `flag_checks`/`core_requirements`, so the hard (35) and core (60) caps do not fire for APInex scores. A missing or invalid sub-score is never defaulted: one retry (`APInexFitScorer.assess`), then `ScoringFailed`. The experience pool and listing go to this third party; there is no `check_private` guard or daily cap on it yet.
- **Gemini no longer scores** (`model_choice.check` rejects it); the single-key pool below serves CV and email only. **Gemini is in single-key mode (accounts under review)** (startup `resume(start=False)` re-queues interrupted scoring but never starts it; `POST /scoring/start` does): `services/gemini_keys.KeyPool` uses only the first `gemini.max_keys` (default 1) keys of `.env`, one request at a time, 6/min, `gemini.daily_cap` (500) a day over every Gemini model with 50 kept for user-triggered work; 3 tries then give up, no rotation, no burst. NOTHING calls Google except real requests (no probe, health or startup check: `health` only reads config). ONE 403/refused key disables the key, sets `gemini.paused` (all traffic stops, scoring waits) and `model_choice.choice` returns Claude for CV and email until Resume (Settings → Models banner, `POST /scoring/gemini/pause`). Keys are shown by label + last 4 characters only. The old multi-key description follows and is superseded. Gemini bulk scoring: `providers/gemini.py` + `services/gemini_keys.KeyPool` (usage in `provider_usage`, Pacific day). Out of quota on every key = `QuotaWait`: the queue pauses and wakes by itself at the reset, it never falls back to another model on its own (`ScoringQueue.continue_with` is the user's explicit choice). Tests use `httpx.MockTransport`, never a real key (conftest blanks `GEMINI_API_KEY(S)`).
- Ask Claude (`services/confirmation.py`): the scoring prompt + `prompts/confirm_verdict.md`, answer schema = `FitAssessment` + `verdict` (`ConfirmationAnswer`). Chain `registry.confirmers`: `ClaudeConfirmer` (claude -p, subscription only, the CV generator's isolation) → `GeminiConfirmer` for `gemma-4-31b-it` (schema in the prompt; Gemma rejects the native schema) → the copy-paste flow. Stored in `fit_confirmation`, never in `fit_score`; `recompute_all` keeps both consistent. Tests fake the CLI and the Gemini transport.
- The cache key includes the prompt version. **Any edit to `app/prompts/fit_score.md` needs a version bump** and a new hash in
  `prompts/versions.json` (`tests/test_prompt.py` tells you the hash).
- `models.letter` / `interview` / `rewrite` / `confirm` / `verifier` are `claude-*` only (`model_choice.claude_model`, `check`): a CV or email model id never reaches `claude -p`.
- Models (Settings → Models): `models.scoring = {model: gemma4:31b-cloud, fallback: gemma4:12b, cloud_concurrency:
  {min, start, max}, local_concurrency}`. Cloud: schema in the prompt + validation; local: native `format`, `think: false`.
- The queue (`ScoringQueue`) is persistent (`scoring_run`/`scoring_task`, `resume()` at startup). Provider errors are typed
  (`ConcurrencyLimited`, `QuotaExceeded`, `TransientError`, `ScoringFailed`; `ollama.classify_error`): 429 concurrency →
  same job to the front + backoff + adaptive limit (`ConcurrencyController`), quota → fallback model for the rest of the
  run, others → 3 attempts + one end-of-run retry.
- Rescore (`POST /scoring/rescore`, `RescoreModal`): scope (`all`, `stale`, `outdated`, `unscored`, `failed`, `jobs`) plus filters `track`, `since_days`, `limit`, `only_unscored`, `job_ids`; bulk scopes always end in `open_jobs.split_open` (so dismissed, closed, duplicate and hidden jobs are skipped and the `limit` counts open jobs only), `job_ids` only narrow a scope, and only `scope=jobs` (picked one by one) can rescore a non-open job. Rescore stale/outdated is reachable from Discover (`ScoringProgress`) and Today.
- Bulk scoring only touches **open** jobs (`services/open_jobs.py`: not closed/dismissed, not a duplicate, not hidden by the location/remote filters, not past max age from a paused source). `enqueue(only_open=True)` filters, `_claim` re-checks per task, the per-job Rescore passes `only_open=False`; `recompute_all` covers every job.
- Discovery is additive and only calls `enqueue_never_scored()`. Bulk rescore of existing scores requires `confirm: true`.
- Roles live only in `search_profile.tracks`; `services/roles.py` is the language lexicon (variants, matching).
  `tests/test_roles.py` fails if role titles get hardcoded in services/providers/prompts.
- Queues are per workspace (`workspace_queue`). The sandbox and tests always use `MockFitScorer`.
- Settings changes to `scoring` or `profile` call `recompute_all` (no LLM). Experience or profile changes make scores stale; never rescore automatically.
- Countries: target list = `search_profile.locations` (Settings). Country names/aliases/cities and region sets live in
  `services/geo.py` only; sources expose `unsupported_countries(targets)` instead of fixed country lists.
- Full listings: honest User-Agent only. If a site blocks us (403), offer paste. Never disguise the client.
- The test CV (`app/seed/test_cv.py`, `is_placeholder`) exists at the user's request. It's removable via `DELETE /api/experience/placeholders`.

## CV generation (docs/CV_TEMPLATES.md)

- Templates are **style only** (`templates/<name>/cv.tex.j2` + `cv.config.yaml`); `templates/reference/cv.tex` is the
  style reference (example content, never used for generation). Jinja delimiters `\VAR{}` (auto-escaped) / `\BLOCK{}`.
- The generator returns a `CVPlan` (pool ids, ranked bullets with a `strength`, each the pool fact or a light
  adaptation of it: see Experience pool below), never LaTeX, titles, companies or dates. `cv_check` validates it; `cv_build.fit_to_page` fits one page in code (no model call).
- Structure is decided in code (`services/cv_rules.py`, Settings → CV): bullet allowances by role type (current,
  roles over a year, graduation/short by relevance, internships ≤ 2, ≤ 2 projects of 2-3 bullets, never 1), entries
  start at their minimum and grow only within allowances while under the fill target (98%): never filler. With the APInex 2-pass generator, pass 1 also rates every other pool bullet and project (`plan.extras`); when the main CV is still under target, `cv_build.fill_by_relevance` adds them one at a time in relevance order (each through `cv_check.check_extra`: the pool's own text, numbers, tools, years, honesty; within the allowances and `projects_max`), skips what fails or doesn't fit, logs it in `plan.fill_log`, and accepts a slightly emptier page. Nothing is injected anymore, and a missing summary is retried once, then fails with Retry (never a snippet). Skills
  are capped and deduplicated but never merged or respelled (categories and items are the pool's, Claude only
  selects and orders: `cv_check.verbatim_skills`); the summary is checked against the writing guide and regenerated once. The
  writing guide and a style exemplar (plain text from `templates/reference/cv.tex`) go to the model.
- `claude -p` runs with `--system-prompt`, `--tools ""`, `--setting-sources ""`, `--strict-mcp-config`, `--json-schema`
  in a temp dir (never `--bare`: it skips the user's login). Prompt: `app/prompts/cv_generate.md` (versioned).
- Personal data never goes in templates or source: `tests/test_no_personal_data.py` derives tokens from the reference.
- The style golden test (`tests/test_cv_render.py`) compiles the default template against the reference: keep it pixel-equal.

## Experience pool (protected: services/experience_write.py, master_import.py, bullet_tailor.py)

- The pool is the user's own text. **No automated process may change it.** Every write to an `ExperienceItem` text
  field or a delete goes through `services/experience_write.py` (the Experience screen = source `user`, the explicit
  master import, Undo). A `before_flush` guard raises `PoolWriteError` for anything else; seeds of the tour sandbox
  run inside `writing()`. `tests/test_pool_protected.py` checks the guard, that no module writes pool text outside
  the gateway, and that generation leaves the pool unchanged. Every change is a row in `experience_history`
  (before/after, source), undoable per item from the Experience sheet.
- Master document import (`scripts/import_master.py`, `data/import/master_experience.md` + `master_mapping.json`):
  verbatim apart from `[cite: n]` markers; dry run by default, `--apply` backs up first; old items not in the
  document are archived (inactive, restorable), never deleted. `date_label` holds the dates exactly as written and
  CVs print it (`cv_pool.span`); `start_date`/`end_date` still drive the years arithmetic.
- CV tailoring is light and only in the CV copy (`services/bullet_tailor.py`): verb, clause order, the listing's term
  for what you did. In code, against the pool original of that exact bullet: every number, tool and named product
  kept, nothing new, length ±15%, most words kept; then the Claude verifier (`kind cv_bullets`) judges each adapted
  bullet against its original. Any failure puts the original back (a warning with the reason). Per CV:
  `overrides.original_only` (no adaptation anywhere) and `overrides.revert` (bullet keys back to the original); user
  edits in CV Studio win over both. Fitting to one page only chooses whole bullets, it never cuts text.

## Contacts (services/contacts.py, contacts_import.py)

- Per job: best-ranked contact at the company, never one marked left/wrong person (ranking in `app_setting.contacts`,
  cached on `contact.role_rank`) → tier `to_get` (nobody yet) → "No contact" when `company.contact_search` is
  not_found / never. `resolve` never replaces a manual pick, never touches closed jobs, never changes routes.
- Get contact step (`services/get_contact.py`, `api/get_contact.py`): states get / verify / ready / never;
  `require_ready` gates drafting (before research) and approval. Anyone you enter is verified; a verification lasts
  `contacts.verify_days`. Contacts to get = jobs past New, best fit first. Paste parsing is `services/contact_paste.py`.
  Hunter (`providers/hunter.py`, `HUNTER_API_KEY`) is called only from the Try Hunter endpoints (tested); paid calls
  are never retried.
- **Find contact waterfall (Phase 12, docs/CONTACT_SOURCES.md)**: `services/contact_waterfall.py` is started only by
  `POST /applications/{id}/contact/find` (one click; `tests/test_waterfall.py` guards it): company cache → Hunter →
  Prospeo → Apollo → Apify (`microworlds/leads-finder`) → local email pattern + verifier → the Apollo extension. It stops at the
  first VERIFIED email (`valid` only: catch-all/unknown are never used) and the contact keeps its provenance
  (`found_by_*`, `verification_status`; `verified_at` stays empty until you confirm). Finders are in
  `providers/contact_finders/` (pure `parse_*` mappers, `retries=0` on paid calls, keys passed per call). Credits are per key
  (`services/provider_quota.py`: monthly counters, real balances synced before a paid call, a refused key is disabled and never
  retried). Keys come from `.env` (`*_API_KEYS` comma-separated, `APIFY_TOKEN`); tests blank them. Never call a finder from
  discovery or the scheduler. Company domain/size: `services/company_resolve.py` (typed → PDL via DuckDB → listing).
- Matching runs after discovery (`discovery.after_discovery`), after each import, and via `POST /contacts/match`.
- Import dedupe: email (case-folded) → company (`normalize_company`) + folded name → create. Fill-only updates.
  The DB is backed up before imports (`contacts_import.backup_db`, sqlite online backup; never `cp` a WAL DB).

## Outreach (services/outreach.py, outreach_check.py, send_queue.py)

- Drafts: one job at a time (a lock), from the **approved** CV's items only; Claude via `providers/claude_email.py`
  (subclass of the CV generator: same isolation, `apiKeySource == "none"`). Prompt `app/prompts/outreach.md` is
  versioned like the others. Checks reuse `cv_check.sentence_problems`; one retry with feedback; errors block approval.
- Code builds the subject ("Software engineer interested in joining {Company}", `intro_check.subject_line`),
  the greeting and the intro line. The signature ends with the sign-off and your name (contact line opt-in);
  no last line by default. The hook is checked against its cited signals by gemma
  (`services/hook_check.py`, `OllamaStructured` shared with research; `MockHookChecker` in tests/sandbox), per
  attempt and again on approve if the hook was edited. Any outreach prompt edit needs `make eval-emails` recorded
  in `app/prompts/eval_log.json`.
- Sending: `send_queue.tick` (worker thread in the real workspace, `SEND_WORKER_ENABLED`), Gmail SMTP
  (`providers/smtp_mailer.py`, `SMTP_APP_PASSWORD` via `get_settings()`). Tests and the sandbox use `MockMailer`;
  never send real email from tests. A test send must succeed before `resume`.

## Tracking after the CV (services/tracking.py, api/tracking.py)

- No model calls. Mark applied (from `cv_ready`/`ready`) locks the CV version sent (`locked_at`, `pdf_sha256`); locked
  versions are never re-rendered, re-approved or superseded. `PATCH stage` refuses `done` (web apply) and `interview`.
- Replies, interview rounds and reminder actions are their own tables; reminders are computed from `app_setting.tracking`.
  Ghosting is only suggested; closing needs the user's click. Stats/CSV come from `tracking.tracked()` rows.
- Frontend: `components/app/tracking/*` (dialogs, AppliedFacts, TrackingActions), `features/applications/*`.

## CV and email generation on Gemini, background drafting (services/generation.py, providers/gemini_generate.py)

- Settings → Models: `models.cv` / `models.email` = `{provider, model, thinking_level}`; `cv` defaults to APInex (`free/minimax-m3.1-flash`, the 2-pass generator; Gemini and Claude stay selectable), `email` to `gemini-3.5-flash-lite`,
  `minimal` (= no thinking; `dynamic` = `thinkingBudget -1`; `thinkingBudget: 0` is rejected by 3.5). `services/model_choice.py`
  reads it; `registry.cv_generator/email_drafter(model, thinking_level, engine)` return the Gemini subclasses
  (`GeminiCVGenerator(ClaudeCVGenerator)`, same prompts/schemas/checks, only `_call` replaced). Claude stays the claim verifier,
  Critique, Ask Claude, and a one-shot `use="claude"` on the generate endpoints ("Generate with Claude").
- A Gemini failure (after 5 backoffs 5-60 s with key rotation) is `GenerationFailed`: HTTP 503 on the CV endpoint,
  `DraftProgress.generation_failed` on the email one; the page shows Retry / Generate with Claude. **Never switch model silently.**
- `gemini_generate.check_private` refuses any request containing the profile's email, phone digits or link URLs. A link inside
  pool text (the Lovester bullet's domain) is not profile data: the email output strips backticks and URLs (`applied_check.clean`).
- One pool for scoring, CV and email (`gemini_keys.pool_for(engine, model)`): `acquire(priority="user"|"background", avoid=)`.
  Scoring is background: it yields while a user call waits and never uses the last `USER_RESERVE` (50) requests of a key's day.
  `snapshot()["pooled"]` is shown in Settings → Models and on Today (`GET /scoring/quota?model=`).
- Background drafting: `generation_task` rows (migration 0031) inserted in-session by hooks, run by one worker thread
  (`generation.start_worker`, real workspace only, `GENERATION_WORKER_ENABLED`; tests/sandbox never start it, the sandbox never
  enqueues). `pipeline.transition` → `on_shortlisted` (queue a CV draft unless a CV exists / setting off / came from cv_ready) and
  `on_unshortlisted` (cancel queued; a running one finishes and its draft stays). The email is queued by
  `maybe_enqueue_email` after CV approval, a contact becoming verified, or a shortlist: needs `generation.auto_email`, a job in
  shortlisted/cv_ready with a posting, an approved CV, a ready contact, no live draft. Settings `generation = {auto_cv: true,
  auto_email: false}`. Drafts only: nothing is approved, no toasts; `Tracks.cv` / `Tracks.generation` feed the badges
  ("CV ready to review", "Email ready to review"), `GET /generation/status` drives the refresh.
- Email prompt v14 (applied mode): experience = a short first-person summary of 1-2 things, not the bullets. Copy check
  `applied_check.copy_run` (8+ consecutive words with a pool bullet or a `style_reference` example) → one automatic regeneration
  ("summarize in your own words"), still copying = warning. Numbers ≤ 2 and tools ≤ 3 per email, fragments (no "I") warn, a
  location sentence warns unless the listing states a LOCATION requirement (`listing_states_location`: a language
  requirement doesn't count). The style reference lives in `email_example` (kind `style_reference`, `inputs.mode = applied`) and is
  sent as a STYLE REFERENCE block; kind `must_warn` rows (emails that copied) are checked by `make eval-emails`
  (`eval.emails.check_must_warn`). Verifier prompt v6 accepts faithful paraphrase and adds the non-blocking `garbled` verdict.
- CV: `cv_check.summary_support` (summary names a tool/concept no included bullet or skill shows, or a qualifier your pool never
  says: Settings → CV `qualifiers`) is a warning and feeds the summary retry; `cv.skill_display` (per-track category names) and
  `cv.skill_keep` (pool skills pinned first per track, e.g. Mobile: Kotlin, Swift) apply in `cv_build.build_document`.

## Cover letters, questions, email route (Phase 6)

- Both routes per job (Phase 7): `services/tracks.py` derives the Application and Outreach tracks (DTO field
  `tracks`); the stage is the overall position and never goes back when the second route finishes. `route` and
  `effective_route` are gone from the logic; `drafted` was retired. Approve and "Add to send queue" are separate.
- Who to contact: `contacts.who_to_contact` (size ranking + track, copyable LinkedIn/Apollo hints; never searches).
- Letter formats: `cover_letter.format` pdf | form (`draft_form`, prompt sections `form`/`form_retry`); writing
  rules checked in `letter_check.check_letter` (restates, cv_copy, jargon, current_role, builds, ask, fit sentences
  `about_candidate` from Settings → Candidate only).
- Copilot: `services/copilot.py` + `providers/ollama_chat.py` (local model, streamed, no tools), prompt
  `app/prompts/copilot.md`; answers get `warnings`. Studio: `api/studio.py`.
- Cover letters: `services/cover_letter.py` + `providers/claude_letter.py` (same headless setup and subscription check
  as the CV), prompt `app/prompts/cover_letter.md` (sections `system`, `retry`, `answers`, `answers_retry`; bump the
  version on any edit). The model returns cited paragraphs + one ask; code adds header, date, salutation, closing.
- Checks in `services/letter_check.py` (grounding reuses `cv_check`/`outreach_check`; French years wording; grouped
  numbers like "2 000"). Template `templates/<name>/cover_letter.tex.j2` must keep the CV header identical.
- Language: `services/text.detect_language` (fr/en), overridable per job (`application.letter_language`).
- Application answers: `services/answers.py` (one call per batch, character limit = hard error, never truncate).
- Real generations run from a standalone script, not through the dev server (reloads kill the subprocess).

## Cold email as an introduction + company research (Phase 8)

- Two modes (`outreach.email_mode`, prompt `outreach.md` v11; the sections `system` = speculative, `applied`): a job
  with a posting gets the **application follow-up** (`services/applied_check.py`, `generate_applied`, plan
  `AppliedEmailPlan`): opening (applied / applying, nothing else), at most two cited one-sentence proofs (aim 90-120
  words), an optional
  signal (default empty), a natural ask; no constraint sentence (the `constraint` field is gone); code builds the greeting and the subject ("<Role>
  application – <name>"); no research starts. **Only facts block** (pool grounding, years, honesty, names, company
  facts from the listing/signals), and the **visa ban**: any visa, sponsorship, work-permit/authorization or relocation
  wording (EN, plus DE/FR: Arbeitserlaubnis, Aufenthalt…, Umzug, titre de séjour, permis de travail, parrainage…) in the
  model-written parts (opening, experience, ask) is an error (`applied_check.visa_disclaimer_banned`; the listing's
  signal and company facts may use the words; on an edited email the paragraph that carries a signal is skipped);
  length (90-170), tools, banned phrases, jargon, restating, a long opening,
  an unprompted location sentence, a listing under `applied_check.SNIPPET_CHARS` (1,500) are warnings (the Job page offers
  Fetch/Paste first; fetching never touches LinkedIn). The Claude verifier gets the listing and the application status for these emails (the "Based in /
  Work authorization / Relocation" lines are no longer sent: the emails never mention them). Don't re-add the old blocking rules here.
- Language (`services/language.py`): detected among en/fr/de/es/ar; write in the listing's language only if it is a
  working-level language in the profile AND en/fr (the app builds greetings/subjects/years in those two), else English;
  explicit choices (draft dropdown, `application.letter_language`, Settings → Email) win; `plan.language_choice` stores
  the reason. Never add a two-language voter again: it read German as French.
- Regenerate with feedback: `outreach.generate(feedback=, base_draft_id=, language=)` puts `rules["revision"]` (previous
  draft + feedback) in the request; prompt sections `revise` (outreach v13, linkedin v5, cover_letter v8). Drafts are kept
  (`parent_id`, `feedback`, `draft_history`); LinkedIn keeps `history` in the message JSON; letters keep versions.
- Approval without verification (`outreach.approve_unverified`, `verifier.send_gate`): this draft only, records
  `unverified_approval` (ignored issues + hashes); the send gate still checks text/attachment hash, contact and CV
  version; a send-back clears it; it is never recorded in the regression set.
- Copy for another AI (`services/external_ai.py`, prompt sections `external*`): prompt = listing + recipient + only the
  relevant experience + rules + language + an approved example; never phone/email/other contacts. A pasted draft is
  checked (code + Claude verifier) before it can be saved as a draft.
- The **speculative email** (no posting, or `?mode=speculative`) keeps the introduction: hook from verified signals,
  intro line built by code (`intro_check.intro_line`), their problem + 1-2 proofs, a direct opening question.
  Checks in `services/intro_check.py`. The listing is never mentioned, nor location/visa.
- Research (`services/research.py`) may start ONLY from `outreach.generate_intro` (the draft step) or
  `api/research.py` (Research now). `tests/test_research_guard.py` fails otherwise. Fresh signals are reused.
  Quotes are verified in code; model output goes through `ollama.structured` (scoring's error classes).
- Any edit to `app/prompts/outreach.md` needs a version bump **and** a `make eval-emails` run recorded in
  `app/prompts/eval_log.json` (tested). Examples set structure and tone only: never put their wording in prompts.
- The sandbox uses `SampleFetcher` + `MockResearcher`: it never fetches the web.

## Interview prep, glossary, listing flags (Phase 12b)

- Interview prep (`services/interview_prep.py`, `providers/claude_interview.py`, `prompts/interview_prep.md`, table
  `interview_prep`): from the whole pool only, every sentence cited and checked with `cv_check.sentence_problems` + the honesty
  rules; a story with no stated result has none. Approval = code errors fixed + `verifier.require_interview_prep` (kind
  "interview preparation"). `MockInterviewDrafter` in tests and the sandbox. Edit = new check, stale verification.
- Glossary (`services/glossary.py`, `profile.glossary`): the user's own words only; code never writes entries. `Pool.all_text` and
  `cv_check.cited_text` add the "to" terms of entries whose "from" the text contains; FACTS.glossary reaches the CV
  summary and letter prompts and the verifier's facts. Any prompt edit still needs a version bump (cv_generate 10,
  cover_letter 7, verify 4, interview_prep 1).
- Listing flags (`services/listing_flags.py`): code only, hints on `JobDetail.listing_flags`, never a score or filter.
- Domains (`services/domains.py`, `dns_check.py`): `company.domain` = website, `company.email_domain` = mail/lookup domain
  (set from verified emails), `company.domains` = every known domain + cached MX. The waterfall checks MX (free) before any paid
  call, tries other known domains, and on "provider found nobody at this domain" stops with `Outcome.choice` instead of paying
  the next provider (rerun with `email_domain`). `CompanyProviderRun.domain` keeps a run for one domain from standing in for another.
  PDL picks by LinkedIn page, then country, then size. Guessed endings are only offered, never used on their own.
- Contact ranking: `contacts.exclude_keywords` (default business development, sales, account) is injected into every
  group by `with_exclude`, so `rank()` skips titles containing them.

## Honesty and LinkedIn readers

- `search_profile.tracks[].experience` is `professional` | `projects`. `services/honesty.py` flags years attached to a
  projects track and titles implying professional experience in it; every checker (CV summary, letters, answers,
  emails, LinkedIn) adds it as an error and every prompt gets `honesty.prompt_facts`. Never weaken it to pass a draft.
- LinkedIn groups are the note's angle (`linkedin.detect_group`, overridable); `hiring_team` is a separate flag.
  Per-group rules are in `linkedin_check._group_rules`; the transition line is code (`linkedin_track.framing`).
  LinkedIn reference notes (`email_example.inputs.channel == "linkedin"`) never enter the email eval or prompts.
- LinkedIn messages are tied to a job (prompt `linkedin.md` v4): the role and the listing may be named, an InMail or
  follow-up states a requirement you don't meet once and plainly (FACTS.logistics), and only facts block
  (grounding, years/honesty, links, a profile-visit hint, length limits); the ask, banned phrases, jargon,
  reference wording and an unprompted location/visa are warnings (`linkedin_check._location`).
- LinkedIn Premium (prompt `linkedin.md` v3, migration 0029): InMail is `linkedin_outreach.inmail` (subject + body, `linkedin_check.check` + `check_subject`, claim-verified as `inmail_text` = subject + body). Credits are derived from `inmail_sent_at` / `inmail_refunded_at` (`linkedin_track.credits`; refund only for a reply within 90 days). Viewer leads store the reason in `reason` and NEVER pass it to a model (`_request` sends only `warm_opener`); `linkedin_check._VIEWED` rejects any mention of a profile visit. No-job leads live in `linkedin_lead` and link themselves in `leads()`.
- `services/agency.py`: agency jobs get recruiters only (no alumni or team-lead searches), and recruiters first in
  the contact ranking (`Ranking.order_for(company, job)`: pass the job when you have it). `company.agency_override`
  (employer | agency) always wins over the signals; `agency.detected` is the rule alone.
- CV approval blocks on errors (as letters and emails). Mark problems the checker fixes itself as warnings.
- Summary checks (`cv_rules.summary_problems`, grounding, honesty, `cv_service.summary_warnings`) are warnings only, with
  `phrase` + `rule`, live via `POST /cv/{id}/summary/check`; they never block approval and never swap in a fallback. Approval
  records them (`approved_summary_warnings`). "New summary" takes optional feedback (prompt `cv_generate` v11 `revise`) on the
  Settings → Models CV model; history in `plan.summary_history`. Transition framing ("now focused on…", "moving into") is
  allowed for Data/AI; those phrases are never banned (`cv_rules.banned` strips them even from saved lists).
- Contact check (`services/contact_check.py`): research also searches news for each contact's name and scans
  pages for departure/new-holder sentences (regex, no model). Active `contact_alert` rows block approval;
  `next_contact` follows the ranking. The sandbox seeds one sample departure (`seed._seed_contact_alert`).

## LinkedIn (Phase 10: services/linkedin.py, linkedin_track.py, linkedin_check.py)

- Never scrape, crawl or automate LinkedIn: the backend builds links only (`tests/test_linkedin.py` guards against
  requests to linkedin.com). Search links use geoIds from `linkedin.geo_ids`, never a text location.
- The bookmarklet (`frontend/src/features/linkedin/capture.ts`, self-contained: its source becomes the bookmark)
  passes data in the `/import` URL fragment. Imports are `Source.linkedin` (excluded from `DISCOVERY_SOURCES`),
  scored alone at the front of the queue.
- LinkedIn messages: `claude -p` with `prompts/linkedin.md` (sections note / followup / retry); checks in
  `linkedin_check.py`; the school angle is alumni-only and LinkedIn-only. Follow-up research may call
  `research.ensure` (allowed in the research guard).
- Fit before/after (`cv_fit.py`, stored in `cv_fit`, never a `fit_score` row) and Critique (`critique.py`,
  `prompts/critique.md`, issues only). Adapted ideas are credited in `docs/CREDITS.md` (MIT).

## Claim verifier (services/verifier.py, providers/claude_verify.py, prompts/verify.md)

- Zero tolerance, Claude (`claude -p`, Opus by default, same isolation and subscription check, never an API key),
  a separate call that gets only the final text and its sources (pool items, approved CV, facts, signals, and the
  listing for letters/answers/LinkedIn, plus the recipient). It splits every sentence into claims; unsupported,
  exaggerated, merged or causal blocks. Code checks the verifier: a "supported" quote must be in its source, and every
  sentence must be judged. Code checks run first; Claude only sees a text that passes them.
- Gates: email and letter approval (`require_email` / `require_letter`, reused when the exact text is unchanged),
  Copy and "I sent it" for LinkedIn and form answers. The send queue's last step (`send_gate`) compares the exact
  subject + body + CV file with the verified hashes; any difference sends the email back to review.
- Facts it knows (prompt v5): the "Application" status is in FACTS (the "Based in", "Work authorization",
  "Relocation" lines no longer populate for job-linked emails: the visa ban keeps them out of the text); the listing is a source for job-linked emails. The regression set includes
  `mode: applied` must-pass and `must_fail` emails (`data/eval/email_examples.json`, `--import`).
- Suggested fixes (`services/claim_fix.py`, prompt v7): each blocking claim gets a `fix` from the same call (no extra request, no Gemini); code repairs first, every candidate re-checked in code, failing ones become "remove"; `POST /claim-fixes/apply` edits via the normal edit path and re-verifies only the changed sentences. It never changes what blocks.
- Tests and the sandbox use `MockVerifier`. `make eval-verifier` runs the must-pass / must-fail set (email_example
  kinds reference_good / approved / must_fail). Any edit to `prompts/verify.md` needs a version bump.

## Motivation (Phase 11: services/motivation/, api/motivation.py, features/motivation/)

- A separate module: it only reads job data (`activity.py`) and only writes its own tables. Never make an existing
  flow depend on it; `motivation.enabled` hides it everywhere (sidebar entry has `feature: 'motivation'`).
- The streak is computed from history every request (`streak.compute`, pure, tested); never store a counter.
  Days are local (`motivation.timezone`). Chests subtract each opened chest's own cost; tokens are a ledger.
- Uploads: `files.check` (extension + magic bytes, size limit), stored under data/motivation/<workspace>/, served
  by name only (uuid names). Undo for "Mark applied" is `tracking.undo_applied` (+ `pipeline.revert`).

## Conventions

- Python: 3.12, type hints everywhere, ruff (line length 100). Datetimes are UTC-aware, and `app.models.base.utcnow()`.
- API: JSON in snake_case (TS types use snake_case too, so there is no mapping layer). Lists return `{items, total}` when paginated.
- No real network or LLM calls unless the task explicitly implements that provider. Tests never hit the network.
- TypeScript: strict, linted with oxlint (no warnings allowed). Components are PascalCase files, hooks are `useX.ts`, and screens live under `features/`. Use the `@/` alias for `src/`. Keep component files exporting only components (fast refresh), and put helpers in `.ts` files.
- UI primitives in `components/ui/` are hand-written shadcn-style wrappers over `radix-ui`. `components.json` exists, so `npx shadcn add x` works, but restyle the result to tokens.
- Commits: small, imperative, prefixed (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).

## Design rules (non-negotiable, see docs/DESIGN.md)

1. Only design tokens. No hex, no Tailwind palette classes (`bg-blue-500`), no arbitrary color values. `make lint` enforces this.
2. Stage → `<StageBadge>`, fit → `<FitBadge>`, source → `<SourceBadge>`. Never hand-roll these.
3. Every data view has loading (skeleton), empty (with one next action), error (with retry), and populated states.
4. One primary button per view. Dismiss and reject use undo toasts, not confirm dialogs.
5. List views support j/k plus their action keys via `useListKeyboard`. Register global keys only through `useHotkeys`.
6. Check light **and** dark theme at 1280px and 1440px widths for every UI change. The minimum width is 1024px.
7. No dead ends. Every screen offers the next step in the flow.
