.DEFAULT_GOAL := help
.PHONY: all help install setup env dev dev-api dev-web db-up db-down db-migrate gen-api build lint test clean

API := apps/api

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install web (bun) and api (uv) dependencies
	bun install
	cd $(API) && uv sync

env: ## Create .env files from examples if missing
	@test -f $(API)/.env || cp $(API)/.env.example $(API)/.env
	@test -f apps/web/.env.local || cp apps/web/.env.example apps/web/.env.local

setup: install env db-up db-migrate ## Full first-time setup

all: ## Run EVERYTHING: db, migrations, Ollama, api, web, scheduler (scripts/dev-all.sh)
	./scripts/dev-all.sh

dev: ## Run api and web together
	bun run dev

dev-api: ## Run api only (:8000)
	bun run dev:api

dev-web: ## Run web only (:3000)
	bun run dev:web

db-up: ## Start postgres and minio
	bun run db:up

db-down: ## Stop docker services
	bun run db:down

db-migrate: ## Apply alembic migrations
	bun run db:migrate

gen-api: ## Regenerate OpenAPI types for web
	bun run gen:api

build: ## Build web
	bun run build

lint: ## Lint web and api
	bun run lint

test: ## Run api tests
	bun run test

clean: ## Remove build artifacts and caches
	rm -rf apps/web/.next apps/web/tsconfig.tsbuildinfo $(API)/.pytest_cache $(API)/.ruff_cache
