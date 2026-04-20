# BenGER Project Makefile
# Central control for all development, deployment, and maintenance tasks
# Run 'make help' to see all available commands

.PHONY: help
help: ## Show this help message
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║                    BenGER Project Commands                     ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  make setup          - Complete initial setup"
	@echo "  make dev            - Start all services in development mode"
	@echo "  make stop           - Stop all running services"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ==================== VARIABLES ====================
# Auto-detect docker compose command (v2 plugin "docker compose" vs v1 standalone "docker-compose")
DOCKER_COMPOSE_CMD := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
DOCKER_COMPOSE := $(DOCKER_COMPOSE_CMD) -f infra/docker-compose.yml
DOCKER_COMPOSE_DEV := $(DOCKER_COMPOSE_CMD) -f infra/docker-compose.yml -f infra/docker-compose.dev.yml
DOCKER_COMPOSE_EXTENDED := $(DOCKER_COMPOSE_CMD) -f infra/docker-compose.yml -f infra/docker-compose.dev.yml -f infra/docker-compose.extended.yml
DOCKER_COMPOSE_TEST := $(DOCKER_COMPOSE_CMD) -f $(CURDIR)/infra/docker-compose.test.yml
API_DIR := services/api
FRONTEND_DIR := services/frontend
WORKERS_DIR := services/workers
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# ==================== SETUP & INSTALLATION ====================

.PHONY: setup
setup: ## Complete initial project setup
	@echo "$(BLUE)🚀 Setting up BenGER project...$(NC)"
	@make install-deps
	@make setup-env
	@make setup-db
	@make install-hooks
	@echo "$(GREEN)✅ Setup complete! Run 'make dev' to start development.$(NC)"

.PHONY: install-deps
install-deps: ## Install all dependencies
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	@echo "Installing API dependencies..."
	@cd $(API_DIR) && uv pip install -r requirements.txt -r requirements-test.txt
	@echo "Installing Frontend dependencies..."
	@cd $(FRONTEND_DIR) && npm install
	@echo "Installing Workers dependencies..."
	@cd $(WORKERS_DIR) && uv pip install -r requirements.txt
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

.PHONY: setup-env
setup-env: ## Setup environment files
	@echo "$(BLUE)🔧 Setting up environment files...$(NC)"
	@if [ ! -f .env ]; then \
		cp .env.template .env; \
		echo "$(YELLOW)⚠️  Created .env from .env.template - please update with your values$(NC)"; \
	else \
		echo "$(GREEN)✓ .env file already exists$(NC)"; \
	fi
	@if [ ! -f infra/.env ]; then \
		ln -s ../.env infra/.env; \
		echo "$(GREEN)✓ Linked .env to infra/$(NC)"; \
	fi

.PHONY: setup-db
setup-db: ## Initialize database with migrations
	@echo "$(BLUE)🗄️  Setting up database...$(NC)"
	@cd $(API_DIR) && python init_db.py
	@cd $(API_DIR) && alembic upgrade head
	@echo "$(GREEN)✅ Database initialized$(NC)"

.PHONY: install-hooks
install-hooks: ## Install git hooks
	@echo "$(BLUE)🪝 Installing git hooks...$(NC)"
	@pre-commit install
	@pre-commit install --hook-type pre-push
	@echo "$(GREEN)✅ Git hooks installed$(NC)"

# ==================== DEVELOPMENT ====================

.PHONY: dev
dev: ## Start all services in development mode with hot reload
	@echo "$(BLUE)Starting development environment (community edition)...$(NC)"
	@$(DOCKER_COMPOSE_DEV) up -d
	@echo "$(GREEN)Development environment running$(NC)"
	@echo ""
	@echo "  Frontend: http://benger.localhost (hot reload enabled)"
	@echo "  API: http://api.localhost"
	@echo "  API Docs: http://api.localhost/docs"
	@echo "  Traefik Dashboard: http://traefik.localhost:8080"
	@echo ""
	@echo "Run 'make logs' to see logs or 'make stop' to stop services"

.PHONY: dev-extended
dev-extended: ## Start with extended features (requires ../benger-extended)
	@if [ ! -d "../benger-extended/benger_extended" ]; then \
		echo "$(RED)Error: benger-extended not found at ../benger-extended$(NC)"; \
		echo "Clone it: git clone git@github.com:SebastianNagl/benger-extended.git ../benger-extended"; \
		exit 1; \
	fi
	@echo "$(BLUE)Starting development environment (extended edition)...$(NC)"
	@$(DOCKER_COMPOSE_EXTENDED) up -d
	@echo "$(GREEN)Extended development environment running$(NC)"
	@echo ""
	@echo "  Frontend: http://benger.localhost (extended features enabled)"
	@echo "  API: http://api.localhost (extended routers loaded)"
	@echo ""
	@echo "Run 'make logs' to see logs or 'make stop' to stop services"

.PHONY: dev-api
dev-api: ## Start API in development mode (standalone)
	@echo "$(BLUE)🌐 Starting API server...$(NC)"
	@cd $(API_DIR) && uvicorn main:app --reload --port 8000

.PHONY: dev-frontend
dev-frontend: ## Start frontend in development mode (standalone)
	@echo "$(BLUE)🎨 Starting frontend...$(NC)"
	@cd $(FRONTEND_DIR) && npm run dev

.PHONY: dev-workers
dev-workers: ## Start workers in development mode
	@echo "$(BLUE)⚙️  Starting workers...$(NC)"
	@cd $(WORKERS_DIR) && celery -A tasks worker --loglevel=info

