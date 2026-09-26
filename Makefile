SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python

.PHONY: setup dev seed reset migrate test lint build backend frontend

setup: ## Create venv, install backend + frontend deps, migrate and seed
	cd $(BACKEND) && uv venv --python 3.12 --allow-existing .venv && uv pip install --python .venv/bin/python -e ".[dev]"
	cd $(FRONTEND) && npm install
	$(MAKE) migrate
	cd $(BACKEND) && .venv/bin/python -m app.seed.seed --defaults
	$(MAKE) seed

dev: ## Run API (:8000) and web (:5173) together
	./scripts/dev.sh

backend:
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd $(FRONTEND) && npm run dev

migrate: ## Apply Alembic migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

seed: ## Rebuild the tour sandbox (sample data lives ONLY there, never in the real DB)
	cd $(BACKEND) && .venv/bin/python -m app.seed.seed

reset: ## ERASE the real workspace (keeps search profile + settings defaults)
	@read -p "Erase ALL real jobs, contacts, CVs and drafts? Type ERASE: " c && [ "$$c" = "ERASE" ]
	cd $(BACKEND) && .venv/bin/python -m app.seed.seed --erase-real

test:
	cd $(BACKEND) && .venv/bin/pytest -q

lint:
	cd $(BACKEND) && .venv/bin/ruff check app tests
	cd $(FRONTEND) && npx tsc -b && npm run lint
	./scripts/check-tokens.sh

build: ## Production build of the frontend (type-checks too)
	cd $(FRONTEND) && npm run build
