# Evaluation Pipeline Critical Issues

This document lists critical issues found during QA testing of the evaluation pipeline on 2025-10-17.

---

## Issue #1: Frontend-Backend API Parameter Mismatch Blocks Evaluation Execution

**Severity:** CRITICAL
**Priority:** P0
**Labels:** bug, evaluation, frontend, backend, api-contract

### Description

The frontend sends incorrect parameters when calling the automated evaluation endpoint, causing all evaluation attempts to fail silently.

### Location

**Frontend:** `/services/frontend/src/app/evaluations/page.tsx` (lines 144-161)
**Backend:** `/services/api/routers/evaluations.py` (lines 909-914, 937-1044)

### Current Behavior

Frontend code (line 148-151):
```typescript
const response = await apiClient.post('/evaluations/automated', {
  project_id: selectedProject.id,
  model_ids: ['gpt-4o', 'claude-sonnet-4'], // Example models
})
```

Backend expects (lines 909-914):
```python
class AutomatedEvaluationRequest(BaseModel):
    project_id: str
    force_rerun: bool = False
    batch_size: int = 100
```

### Expected Behavior

Frontend should send parameters that match the backend API contract:
- `project_id` (string)
- `force_rerun` (boolean, optional, default: false)
- `batch_size` (integer, optional, default: 100)

### Steps to Reproduce

1. Navigate to http://benger.localhost/evaluations
2. Log in as superadmin
3. Select a project from the project selector
4. Click on "Automatic" step (step 2)
5. Click "Start Evaluation" button
6. Observe that evaluation does not start
7. Check network tab - request to `/api/evaluations/automated` fails or returns error
8. Check console - error logged but user sees no helpful message

### Impact

- Prevents all automated evaluations from running
- Users cannot test the evaluation pipeline
- Blocks entire evaluation workflow
- Silent failure provides no guidance to users

### Proposed Fix

**Option 1: Fix Frontend to Match Backend**

```typescript
const startAutomatedEvaluation = async () => {
  if (!selectedProject) return

  try {
    const response = await apiClient.post('/evaluations/automated', {
      project_id: selectedProject.id,
      force_rerun: false,  // Allow user to toggle via checkbox
      batch_size: 100       // Allow user to configure via input
    })

    addToast('Automated evaluation started successfully', 'success')
    fetchProjectData(selectedProject.id)
  } catch (error: any) {
    const message = error.response?.data?.detail || 'Failed to start automated evaluation'
    console.error('Failed to start automated evaluation:', error)
    addToast(message, 'error')
  }
}
```

**Option 2: Update Backend to Accept model_ids**

If model selection should happen at evaluation time (rather than using all project models), update the backend to accept and use `model_ids`.

### Additional Context

- This issue was discovered during comprehensive QA testing
- Network request completes in ~17ms but returns error
- Error is not properly surfaced to the user
- Related to Issue #2 (missing evaluation config UI)

### Testing Checklist

- [ ] Fix applied to frontend
- [ ] Manual testing of evaluation start flow
- [ ] Error scenarios tested (invalid params, missing config)
- [ ] E2E test added to prevent regression
- [ ] API contract documented

---

## Issue #2: Missing Evaluation Configuration UI Blocks Workflow

**Severity:** CRITICAL
**Priority:** P0
**Labels:** bug, evaluation, frontend, ux, missing-feature

### Description

Projects require `evaluation_config` with `selected_methods` configured before automated evaluation can run, but there is no UI to configure this. The backend API has endpoints for managing evaluation config (GET/PUT `/api/evaluations/projects/{id}/evaluation-config`), but they are not integrated in the frontend.

### Location

**Backend API:** `/services/api/routers/evaluations.py` (lines 302-428)
**Missing Frontend:** No UI component exists for evaluation configuration
**Validation Check:** Lines 967-972 in `evaluations.py` block evaluation without config

### Current Behavior