.PHONY: dev-mail
dev-mail: ## Start development with MailHog email testing
	@echo "$(BLUE)📧 Starting MailHog email catcher...$(NC)"
	@$(DOCKER_COMPOSE) -f infra/docker-compose.mailhog.yml up -d mailhog
	@echo "$(GREEN)✅ MailHog running$(NC)"
	@echo "  📧 Web UI: http://localhost:8025"
	@echo "  📮 SMTP: localhost:1025"

.PHONY: prod-mail
prod-mail: ## Start production mail server (Stalwart)
	@echo "$(BLUE)📬 Starting Stalwart mail server...$(NC)"
	@$(DOCKER_COMPOSE) -f infra/docker-compose.mail.yml up -d mail
	@echo "$(GREEN)✅ Stalwart mail server running$(NC)"
	@echo "  📧 Admin: http://localhost:8081"
	@echo "  📮 SMTP: localhost:2525"

.PHONY: stop
stop: ## Stop all running services
	@echo "$(BLUE)🛑 Stopping services...$(NC)"
	@$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✅ Services stopped$(NC)"

.PHONY: restart
restart: stop dev ## Restart all services

.PHONY: clean-docker
clean-docker: ## Clean Docker resources
	@echo "$(BLUE)🧹 Cleaning Docker resources...$(NC)"
	@$(DOCKER_COMPOSE) down -v --remove-orphans
	@docker system prune -f
	@echo "$(GREEN)✅ Docker cleaned$(NC)"

# ==================== DATABASE ====================

.PHONY: db-migrate
db-migrate: ## Run database migrations
	@echo "$(BLUE)🔄 Running migrations...$(NC)"
	@cd $(API_DIR) && alembic upgrade head
	@echo "$(GREEN)✅ Migrations complete$(NC)"

.PHONY: db-rollback
db-rollback: ## Rollback last migration
	@echo "$(YELLOW)⏪ Rolling back migration...$(NC)"
	@cd $(API_DIR) && alembic downgrade -1
	@echo "$(GREEN)✅ Rollback complete$(NC)"

.PHONY: db-reset
db-reset: ## Reset database (WARNING: destroys all data)
	@echo "$(RED)⚠️  WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@$(DOCKER_COMPOSE) down -v
	@$(DOCKER_COMPOSE) up -d db redis
	@sleep 5
	@cd $(API_DIR) && python init_db.py
	@cd $(API_DIR) && alembic upgrade head
	@echo "$(GREEN)✅ Database reset complete$(NC)"

.PHONY: db-backup
db-backup: ## Backup database
	@echo "$(BLUE)💾 Creating database backup...$(NC)"
	@mkdir -p backups
	@docker exec $$(docker ps -qf "name=db") pg_dump -U postgres benger > backups/benger_$(TIMESTAMP).sql
	@echo "$(GREEN)✅ Backup saved to backups/benger_$(TIMESTAMP).sql$(NC)"

.PHONY: db-restore
db-restore: ## Restore database from backup (requires BACKUP_FILE=path/to/backup.sql)
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "$(RED)Error: BACKUP_FILE not specified$(NC)"; \
		echo "Usage: make db-restore BACKUP_FILE=backups/benger_20240101_120000.sql"; \
		exit 1; \
	fi
	@echo "$(BLUE)📥 Restoring database from $(BACKUP_FILE)...$(NC)"
	@docker exec -i $$(docker ps -qf "name=db") psql -U postgres benger < $(BACKUP_FILE)
	@echo "$(GREEN)✅ Database restored$(NC)"

# ==================== TESTING ====================
# Unified test infrastructure - single environment for all tests
#
# Quick Start:
#   make test           - Full cycle (start -> seed -> test all -> stop)
#   make test-start     - Start test infrastructure (reuses existing images)
#   make test-build     - Rebuild changed images then start (uses Docker cache)
#   make test-rebuild   - Full rebuild from scratch (no cache)
#   make test-stop      - Stop and cleanup
#
# Individual Test Suites:
#   make test-unit      - API + Workers + Frontend Jest
#   make test-e2e       - Playwright E2E tests (all)
#   make test-e2e-gate  - Fast E2E (excludes @extended full-workflow tests)
#   make test-e2e-extended - Extended E2E only (@extended full-workflow tests)
#   make test-all       - All tests excluding @extended (requires infra running)
#   make test-extended  - Full suite including @extended (nightly/manual)
#
# Ports (isolated from dev):
#   PostgreSQL: 5433, Redis: 6380, API: 8002, Frontend: 8090
#
# NOTE: test-start does NOT rebuild images to avoid memory spikes that
# can kill the dev environment. Use test-build after code changes.

