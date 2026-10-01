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
make migrate   # alembic upgrade head
make test      # backend pytest (never calls a model or the network)
make eval      # score your labeled jobs with the real model; report in data/eval/ (ARGS="--fresh")
make lint      # ruff + tsc + oxlint + design-token guard
make build     # frontend production build
```
Dev aids: `MOCK_LATENCY_MS=1500 make dev` slows every API response (check skeletons). Stopping only the
backend shows error states. `JOB_SOURCES=mock` swaps every job source for the offline mock.
Secrets and keys go in `.env` (see `.env.example`): `ADZUNA_APP_ID/KEY`, optional `WTTJ_ALGOLIA_KEY`.

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
  FitScorer=Ollama, CVGenerator=Claude Code headless (`providers/claude_cv.py`); rendering is `services/cv_render.py`
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
- The cache key includes the prompt version. **Any edit to `app/prompts/fit_score.md` needs a version bump** and a new hash in
  `prompts/versions.json` (`tests/test_prompt.py` tells you the hash).
- Models (Settings → Models): `models.scoring = {model: gemma4:31b-cloud, fallback: gemma4:12b, cloud_concurrency:
  {min, start, max}, local_concurrency}`. Cloud: schema in the prompt + validation; local: native `format`, `think: false`.
- The queue (`ScoringQueue`) is persistent (`scoring_run`/`scoring_task`, `resume()` at startup). Provider errors are typed
  (`ConcurrencyLimited`, `QuotaExceeded`, `TransientError`, `ScoringFailed`; `ollama.classify_error`): 429 concurrency →
  same job to the front + backoff + adaptive limit (`ConcurrencyController`), quota → fallback model for the rest of the
  run, others → 3 attempts + one end-of-run retry.
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
- The generator returns a `CVPlan` (pool ids, ranked reworded bullets with a `strength`), never LaTeX, titles,
  companies or dates. `cv_check` validates it; `cv_build.fit_to_page` fits one page in code (no model call).
- Structure is decided in code (`services/cv_rules.py`, Settings → CV): bullet allowances by role type (current,
  roles over a year, graduation/short by relevance, internships ≤ 2, ≤ 2 projects of 2-3 bullets, never 1), entries
  start at their minimum and grow only within allowances while under the fill target (88%): never filler. Skills
  are capped/merged/deduplicated; the summary is checked against the writing guide and regenerated once. The
  writing guide and a style exemplar (plain text from `templates/reference/cv.tex`) go to the model.
- `claude -p` runs with `--system-prompt`, `--tools ""`, `--setting-sources ""`, `--strict-mcp-config`, `--json-schema`
  in a temp dir (never `--bare`: it skips the user's login). Prompt: `app/prompts/cv_generate.md` (versioned).
- Personal data never goes in templates or source: `tests/test_no_personal_data.py` derives tokens from the reference.
- The style golden test (`tests/test_cv_render.py`) compiles the default template against the reference: keep it pixel-equal.

## Contacts (services/contacts.py, contacts_import.py)

- Per job: best-ranked contact at the company, never one marked left/wrong person (ranking in `app_setting.contacts`,
  cached on `contact.role_rank`) → tier `to_get` (nobody yet) → "No contact" when `company.contact_search` is
  not_found / never. `resolve` never replaces a manual pick, never touches closed jobs, never changes routes.
- Get contact step (`services/get_contact.py`, `api/get_contact.py`): states get / verify / ready / never;
  `require_ready` gates drafting (before research) and approval. Anyone you enter is verified; a verification lasts
  `contacts.verify_days`. Contacts to get = jobs past New, best fit first. Paste parsing is `services/contact_paste.py`.
  Hunter (`providers/hunter.py`, `HUNTER_API_KEY`) is called only from the Try Hunter endpoints (tested); paid calls
  are never retried.
- Matching runs after discovery (`discovery.after_discovery`), after each import, and via `POST /contacts/match`.
- Import dedupe: email (case-folded) → company (`normalize_company`) + folded name → create. Fill-only updates.
  The DB is backed up before imports (`contacts_import.backup_db`, sqlite online backup; never `cp` a WAL DB).

## Outreach (services/outreach.py, outreach_check.py, send_queue.py)

- Drafts: one job at a time (a lock), from the **approved** CV's items only; Claude via `providers/claude_email.py`
  (subclass of the CV generator: same isolation, `apiKeySource == "none"`). Prompt `app/prompts/outreach.md` is
  versioned like the others. Checks reuse `cv_check.sentence_problems`; one retry with feedback; errors block approval.
- Code builds the greeting and the intro line. The hook is checked against its cited signals by gemma
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

- The email is a personal introduction (prompt `outreach.md` v5+): hook from verified signals, intro line built by
  code (`intro_check.intro_line`), their problem + 1-2 proofs, a direct opening question. Checks in
  `services/intro_check.py`. The listing is never mentioned, nor location/visa.
- Research (`services/research.py`) may start ONLY from `outreach.generate_intro` (the draft step) or
  `api/research.py` (Research now). `tests/test_research_guard.py` fails otherwise. Fresh signals are reused.
  Quotes are verified in code; model output goes through `ollama.structured` (scoring's error classes).
- Any edit to `app/prompts/outreach.md` needs a version bump **and** a `make eval-emails` run recorded in
  `app/prompts/eval_log.json` (tested). Examples set structure and tone only: never put their wording in prompts.
- The sandbox uses `SampleFetcher` + `MockResearcher`: it never fetches the web.
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
