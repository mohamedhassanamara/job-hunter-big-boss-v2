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
  Planned: FitScorer=Ollama, CVGenerator=Claude, CVRenderer=pdflatex with one universal template, Mailer=Gmail SMTP.
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
- `score_job` never raises for model problems. It stores `status=failed` with the error, and a score is never defaulted.
- The cache key includes the prompt version. **Any edit to `app/prompts/fit_score.md` needs a version bump** and a new hash in
  `prompts/versions.json` (`tests/test_prompt.py` tells you the hash).
- Model = `app_setting.models.scoring.model` (Settings → Models): one local model, **gemma4:12b**, for every score
  (rescore all when it changes; eval reports record the model). Requests use structured output (`format` = schema),
  `think: false`, temperature 0. Parallel jobs ≤ 2 for local models (use 1 if the Mac gets sluggish). Cloud models
  (`…-cloud`) still work: the schema is added to the prompt for them, fences are stripped, 429s back off.
- Queues are per workspace (`workspace_queue`). The sandbox and tests always use `MockFitScorer`.
- Settings changes to `scoring` or `profile` call `recompute_all` (no LLM). Experience or profile changes make scores stale; never rescore automatically.
- Countries: target list = `search_profile.locations` (Settings). Country names/aliases/cities and region sets live in
  `services/geo.py` only; sources expose `unsupported_countries(targets)` instead of fixed country lists.
- Full listings: honest User-Agent only. If a site blocks us (403), offer paste. Never disguise the client.
- The test CV (`app/seed/test_cv.py`, `is_placeholder`) exists at the user's request. It's removable via `DELETE /api/experience/placeholders`.

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
