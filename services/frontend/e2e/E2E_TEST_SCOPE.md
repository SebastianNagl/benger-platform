# E2E Test Scope and Mocking Strategy

## Overview

This document describes the scope and mocking strategy for BenGER's E2E test suite, specifically for the user workflow tests added in Issue #796.

## Test Categories

### 1. Role-Based Workflow Tests (`e2e/role-scenarios/`)

- **Purpose**: Verify role-based access control (RBAC) and permission boundaries
- **Roles Tested**: superadmin, org_admin, contributor, annotator, user
- **Scope**: Navigation, permission checks, UI element visibility
- **Execution**: UI-only, no backend workflow execution

### 2. User Workflow Tests (`e2e/user-workflows/`)

- **Purpose**: Verify complete user workflows and feature functionality
- **Features Tested**: API keys, models, prompts, file upload, generation, evaluation, export, label config
- **Scope**: UI interaction, form validation, configuration management
- **Execution**: Mixed UI and lightweight backend operations

## Mocking Strategy Analysis

### ✅ API Key Management (`api-key-management.spec.ts`)

**Mocking Status**: NOT mocked (uses real workflow)

**What Tests Do**:

- Navigate to profile page and expand API keys section
- Fill API key input fields with test values (e.g., `sk-test1234567890abcdefghijklmnopqrstuvwxyz`)
- Save API keys to database via real encryption service
- Verify persistence across page reloads
- Test CRUD operations for all providers (OpenAI, Anthropic, Google, DeepInfra)

**Backend Services Used**:

- `UserApiKeyService` - Real encryption and database storage
- `EncryptionService` - Real Fernet encryption
- Database - Real SQLAlchemy session

**External Dependencies**: None (pure CRUD operations)

**Risk Level**: ✅ **Low** - No external API calls, safe to use real workflow

---

### ⚠️ Generation Workflow (`generation-complete-workflow.spec.ts`)

**Mocking Status**: NOT mocked (would make REAL LLM API calls if triggered)

**What Tests Do**:

- Navigate to `/generations` page
- Verify project selector shows generation status indicators
- Check for "Start Generation" button visibility
- Open generation control modal and verify options
- Verify multiple model columns in task list
- **DO NOT actually click "Start Generation"** (avoids real API calls)

**What Happens If Generation Is Triggered**:

1. API creates `ResponseGeneration` record in database
2. Celery task `generate_llm_responses` is dispatched to worker
3. Worker retrieves user's API key from database
4. Worker makes **REAL API calls** to OpenAI/Anthropic/Google/DeepInfra
5. Costs real money, depends on external service availability
6. Results are stored in database

**Backend Services Used** (if triggered):

- `services/api/routers/generation.py` - Generation API endpoints
- `services/workers/tasks.py:generate_llm_responses` - Real LLM generation task
- `services/shared/ai_services/` - Direct LLM API client calls
- Celery - Async task execution
- WebSocket - Real-time progress updates

**External Dependencies**: OpenAI, Anthropic, Google, DeepInfra APIs

**Risk Level**: ⚠️ **HIGH** - Tests are UI-only to avoid external API calls, but no safety mechanism prevents accidental execution

**Current Mitigation**: Tests deliberately avoid clicking "Start Generation" button

---

### ✅ Evaluation Workflow (`evaluation-complete-workflow.spec.ts`)

**Mocking Status**: NOT mocked (uses real metric calculations)

**What Tests Do**:

- Navigate to `/evaluations` page
- Configure evaluation metrics (exact_match, BLEU, ROUGE, F1, etc.)
- Verify metric parameter inputs (e.g., BLEU n-gram size)
- Check evaluation results display
- Verify confusion matrix and distribution charts

**Backend Services Used**:

- `services/api/routers/evaluations.py` - Evaluation API endpoints
- `services/workers/tasks.py:run_selected_evaluation` - Real evaluation task
- `ml_evaluation/sample_evaluator.py` - Real metric calculations
- Database - Real task, annotation, and generation data

**External Dependencies**: None (all computations are local)

**Risk Level**: ✅ **Low** - No external dependencies, safe to execute

---

### ✅ Model Configuration (`model-configuration.spec.ts`)

**Mocking Status**: NOT mocked (uses real configuration workflow)

**What Tests Do**:

- Navigate to model configuration page
- Select models via checkboxes
- Configure model parameters (temperature, max_tokens, top_p)
- Save configuration to project.generation_config JSONB field
- Verify persistence across reloads

**Backend Services Used**:

- `services/api/routers/llm_models.py` - Model listing endpoint
- Database - Real project configuration updates

**External Dependencies**: None

**Risk Level**: ✅ **Low** - Pure configuration management

---

### ✅ Prompt Management (`prompt-management.spec.ts`)

**Mocking Status**: NOT mocked (uses real prompt structure CRUD)

**What Tests Do**:

- Create, edit, delete prompt structures
- Test variable syntax (e.g., `{{domain}}`, `{{question}}`)
- Toggle active/inactive status
- Verify persistence

**Backend Services Used**:

- `services/api/routers/generation.py` - Prompt structure endpoints
- Database - Real JSONB updates to project.generation_config

**External Dependencies**: None

**Risk Level**: ✅ **Low** - Pure CRUD operations

---

### ✅ File Upload (`file-upload.spec.ts`)

**Mocking Status**: NOT mocked (uses real file processing)

**What Tests Do**:

- Upload CSV/JSON/XML files via file picker or drag-and-drop
- Verify file validation (format, size)
- Test import preview and task creation
- Verify error handling for invalid files

**Test Fixtures Used**:

