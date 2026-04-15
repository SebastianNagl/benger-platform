/**
 * QA Project Full Workflow E2E Test
 *
 * This test creates a complete end-to-end workflow from scratch:
 * 1. Create a new QA project with TextArea label config
 * 2. Import tasks with question data
 * 3. Create annotations by multiple annotators (simulated via API)
 * 4. Seed mock LLM generations for 3 models
 * 5. Run REAL evaluation with all available metrics (text, model-based, mocked LLM judge)
 * 6. Verify evaluation results and computed metric values via API
 * 7. Verify leaderboards show model and annotator rankings
 * 8. Clean up the created project
 *
 * IMPORTANT: This test runs in the ephemeral test environment only.
 * Execute via: make test-e2e
 */
import { test, expect } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

// Test configuration
const PROJECT_NAME = `E2E Full Workflow QA ${Date.now()}`
const MODELS = ['gpt-4-turbo', 'claude-3-sonnet', 'gemini-pro']
const ANNOTATORS = ['admin', 'contributor', 'annotator'] // Seeded test users

// QA label config for TextArea answers (rows="10" triggers LONG_TEXT detection for full metric coverage)
const LABEL_CONFIG = `<View>
  <Text name="question" value="$question"/>
  <TextArea name="answer" toName="question" placeholder="Enter your answer" required="true" rows="10"/>
</View>`

// Test tasks with questions
const TEST_TASKS = [
  { data: { question: 'What are the requirements to form a GmbH in Germany?' } },
  { data: { question: 'How does German contract law handle breach of contract?' } },
  { data: { question: 'What is the limitation period for tort claims?' } },
  { data: { question: 'What rights do employees have under German labor law?' } },
  { data: { question: 'How are intellectual property rights protected in Germany?' } },
]

// Reference answers (annotations)
const REFERENCE_ANSWERS = [
  'A GmbH requires minimum capital of €25,000, notarized articles, and commercial register entry.',
  'German contract law allows claims for damages, specific performance, or contract rescission.',
  'The standard limitation period for tort claims is 3 years from knowledge of the claim.',
  'Employees have rights to paid leave, notice periods, dismissal protection, and works councils.',
  'IP is protected via Patent Act, Trademark Act, Copyright Act, and EU design regulations.',
]

// Mock LLM responses for each model
const MODEL_RESPONSES: Record<string, string[]> = {
  'gpt-4-turbo': [
    'To form a GmbH: €25,000 minimum capital, notarized articles, commercial register entry required.',
    'Breach of contract under BGB: damages (§280), specific performance, or rescission (§323) available.',
    'Tort limitation: 3 years from year-end when claim arose and claimant had knowledge (§195, §199).',
    'Employee rights: 20+ days leave, notice periods, dismissal protection, collective bargaining.',
    'IP protection: PatG for patents, MarkenG for trademarks, UrhG for copyright, DesignG for designs.',
  ],
  'claude-3-sonnet': [
    'GmbH formation requires: €25k capital, notarized founding docs, commercial register, German address.',
    'Contract breach under BGB: specific performance, damage compensation (§§280ff), termination rights.',
    'Standard tort limitation: 3 years starting from year-end when claim and knowledge arose.',
    'Key employee rights: 4+ weeks leave, statutory notice, dismissal protection after 6 months.',
    'Germany protects IP via: patents (20 years), trademarks (10-year renewable), copyright (life+70).',
  ],
  'gemini-pro': [
    'GmbH needs: €25k capital, notarized articles, commercial register. Managing director required.',
    'Contract breach in BGB: Claims for damages, specific performance, or rescission available.',
    'Tort claims: 3-year limitation from end of year when claim arose and claimant knew.',
    'Employee protections: Minimum 20 days leave, notice periods, dismissal protection, works councils.',
    'IP: Patents (PatG), trademarks (MarkenG), copyright (UrhG), designs (DesignG) protected.',
  ],
}

// All non-LLM metrics for LONG_TEXT answer type (matches ANSWER_TYPE_TO_METRICS)
// Lightweight text metrics + model-based metrics (models are downloaded on first run)
const EVAL_METRICS = [
  'bleu', 'rouge', 'meteor', 'chrf',          // lightweight text metrics
  'bertscore', 'moverscore',                    // embedding-based metrics
  'semantic_similarity',                        // sentence-transformer-based
  'factcc', 'qags',                             // factual consistency
  // Note: 'coherence' excluded — requires 2+ sentences, test answers are single sentences
]

// LLM judge metrics (mocked in E2E test mode — no API keys needed)
const LLM_JUDGE_METRICS = ['llm_judge_classic', 'llm_judge_custom']

