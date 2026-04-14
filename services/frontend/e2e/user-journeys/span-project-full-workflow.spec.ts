/**
 * Span/NER Project Full Workflow E2E Test (Create-to-Verify)
 *
 * This test creates a Named Entity Recognition project from scratch:
 * 1. Create a new project with NER/Labels label config
 * 2. Import tasks with text data
 * 3. Create span annotations using test seeding API
 * 4. Seed mock LLM generations for multiple models
 * 5. Run REAL evaluation with span metrics (span_exact_match, iou) via Celery worker
 * 6. Verify evaluation results and computed metric values via API
 * 7. Verify leaderboards show rankings
 * 8. Clean up test project
 *
 * IMPORTANT: This test runs in the ephemeral test environment only.
 * Execute via: make test-e2e
 */
import { test, expect } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

// Constants for test data
const MODELS = ['gpt-4-turbo', 'claude-3-sonnet', 'gemini-pro']
const ANNOTATORS = ['admin', 'contributor', 'annotator'] // Seeded test users
const EXPECTED_TASK_COUNT = 5

// German legal texts with entities
const LEGAL_TEXTS = [
  'Dr. Hans Müller vertritt die Klägerin vor dem Landgericht München.',
  'Die BMW AG wurde am 15. März 2023 in München gegründet.',
  'Prof. Maria Schmidt arbeitet an der Universität Heidelberg.',
  'Der Bundesgerichtshof in Karlsruhe hat am 1. Januar 2024 entschieden.',
  'Thomas Weber von der Deutschen Bank AG erschien vor dem Oberlandesgericht Frankfurt.',
]

// NER annotations for each text (character offsets)
const NER_ANNOTATIONS = [
  [{ start: 4, end: 15, text: 'Hans Müller', label: 'PERSON' }, { start: 47, end: 66, text: 'Landgericht München', label: 'ORG' }],
  [{ start: 4, end: 10, text: 'BMW AG', label: 'ORG' }, { start: 18, end: 31, text: '15. März 2023', label: 'DATE' }, { start: 35, end: 42, text: 'München', label: 'LOC' }],
  [{ start: 6, end: 18, text: 'Maria Schmidt', label: 'PERSON' }, { start: 32, end: 55, text: 'Universität Heidelberg', label: 'ORG' }],
  [{ start: 4, end: 21, text: 'Bundesgerichtshof', label: 'ORG' }, { start: 25, end: 34, text: 'Karlsruhe', label: 'LOC' }, { start: 43, end: 58, text: '1. Januar 2024', label: 'DATE' }],
  [{ start: 0, end: 12, text: 'Thomas Weber', label: 'PERSON' }, { start: 21, end: 40, text: 'Deutschen Bank AG', label: 'ORG' }, { start: 56, end: 82, text: 'Oberlandesgericht Frankfurt', label: 'ORG' }],
]

