# BenGER Test Infrastructure

## Overview

BenGER has **655 total test files** across 4 test categories with comprehensive ephemeral testing infrastructure.

## Quick Reference

```bash
# Full test suite (recommended)
make test              # Ephemeral Docker env → all tests → cleanup

# Quick feedback (mocked infrastructure)
make test-quick        # Unit tests only, skips integration tests

# E2E only
make test-e2e          # Full E2E with ephemeral infrastructure
make test-e2e-dev      # E2E with persistent env for fast iterations
```

---

## Test Categories

### 1. API Tests (`services/api/tests/`) - 134 files

| Category | Count | Location | Description |
|----------|-------|----------|-------------|
| Unit | 52 | `tests/unit/` | Isolated unit tests |
| Integration | 53 | `tests/integration/` | Cross-component tests |
| Router | 12 | `tests/routers/projects/` | API endpoint tests |
| Security | 7 | `tests/security/` | OWASP security tests |
| E2E | 6 | `tests/e2e/` | End-to-end API flows |
| Performance | 1 | `tests/performance/` | Performance benchmarks |
| Health | 1 | `tests/health/` | Health check tests |
| Container | 1 | `tests/container/` | Container behavior tests |
| Migration | 1 | `tests/migration/` | Database migration tests |

**Key test files:**
- `test_api_endpoints.py` - API endpoint coverage
- `test_auth_module_consolidation.py` - Authentication system
- `test_evaluation_config_validation.py` - Evaluation configuration
- `test_project_import.py` - Import/export functionality
- `test_security_*.py` - Security regression tests

**Run API tests:**
```bash
make test-api              # Unit tests only
make test-api-integration  # Integration tests
make test-api-security     # Security tests
make test-api-comprehensive # All API tests
```

---

### 2. Worker Tests (`services/workers/tests/`) - 16 files

| Category | Files |
|----------|-------|
| LLM Pipeline | `test_llm_generation_pipeline.py` |
| Evaluation | `test_evaluation_*.py` (5 files) |
| Email | `test_email_service.py`, `test_sendgrid_client.py` |
| Celery | `test_e2e_pipeline.py` |
| Resource Management | `test_resource_management.py` |

**Run worker tests:**
```bash
make test-workers          # Unit tests only
make test-workers-comprehensive # All worker tests
```

---

### 3. Frontend Tests (`services/frontend/`) - 465 files

#### Jest Unit Tests - 425 files

Location: `src/__tests__/` and component-level `__tests__/` directories

| Category | Examples |
|----------|----------|
| Components | `AnnotatorBadges.test.tsx`, `GenerationTaskList.test.tsx` |
| Pages | `page.test.tsx` in each `app/*/` directory |
| Contexts | `AuthContext.test.tsx`, `FeatureFlagContext.test.tsx` |
| Hooks | `useAnnotationWebSocket.test.ts` |
| API Client | `client.test.ts`, `evaluations.test.ts` |
| Utils | `jsonUtils.test.ts`, `permissions.test.ts` |

**Run frontend unit tests:**
```bash
make test-frontend         # Jest unit tests
make test-frontend-integration # Integration tests
cd services/frontend && npm test -- --watch  # Watch mode
```

#### Playwright E2E Tests - 40 files

Location: `e2e/`

| Project | Tests | Description |
|---------|-------|-------------|
| `role-scenarios` | 6 files (85 tests) | Role-based access testing |
| `enhanced-workflows` | 4 files (16 tests) | Advanced workflow tests |
| `user-workflows` | 5 files (35 tests) | User workflow tests |
| `user-journeys` | 13 files | Complete user journey tests |
| `feature-tests` | 1 file (10 tests) | Feature-specific tests |
| `realtime-tests` | 1 file (8 tests) | WebSocket/real-time tests |
| `admin` | 1 file (2 tests) | Admin interface tests |
| `visual-regression` | 1 file | Visual screenshot tests |
| `cross-browser` | 1 file | Firefox/WebKit compatibility |
| `mobile` | 1 file | Mobile device tests |

**E2E test directories:**
```
e2e/
├── admin/                 # Admin interface tests
├── enhanced-workflows/    # Complex workflow tests
├── role-scenarios/        # Role-based access tests
├── user-journeys/         # Complete user journeys
├── user-workflows/        # User workflow tests
├── helpers/               # Test utilities
├── personas/              # User persona classes
├── pages/                 # Page object models
└── fixtures/              # Test data
```

**Run E2E tests:**
```bash
make test-e2e              # Full E2E (ephemeral infrastructure)
make test-e2e-dev          # Keep environment running
make test-e2e-ui           # Interactive Playwright UI
make test-e2e-headed       # Visible browser
make e2e-report            # View HTML report
```

---

### 4. Infrastructure Tests (`infra/tests/`) - 16 files

| Category | Files |
|----------|-------|
| Helm | `test_helm_template_rendering.py` |
| Runner | `test_runner_reliability.py` |
| Integration | `integration/*.py` (10 files) |
| Workflow | `workflow-optimization/*.py` (2 files) |

**Run infrastructure tests:**
```bash
make test-infra            # All infrastructure tests
make test-infra-helm       # Helm template tests only
```

---

## Ephemeral Test Infrastructure

### How `make test` Works