When attempting to start an evaluation:
1. User clicks "Start Evaluation"
2. Backend checks if project has `evaluation_config`
3. If missing, returns HTTP 400: "Project has no evaluation configuration. Please configure evaluation methods first."
4. Frontend shows generic error message
5. User has no way to configure evaluation methods from UI

### Expected Behavior

1. Project settings should have an "Evaluation Configuration" section
2. Users can view detected answer types from label_config
3. Users can select which evaluation methods to run for each field:
   - Automated metrics (exact_match, BLEU, ROUGE, F1, etc.)
   - Human evaluation methods (Likert scales, preference ranking)
4. Configuration is saved via PUT endpoint
5. Validation provides feedback on configuration completeness
6. "Start Evaluation" button is disabled if config is incomplete

### Backend API Available

**GET `/api/evaluations/projects/{project_id}/evaluation-config`**
- Returns current evaluation config
- Auto-generates config from label_config if missing
- Response includes:
  - `detected_answer_types`: Array of fields with types
  - `available_methods`: Methods applicable to each field type
  - `selected_methods`: User's selected methods for each field

**PUT `/api/evaluations/projects/{project_id}/evaluation-config`**
- Updates evaluation configuration
- Validates selected methods against available methods
- Persists to `project.evaluation_config` JSONB field

**GET `/api/evaluations/projects/{project_id}/detect-answer-types`**
- Analyzes label_config to detect field types
- Returns applicable evaluation methods for each type

### Steps to Reproduce

1. Create a new project or use existing project without evaluation_config
2. Navigate to Evaluations page
3. Select the project
4. Go to Automatic evaluation step
5. Click "Start Evaluation"
6. Receive error: "Project has no evaluation configuration"
7. Attempt to find configuration UI - none exists
8. User is blocked with no clear path forward

### Impact

- Even with Issue #1 fixed, evaluations cannot run without config
- Users cannot use the evaluation system at all
- No way to select which metrics to run
- Dead-end user experience
- Backend implementation is wasted without frontend integration

### Proposed Solution

**Phase 1: Basic Configuration UI (MVP)**

Add evaluation configuration to project settings:

```typescript
// /services/frontend/src/app/projects/[id]/settings/evaluation/page.tsx

export default function EvaluationConfigPage() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fetch current config
    apiClient.get(`/evaluations/projects/${projectId}/evaluation-config`)
      .then(response => setConfig(response.data))
  }, [projectId])

  const handleSave = async () => {
    await apiClient.put(`/evaluations/projects/${projectId}/evaluation-config`, config)
    addToast('Evaluation configuration saved', 'success')
  }

  return (
    <div>
      <h2>Evaluation Configuration</h2>

      {config?.detected_answer_types.map(field => (
        <Card key={field.name}>
          <h3>{field.name}</h3>
          <p>Type: {field.type}</p>

          <h4>Automated Metrics</h4>
          {config.available_methods[field.name].available_metrics.map(metric => (
            <Checkbox
              key={metric}
              checked={config.selected_methods[field.name]?.automated?.includes(metric)}
              onChange={() => toggleMetric(field.name, metric)}
            >
              {metric}
            </Checkbox>
          ))}

          <h4>Human Evaluation</h4>
          {config.available_methods[field.name].available_human.map(method => (
            <Checkbox
              key={method}
              checked={config.selected_methods[field.name]?.human?.includes(method)}
              onChange={() => toggleHumanMethod(field.name, method)}
            >
              {method}
            </Checkbox>
          ))}
        </Card>
      ))}

      <Button onClick={handleSave}>Save Configuration</Button>
    </div>
  )
}
```

**Phase 2: Validation Integration**

Add validation before allowing evaluation start:

```typescript
const startAutomatedEvaluation = async () => {
  if (!selectedProject) return

  // Pre-flight check
  try {
    const configResponse = await apiClient.get(
      `/evaluations/projects/${selectedProject.id}/evaluation-config`
    )

    const selectedMethods = configResponse.data?.selected_methods || {}
    const hasSelectedMetrics = Object.values(selectedMethods).some(
      (field: any) => field.automated?.length > 0
    )

    if (!hasSelectedMetrics) {
      addToast('Please configure evaluation methods first', 'warning')
      router.push(`/projects/${selectedProject.id}/settings/evaluation`)
      return
    }
  } catch (error) {
    console.error('Failed to check evaluation config:', error)
    addToast('Please configure evaluation settings first', 'warning')
    return
  }

  // Proceed with evaluation start...
}
```