.PHONY: test
test: ## Run full test suite (clean -> build -> seed -> test all -> stop -> prune) - for CI/CD
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║            BenGER Complete Test Suite                         ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "$(BLUE)🧹 Cleaning pre-existing test environment...$(NC)"
	@$(DOCKER_COMPOSE_TEST) down -v 2>/dev/null || true
	@echo ""
	@echo "$(BLUE)🔨 Building and starting fresh test environment...$(NC)"
	@$(DOCKER_COMPOSE_TEST) up -d --build 2>&1 | grep -v "orphan\|Running\|Creating\|Starting\|Started\|Created\|Pulling\|Network\|Volume\|Container\|Building" || true
	@echo "$(YELLOW)⏳ Waiting for services to be healthy...$(NC)"
	@timeout=300; while [ $$timeout -gt 0 ]; do \
		healthy=$$(docker ps --filter "name=benger-test" --filter "health=healthy" --format "{{.Names}}" 2>/dev/null | wc -l); \
		if [ "$$healthy" -ge 7 ]; then \
			echo "$(GREEN)  All 7 services healthy!$(NC)"; \
			break; \
		fi; \
		echo "  Waiting... ($$healthy/7 healthy, $${timeout}s remaining)"; \
		sleep 5; \
		timeout=$$((timeout - 5)); \
	done
	@echo "$(YELLOW)⏳ Verifying API responds...$(NC)"
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -sf http://localhost:8002/health > /dev/null 2>&1; then \
			echo "$(GREEN)  API responding!$(NC)"; \
			break; \
		fi; \
		sleep 3; \
	done
	@echo "$(BLUE)🔧 Initializing database...$(NC)"
	@docker exec benger-test-test-api-1 python init_complete.py > /tmp/test-init.log 2>&1; \
	if [ $$? -ne 0 ]; then \
		echo "$(RED)  Database initialization FAILED:$(NC)"; \
		tail -5 /tmp/test-init.log; \
	else \
		grep -E "✅|Created|🎯" /tmp/test-init.log || true; \
	fi
	@echo ""
	@$(MAKE) test-all; EXIT_CODE=$$?; \
	echo ""; \
	$(MAKE) test-stop; \
	$(MAKE) test-prune; \
	exit $$EXIT_CODE

.PHONY: test-start
test-start: ## Start test infrastructure (all services)
	@echo "$(BLUE)🚀 Starting test infrastructure...$(NC)"
	@$(DOCKER_COMPOSE_TEST) up -d 2>&1 | grep -v "orphan\|Running\|Creating\|Starting\|Started\|Created\|Pulling\|Network\|Volume\|Container\|Building" || true
	@echo "$(YELLOW)⏳ Waiting for services to be healthy...$(NC)"
	@timeout=300; while [ $$timeout -gt 0 ]; do \
		healthy=$$(docker ps --filter "name=benger-test" --filter "health=healthy" --format "{{.Names}}" 2>/dev/null | wc -l); \
		if [ "$$healthy" -ge 7 ]; then \
			echo "$(GREEN)  All 7 services healthy!$(NC)"; \
			break; \
		fi; \
		echo "  Waiting... ($$healthy/7 healthy, $${timeout}s remaining)"; \
		sleep 5; \
		timeout=$$((timeout - 5)); \
	done
	@echo "$(YELLOW)⏳ Verifying API responds...$(NC)"
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -sf http://localhost:8002/health > /dev/null 2>&1; then \
			echo "$(GREEN)  API responding!$(NC)"; \
			break; \
		fi; \
		sleep 3; \
	done
	@echo "$(BLUE)🔧 Initializing database...$(NC)"
	@docker exec benger-test-test-api-1 python init_complete.py > /tmp/test-init.log 2>&1; \
	if [ $$? -ne 0 ]; then \
		echo "$(RED)  Database initialization FAILED:$(NC)"; \
		tail -5 /tmp/test-init.log; \
	else \
		grep -E "✅|Created|🎯" /tmp/test-init.log || true; \
	fi
	@echo "$(YELLOW)⏳ Verifying frontend→API proxy chain...$(NC)"
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12; do \
		if curl -sf -X POST http://benger-test.localhost:8090/api/auth/login \
			-H "Content-Type: application/json" \
			-d '{"username":"admin","password":"admin"}' > /dev/null 2>&1; then \
			echo "$(GREEN)  Frontend→API proxy OK!$(NC)"; \
			break; \
		fi; \
		echo "  Proxy not ready yet... ($$i/12)"; \
		sleep 5; \
	done
	@echo ""
	@echo "$(GREEN)✅ Test infrastructure ready!$(NC)"
	@echo ""
	@echo "  📍 Frontend: http://benger-test.localhost:8090"
	@echo "  📍 API: http://localhost:8002"
	@echo "  📍 PostgreSQL: localhost:5433"
	@echo "  📍 Redis: localhost:6380"
	@echo ""

.PHONY: test-build
test-build: ## Rebuild changed test images (uses cache) then start
	@echo "$(BLUE)🔄 Rebuilding changed test images...$(NC)"
	@$(DOCKER_COMPOSE_TEST) up -d --build 2>&1 | grep -v "orphan\|Running\|Creating\|Starting\|Started\|Created\|Pulling\|Network\|Volume\|Container\|Building" || true
	@echo "$(GREEN)✅ Rebuilt and started$(NC)"

.PHONY: test-rebuild
test-rebuild: ## Force rebuild all test images (no cache) then start
	@echo "$(BLUE)🔄 Rebuilding test infrastructure (no cache)...$(NC)"
	@$(DOCKER_COMPOSE_TEST) build --no-cache 2>&1 | grep -v "Pulling\|Waiting\|Extracting\|Downloading" || true
	@$(MAKE) test-start

.PHONY: test-restart-workers
test-restart-workers: ## Restart test workers to pick up code changes (Celery has no hot-reload)
	@$(DOCKER_COMPOSE_TEST) restart test-worker test-scheduler
	@echo "$(GREEN)✅ Test workers restarted$(NC)"

.PHONY: test-stop
test-stop: ## Stop test infrastructure
	@echo "$(BLUE)🛑 Stopping test infrastructure...$(NC)"
	@$(DOCKER_COMPOSE_TEST) down -v 2>/dev/null || true
	@echo "$(GREEN)✅ Test infrastructure stopped$(NC)"

