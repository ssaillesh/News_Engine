.DEFAULT_GOAL := help
.PHONY: help install test test-postgres lint fmt typecheck run clean pg-up pg-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv deps (editable + dev extras)
	python3 -m venv .venv
	. .venv/bin/activate && pip install -e ".[dev]"

test: ## Run the test suite (SQLite backend)
	pytest -q

PG_TEST_URL ?= postgresql+psycopg://postgres:postgres@localhost:55432/archive

pg-up: ## Start a throwaway Postgres 16 container for tests
	docker rm -f ts-archiver-pg >/dev/null 2>&1 || true
	docker run -d --name ts-archiver-pg -e POSTGRES_PASSWORD=postgres \
		-e POSTGRES_DB=archive -p 55432:5432 postgres:16 >/dev/null
	@echo "waiting for postgres..." && sleep 3

pg-down: ## Remove the throwaway Postgres container
	docker rm -f ts-archiver-pg >/dev/null 2>&1 || true

test-postgres: ## Run the integration tests against real Postgres (needs pg-up + .[postgres])
	TEST_DATABASE_URL="$(PG_TEST_URL)" pytest tests/integration -q

lint: ## Ruff + mypy
	ruff check src tests
	mypy

fmt: ## Auto-format / auto-fix with ruff
	ruff format src tests
	ruff check --fix src tests

typecheck: ## Static type check only
	mypy

run: ## Show the CLI help (Phase 1: no collection)
	archiver --help

clean: ## Remove caches and local build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