**Phase 3: Enhanced UX**

- Add "Configure Evaluation" button to project overview
- Show configuration status on evaluation dashboard
- Display warning if config is incomplete
- Add tooltip explaining required configuration
- Provide link to configuration page

### Alternative Approaches

1. **Auto-configuration:** Generate default config automatically and allow users to modify later
2. **Inline configuration:** Add configuration step to evaluation workflow before starting
3. **Template-based:** Provide evaluation config templates for common use cases

### Testing Checklist

- [ ] Configuration UI created and accessible
- [ ] Can view detected answer types
- [ ] Can select/deselect metrics for each field
- [ ] Configuration saves successfully
- [ ] Validation prevents invalid configurations
- [ ] Pre-flight check blocks evaluation if config missing
- [ ] Users are guided to configuration page when needed
- [ ] E2E test for full configuration workflow

### Related Issues

- Depends on: Issue #1 (API parameter fix)
- Related to: Issue #3 (error handling)
- Blocks: All evaluation result visualization features

---

## Issue #3: Poor Error Handling Provides No User Guidance

**Severity:** HIGH
**Priority:** P1
**Labels:** bug, evaluation, frontend, ux, error-handling

### Description

When evaluation operations fail, error messages are minimal, non-actionable, and easy to miss. Users receive a tiny "1 Issue" badge and a generic toast message with no details about what went wrong or how to fix it.

### Location

**Frontend:** `/services/frontend/src/app/evaluations/page.tsx` (lines 157-160)

### Current Behavior

```typescript
} catch (error) {
  console.error('Failed to start automated evaluation:', error)
  addToast('Failed to start automated evaluation', 'error')
}
```

**User Experience:**
1. Click "Start Evaluation"
2. See brief toast message: "Failed to start automated evaluation"
3. Small "1 Issue" badge appears in bottom-right corner
4. No indication of:
   - What went wrong
   - Why it failed
   - How to fix it
   - Whether it's a permission issue, configuration issue, or data issue

### Expected Behavior

**Detailed Error Messages:**
```typescript
} catch (error: any) {
  const detail = error.response?.data?.detail
  const status = error.response?.status

  let message = 'Failed to start automated evaluation'
  let action = null

  if (status === 400 && detail?.includes('no evaluation configuration')) {
    message = 'Evaluation configuration required'
    action = {
      label: 'Configure Now',
      onClick: () => router.push(`/projects/${selectedProject.id}/settings/evaluation`)
    }
  } else if (status === 403) {
    message = 'Only superadmins can start evaluations'
  } else if (detail) {
    message = detail
  }

  console.error('Failed to start automated evaluation:', error)
  addToast(message, 'error', { action })
}
```

**Enhanced Notification System:**
- Display full error message from API
- Provide actionable buttons ("Configure Evaluation", "Learn More")
- Show error details in expandable section
- Make notifications more prominent and persistent
- Add error icon with hover tooltip

### Impact

- Users cannot diagnose issues
- No path forward when errors occur
- Frustrating user experience
- Increased support burden
- Reduced adoption of evaluation features

### Examples of Improved Messages

| Current | Improved |
|---------|----------|
| "Failed to start automated evaluation" | "Evaluation configuration missing. You need to select evaluation methods before starting. [Configure Now]" |
| "Failed to start automated evaluation" | "Permission denied. Only superadmins can start evaluation runs. Contact your administrator." |
| "Failed to start automated evaluation" | "No annotated tasks found. Add ground truth annotations before running evaluations. [View Tasks]" |

### Proposed Solution

**1. Enhanced Error Component**

