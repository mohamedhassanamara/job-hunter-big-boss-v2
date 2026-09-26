# Job Hunter v2

A local, single-user web app for my Data/AI Engineering job search (ES/PT/FR/IT/remote). It discovers jobs,
scores fit, resolves contacts, generates a tailored one-page LaTeX CV, and drafts cold emails or routes
the job to manual web apply. I review everything before anything is sent.

**Read before working:** `docs/SPEC.md` (screens, flow, states), `docs/DATA_MODEL.md` (tables, stage
transitions), `docs/DESIGN.md` (tokens and UI rules). Keep them updated when behavior changes.

## How to run

```bash
make setup     # first time: uv venv (Python 3.12) + pip deps, npm install, migrate, seed
make dev       # API on :8000 (docs at /docs) + web on :5173, Ctrl-C stops both
make seed      # reset DB contents to mock data
make migrate   # alembic upgrade head
make test      # backend pytest
make lint      # ruff + tsc + eslint + design-token guard
```
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

## Conventions

- Python: 3.12, type hints everywhere, ruff (line length 100). Datetimes are UTC-aware, and `app.models.base.utcnow()`.
- API: JSON in snake_case (TS types use snake_case too, so there is no mapping layer). Lists return `{items, total}` when paginated.
- No real network or LLM calls unless the task explicitly implements that provider. Tests never hit the network.
- TypeScript: strict. Components are PascalCase files, hooks are `useX.ts`, and screens live under `features/`. Use the `@/` alias for `src/`.
- Commits: small, imperative, prefixed (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).

## Design rules (non-negotiable, see docs/DESIGN.md)

1. Only design tokens. No hex, no Tailwind palette classes (`bg-blue-500`), no arbitrary color values. `make lint` enforces this.
2. Stage → `<StageBadge>`, fit → `<FitBadge>`, source → `<SourceBadge>`. Never hand-roll these.
3. Every data view has loading (skeleton), empty (with one next action), error (with retry), and populated states.
4. One primary button per view. Dismiss and reject use undo toasts, not confirm dialogs.
5. List views support j/k plus their action keys via `useListKeyboard`. Register global keys only through `useHotkeys`.
6. Check light **and** dark theme at 1280px and 1440px widths for every UI change. The minimum width is 1024px.
7. No dead ends. Every screen offers the next step in the flow.
