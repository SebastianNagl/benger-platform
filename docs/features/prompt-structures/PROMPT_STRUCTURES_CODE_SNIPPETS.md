# Prompt Structures Manager - Code Snippets

## Component Structure Overview

### Main Component Interface
```typescript
interface PromptStructure {
  key: string
  name: string
  description?: string
  system_prompt: string | object
  instruction_prompt: string | object
  evaluation_prompt?: string | object | null
}

interface PromptStructuresManagerProps {
  projectId: string
  onStructuresChange?: () => void
}
```

## Key Implementation Patterns

### 1. Field Reference Extraction
Automatically extracts field references from structures to show which task.data fields are used:

```typescript
const extractFieldReferences = (structure: PromptStructure): string[] => {
  const refs: string[] = []

  const extract = (value: any) => {
    if (typeof value === 'string' && value.startsWith('$')) {
      refs.push(value.substring(1))
    } else if (typeof value === 'object' && value !== null) {
      Object.values(value).forEach(extract)
    }
  }

  extract(structure.system_prompt)
  extract(structure.instruction_prompt)
  if (structure.evaluation_prompt) {
    extract(structure.evaluation_prompt)
  }

  return [...new Set(refs)] // Remove duplicates
}
```

### 2. Active Structure Toggle
Optimistic UI update with rollback on error:

```typescript
const handleToggleActive = async (key: string) => {
  const newActiveStructures = activeStructures.includes(key)
    ? activeStructures.filter((k) => k !== key)
    : [...activeStructures, key]

  setActiveStructures(newActiveStructures)

  try {
    await apiClient.put(
      `/projects/${projectId}/generation-config/structures`,
      newActiveStructures
    )
    if (onStructuresChange) {
      onStructuresChange()
    }
  } catch (err) {
    console.error('Failed to update active structures:', err)
    setError('Failed to update active structures')
    // Revert on error
    setActiveStructures(activeStructures)
  }
}
```

### 3. Structure Key Validation
Client-side validation matching backend pattern:

```typescript
const validateStructureKey = (key: string): string | null => {
  if (!key || key.length < 1 || key.length > 50) {
    return 'Structure key must be 1-50 characters long'
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(key)) {
    return 'Structure key can only contain alphanumeric characters, underscores, and hyphens'
  }
  if (!editingKey && structures[key]) {
    return 'A structure with this key already exists'
  }
  return null
}
```

### 4. Collapsed Header Display
Dynamic summary showing active structures:

```typescript
{!expanded && (
  <p className="text-sm text-zinc-500 dark:text-zinc-400">
    {totalCount === 0
      ? 'No structures configured'
      : `${activeCount} active of ${totalCount} total`}
    {activeCount > 0 &&
      `: ${activeStructures.map((k) => structures[k]?.name || k).join(', ')}`}
  </p>
)}
```

### 5. Structure Card Display
Shows structure details with action buttons:

```typescript
<Card key={key} className="overflow-hidden">
  <div className="flex items-start justify-between p-4">
    <div className="flex min-w-0 flex-1 items-start space-x-3">
      <input
        type="checkbox"
        checked={isActive}
        onChange={() => handleToggleActive(key)}
        className="mt-1 h-4 w-4 flex-shrink-0 rounded border-zinc-300"
        title={isActive ? 'Active' : 'Inactive'}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center space-x-2">
          <h4 className="font-medium">{structure.name}</h4>
          <span className="inline-flex items-center rounded bg-zinc-100 px-2 py-0.5 text-xs">
            {key}
          </span>
          {isActive && (
            <span className="inline-flex items-center rounded bg-emerald-100 px-2 py-0.5 text-xs">
              Active
            </span>
          )}
        </div>
        {structure.description && (
          <p className="mt-1 text-sm text-zinc-600">{structure.description}</p>
        )}
        {fieldRefs.length > 0 && (
          <div className="mt-2">
            <p className="text-xs text-zinc-500">References fields:</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {fieldRefs.map((field, i) => (
                <span key={i} className="rounded bg-blue-100 px-2 py-0.5 text-xs">
                  {field}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
    <div className="flex flex-shrink-0 items-center space-x-2">
      <Button onClick={() => openEditModal(key, structure)} variant="outline">
        <PencilIcon className="h-4 w-4" />
      </Button>
      <Button onClick={() => setDeletingKey(key)} variant="outline" className="border-red-500">
        <TrashIcon className="h-4 w-4" />
      </Button>
    </div>
  </div>
</Card>
```

## Project Detail Page Integration

### Import Statement
```typescript
import { PromptStructuresManager } from '@/components/projects/PromptStructuresManager'
```