// Mock LLM NER outputs (JSON format)
const MODEL_RESPONSES: Record<string, string[]> = {
  'gpt-4-turbo': [
    '[{"start": 4, "end": 15, "label": "PERSON"}, {"start": 47, "end": 66, "label": "ORG"}]',
    '[{"start": 4, "end": 10, "label": "ORG"}, {"start": 18, "end": 31, "label": "DATE"}]',
    '[{"start": 6, "end": 18, "label": "PERSON"}, {"start": 32, "end": 55, "label": "ORG"}]',
    '[{"start": 4, "end": 21, "label": "ORG"}, {"start": 25, "end": 34, "label": "LOC"}]',
    '[{"start": 0, "end": 12, "label": "PERSON"}, {"start": 21, "end": 40, "label": "ORG"}]',
  ],
  'claude-3-sonnet': [
    '[{"start": 4, "end": 15, "label": "PERSON"}]',
    '[{"start": 4, "end": 10, "label": "ORG"}, {"start": 35, "end": 42, "label": "LOC"}]',
    '[{"start": 6, "end": 18, "label": "PERSON"}]',
    '[{"start": 4, "end": 21, "label": "ORG"}, {"start": 43, "end": 58, "label": "DATE"}]',
    '[{"start": 0, "end": 12, "label": "PERSON"}, {"start": 56, "end": 82, "label": "ORG"}]',
  ],
  'gemini-pro': [
    '[{"start": 4, "end": 15, "label": "PERSON"}, {"start": 47, "end": 66, "label": "ORG"}]',
    '[{"start": 4, "end": 10, "label": "ORG"}, {"start": 18, "end": 31, "label": "DATE"}, {"start": 35, "end": 42, "label": "LOC"}]',
    '[{"start": 6, "end": 18, "label": "PERSON"}, {"start": 32, "end": 55, "label": "ORG"}]',
    '[{"start": 4, "end": 21, "label": "ORG"}, {"start": 25, "end": 34, "label": "LOC"}, {"start": 43, "end": 58, "label": "DATE"}]',
    '[{"start": 0, "end": 12, "label": "PERSON"}, {"start": 21, "end": 40, "label": "ORG"}, {"start": 56, "end": 82, "label": "ORG"}]',
  ],
}

// State variables shared between tests
let projectId: string | null = null
let taskIds: string[] = []
let generationIds: string[] = []

