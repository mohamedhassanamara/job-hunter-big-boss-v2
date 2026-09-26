SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python

.PHONY: setup dev seed seed-empty migrate test lint build backend frontend

setup: ## Create venv, install backend + frontend deps, migrate and seed
	cd $(BACKEND) && uv venv --python 3.12 --allow-existing .venv && uv pip install --python .venv/bin/python -e ".[dev]"
	cd $(FRONTEND) && npm install
	$(MAKE) migrate seed

dev: ## Run API (:8000) and web (:5173) together
	./scripts/dev.sh

backend:
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd $(FRONTEND) && npm run dev

migrate: ## Apply Alembic migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

seed: ## Reset the DB contents with mock data
	cd $(BACKEND) && .venv/bin/python -m app.seed.seed

seed-empty: ## Reset to an empty workspace (to see empty states / onboarding)
	cd $(BACKEND) && .venv/bin/python -m app.seed.seed --empty

test:
	cd $(BACKEND) && .venv/bin/pytest -q

lint:
	cd $(BACKEND) && .venv/bin/ruff check app tests
	cd $(FRONTEND) && npx tsc -b && npm run lint
	./scripts/check-tokens.sh

build: ## Production build of the frontend (type-checks too)
	cd $(FRONTEND) && npm run build
