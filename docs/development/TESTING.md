# BenGER Testing Documentation

> **Complete testing guide for BenGER** - Last updated: March 2026

## Quick Start

```bash
# Full test suite (start -> seed -> test all -> stop -> prune)
make test

# Individual suites (requires `make test-start` first)
make test-unit         # API + Workers + Frontend Jest
make test-api          # API tests only
make test-workers      # Worker tests only
make test-frontend     # Frontend Jest only
make test-e2e          # Playwright E2E tests
```

### Targeted Test Runs

All test commands support `FILE` and `GREP` parameters:

```bash
# Run a specific test file
make test-api FILE="tests/routers/projects/test_tasks.py"

# Filter by test name pattern
make test-api GREP="bulk_export"

# Specific E2E spec
make test-e2e FILE="e2e/user-journeys/login.spec.ts"

# E2E tests matching a pattern
make test-e2e GREP="annotation"

# Workers by pattern
make test-workers GREP="evaluation_metrics"

# Frontend Jest by pattern
make test-frontend GREP="ProjectListTable"
```

---

## Test Infrastructure

### Architecture

Dev and test environments run in parallel on separate Docker networks and ports:

| Service | Dev Port | Test Port |
|---------|----------|-----------|
| PostgreSQL | 5432 | 5433 |
| Redis | 6379 | 6380 |
| API | 8000 | 8002 |
| Frontend | 3000 | 8090 |
| Traefik Dashboard | 8080 | 8091 |

**Dev network:** `benger-network` (project name: `benger`)
**Test network:** `benger-test-network` (project name: `benger-test`)

### Infrastructure Commands

```bash
# Start test containers (reuses existing images, safe for dev)
make test-start

# Rebuild changed images with Docker cache, then start
make test-build

# Full rebuild from scratch (no cache) - use when Dockerfile changes
make test-rebuild

# Stop and remove test containers
make test-stop

# Check health of test services
make test-status

# View test container logs
make test-logs

# Re-seed the test database
make test-seed

# Restart test workers after code changes
make test-restart-workers

# Clean up Docker resources after tests (safe for dev data)
make test-prune

# Stop + clean artifacts
make test-clean
```

### Hot-Reload Behavior

| Service | Dev | Test | How to apply changes in test |
|---------|-----|------|------------------------------|
| **API** | Auto (uvicorn `--reload`) | Auto (uvicorn `--reload`) | Automatic on file save |
| **Workers** | Manual restart | Manual restart | `make test-restart-workers` |
| **Frontend** | Auto (watchpack) | Baked into image | `make test-build` (needs rebuild) |

**Why `test-start` doesn't rebuild:** Building test images (especially workers with ML models at ~4.3GB) causes memory spikes that can kill the dev environment. `test-start` reuses existing images. Use `test-build` when you need to pick up code changes that require a rebuild.

### Test Database

- **User:** postgres
- **Password:** postgres_test
- **Database:** test_benger
- **Host:** localhost:5433

Test data is ephemeral — `make test-stop` removes all volumes.

---

## Test Organization

Tests live within each service directory:

### API Tests (`services/api/tests/`)

```
services/api/tests/
├── unit/                    # Fast, isolated unit tests
├── integration/             # Database/Redis integration tests
├── routers/                 # Router-specific tests
│   └── projects/            # Project router tests
├── security/                # OWASP security tests
├── health/                  # Health check tests
└── conftest.py              # Shared pytest fixtures
```

**Test count:** ~1,495 tests

### Frontend Tests (`services/frontend/`)

```
services/frontend/
├── src/__tests__/           # Jest unit tests (381 test suites)
└── e2e/                     # Playwright E2E tests (~178 specs)
    ├── user-journeys/       # Complete user journey tests
    ├── user-workflows/      # Workflow-specific tests
    ├── annotation-types/    # Annotation type tests
    ├── settings/            # Project settings tests
    ├── resilience/          # Network failure recovery
    ├── mobile/              # Mobile device tests
    ├── helpers/             # Test utilities
    ├── factories/           # Test data generation
    └── pages/               # Page Object Models
```

### Workers Tests (`services/workers/tests/`)

```
services/workers/tests/
├── test_evaluation_metrics_accuracy.py
├── test_llm_generation_pipeline.py
├── test_celery_reliability.py
├── test_resource_management.py
└── ... (~558 tests)
```

---

## Testing Strategy

### Test Pyramid

```
        /\
       /  \      E2E Tests (Playwright, ~178 specs)
      /----\     - Complete user workflows
     /      \    - Multi-user scenarios
    /--------\
   /          \  Integration Tests (API + Workers)
  /------------\ - Database/Redis/Celery
 /              \
/________________\ Unit Tests (Jest + pytest)
                   - Fast, isolated
                   - ~2,400+ tests
```