- `e2e/fixtures/test-data-small.csv` (10 rows)
- `e2e/fixtures/test-data-medium.csv` (100 rows)
- `e2e/fixtures/test-data.json` (15 objects)
- `e2e/fixtures/test-data.xml` (10 tasks)
- `e2e/fixtures/invalid-data.txt` (negative testing)

**Backend Services Used**:

- `services/api/routers/projects/data.py` - Data import endpoints
- File parsing logic (CSV, JSON, XML parsers)
- Database - Real task creation

**External Dependencies**: None

**Risk Level**: ✅ **Low** - File processing is local

---

### ✅ Data Export (`data-export.spec.ts`)

**Mocking Status**: NOT mocked (uses real export logic)

**What Tests Do**:

- Export project data in multiple formats (JSON, CSV, XML/Label Studio)
- Verify file download
- Validate export structure
- Test round-trip (import → export → verify)

**Backend Services Used**:

- `services/api/routers/projects/export.py` - Export endpoints
- Export formatters (JSON, CSV, XML)
- Database - Real project, task, and annotation data

**External Dependencies**: None

**Risk Level**: ✅ **Low** - Export is read-only operation

---

### ✅ Label Config Updates (`label-config-updates.spec.ts`)

**Mocking Status**: NOT mocked (uses real label config workflow)

**What Tests Do**:

- Update label configuration after project creation
- Add/remove/modify fields
- Verify annotation preservation
- Test template switching
- Validate XML syntax

**Backend Services Used**:

- `services/api/routers/projects/config.py` - Label config endpoints
- XML validator
- Database - Real project.label_config updates with versioning

**External Dependencies**: None

**Risk Level**: ✅ **Low** - Configuration management only

---

## Environment Variables

### Existing Test Mode Detection

```python
# services/workers/tasks.py:947, 1000
if os.getenv("TESTING") == "true":
    # Only affects error handling (re-raise vs return)
```

**No Mock Mode Exists** for:

- LLM API calls
- Celery task execution
- WebSocket real-time updates
- External service integrations

### E2E Test Environment (from `global-setup.ts`)

```typescript
sessionStorage.setItem('e2e_test_mode', 'true')
sessionStorage.setItem('auto_login_attempted', 'true')
```

**Purpose**: Disables auto-login for E2E tests

---

## Risk Assessment Summary

| Test Suite           | External API Calls        | Risk Level  | Mitigation                                  |
| -------------------- | ------------------------- | ----------- | ------------------------------------------- |
| API Key Management   | ❌ None                   | ✅ Low      | N/A                                         |
| Model Configuration  | ❌ None                   | ✅ Low      | N/A                                         |
| Prompt Management    | ❌ None                   | ✅ Low      | N/A                                         |
| File Upload          | ❌ None                   | ✅ Low      | N/A                                         |
| Generation Workflow  | ⚠️ **YES** (if triggered) | ⚠️ **HIGH** | **Tests avoid clicking "Start Generation"** |
| Evaluation Workflow  | ❌ None                   | ✅ Low      | N/A                                         |
| Data Export          | ❌ None                   | ✅ Low      | N/A                                         |
| Label Config Updates | ❌ None                   | ✅ Low      | N/A                                         |

---

## Recommendations

### Short-term: Document Current Scope ✅

- **Status**: DONE (this document)
- Tests are **UI-focused** and deliberately avoid triggering external API calls
- Current approach is safe but limited in coverage

### Medium-term: Add E2E Mock Mode (Optional)

If full workflow testing is desired, add mock mode for LLM services:

```python
# services/shared/ai_services/openai_service.py
def generate(self, prompt, system_prompt, model_name, **kwargs):
    if os.getenv("E2E_TEST_MODE") == "true":
        return self._create_response_dict(
            content="Mock LLM response for E2E testing",
            model=model_name,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            success=True
        )
    # Real API call...
```

**Benefits**:

- Tests can verify complete workflows end-to-end
- No external dependencies or costs
- Fast and deterministic

**Complexity**: Medium (requires mocking in multiple services)

### Long-term: Separate Integration Test Suite

Create dedicated integration tests that use real API keys (with budget limits):

- Run nightly or on-demand (not in CI)
- Use rate limiting and quotas
- Verify real LLM integrations work
- Complement E2E tests with real-world validation

---

## Test Execution

### Running E2E Tests

```bash
# All E2E tests (role-scenarios + user-workflows)
make test-e2e

# User workflow tests only
npx playwright test --project=user-workflows

# Specific test file
npx playwright test e2e/user-workflows/generation-complete-workflow.spec.ts

# Headed mode (see browser)
make test-e2e-headed

# Debug mode
make test-e2e-debug
```

### Test Configuration

- **Base URL**: `http://benger.localhost` (via Docker Traefik)
- **Resolution**: 1920x1080 (desktop)
- **Browser**: Chromium (Desktop Chrome)
- **Parallel Workers**: 2 (role-scenarios), 2-4 (user-workflows)
- **Timeout**: 60s per test (isolated E2E mode), 30s (default)

---

## Conclusion

**Current E2E test suite is SAFE and APPROPRIATE for its scope:**

- ✅ No external API calls are made (tests avoid triggering generation)
- ✅ Tests verify UI behavior, configuration, and permission boundaries
- ✅ Backend operations tested are CRUD-only (no costly external dependencies)
- ✅ File processing, evaluations, and exports use real logic (safe local operations)

**Limitations:**

- ⚠️ Generation workflow not tested end-to-end (UI-only)
- ⚠️ WebSocket real-time updates not verified in tests
- ⚠️ Celery task execution not covered

**This is an acceptable trade-off** for E2E tests that run frequently in CI/CD. For full integration testing, consider a separate test suite with mocked LLM services or budget-controlled real API usage.