.PHONY: test-prune
test-prune: ## Clean up Docker resources after tests (safe for dev data)
	@echo "$(BLUE)🧹 Pruning test Docker resources...$(NC)"
	@# Remove dangling images (untagged images from old builds)
	@docker image prune -f 2>/dev/null || true
	@# Remove build cache
	@docker builder prune -f 2>/dev/null || true
	@# Remove only test-related volumes (NOT dev volumes like benger-postgres-data)
	@docker volume ls -q --filter "name=benger-test" 2>/dev/null | xargs -r docker volume rm 2>/dev/null || true
	@echo "$(GREEN)✅ Docker resources pruned (dev data preserved)$(NC)"

.PHONY: test-status
test-status: ## Check test infrastructure health
	@echo "$(BLUE)🔍 Checking test infrastructure status...$(NC)"
	@echo ""
	@if docker ps | grep -q "benger-test-test-api-1"; then \
		echo "$(GREEN)✅ Test infrastructure is running$(NC)"; \
		echo ""; \
		docker ps --filter "name=test-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"; \
	else \
		echo "$(YELLOW)⚠️  Test infrastructure is not running$(NC)"; \
		echo "$(YELLOW)💡 Run 'make test-start' to start it$(NC)"; \
	fi
	@echo ""

.PHONY: test-seed
test-seed: ## Re-seed test database
	@echo "$(BLUE)🌱 Re-seeding test database...$(NC)"
	@docker exec benger-test-test-api-1 python init_complete.py
	@echo "$(GREEN)✅ Database re-seeded$(NC)"

.PHONY: test-all
test-all: ## Run all tests (requires test-start first)
	@echo "$(BLUE)🧪 Running all tests...$(NC)"
	@echo ""
	@API_RESULT=0; WORKER_RESULT=0; FRONTEND_RESULT=0; E2E_RESULT=0; \
	\
	echo "$(BLUE)1️⃣  API Tests$(NC)"; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-api-runner && API_RESULT=0 || API_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)2️⃣  Worker Tests$(NC)"; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-workers-runner && WORKER_RESULT=0 || WORKER_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)3️⃣  Frontend Unit Tests (Jest)$(NC)"; \
	cd $(CURDIR)/services/frontend && npm test && FRONTEND_RESULT=0 || FRONTEND_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)4️⃣  E2E Tests (Playwright, excluding @extended)$(NC)"; \
	cd $(CURDIR)/services/frontend && \
	E2E_ISOLATED=true \
	PLAYWRIGHT_BASE_URL=http://benger-test.localhost:8090 \
	npx playwright test --grep-invert "@extended" --reporter=line && E2E_RESULT=0 || E2E_RESULT=1; \
	echo ""; \
	\
	echo "╔════════════════════════════════════════════════════════════════╗"; \
	echo "║                    TEST RESULTS SUMMARY                        ║"; \
	echo "╚════════════════════════════════════════════════════════════════╝"; \
	echo ""; \
	if [ $$API_RESULT -eq 0 ]; then echo "  $(GREEN)✅ API Tests:      PASSED$(NC)"; else echo "  $(RED)❌ API Tests:      FAILED$(NC)"; fi; \
	if [ $$WORKER_RESULT -eq 0 ]; then echo "  $(GREEN)✅ Worker Tests:   PASSED$(NC)"; else echo "  $(RED)❌ Worker Tests:   FAILED$(NC)"; fi; \
	if [ $$FRONTEND_RESULT -eq 0 ]; then echo "  $(GREEN)✅ Frontend Tests: PASSED$(NC)"; else echo "  $(RED)❌ Frontend Tests: FAILED$(NC)"; fi; \
	if [ $$E2E_RESULT -eq 0 ]; then echo "  $(GREEN)✅ E2E Tests:      PASSED$(NC)"; else echo "  $(RED)❌ E2E Tests:      FAILED$(NC)"; fi; \
	echo ""; \
	\
	TOTAL=$$((API_RESULT + WORKER_RESULT + FRONTEND_RESULT + E2E_RESULT)); \
	if [ $$TOTAL -eq 0 ]; then \
		echo "$(GREEN)🎉 All tests passed!$(NC)"; \
		exit 0; \
	else \
		echo "$(RED)⚠️  $$TOTAL test suite(s) failed$(NC)"; \
		echo "$(YELLOW)💡 Run 'make test-report' to view E2E test details$(NC)"; \
		exit 1; \
	fi