```typescript
interface ErrorDetails {
  title: string
  message: string
  details?: string
  action?: {
    label: string
    onClick: () => void
  }
  severity: 'error' | 'warning' | 'info'
}

function EvaluationError({ error }: { error: ErrorDetails }) {
  return (
    <div className="rounded-lg border-l-4 border-red-500 bg-red-50 p-4">
      <div className="flex">
        <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
        <div className="ml-3">
          <h3 className="text-sm font-medium text-red-800">{error.title}</h3>
          <div className="mt-2 text-sm text-red-700">
            <p>{error.message}</p>
            {error.details && (
              <details className="mt-2">
                <summary className="cursor-pointer font-medium">Show details</summary>
                <pre className="mt-2 text-xs">{error.details}</pre>
              </details>
            )}
          </div>
          {error.action && (
            <div className="mt-4">
              <Button onClick={error.action.onClick} variant="outline">
                {error.action.label}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
```

**2. Centralized Error Handler**

```typescript
function handleEvaluationError(error: any, context: string): ErrorDetails {
  const status = error.response?.status
  const detail = error.response?.data?.detail

  // Map API errors to user-friendly messages
  const errorMap: Record<number, (detail: string) => ErrorDetails> = {
    400: (detail) => ({
      title: 'Configuration Required',
      message: 'Evaluation cannot start without proper configuration.',
      details: detail,
      action: {
        label: 'Configure Evaluation',
        onClick: () => router.push(`/projects/${projectId}/settings/evaluation`)
      },
      severity: 'warning'
    }),
    403: () => ({
      title: 'Permission Denied',
      message: 'Only superadmins can start evaluation runs.',
      details: 'Contact your system administrator for access.',
      severity: 'error'
    }),
    404: () => ({
      title: 'Not Found',
      message: 'The requested resource was not found.',
      details: detail,
      severity: 'error'
    }),
    500: () => ({
      title: 'Server Error',
      message: 'An unexpected error occurred. Please try again.',
      details: detail,
      action: {
        label: 'Retry',
        onClick: () => window.location.reload()
      },
      severity: 'error'
    })
  }

  return errorMap[status]?.(detail) || {
    title: 'Error',
    message: 'An unexpected error occurred',
    details: detail || error.message,
    severity: 'error'
  }
}
```

**3. Usage in Components**

```typescript
const [error, setError] = useState<ErrorDetails | null>(null)

const startAutomatedEvaluation = async () => {
  setError(null)

  try {
    // ... evaluation logic
  } catch (err) {
    const errorDetails = handleEvaluationError(err, 'startEvaluation')
    setError(errorDetails)
    addToast(errorDetails.title, errorDetails.severity)
  }
}

return (
  <div>
    {error && <EvaluationError error={error} />}
    {/* rest of component */}
  </div>
)
```

### Testing Checklist

- [ ] All error scenarios identified and mapped
- [ ] User-friendly messages for each error type
- [ ] Actionable buttons provide correct navigation
- [ ] Error details are expandable and informative
- [ ] Toast notifications are prominent and persistent
- [ ] Error component styling matches design system
- [ ] E2E tests for error scenarios
- [ ] User testing validates improved experience

### Related Issues

- Related to: Issue #1 (API parameter fix)
- Related to: Issue #2 (missing config UI)
- Blocks: User adoption of evaluation features

---

## Summary

These three critical issues prevent the evaluation pipeline from functioning and must be resolved before the feature can be considered production-ready:

1. **Issue #1 (P0):** Fix API parameter mismatch - 1-2 hours
2. **Issue #2 (P0):** Create evaluation configuration UI - 1-2 days
3. **Issue #3 (P1):** Improve error handling and messaging - 4-8 hours

**Total Estimated Fix Time:** 2-3 days for critical path

Once these issues are resolved, additional testing will be needed for:
- Sample results visualization
- Confusion matrix rendering
- Metric distribution charts
- Config validation UI
- Human evaluation workflows

---

**Document Created:** 2025-10-17
**Testing Report:** See EVALUATION_PIPELINE_QA_REPORT.md
**Next Steps:** Development team to prioritize and implement fixes