```
┌─────────────────────────────────────────────────────────────┐
│                    make test                                 │
├─────────────────────────────────────────────────────────────┤
│ PHASE 1: Unit & Integration Tests                           │
│   1. Start test PostgreSQL (port 5433) + Redis (port 6380)  │
│   2. Run API tests in Docker container                      │
│   3. Run Worker tests in Docker container                   │
│   4. Run Frontend Jest tests                                │
│   5. Tear down unit test infrastructure                     │
├─────────────────────────────────────────────────────────────┤
│ PHASE 2: End-to-End Tests                                   │
│   6. Start E2E stack (PostgreSQL 5434, Redis 6381, App)     │
│   7. Initialize database with demo users                    │
│   8. Run Playwright E2E tests (6 projects, 155 tests)       │
│   9. Tear down E2E infrastructure                           │
├─────────────────────────────────────────────────────────────┤
│ SUMMARY: Pass/fail report for each test suite               │
└─────────────────────────────────────────────────────────────┘
```

### Infrastructure Ports

| Environment | PostgreSQL | Redis | Frontend | API |
|-------------|------------|-------|----------|-----|
| Development | 5432 | 6379 | 3000 / 80 | 8000 |
| Unit Tests | 5433 | 6380 | - | - |
| E2E Tests | 5434 | 6381 | 8090 | 8002 |

### E2E Demo Users

| User | Role | Password |
|------|------|----------|
| admin@example.com | Superadmin | admin |
| org_admin@example.com | Org Admin | admin |
| contributor@example.com | Contributor | admin |
| annotator@example.com | Annotator | admin |

---

## Test Commands Reference

### Full Suite
```bash
make test                  # Full ephemeral test suite (recommended)
make test-quick            # Quick unit tests (mocked infrastructure)
make test-coverage         # Generate coverage reports
```

### By Service
```bash
make test-api              # API unit tests
make test-workers          # Worker unit tests
make test-frontend         # Frontend Jest tests
make test-infra            # Infrastructure tests
```

### E2E Testing
```bash
make test-e2e              # Full automated E2E
make test-e2e-dev          # Development mode (keeps env running)
make test-e2e-ui           # Interactive Playwright UI
make test-e2e-headed       # Visible browser for debugging
make test-e2e-debug        # Step-through debugging
```

### E2E Infrastructure
```bash
make e2e-start             # Start E2E environment
make e2e-stop              # Stop E2E environment
make e2e-restart           # Clean restart
make e2e-status            # Check health
make e2e-logs              # View logs
make e2e-seed              # Re-seed database
make e2e-report            # View test report
```

### Specialized
```bash
make test-api-security     # OWASP security tests
make test-api-performance  # Performance benchmarks
make test-api-comprehensive # All API test categories
```

---

## CI/CD Pipeline

The GitHub Actions CI/CD pipeline runs the same tests as `make test`:

1. **API Unit Tests** - In Docker container
2. **Worker Unit Tests** - In Docker container
3. **Frontend Jest Tests** - npm test
4. **E2E Playwright Tests** - Against full ephemeral stack

Triggered on:
- Pull requests to master
- Direct pushes to master
- Manual workflow dispatch

---

## Test Directory Structure

```
BenGER/
├── services/
│   ├── api/tests/
│   │   ├── unit/              # 52 unit tests
│   │   ├── integration/       # 53 integration tests
│   │   ├── routers/           # 12 router tests
│   │   ├── security/          # 7 security tests
│   │   ├── e2e/               # 6 API e2e tests
│   │   ├── performance/       # 1 performance test
│   │   ├── health/            # 1 health test
│   │   ├── container/         # 1 container test
│   │   ├── migration/         # 1 migration test
│   │   ├── conftest.py        # Pytest fixtures
│   │   └── fixtures.py        # Test data
│   │
│   ├── frontend/
│   │   ├── src/__tests__/     # Jest unit tests (distributed)
│   │   ├── e2e/               # Playwright E2E tests
│   │   │   ├── admin/
│   │   │   ├── enhanced-workflows/
│   │   │   ├── role-scenarios/
│   │   │   ├── user-journeys/
│   │   │   ├── user-workflows/
│   │   │   ├── helpers/
│   │   │   ├── personas/
│   │   │   ├── pages/
│   │   │   └── fixtures/
│   │   ├── jest.setup.js      # Jest configuration
│   │   └── playwright.config.ts
│   │
│   └── workers/tests/         # 16 worker tests
│       └── conftest.py
│
└── infra/tests/               # 16 infrastructure tests
    └── integration/
```

---

## Writing New Tests

### API Tests
```python
# services/api/tests/unit/test_example.py
import pytest

@pytest.mark.unit
def test_example():
    assert True
```

### Frontend Unit Tests
```typescript
// services/frontend/src/components/__tests__/Example.test.tsx
import { render, screen } from '@testing-library/react'
import { Example } from '../Example'

describe('Example', () => {
  it('renders correctly', () => {
    render(<Example />)
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })
})
```

### E2E Tests
```typescript
// services/frontend/e2e/user-workflows/example.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Example Workflow', () => {
  test('completes successfully', async ({ page }) => {
    await page.goto('/projects')
    await expect(page.locator('h1')).toContainText('Projects')
  })
})
```

---

## Troubleshooting

### E2E tests fail with "element not found"
- Check if the E2E infrastructure is running: `make e2e-status`
- View logs: `make e2e-logs-api` or `make e2e-logs-frontend`
- Re-seed the database: `make e2e-seed`

### Tests hang or timeout
- Increase timeout in playwright.config.ts
- Check for infinite loops in application code
- View browser: `make test-e2e-headed`

### Port conflicts
- Stop development environment: `make stop`
- Stop E2E environment: `make e2e-stop`
- Check ports: `lsof -i :5432,5433,5434,6379,6380,6381`

### Docker issues
- Clean up: `make clean-docker`
- Remove E2E images: `make e2e-clean-images`
- Full cleanup: `make e2e-clean-all`