.PHONY: test-extended
test-extended: ## Run full test suite including @extended E2E tests (nightly/manual)
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║            BenGER Extended Test Suite                         ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "$(BLUE)🧹 Cleaning pre-existing test environment...$(NC)"
	@$(DOCKER_COMPOSE_TEST) down -v 2>/dev/null || true
	@echo ""
	@echo "$(BLUE)🔨 Building and starting fresh test environment...$(NC)"
	@$(DOCKER_COMPOSE_TEST) up -d --build 2>&1 | grep -v "orphan\|Running\|Creating\|Starting\|Started\|Created\|Pulling\|Network\|Volume\|Container\|Building" || true
	@echo "$(YELLOW)⏳ Waiting for services to be healthy...$(NC)"
	@timeout=300; while [ $$timeout -gt 0 ]; do \
		healthy=$$(docker ps --filter "name=benger-test" --filter "health=healthy" --format "{{.Names}}" 2>/dev/null | wc -l); \
		if [ "$$healthy" -ge 7 ]; then \
			echo "$(GREEN)  All 7 services healthy!$(NC)"; \
			break; \
		fi; \
		echo "  Waiting... ($$healthy/7 healthy, $${timeout}s remaining)"; \
		sleep 5; \
		timeout=$$((timeout - 5)); \
	done
	@echo "$(YELLOW)⏳ Verifying API responds...$(NC)"
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -sf http://localhost:8002/health > /dev/null 2>&1; then \
			echo "$(GREEN)  API responding!$(NC)"; \
			break; \
		fi; \
		sleep 3; \
	done
	@echo "$(BLUE)🔧 Initializing database...$(NC)"
	@docker exec benger-test-test-api-1 python init_complete.py > /tmp/test-init.log 2>&1; \
	if [ $$? -ne 0 ]; then \
		echo "$(RED)  Database initialization FAILED:$(NC)"; \
		tail -5 /tmp/test-init.log; \
	else \
		grep -E "✅|Created|🎯" /tmp/test-init.log || true; \
	fi
	@echo ""
	@$(MAKE) test-all-extended; EXIT_CODE=$$?; \
	echo ""; \
	$(MAKE) test-stop; \
	$(MAKE) test-prune; \
	exit $$EXIT_CODE

.PHONY: test-all-extended
test-all-extended: ## Run all tests including @extended E2E (requires test-start first)
	@echo "$(BLUE)🧪 Running all tests (including @extended)...$(NC)"
	@echo ""
	@API_RESULT=0; WORKER_RESULT=0; FRONTEND_RESULT=0; E2E_RESULT=0; \
	\
	echo "$(BLUE)1️⃣  API Tests$(NC)"; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-api-runner && API_RESULT=0 || API_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)2️⃣  Worker Tests$(NC)"; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-workers-runner && WORKER_RESULT=0 || WORKER_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)3️⃣  Frontend Unit Tests (Jest)$(NC)"; \
	cd $(CURDIR)/services/frontend && npm test && FRONTEND_RESULT=0 || FRONTEND_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)4️⃣  E2E Tests (Playwright, ALL including @extended)$(NC)"; \
	cd $(CURDIR)/services/frontend && \
	E2E_ISOLATED=true \
	PLAYWRIGHT_BASE_URL=http://benger-test.localhost:8090 \
	npx playwright test --reporter=line,html && E2E_RESULT=0 || E2E_RESULT=1; \
	echo ""; \
	\
	echo "╔════════════════════════════════════════════════════════════════╗"; \
	echo "║                    TEST RESULTS SUMMARY                        ║"; \
	echo "╚════════════════════════════════════════════════════════════════╝"; \
	echo ""; \
	if [ $$API_RESULT -eq 0 ]; then echo "  $(GREEN)✅ API Tests:      PASSED$(NC)"; else echo "  $(RED)❌ API Tests:      FAILED$(NC)"; fi; \
	if [ $$WORKER_RESULT -eq 0 ]; then echo "  $(GREEN)✅ Worker Tests:   PASSED$(NC)"; else echo "  $(RED)❌ Worker Tests:   FAILED$(NC)"; fi; \
	if [ $$FRONTEND_RESULT -eq 0 ]; then echo "  $(GREEN)✅ Frontend Tests: PASSED$(NC)"; else echo "  $(RED)❌ Frontend Tests: FAILED$(NC)"; fi; \
	if [ $$E2E_RESULT -eq 0 ]; then echo "  $(GREEN)✅ E2E Tests:      PASSED$(NC)"; else echo "  $(RED)❌ E2E Tests:      FAILED$(NC)"; fi; \
	echo ""; \
	\
	TOTAL=$$((API_RESULT + WORKER_RESULT + FRONTEND_RESULT + E2E_RESULT)); \
	if [ $$TOTAL -eq 0 ]; then \
		echo "$(GREEN)🎉 All tests passed!$(NC)"; \
		exit 0; \
	else \
		echo "$(RED)⚠️  $$TOTAL test suite(s) failed$(NC)"; \
		echo "$(YELLOW)💡 Run 'make test-report' to view E2E test details$(NC)"; \
		exit 1; \
	fi

.PHONY: test-unit
test-unit: ## Run unit tests only (API + Workers + Frontend Jest)
	@echo "$(BLUE)🧪 Running unit tests...$(NC)"
	@API_RESULT=0; WORKER_RESULT=0; FRONTEND_RESULT=0; \
	\
	echo "$(BLUE)1️⃣  API Tests$(NC)"; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-api-runner && API_RESULT=0 || API_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)2️⃣  Worker Tests$(NC)"; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-workers-runner && WORKER_RESULT=0 || WORKER_RESULT=1; \
	echo ""; \
	\
	echo "$(BLUE)3️⃣  Frontend Unit Tests (Jest)$(NC)"; \
	cd $(CURDIR)/services/frontend && npm test && FRONTEND_RESULT=0 || FRONTEND_RESULT=1; \
	echo ""; \
	\
	TOTAL=$$((API_RESULT + WORKER_RESULT + FRONTEND_RESULT)); \
	if [ $$TOTAL -eq 0 ]; then echo "$(GREEN)✅ All unit tests passed$(NC)"; exit 0; \
	else echo "$(RED)❌ $$TOTAL suite(s) failed$(NC)"; exit 1; fi