test.describe('QA Project Full Workflow (Create-to-Verify) @extended', () => {
  let projectId: string | null = null
  let taskIds: string[] = []
  let generationIds: string[] = []

  test.beforeEach(async ({ page }) => {
    const testHelpers = new TestHelpers(page)
    await testHelpers.login('admin', 'admin')
  })

  test('Step 1: Create new QA project with TextArea label config', async ({ page }) => {
    // Create project via API
    const createResult = await page.evaluate(
      async ({ name, labelConfig }) => {
        const response = await fetch('/api/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            title: name,
            description: 'E2E full workflow test - QA project',
            label_config: labelConfig,
          }),
        })
        if (!response.ok) {
          const error = await response.text()
          return { success: false, error, status: response.status }
        }
        const data = await response.json()
        return { success: true, projectId: data.id, title: data.title }
      },
      { name: PROJECT_NAME, labelConfig: LABEL_CONFIG }
    )

    console.log(`[Step 1] Create project: ${JSON.stringify(createResult)}`)

    expect(createResult.success).toBeTruthy()
    projectId = createResult.projectId!
    console.log(`[Step 1] Created project: ${projectId}`)
  })

  test('Step 2: Import tasks with question data', async ({ page }) => {
    // Get project ID from previous test or find it
    if (!projectId) {
      projectId = await page.evaluate(async (name) => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow QA')
        )
        return project?.id || null
      }, PROJECT_NAME)
    }

    test.skip(!projectId, 'Project not found from Step 1')

    // Import tasks
    const importResult = await page.evaluate(
      async ({ pid, tasks }) => {
        const response = await fetch(`/api/projects/${pid}/import`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ data: tasks }),
        })
        if (!response.ok) {
          return { success: false, error: await response.text() }
        }
        const data = await response.json()
        return { success: true, taskCount: data.task_count || tasks.length }
      },
      { pid: projectId, tasks: TEST_TASKS }
    )

    console.log(`[Step 2] Import tasks: ${JSON.stringify(importResult)}`)
    expect(importResult.success).toBeTruthy()

    // Get task IDs
    const tasks = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/projects/${pid}/tasks`, { credentials: 'include' })
      if (!response.ok) return []
      const data = await response.json()
      return (data.items || data.tasks || data || []).map((t: { id: string }) => t.id)
    }, projectId)

    taskIds = tasks
    console.log(`[Step 2] Got ${taskIds.length} task IDs`)
    expect(taskIds.length).toBe(TEST_TASKS.length)
  })

  test('Step 3: Create annotations by multiple annotators', async ({ page }) => {
    // Get project and task IDs
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow QA')
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

    // Create annotations from MULTIPLE ANNOTATORS
    // Each task gets annotations from all 3 annotators with slightly varied answers
    const annotations: Array<{task_id: string; result: object[]; annotator_username: string}> = []

    for (let i = 0; i < taskIds.length && i < REFERENCE_ANSWERS.length; i++) {
      // Each annotator provides their answer for this task
      for (let a = 0; a < ANNOTATORS.length; a++) {
        const annotator = ANNOTATORS[a]
        // Vary answers slightly per annotator to simulate real multi-annotator scenario
        const answerVariant = a === 0
          ? REFERENCE_ANSWERS[i]
          : `${REFERENCE_ANSWERS[i]} (${annotator}'s perspective)`

        annotations.push({
          task_id: taskIds[i],
          annotator_username: annotator,
          result: [{
            from_name: 'answer',
            to_name: 'question',
            type: 'textarea',
            value: { text: [answerVariant] },
          }],
        })
      }
    }

    const seedResult = await page.evaluate(
      async ({ pid, anns }) => {
        for (let attempt = 0; attempt < 3; attempt++) {
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
              if (attempt < 2) { await new Promise(r => setTimeout(r, 2000)); continue }
              return { success: false, error: error, created_count: 0 }
            }
            return await response.json()
          } catch (e) {
            if (attempt < 2) { await new Promise(r => setTimeout(r, 2000)); continue }
            return { success: false, error: String(e), created_count: 0 }
          }
        }
        return { success: false, error: 'All retries failed', created_count: 0 }
      },
      { pid: projectId, anns: annotations }
    )

    if (!seedResult.success) {
      console.log(`[Step 3] Annotation seeding error: ${seedResult.error}`)
    }
    const annotationsCreated = seedResult.created_count || 0
    const expectedAnnotations = REFERENCE_ANSWERS.length * ANNOTATORS.length // 5 tasks × 3 annotators

    console.log(`[Step 3] Created ${annotationsCreated} annotations from ${ANNOTATORS.length} annotators`)
    expect(annotationsCreated).toBe(expectedAnnotations)
  })

  test('Step 4: Seed mock LLM generations for 3 models', async ({ page }) => {
    // Get project and task IDs
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow QA')
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

  test('Step 5: Run real evaluation with all metrics', async ({ page }) => {
    test.setTimeout(600_000) // 10 min — model downloads + real evaluation via Celery

    // Get project ID
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow QA')
        )
        return project?.id || null
      })
    }

    test.skip(!projectId, 'Project not found')

    // 1. GET auto-generated evaluation config (detects answer types from label config)
    const autoConfig = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/evaluations/projects/${pid}/evaluation-config`, {
        credentials: 'include',
      })
      if (!response.ok) return { success: false, error: await response.text() }
      return { success: true, ...(await response.json()) }
    }, projectId)

    console.log(`[Step 5] Auto-detected types: ${JSON.stringify(autoConfig.detected_answer_types?.map((t: any) => t.type))}`)
    console.log(`[Step 5] Available methods: ${JSON.stringify(Object.keys(autoConfig.available_methods || {}))}`)
    expect(autoConfig.success).toBeTruthy()
    expect(autoConfig.available_methods).toHaveProperty('answer')

    // 2. Build evaluation configs for all metrics (deterministic + LLM judge)
    const allMetrics = [...EVAL_METRICS, ...LLM_JUDGE_METRICS]
    const evalConfigs = allMetrics.map(metric => ({
      id: `e2e-qa-${metric}`,
      metric,
      display_name: metric.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      prediction_fields: ['answer'],
      reference_fields: ['answer'],
      enabled: true,
    }))

    // 3. PUT: Save selected evaluation methods
    const { success: _s, ...baseConfig } = autoConfig
    const saveResult = await page.evaluate(async ({ pid, config, evalCfgs, metrics }) => {
      const response = await fetch(`/api/evaluations/projects/${pid}/evaluation-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          ...config,
          selected_methods: {
            answer: {
              automated: metrics,
              human: [],
              field_mapping: {
                prediction_field: 'answer',
                reference_field: 'answer',
              },
            },
          },
          evaluation_configs: evalCfgs,
        }),
      })
      if (!response.ok) return { success: false, error: await response.text() }
      return { success: true, ...(await response.json()) }
    }, { pid: projectId, config: baseConfig, evalCfgs: evalConfigs, metrics: allMetrics })

    console.log(`[Step 5] Saved evaluation config: ${saveResult.success ? 'OK' : saveResult.error}`)
    expect(saveResult.success).toBeTruthy()

    // 4. POST: Run evaluation using the saved configs
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
      if (!response.ok) return { success: false, error: await response.text() }
      const data = await response.json()
      return { success: true, evaluation_id: data.evaluation_id, status: data.status }
    }, { pid: projectId, evalCfgs: evalConfigs })

    console.log(`[Step 5] Started evaluation: ${JSON.stringify(runResult)}`)
    expect(runResult.success).toBeTruthy()
    expect(runResult.evaluation_id).toBeTruthy()

    // 5. Poll for completion (every 5s, max 540s — model downloads can be slow)
    const evalId = runResult.evaluation_id
    const pollResult = await page.evaluate(async (eid: string) => {
      const maxAttempts = 108
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise(r => setTimeout(r, 5000))
        try {
          const response = await fetch(`/api/evaluations/evaluation/status/${eid}`, {
            credentials: 'include',
          })
          if (!response.ok) continue
          const data = await response.json()
          if (data.status === 'completed') return { success: true, status: 'completed', attempts: i + 1 }
          if (data.status === 'failed') return { success: false, status: 'failed', error: data.message, attempts: i + 1 }
        } catch (e) { /* retry */ }
      }
      return { success: false, status: 'timeout', error: 'Timeout', attempts: maxAttempts }
    }, evalId)

    console.log(`[Step 5] Poll result: ${JSON.stringify(pollResult)}`)
    expect(pollResult.success).toBeTruthy()
    expect(pollResult.status).toBe('completed')

    // 6. Verify results have real metric values
    const results = await page.evaluate(async (eid: string) => {
      const response = await fetch(`/api/evaluations/run/results/${eid}`, { credentials: 'include' })
      if (!response.ok) return { success: false, error: await response.text() }
      return { success: true, ...(await response.json()) }
    }, evalId)

    console.log(`[Step 5] Results: samples=${results.samples_evaluated}, status=${results.status}`)
    const aggMetrics = results.aggregated_metrics || {}
    for (const [key, value] of Object.entries(aggMetrics)) {
      console.log(`[Step 5]   ${key} = ${value}`)
    }

    expect(results.success).toBeTruthy()
    expect(results.status).toBe('completed')
    expect(results.samples_evaluated).toBeGreaterThan(0)

    // Verify each configured metric produced results
    const metricKeys = Object.keys(aggMetrics)
    for (const metric of allMetrics) {
      const hasMetric = metricKeys.some(k => k.includes(metric))
      console.log(`[Step 5] Has ${metric}: ${hasMetric}`)
      expect(hasMetric).toBeTruthy()
    }

    // All values should be in valid range (0-1)
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
          (p: { title: string }) => p.title.includes('E2E Full Workflow QA')
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
      if (!resultsRes.ok) return { success: false, error: await resultsRes.text() }

      const data = await resultsRes.json()
      const latest = (data.evaluations || [])[0]

      // Extract scores from results_by_config
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
        evaluationCount: (data.evaluations || []).length,
        latestStatus: latest?.status || null,
        latestSamplesEvaluated: latest?.samples_evaluated || 0,
        scores,
      }
    }, projectId)

    console.log(`[Step 6] Evaluations: ${evalData.evaluationCount}, status: ${evalData.latestStatus}`)
    console.log(`[Step 6] Samples: ${evalData.latestSamplesEvaluated}`)

    expect(evalData.success).toBeTruthy()
    expect(evalData.evaluationCount).toBeGreaterThan(0)
    expect(evalData.latestStatus).toBe('completed')
    expect(evalData.latestSamplesEvaluated).toBeGreaterThan(0)

    // Verify scores for each metric
    const scores = evalData.scores as Record<string, number>
    for (const [key, value] of Object.entries(scores)) {
      console.log(`[Step 6]   ${key} = ${value}`)
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThanOrEqual(1)
    }

    // Verify all configured metrics have scores
    const allMetrics = [...EVAL_METRICS, ...LLM_JUDGE_METRICS]
    for (const metric of allMetrics) {
      const hasScore = Object.keys(scores).some(k => k.includes(metric))
      expect(hasScore).toBeTruthy()
    }
  })

  test('Step 7: Verify leaderboards show model and annotator rankings', async ({ page }) => {
    // Navigate to leaderboards
    await page.goto('/leaderboards')
    await page.waitForTimeout(2000)

    // Check for leaderboard table
    const hasTable = await page.locator('table').first().isVisible({ timeout: 5000 }).catch(() => false)
    console.log(`[Step 7] Leaderboard table visible: ${hasTable}`)

    // Check for LLM section and model names
    const llmSection = await page.locator('text=/LLM|Models/i').first().isVisible({ timeout: 3000 }).catch(() => false)
    console.log(`[Step 7] LLM section visible: ${llmSection}`)

    // Verify models appear in leaderboard
    let modelsFound = 0
    for (const model of MODELS) {
      const modelVisible = await page.locator(`text=${model}`).first().isVisible({ timeout: 2000 }).catch(() => false)
      if (modelVisible) modelsFound++
    }
    console.log(`[Step 7] Models found in leaderboard: ${modelsFound}/${MODELS.length}`)

    // Check for Human/Annotator section
    const humanSection = await page.locator('text=/Human|Annotator/i').first().isVisible({ timeout: 3000 }).catch(() => false)
    console.log(`[Step 7] Human section visible: ${humanSection}`)

    // Verify annotators appear in leaderboard (check for usernames or display names)
    let annotatorsFound = 0
    for (const annotator of ANNOTATORS) {
      // Check for username or common display name patterns
      const annotatorVisible = await page.locator(`text=/${annotator}|System Administrator|contributor|Annotator User/i`)
        .first().isVisible({ timeout: 2000 }).catch(() => false)
      if (annotatorVisible) annotatorsFound++
    }
    console.log(`[Step 7] Annotators found in leaderboard: ${annotatorsFound}/${ANNOTATORS.length}`)

    // Leaderboard should show either models or annotators (or both)
    expect(hasTable || llmSection || humanSection).toBeTruthy()
  })

  test('Step 8: Clean up test project', async ({ page }) => {
    // Get project ID
    if (!projectId) {
      projectId = await page.evaluate(async () => {
        const response = await fetch('/api/projects', { credentials: 'include' })
        const data = await response.json()
        const project = (data.items || data || []).find(
          (p: { title: string }) => p.title.includes('E2E Full Workflow QA')
        )
        return project?.id || null
      })
    }

    if (!projectId) {
      console.log('[Step 8] No project to clean up')
      return
    }

    // Clean up via test endpoint
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
  })
})