### Pytest Markers (API/Workers)

```python
@pytest.mark.unit           # Fast unit tests
@pytest.mark.integration    # Service integration tests
@pytest.mark.security       # Security/OWASP tests
@pytest.mark.slow           # Long-running tests (>5s)
```

---

## Security Testing

BenGER includes comprehensive security testing covering OWASP Top 10:

**`services/api/tests/security/`**:
- `test_security_comprehensive.py` — SQL injection, XSS, CSRF, access control, rate limiting
- `test_security_owasp.py` — A01-A10 coverage
- `test_security_enhancements.py` — Advanced injection, JWT confusion, timing attacks

```bash
# Run security tests
make test-api GREP="security"
```

---

## E2E Testing

### Test Categories

| Category | Location | Description |
|----------|----------|-------------|
| User Journeys | `e2e/user-journeys/` | Complete workflows (login, project lifecycle, annotation) |
| User Workflows | `e2e/user-workflows/` | Specific features (bulk export, import, label config) |
| Annotation Types | `e2e/annotation-types/` | Comparison, span, QA annotation workflows |
| Settings | `e2e/settings/` | Project settings behavior, randomize task order |
| Resilience | `e2e/resilience/` | Network failures, error recovery |
| Mobile | `e2e/mobile/` | Touch gestures, responsive layout |

### Running E2E Tests

```bash
# All E2E tests
make test-e2e

# Specific spec file
make test-e2e FILE="e2e/user-journeys/qa-project-full-workflow.spec.ts"

# Filter by test name
make test-e2e GREP="annotation"
```

### E2E Test Infrastructure

- **Frontend:** http://benger-test.localhost:8090
- **API:** http://localhost:8002
- **Default users:** admin/admin, contributor/admin, annotator/admin

### E2E Debugging Tips

- `isVisible()` does NOT auto-retry — use `waitFor({ state: 'visible' })` or `expect().toBeVisible()`
- HeadlessUI Dialog portals may not be found by `page.locator()` — use `page.evaluate()` as workaround
- Docker test env is slow — use generous timeouts (30s+) for initial element detection
- `waitForLoadState('domcontentloaded')` does NOT wait for React hydration — use `waitForURL()` or `waitFor()`

---

## CI/CD Testing

### GitHub Actions

**File:** `.github/workflows/cicd.yml`

Runs on PRs to master and direct pushes. Uses the same Docker-based test infrastructure.

**Always run `make test` locally before pushing** to avoid wasting CI minutes.

### CI Test Stages

1. **Frontend tests** — Jest with coverage (15 min timeout)
2. **Database migrations** — Alembic on clean DB (5 min timeout)
3. **API tests** — pytest with coverage (10 min timeout)
4. **Workers tests** — pytest with memory backend

---

## Troubleshooting

### Test Infrastructure Not Starting

```bash
# Check health
make test-status

# View logs
make test-logs

# Clean restart
make test-stop && make test-start
```

### Database Connection Errors

```bash
# Check test DB is running
docker ps | grep benger-test-test-db

# Connect manually
PGPASSWORD=postgres_test psql -h localhost -p 5433 -U postgres -d test_benger
```

### Redis Connection Errors

```bash
redis-cli -p 6380 ping
```

### Tests Pass Locally but Fail in CI

- CI uses fresh images — try `make test-rebuild` locally
- CI has different resource limits — check for timing-sensitive tests

### Dev Environment Crashes During Tests

This was caused by `--build` in `test-start` triggering memory-heavy image rebuilds. Fixed: `test-start` no longer rebuilds. Use `test-build` explicitly when needed.

---

## Testing Policy

### Jest-Only for Frontend

This project uses **Jest exclusively** — no Vitest.

```javascript
// Correct (Jest)
import { jest, describe, it, expect } from '@jest/globals'
jest.mock('@/lib/api')

// Wrong (Vitest) — will be caught by linting
import { vi } from 'vitest'
```

### Test Quality Standards

- Unit tests: <1s
- Integration tests: <10s
- E2E tests: 30s timeout (local), 60s (CI)
- Flaky tests: fix immediately
- Test data: use factories, not hardcoded values

---

## Quick Reference

```bash
# Full suite
make test

# Individual suites
make test-api          make test-workers
make test-frontend     make test-e2e
make test-unit         make test-all

# Targeted
make test-api GREP="pattern" FILE="path"

# Infrastructure
make test-start        make test-stop
make test-build        make test-rebuild
make test-status       make test-logs
make test-seed         make test-restart-workers
make test-clean        make test-prune

# Reports
make test-report       # E2E HTML report
make test-quiet        # Minimal output (for agents/CI)
```

---

**Last Updated:** March 2026