.PHONY: test-e2e
test-e2e: ## Run E2E Playwright tests only (use GREP="pattern" to filter, FILE="path" to target file)
	@echo "$(BLUE)🎭 Running E2E tests...$(NC)"
	@cd $(FRONTEND_DIR) && npx playwright install chromium --with-deps 2>/dev/null || npx playwright install chromium
	@cd $(FRONTEND_DIR) && \
	E2E_ISOLATED=true \
	PLAYWRIGHT_BASE_URL=http://benger-test.localhost:8090 \
	npx playwright test $(if $(FILE),$(FILE),) $(if $(GREP),--grep "$(GREP)",) --reporter=line

.PHONY: test-e2e-gate
test-e2e-gate: ## Run fast E2E tests only (excludes @extended full-workflow tests)
	@echo "$(BLUE)🎭 Running gate E2E tests (excluding @extended)...$(NC)"
	@cd $(FRONTEND_DIR) && npx playwright install chromium --with-deps 2>/dev/null || npx playwright install chromium
	@cd $(FRONTEND_DIR) && \
	E2E_ISOLATED=true \
	PLAYWRIGHT_BASE_URL=http://benger-test.localhost:8090 \
	npx playwright test --grep-invert "@extended" --reporter=line

.PHONY: test-e2e-extended
test-e2e-extended: ## Run extended E2E tests only (@extended full-workflow tests)
	@echo "$(BLUE)🎭 Running extended E2E tests (@extended only)...$(NC)"
	@cd $(FRONTEND_DIR) && npx playwright install chromium --with-deps 2>/dev/null || npx playwright install chromium
	@cd $(FRONTEND_DIR) && \
	E2E_ISOLATED=true \
	PLAYWRIGHT_BASE_URL=http://benger-test.localhost:8090 \
	npx playwright test --grep "@extended" --reporter=line

.PHONY: test-api
test-api: ## Run API tests only (use GREP="pattern" to filter, FILE="path" to target file)
	@echo "$(BLUE)🔍 Running API tests...$(NC)"
ifdef GREP
	@$(DOCKER_COMPOSE_TEST) --profile test run --rm test-api-runner \
		"pip install -q -r requirements-test.txt && pytest $(if $(FILE),$(FILE),tests/) -v --tb=short --maxfail=10 --ignore=tests/e2e -k '$(GREP)'"
else ifdef FILE
	@$(DOCKER_COMPOSE_TEST) --profile test run --rm test-api-runner \
		"pip install -q -r requirements-test.txt && pytest $(FILE) -v --tb=short --maxfail=10 --ignore=tests/e2e"
else
	@$(DOCKER_COMPOSE_TEST) --profile test run --rm test-api-runner
endif

.PHONY: test-workers
test-workers: ## Run worker tests only (use GREP="pattern" to filter, FILE="path" to target file)
	@echo "$(BLUE)⚙️  Running worker tests...$(NC)"
ifdef GREP
	@$(DOCKER_COMPOSE_TEST) --profile test run --rm test-workers-runner \
		"pytest $(if $(FILE),$(FILE),tests/) -v --tb=short --maxfail=10 --timeout=120 --cov=. --cov-branch --cov-report=term --cov-fail-under=60 -k '$(GREP)'"
else ifdef FILE
	@$(DOCKER_COMPOSE_TEST) --profile test run --rm test-workers-runner \
		"pytest $(FILE) -v --tb=short --maxfail=10 --timeout=120 --cov=. --cov-branch --cov-report=term --cov-fail-under=60"
else
	@$(DOCKER_COMPOSE_TEST) --profile test run --rm test-workers-runner
endif

.PHONY: test-frontend
test-frontend: ## Run frontend Jest tests only (use GREP="pattern" to filter, FILE="path" to target file)
	@echo "$(BLUE)🎨 Running frontend tests...$(NC)"
	@rm -rf $(FRONTEND_DIR)/.jest-cache
	@cd $(FRONTEND_DIR) && npm test -- \
		$(if $(FILE),--testPathPattern="$(FILE)",) $(if $(GREP),--testNamePattern="$(GREP)",)

.PHONY: test-quiet
test-quiet: ## Run tests with minimal output (for agents/CI)
	@echo "$(BLUE)🤖 Running tests (minimal output)...$(NC)"
	@API_RESULT=0; WORKER_RESULT=0; FRONTEND_RESULT=0; E2E_RESULT=0; \
	\
	echo "Starting infrastructure..."; \
	$(DOCKER_COMPOSE_TEST) up -d 2>/dev/null; \
	sleep 30; \
	docker exec benger-test-test-api-1 python init_complete.py 2>&1 | grep -E "✅|🎯" || true; \
	\
	echo "Running tests..."; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-api-runner 2>&1 | tail -5 && API_RESULT=0 || API_RESULT=1; \
	$(DOCKER_COMPOSE_TEST) --profile test run --rm test-workers-runner 2>&1 | tail -5 && WORKER_RESULT=0 || WORKER_RESULT=1; \
	cd $(CURDIR)/services/frontend && npm test -- --silent 2>&1 | tail -5 && FRONTEND_RESULT=0 || FRONTEND_RESULT=1; \
	cd $(CURDIR)/services/frontend && E2E_ISOLATED=true PLAYWRIGHT_BASE_URL=http://benger-test.localhost:8090 \
	npx playwright test --reporter=dot 2>&1 | tail -10 && E2E_RESULT=0 || E2E_RESULT=1; \
	\
	$(DOCKER_COMPOSE_TEST) down -v 2>/dev/null; \
	docker image prune -f 2>/dev/null || true; \
	docker builder prune -f 2>/dev/null || true; \
	\
	echo ""; \
	echo "=== RESULTS ==="; \
	if [ $$API_RESULT -eq 0 ]; then echo "✅ API"; else echo "❌ API"; fi; \
	if [ $$WORKER_RESULT -eq 0 ]; then echo "✅ Workers"; else echo "❌ Workers"; fi; \
	if [ $$FRONTEND_RESULT -eq 0 ]; then echo "✅ Frontend"; else echo "❌ Frontend"; fi; \
	if [ $$E2E_RESULT -eq 0 ]; then echo "✅ E2E"; else echo "❌ E2E"; fi; \
	TOTAL=$$((API_RESULT + WORKER_RESULT + FRONTEND_RESULT + E2E_RESULT)); \
	if [ $$TOTAL -eq 0 ]; then echo "🎉 All passed"; exit 0; else echo "⚠️  $$TOTAL suite(s) failed"; exit 1; fi