### Usage in JSX
```typescript
{/* Prompt Structures Section - Issue #762 */}
<div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
  {canEditProject() ? (
    <PromptStructuresManager
      projectId={projectId || ''}
      onStructuresChange={() => {
        // Refetch project to update UI
        if (projectId) {
          fetchProject(projectId)
        }
      }}
    />
  ) : (
    <div className="py-6 text-center">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Only the project creator can manage prompt structures
      </p>
    </div>
  )}
</div>
```

## E2E Test Examples

### Test Structure Creation
```typescript
test('should create a new prompt structure', async ({ page }) => {
  await page.goto('http://benger.localhost/projects')
  await page.waitForLoadState('networkidle')
  
  const projectCard = page.locator('a[href*="/projects/"]').first()
  await projectCard.click()
  await page.waitForLoadState('networkidle')

  // Expand and open add modal
  await page.click('h3:has-text("Prompt Structures")')
  await page.click('button:has-text("Add Structure")')

  // Fill in structure details
  const timestamp = Date.now()
  const structureKey = `test-structure-${timestamp}`

  await page.fill('input#structure-key', structureKey)
  await page.fill('input#structure-name', 'Test Legal Analysis')
  await page.fill(
    'textarea#structure-description',
    'A test structure for legal document analysis'
  )

  // Select a template
  await page.click('button:has-text("Simple Q&A")')
  await page.waitForTimeout(500)

  // Save the structure
  await page.click('button:has-text("Create Structure")')
  await page.waitForTimeout(1000)

  // Verify structure appears in list
  await expect(page.locator(`text=${structureKey}`)).toBeVisible()
  await expect(page.locator('text=Test Legal Analysis')).toBeVisible()
})
```

### Test Active Toggle
```typescript
test('should toggle structure active state', async ({ page }) => {
  await page.goto('http://benger.localhost/projects')
  await page.waitForLoadState('networkidle')
  
  const projectCard = page.locator('a[href*="/projects/"]').first()
  await projectCard.click()
  await page.waitForLoadState('networkidle')

  await page.click('h3:has-text("Prompt Structures")')

  const firstCheckbox = page
    .locator('input[type="checkbox"]')
    .first()
    .locator('visible=true')

  if ((await firstCheckbox.count()) > 0) {
    const initialState = await firstCheckbox.isChecked()
    await firstCheckbox.click()
    await page.waitForTimeout(500)
    
    const newState = await firstCheckbox.isChecked()
    expect(newState).toBe(!initialState)
  }
})
```

## API Call Examples

### List Structures
```typescript
const structures = await apiClient.get(
  `/projects/${projectId}/generation-config/structures`
)
// Returns: { "structure-key-1": {...}, "structure-key-2": {...} }
```

### Create/Update Structure
```typescript
await apiClient.put(
  `/projects/${projectId}/generation-config/structures/${key}`,
  {
    name: 'Legal Analysis',
    description: 'For analyzing legal documents',
    system_prompt: 'You are a legal expert...',
    instruction_prompt: '$question',
    evaluation_prompt: null
  }
)
```

### Update Active Structures
```typescript
await apiClient.put(
  `/projects/${projectId}/generation-config/structures`,
  ['structure-1', 'structure-2']
)
```

### Delete Structure
```typescript
await apiClient.delete(
  `/projects/${projectId}/generation-config/structures/${key}`
)
```

## Error Handling Patterns

### Modal Error Display
```typescript
{modalError && (
  <Alert variant="destructive">
    <XMarkIcon className="h-4 w-4" />
    <AlertDescription>{modalError}</AlertDescription>
  </Alert>
)}
```

### API Error Handling
```typescript
try {
  await apiClient.put(/* ... */)
  setShowModal(false)
  if (onStructuresChange) {
    onStructuresChange()
  }
} catch (err: any) {
  console.error('Failed to save structure:', err)
  setModalError(
    err?.detail || err?.message || 'Failed to save structure'
  )
} finally {
  setSaving(false)
}
```

## Style Patterns

### Card with Hover Effect
```typescript
className="overflow-hidden hover:shadow-md transition-shadow"
```

### Conditional Styling for Active Badge
```typescript
{isActive && (
  <span className="inline-flex items-center rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300">
    Active
  </span>
)}
```

### Field Reference Badges
```typescript
<span className="rounded bg-blue-100 px-2 py-0.5 text-xs dark:bg-blue-900">
  {field}
</span>
```

---

These code snippets demonstrate the key patterns and implementations used in the PromptStructuresManager component.
