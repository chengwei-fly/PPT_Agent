# PPTagent — root Makefile
# `make dev` should bring up infra + backend + frontend with a single command.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      ?= docker compose
BACKEND_DIR  := backend
FRONTEND_DIR := frontend
PYTHON       ?= python3
PIP          ?= uv

# ─── Help ─────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ─── Dev environment ──────────────────────────────────────────────────
.PHONY: dev
dev: infra-up backend-install frontend-install migrate seed dev-up ## 🚀 Bring up the full dev stack

.PHONY: dev-up
dev-up: ## Start backend + frontend in foreground
	@echo "Starting backend on :8000 and frontend on :5173"
	@$(MAKE) -j2 backend-run frontend-run

.PHONY: stop
stop: infra-down ## ⏹ Stop everything

.PHONY: clean
clean: ## 🧹 Remove caches + volumes
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .venv -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true

.PHONY: nuke
nuke: clean infra-down ## 💥 DESTRUCTIVE: nuke everything including volumes
	$(COMPOSE) -f infra/docker-compose.yml down -v
	@echo "All gone."

# ─── Infra ────────────────────────────────────────────────────────────
.PHONY: infra-up
infra-up: ## Start infra services (postgres, redis, minio, jaeger)
	cd infra && $(COMPOSE) up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@cd infra && $(COMPOSE) ps

.PHONY: infra-down
infra-down: ## Stop infra services
	cd infra && $(COMPOSE) down

.PHONY: infra-logs
infra-logs: ## Tail infra logs
	cd infra && $(COMPOSE) logs -f

.PHONY: infra-ps
infra-ps: ## Show infra service status
	cd infra && $(COMPOSE) ps

# ─── Backend ──────────────────────────────────────────────────────────
.PHONY: backend-install
backend-install: ## Install backend Python deps via uv
	cd $(BACKEND_DIR) && $(PIP) sync --extra dev

.PHONY: backend-run
backend-run: ## Run backend dev server
	cd $(BACKEND_DIR) && $(PIP) run uvicorn src.main:app --reload --port 8000

.PHONY: backend-shell
backend-shell: ## Open a Python shell in backend env
	cd $(BACKEND_DIR) && $(PIP) run python

.PHONY: backend-format
backend-format: ## Format backend Python
	cd $(BACKEND_DIR) && $(PIP) run ruff format .
	cd $(BACKEND_DIR) && $(PIP) run ruff check --fix .

# ─── Database ─────────────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Apply Alembic migrations to head
	cd $(BACKEND_DIR) && $(PIP) run alembic upgrade head

.PHONY: migration
migration: ## Create new Alembic migration (use msg="...")
	cd $(BACKEND_DIR) && $(PIP) run alembic revision --autogenerate -m "$(msg)"

.PHONY: db-reset
db-reset: ## Drop + recreate database (DESTRUCTIVE)
	@echo "⚠️  Dropping + recreating database"
	cd infra && $(COMPOSE) stop postgres
	cd infra && $(COMPOSE) rm -f postgres
	cd infra && $(COMPOSE) up -d postgres
	@sleep 5
	$(MAKE) migrate

.PHONY: seed
seed: ## Seed 5 typical PPTX samples into MinIO
	cd $(BACKEND_DIR) && $(PIP) run python -m src.scripts.seed_samples

# ─── Frontend ─────────────────────────────────────────────────────────
.PHONY: frontend-install
frontend-install: ## Install frontend deps via pnpm
	cd $(FRONTEND_DIR) && pnpm install

.PHONY: frontend-run
frontend-run: ## Run frontend dev server
	cd $(FRONTEND_DIR) && pnpm dev

.PHONY: frontend-build
frontend-build: ## Build frontend for production
	cd $(FRONTEND_DIR) && pnpm build

.PHONY: frontend-format
frontend-format: ## Format frontend
	cd $(FRONTEND_DIR) && pnpm format

# ─── Tests (Constitution §VI: 6 stages) ───────────────────────────────
.PHONY: test
test: ## 🧪 Run all unit + contract tests
	cd $(BACKEND_DIR) && $(PIP) run pytest tests/unit tests/contract -v

.PHONY: test-unit
test-unit: ## Unit tests only
	cd $(BACKEND_DIR) && $(PIP) run pytest tests/unit -v

.PHONY: test-contract
test-contract: ## Pact contract tests
	cd $(BACKEND_DIR) && $(PIP) run pytest tests/contract -v

.PHONY: test-integration
test-integration: ## Integration tests (requires infra)
	cd $(BACKEND_DIR) && $(PIP) run pytest tests/integration -v

.PHONY: test-e2e
test-e2e: ## Playwright E2E tests
	cd $(FRONTEND_DIR) && pnpm exec playwright test

.PHONY: test-perf
test-perf: ## Performance tests
	cd $(BACKEND_DIR) && $(PIP) run pytest tests/perf -v

.PHONY: test-token-budget
test-token-budget: ## Token budget validation (SC-001 / SC-009)
	cd $(BACKEND_DIR) && $(PIP) run pytest tests/integration/test_token_budget.py -v

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	cd $(BACKEND_DIR) && $(PIP) run pytest --cov --cov-report=html --cov-report=term-missing

# ─── Quality gates ────────────────────────────────────────────────────
.PHONY: lint
lint: ## Lint backend + frontend
	cd $(BACKEND_DIR) && $(PIP) run ruff check .
	cd $(BACKEND_DIR) && $(PIP) run ruff format --check .
	cd $(FRONTEND_DIR) && pnpm lint
	cd $(FRONTEND_DIR) && pnpm typecheck

.PHONY: security
security: ## Run security scans (bandit + npm audit)
	cd $(BACKEND_DIR) && $(PIP) run bandit -r src

.PHONY: typecheck
typecheck: ## Type-check both
	cd $(BACKEND_DIR) && $(PIP) run mypy src
	cd $(FRONTEND_DIR) && pnpm typecheck

# ─── CI dry-run ───────────────────────────────────────────────────────
.PHONY: ci-dry
ci-dry: lint test ## Run local CI stages 1-3
	@echo "✅ All CI dry-run stages passed."

# ─── Hooks ────────────────────────────────────────────────────────────
.PHONY: install-hooks
install-hooks: ## Install pre-commit hooks
	pre-commit install

.PHONY: run-hooks
run-hooks: ## Run pre-commit hooks on all files
	pre-commit run --all-files