.PHONY: test-report
test-report: ## View E2E test HTML report
	@echo "$(BLUE)📊 Opening test report...$(NC)"
	@cd $(FRONTEND_DIR) && npx playwright show-report

.PHONY: test-logs
test-logs: ## View test infrastructure logs
	@echo "$(BLUE)📋 Test infrastructure logs:$(NC)"
	@$(DOCKER_COMPOSE_TEST) logs --tail=100 -f

.PHONY: test-clean
test-clean: test-stop ## Clean test artifacts and stop infrastructure
	@echo "$(BLUE)🧹 Cleaning test environment...$(NC)"
	@cd $(FRONTEND_DIR) && rm -rf playwright-report/ test-results/ test-output.txt
	@echo "$(GREEN)✅ Test environment cleaned$(NC)"

# ==================== CODE QUALITY ====================

.PHONY: format
format: ## Format all code
	@echo "$(BLUE)🎨 Formatting code...$(NC)"
	@cd $(API_DIR) && black . && isort .
	@cd $(WORKERS_DIR) && black . && isort .
	@cd $(FRONTEND_DIR) && npm run format
	@echo "$(GREEN)✅ Code formatted$(NC)"

.PHONY: lint
lint: ## Lint all code
	@echo "$(BLUE)🔍 Linting code...$(NC)"
	@cd $(API_DIR) && flake8 . --max-line-length=100
	@cd $(FRONTEND_DIR) && npm run lint
	@echo "$(GREEN)✅ Linting complete$(NC)"

.PHONY: type-check
type-check: ## Run type checking
	@echo "$(BLUE)🔍 Type checking...$(NC)"
	@cd $(API_DIR) && mypy . || true
	@cd $(FRONTEND_DIR) && npm run type-check
	@echo "$(GREEN)✅ Type checking complete$(NC)"

.PHONY: security-scan
security-scan: ## Run security scans
	@echo "$(BLUE)🔒 Running security scans...$(NC)"
	@cd $(API_DIR) && bandit -r . -x tests/
	@cd $(FRONTEND_DIR) && npm audit
	@echo "$(GREEN)✅ Security scan complete$(NC)"

# ==================== BUILD & DEPLOY ====================

.PHONY: build
build: ## Build all Docker images
	@echo "$(BLUE)🔨 Building Docker images...$(NC)"
	@$(DOCKER_COMPOSE) build
	@echo "$(GREEN)✅ Build complete$(NC)"

.PHONY: build-prod
build-prod: ## Build production images
	@echo "$(BLUE)🔨 Building production images...$(NC)"
	@docker build -t benger-api:latest $(API_DIR)
	@docker build -t benger-frontend:latest $(FRONTEND_DIR)
	@docker build -t benger-workers:latest $(WORKERS_DIR)
	@echo "$(GREEN)✅ Production build complete$(NC)"

.PHONY: deploy-staging
deploy-staging: ## Deploy to staging environment
	@echo "$(BLUE)🚀 Deploying to staging...$(NC)"
	@./scripts/deployment/deploy-benger.sh staging
	@echo "$(GREEN)✅ Staging deployment complete$(NC)"

.PHONY: deploy-prod
deploy-prod: ## Deploy to production
	@echo "$(RED)🚀 Deploying to PRODUCTION...$(NC)"
	@read -p "Are you sure you want to deploy to production? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@./scripts/deployment/deploy-benger.sh production
	@echo "$(GREEN)✅ Production deployment complete$(NC)"

# ==================== MONITORING & LOGS ====================

.PHONY: logs
logs: ## Show logs from all services
	@$(DOCKER_COMPOSE) logs -f

.PHONY: logs-api
logs-api: ## Show API logs
	@$(DOCKER_COMPOSE) logs -f api

.PHONY: logs-frontend
logs-frontend: ## Show frontend logs
	@$(DOCKER_COMPOSE) logs -f frontend

.PHONY: logs-workers
logs-workers: ## Show worker logs
	@$(DOCKER_COMPOSE) logs -f worker

.PHONY: logs-mail
logs-mail: ## Show mail service logs
	@$(DOCKER_COMPOSE) logs -f mailhog 2>/dev/null || $(DOCKER_COMPOSE) logs -f mail 2>/dev/null || echo "$(YELLOW)⚠️  No mail service running$(NC)"

.PHONY: status
status: ## Show status of all services
	@echo "$(BLUE)📊 Service Status:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(BLUE)🔍 Port Usage:$(NC)"
	@lsof -i :3000,8000,5432,6379 2>/dev/null | grep LISTEN || echo "No services running on standard ports"

