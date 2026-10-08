.PHONY: help up down logs pull-models test lint format typecheck check eval verify-airgap bundle

COMPOSE ?= docker compose

help: ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

pull-models: ## ONLINE ONLY: download models into the Ollama volume
	$(COMPOSE) --profile online run --rm model-pull

up: ## start the stack (models must already be in the volume)
	$(COMPOSE) up -d --build --wait

down: ## stop the stack (volumes are kept)
	$(COMPOSE) down

logs: ## follow logs
	$(COMPOSE) logs -f --tail=100

test: ## unit tests (no models, no network)
	uv run pytest

lint: ## ruff lint and format check
	uv run ruff check .
	uv run ruff format --check .

format: ## apply ruff formatting
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy
	uv run mypy

check: lint typecheck test ## everything CI runs

eval: ## ingest the sample docs and measure retrieval and latency against the running stack
	uv run python scripts/eval.py

verify-airgap: ## prove containers have no outbound network
	./scripts/verify_airgap.sh

bundle: ## ONLINE ONLY: build the offline bundle in dist/
	./scripts/bundle.sh