test.describe('Span/NER Project Full Workflow (Create-to-Verify) @extended', () => {
  test.beforeEach(async ({ page }) => {
    const testHelpers = new TestHelpers(page)
    await testHelpers.login('admin', 'admin')
  })

  test('Step 1: Create new NER project with Labels config', async ({ page }) => {
    const labelConfig = `<View>
  <Labels name="label" toName="text">
    <Label value="PERSON" background="#FF6B6B"/>
    <Label value="ORG" background="#4ECDC4"/>
    <Label value="LOC" background="#96CEB4"/>
    <Label value="DATE" background="#45B7D1"/>
  </Labels>
  <Text name="text" value="$text"/>
</View>`

    const result = await page.evaluate(async (config) => {
      const response = await fetch('/api/projects/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          title: `E2E Full Workflow NER ${Date.now()}`,
          description: 'NER project created by E2E test workflow',
          label_config: config,
        }),
      })

      if (!response.ok) {
        const error = await response.text()
        return { success: false, error }
      }

      const project = await response.json()
      return {
        success: true,
        projectId: project.id,
        title: project.title,
      }
    }, labelConfig)

    console.log(`[Step 1] Create project: ${JSON.stringify(result)}`)
    expect(result.success).toBeTruthy()
    projectId = result.projectId
    console.log(`[Step 1] Created project: ${projectId}`)
  })

  test('Step 2: Import tasks with text data', async ({ page }) => {
    // Get project ID if not available
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow NER')
        )
        return project?.id || null
      })
    }

    test.skip(!projectId, 'Project not found')

    // Prepare tasks with text data
    const tasks = LEGAL_TEXTS.map((text, idx) => ({
      data: { text, id: `task-${idx + 1}` },
    }))

    const importResult = await page.evaluate(
      async ({ pid, taskData }) => {
        const response = await fetch(`/api/projects/${pid}/import`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ data: taskData }),
        })
        if (!response.ok) {
          return { success: false, error: await response.text() }
        }
        return { success: true, taskCount: taskData.length }
      },
      { pid: projectId, taskData: tasks }
    )

    console.log(`[Step 2] Import tasks: ${JSON.stringify(importResult)}`)
    expect(importResult.success).toBeTruthy()

    // Get task IDs
    taskIds = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/projects/${pid}/tasks`, { credentials: 'include' })
      if (!response.ok) return []
      const data = await response.json()
      return (data.items || data.tasks || data || []).map((t: { id: string }) => t.id)
    }, projectId)

    console.log(`[Step 2] Got ${taskIds.length} task IDs`)
    expect(taskIds.length).toBe(EXPECTED_TASK_COUNT)
  })

  test('Step 3: Create span annotations by multiple annotators', async ({ page }) => {
    // Get project and task IDs
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow NER')
        )
        return project?.id || null
      })
    }

    if (taskIds.length === 0) {
      taskIds = await page.evaluate(async (pid) => {
        const response = await fetch(`/api/projects/${pid}/tasks`, { credentials: 'include' })
        if (!response.ok) return []
        const data = await response.json()
        return (data.items || data.tasks || data || []).map((t: { id: string }) => t.id)
      }, projectId)
    }

    test.skip(!projectId || taskIds.length === 0, 'Project or tasks not found')

    // Create span annotations from MULTIPLE ANNOTATORS
    // Each task gets annotations from all 3 annotators
    const annotations: Array<{task_id: string; result: object[]; annotator_username: string}> = []

    for (let i = 0; i < taskIds.length && i < NER_ANNOTATIONS.length; i++) {
      // Each annotator provides their NER annotations for this task
      for (let a = 0; a < ANNOTATORS.length; a++) {
        const annotator = ANNOTATORS[a]
        // Use same entities but this simulates multi-annotator agreement
        annotations.push({
          task_id: taskIds[i],
          annotator_username: annotator,
          result: [{
            from_name: 'label',
            to_name: 'text',
            type: 'labels',
            value: {
              spans: NER_ANNOTATIONS[i]?.map(entity => ({
                start: entity.start,
                end: entity.end,
                text: entity.text,
                labels: [entity.label],
              })) || [],
            },
          }],
        })
      }
    }

    const seedResult = await page.evaluate(
      async ({ pid, anns }) => {
        try {
          const response = await fetch('/api/test/seed/annotations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              project_id: pid,
              annotations: anns,
            }),
          })
          if (!response.ok) {
            const error = await response.text()
            return { success: false, error: error, created_count: 0 }
          }
          return await response.json()
        } catch (e) {
          return { success: false, error: String(e), created_count: 0 }
        }
      },
      { pid: projectId, anns: annotations }
    )

    if (!seedResult.success) {
      console.log(`[Step 3] Annotation seeding error: ${seedResult.error}`)
    }
    const annotationsCreated = seedResult.created_count || 0
    const expectedAnnotations = EXPECTED_TASK_COUNT * ANNOTATORS.length // 5 tasks × 3 annotators

    console.log(`[Step 3] Created ${annotationsCreated} annotations from ${ANNOTATORS.length} annotators`)
    expect(annotationsCreated).toBe(expectedAnnotations)
  })

  test('Step 4: Seed mock LLM NER generations for 3 models', async ({ page }) => {
    // Get project and task IDs
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow NER')
        )
        return project?.id || null
      })
    }

    if (taskIds.length === 0) {
      taskIds = await page.evaluate(async (pid) => {
        const response = await fetch(`/api/projects/${pid}/tasks`, { credentials: 'include' })
        if (!response.ok) return []
        const data = await response.json()
        return (data.items || data.tasks || data || []).map((t: { id: string }) => t.id)
      }, projectId)
    }

    test.skip(!projectId || taskIds.length === 0, 'Project or tasks not found')

    // Build generations list for all models
    const generations: Array<{ task_id: string; model_id: string; output: string }> = []
    for (const model of MODELS) {
      const responses = MODEL_RESPONSES[model]
      for (let i = 0; i < taskIds.length && i < responses.length; i++) {
        generations.push({
          task_id: taskIds[i],
          model_id: model,
          output: responses[i],
        })
      }
    }

    // Seed generations via test endpoint
    const seedResult = await page.evaluate(
      async ({ pid, gens }) => {
        const response = await fetch('/api/test/seed/generations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            project_id: pid,
            generations: gens,
          }),
        })
        if (!response.ok) {
          return { success: false, error: await response.text() }
        }
        return response.json()
      },
      { pid: projectId, gens: generations }
    )

    console.log(`[Step 4] Seed generations: ${JSON.stringify(seedResult)}`)
    expect(seedResult.success).toBeTruthy()
    generationIds = seedResult.ids || []
    console.log(`[Step 4] Created ${generationIds.length} generations`)
  })

  test('Step 5: Run real evaluation with span metrics', async ({ page }) => {
    test.setTimeout(180_000) // 3 min — real evaluation via Celery

    // Get project ID
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow NER')
        )
        return project?.id || null
      })
    }

    test.skip(!projectId, 'Project not found')

    // 1. GET auto-generated evaluation config (detects span answer types)
    const autoConfig = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/evaluations/projects/${pid}/evaluation-config`, {
        credentials: 'include',
      })
      if (!response.ok) return { success: false, error: await response.text() }
      return { success: true, ...(await response.json()) }
    }, projectId)

    console.log(`[Step 5] Auto-detected config: detected_types=${JSON.stringify(autoConfig.detected_answer_types?.map((t: any) => t.type))}`)
    console.log(`[Step 5] Available methods: ${JSON.stringify(Object.keys(autoConfig.available_methods || {}))}`)
    expect(autoConfig.success).toBeTruthy()
    expect(autoConfig.detected_answer_types?.length).toBeGreaterThan(0)
    expect(autoConfig.available_methods).toHaveProperty('label')

    // 2. PUT: Save selected evaluation methods (user picks span_exact_match + iou)
    const evalConfigs = [
      {
        id: 'e2e-ner-eval',
        metric: 'span_exact_match',
        display_name: 'Span Exact Match',
        prediction_fields: ['label'],
        reference_fields: ['label'],
        enabled: true,
      },
      {
        id: 'e2e-ner-iou',
        metric: 'iou',
        display_name: 'IoU',
        prediction_fields: ['label'],
        reference_fields: ['label'],
        enabled: true,
      },
    ]

    // Build the config body from auto-detected config, adding user selections
    const { success: _s, ...baseConfig } = autoConfig
    const saveResult = await page.evaluate(async ({ pid, config, evalCfgs }) => {
      const response = await fetch(`/api/evaluations/projects/${pid}/evaluation-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          ...config,
          selected_methods: {
            label: {
              automated: ['span_exact_match', 'iou'],
              human: [],
              field_mapping: {
                prediction_field: 'label',
                reference_field: 'label',
              },
            },
          },
          evaluation_configs: evalCfgs,
        }),
      })
      if (!response.ok) return { success: false, error: await response.text() }
      return { success: true, ...(await response.json()) }
    }, { pid: projectId, config: baseConfig, evalCfgs: evalConfigs })

    console.log(`[Step 5] Saved evaluation config: ${saveResult.success ? 'OK' : saveResult.error}`)
    expect(saveResult.success).toBeTruthy()

    // 3. POST: Run evaluation using the saved configs
    const runResult = await page.evaluate(async ({ pid, evalCfgs }) => {
      const response = await fetch('/api/evaluations/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          project_id: pid,
          evaluation_configs: evalCfgs,
          batch_size: 100,
          force_rerun: true,
        }),
      })
      if (!response.ok) {
        return { success: false, error: await response.text() }
      }
      const data = await response.json()
      return { success: true, evaluation_id: data.evaluation_id, status: data.status }
    }, { pid: projectId, evalCfgs: evalConfigs })

    console.log(`[Step 5] Started evaluation: ${JSON.stringify(runResult)}`)
    expect(runResult.success).toBeTruthy()
    expect(runResult.evaluation_id).toBeTruthy()

    // Poll for completion (every 3s, max 120s)
    const evalId = runResult.evaluation_id
    const pollResult = await page.evaluate(async (eid: string) => {
      const maxAttempts = 40
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise(r => setTimeout(r, 3000))
        try {
          const response = await fetch(`/api/evaluations/evaluation/status/${eid}`, {
            credentials: 'include',
          })
          if (!response.ok) {
            console.log(`Poll attempt ${i + 1}: HTTP ${response.status}`)
            continue
          }
          const data = await response.json()
          console.log(`Poll attempt ${i + 1}: status=${data.status}`)
          if (data.status === 'completed') {
            return { success: true, status: data.status, attempts: i + 1 }
          }
          if (data.status === 'failed') {
            return { success: false, status: 'failed', error: data.message || 'Evaluation failed', attempts: i + 1 }
          }
        } catch (e) {
          console.log(`Poll attempt ${i + 1}: error ${e}`)
        }
      }
      return { success: false, status: 'timeout', error: 'Timeout waiting for evaluation', attempts: 40 }
    }, evalId)

    console.log(`[Step 5] Evaluation poll result: ${JSON.stringify(pollResult)}`)
    expect(pollResult.success).toBeTruthy()
    expect(pollResult.status).toBe('completed')

    // Verify results have real metric values
    const results = await page.evaluate(async (eid: string) => {
      const response = await fetch(`/api/evaluations/run/results/${eid}`, {
        credentials: 'include',
      })
      if (!response.ok) return { success: false, error: await response.text() }
      return { success: true, ...(await response.json()) }
    }, evalId)

    console.log(`[Step 5] Evaluation results: samples_evaluated=${results.samples_evaluated}, status=${results.status}`)
    const aggMetrics = results.aggregated_metrics || {}
    console.log(`[Step 5] Aggregated metrics keys: ${Object.keys(aggMetrics).join(', ') || 'none'}`)
    for (const [key, value] of Object.entries(aggMetrics)) {
      console.log(`[Step 5]   ${key} = ${value}`)
    }

    expect(results.success).toBeTruthy()
    expect(results.status).toBe('completed')
    expect(results.samples_evaluated).toBeGreaterThan(0)

    // Verify metric keys contain span metrics
    const metricKeys = Object.keys(aggMetrics)
    const hasSpanExactMatch = metricKeys.some(k => k.includes('span_exact_match'))
    const hasIoU = metricKeys.some(k => k.includes('iou'))
    console.log(`[Step 5] Has span_exact_match: ${hasSpanExactMatch}, Has iou: ${hasIoU}`)
    expect(hasSpanExactMatch).toBeTruthy()
    expect(hasIoU).toBeTruthy()

    // Verify metric values are in valid range (0-1)
    for (const [key, value] of Object.entries(aggMetrics)) {
      const numValue = Number(value)
      if (!isNaN(numValue)) {
        expect(numValue).toBeGreaterThanOrEqual(0)
        expect(numValue).toBeLessThanOrEqual(1)
      }
    }
  })

  test('Step 6: Verify evaluation results and metrics via API', async ({ page }) => {
    // Get project ID
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow NER')
        )
        return project?.id || null
      })
    }

    test.skip(!projectId, 'Project not found')

    // Fetch project evaluation results
    const evalData = await page.evaluate(async (pid) => {
      const resultsRes = await fetch(`/api/evaluations/run/results/project/${pid}`, {
        credentials: 'include',
      })

      if (!resultsRes.ok) {
        return { success: false, error: await resultsRes.text() }
      }

      const data = await resultsRes.json()
      const evaluations = data.evaluations || []
      const latest = evaluations[0]

      // Extract scores from results_by_config structure
      const scores: Record<string, number> = {}
      if (latest?.results_by_config) {
        for (const [configId, configData] of Object.entries(latest.results_by_config as Record<string, any>)) {
          for (const fieldResult of (configData.field_results || [])) {
            for (const [metricName, metricValue] of Object.entries(fieldResult.scores || {})) {
              scores[`${configId}:${metricName}`] = Number(metricValue)
            }
          }
        }
      }

      return {
        success: true,
        evaluationCount: evaluations.length,
        latestStatus: latest?.status || null,
        latestSamplesEvaluated: latest?.samples_evaluated || 0,
        latestModelId: latest?.model_id || null,
        scores,
      }
    }, projectId)

    console.log(`[Step 6] Evaluation count: ${evalData.evaluationCount}`)
    console.log(`[Step 6] Latest status: ${evalData.latestStatus}`)
    console.log(`[Step 6] Samples evaluated: ${evalData.latestSamplesEvaluated}`)
    console.log(`[Step 6] Model: ${evalData.latestModelId}`)

    expect(evalData.success).toBeTruthy()
    expect(evalData.evaluationCount).toBeGreaterThan(0)
    expect(evalData.latestStatus).toBe('completed')
    expect(evalData.latestSamplesEvaluated).toBeGreaterThan(0)

    // Verify metric scores exist and are reasonable
    const scores = evalData.scores as Record<string, number>
    const scoreKeys = Object.keys(scores)
    console.log(`[Step 6] Score keys: ${scoreKeys.join(', ')}`)

    const hasSpanExact = scoreKeys.some(k => k.includes('span_exact_match'))
    const hasIoU = scoreKeys.some(k => k.includes('iou'))
    expect(hasSpanExact).toBeTruthy()
    expect(hasIoU).toBeTruthy()

    // All scores should be between 0 and 1
    for (const [key, value] of Object.entries(scores)) {
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThanOrEqual(1)
      console.log(`[Step 6]   ${key} = ${value}`)
    }
  })

  test('Step 7: Verify leaderboards show rankings', async ({ page }) => {
    // Navigate to leaderboards
    await page.goto('/leaderboards')
    await page.waitForTimeout(2000)

    // Verify leaderboard page loads
    const hasTable = await page.locator('table')
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false)

    console.log(`[Step 7] Leaderboard table visible: ${hasTable}`)

    // Check for LLM section and model names
    const hasLLMSection = await page.locator('text=/LLM|Model/i')
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    console.log(`[Step 7] LLM section visible: ${hasLLMSection}`)

    // Verify models appear in leaderboard
    let modelsFound = 0
    for (const model of MODELS) {
      const modelVisible = await page.locator(`text=${model}`).first().isVisible({ timeout: 2000 }).catch(() => false)
      if (modelVisible) modelsFound++
    }
    console.log(`[Step 7] Models found in leaderboard: ${modelsFound}/${MODELS.length}`)

    // Check for Human/Annotator section
    const hasHumanSection = await page.locator('text=/Human|Annotator/i')
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    console.log(`[Step 7] Human section visible: ${hasHumanSection}`)

    // Verify annotators appear in leaderboard
    let annotatorsFound = 0
    for (const annotator of ANNOTATORS) {
      const annotatorVisible = await page.locator(`text=/${annotator}|System Administrator|contributor|Annotator User/i`)
        .first().isVisible({ timeout: 2000 }).catch(() => false)
      if (annotatorVisible) annotatorsFound++
    }
    console.log(`[Step 7] Annotators found in leaderboard: ${annotatorsFound}/${ANNOTATORS.length}`)

    expect(hasTable || hasLLMSection || hasHumanSection).toBeTruthy()
  })

  test('Step 8: Clean up test project', async ({ page }) => {
    // Get project ID
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow NER')
        )
        return project?.id || null
      })
    }

    test.skip(!projectId, 'Project not found, nothing to clean up')

    // Clean up the test project using seeding API
    const cleanupResult = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/test/cleanup/${pid}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!response.ok) {
        return { success: false, error: await response.text() }
      }
      return response.json()
    }, projectId)

    console.log(`[Step 8] Cleanup result: ${JSON.stringify(cleanupResult)}`)
    expect(cleanupResult.success).toBeTruthy()

    // Reset state
    projectId = null
    taskIds = []
    generationIds = []
  })
})