.PHONY: health-check
health-check: ## Run health checks
	@echo "$(BLUE)🏥 Running health checks...$(NC)"
	@curl -f http://localhost:8000/health || echo "$(RED)❌ API health check failed$(NC)"
	@curl -f http://localhost:3000 || echo "$(RED)❌ Frontend health check failed$(NC)"
	@echo "$(GREEN)✅ Health check complete$(NC)"

# ==================== MAINTENANCE ====================

.PHONY: clean
clean: ## Clean all generated files and caches
	@echo "$(BLUE)🧹 Cleaning project...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "node_modules/.cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name ".DS_Store" -delete
	@rm -rf htmlcov/ .coverage coverage.xml
	@rm -rf $(FRONTEND_DIR)/.next
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

.PHONY: update-deps
update-deps: ## Update all dependencies
	@echo "$(BLUE)📦 Updating dependencies...$(NC)"
	@cd $(API_DIR) && uv pip list --outdated
	@cd $(FRONTEND_DIR) && npm outdated
	@echo "$(YELLOW)Run 'make upgrade-deps' to actually upgrade$(NC)"

.PHONY: upgrade-deps
upgrade-deps: ## Upgrade all dependencies (use with caution)
	@echo "$(YELLOW)⚠️  Upgrading dependencies...$(NC)"
	@cd $(API_DIR) && uv pip install --upgrade -r requirements.txt
	@cd $(FRONTEND_DIR) && npm update
	@echo "$(GREEN)✅ Dependencies upgraded$(NC)"

.PHONY: validate-env
validate-env: ## Validate environment configuration
	@echo "$(BLUE)🔍 Validating environment...$(NC)"
	@python scripts/core/validate-config.sh
	@echo "$(GREEN)✅ Environment valid$(NC)"

# ==================== UTILITIES ====================

.PHONY: shell-api
shell-api: ## Open shell in API container
	@docker exec -it $$(docker ps -qf "name=api") /bin/bash

.PHONY: shell-db
shell-db: ## Open PostgreSQL shell
	@docker exec -it $$(docker ps -qf "name=db") psql -U postgres benger

.PHONY: shell-redis
shell-redis: ## Open Redis CLI
	@docker exec -it $$(docker ps -qf "name=redis") redis-cli

.PHONY: create-admin
create-admin: ## Create admin user
	@echo "$(BLUE)👤 Creating admin user...$(NC)"
	@cd $(API_DIR) && python -c "from scripts.create_admin import create_admin; create_admin()"

.PHONY: generate-api-docs
generate-api-docs: ## Generate API documentation
	@echo "$(BLUE)📚 Generating API docs...$(NC)"
	@cd $(API_DIR) && python -c "from main import app; import json; print(json.dumps(app.openapi(), indent=2))" > ../../docs/api-docs/openapi.json
	@echo "$(GREEN)✅ API docs generated at docs/api-docs/openapi.json$(NC)"

.PHONY: analyze-bundle
analyze-bundle: ## Analyze frontend bundle size
	@echo "$(BLUE)📊 Analyzing bundle...$(NC)"
	@cd $(FRONTEND_DIR) && npm run analyze

# ==================== GIT WORKFLOWS ====================

.PHONY: pr
pr: format lint ## Prepare for pull request
	@echo "$(BLUE)🔧 Preparing for PR...$(NC)"
	@git status
	@echo "$(GREEN)✅ Ready for PR$(NC)"

.PHONY: release
release: ## Create a new release (requires VERSION=x.y.z)
	@if [ -z "$(VERSION)" ]; then \
		echo "$(RED)Error: VERSION not specified$(NC)"; \
		echo "Usage: make release VERSION=1.2.3"; \
		exit 1; \
	fi
	@echo "$(BLUE)📦 Creating release $(VERSION)...$(NC)"
	@git tag -a v$(VERSION) -m "Release v$(VERSION)"
	@git push origin v$(VERSION)
	@echo "$(GREEN)✅ Release v$(VERSION) created$(NC)"

# ==================== HELP & INFO ====================

.PHONY: info
info: ## Show project information
	@echo "$(BLUE)ℹ️  BenGER Project Information$(NC)"
	@echo ""
	@echo "📁 Project Root: $$(pwd)"
	@echo "🐍 Python Version: $$(python3 --version 2>/dev/null || echo 'Python not found')"
	@echo "📦 Node Version: $$(node --version)"
	@echo "🐳 Docker Version: $$(docker --version)"
	@echo "🔧 Docker Compose Version: $$($(DOCKER_COMPOSE_CMD) version)"
	@echo ""
	@echo "$(GREEN)Run 'make help' to see all available commands$(NC)"

.PHONY: check-deps
check-deps: ## Check if required tools are installed
	@echo "$(BLUE)🔍 Checking dependencies...$(NC)"
	@command -v python3 >/dev/null 2>&1 || { echo "$(RED)❌ Python not installed$(NC)"; exit 1; }
	@command -v node >/dev/null 2>&1 || { echo "$(RED)❌ Node.js not installed$(NC)"; exit 1; }
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)❌ Docker not installed$(NC)"; exit 1; }
	@docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1 || { echo "$(RED)❌ Docker Compose not installed$(NC)"; exit 1; }
	@command -v uv >/dev/null 2>&1 || { echo "$(YELLOW)⚠️  uv not installed (optional but recommended)$(NC)"; }
	@command -v pre-commit >/dev/null 2>&1 || { echo "$(YELLOW)⚠️  pre-commit not installed (optional)$(NC)"; }
	@echo "$(GREEN)✅ All required dependencies installed$(NC)"

# Default target
.DEFAULT_GOAL := help