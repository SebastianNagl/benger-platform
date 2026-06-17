/**
 * Evaluation Dispatch → Results → Leaderboard E2E Journey
 *
 * Unifies the previously-split `evaluation-results-display` + `leaderboards`
 * specs into one continuous flow that mirrors the highest-value cross-app path:
 *
 *   1. Create a QA project (TextArea answers — full text-metric coverage).
 *   2. Import tasks + seed reference annotations + seed mock LLM generations
 *      for 3 models (no real LLM API calls).
 *   3. Configure + DISPATCH a real evaluation via the Celery worker
 *      (POST /api/evaluations/run) and poll to completion.
 *   4. Assert evaluated results render: aggregated metrics exist via API AND
 *      the /evaluations page surfaces the project.
 *   5. Assert the evaluated models appear on the LLM leaderboard
 *      (/api/leaderboards/llm-models API + the /leaderboards "LLMs" tab UI).
 *
 * The project is created INSIDE the TUM org, because the LLM leaderboard
 * hard-filters to the TUM trust-scope allowlist (see routers/leaderboards.py);
 * a Privat-org project's evaluations would be silently excluded. The
 * leaderboard query also passes min_generation_count=0 & min_samples_evaluated=0
 * to bypass the default ≥50 thresholds for this small seeded dataset.
 *
 * IMPORTANT: Runs only in the ephemeral test environment. Execute via:
 *   make test-e2e
 */
import { test, expect } from '@playwright/test'
import { importTasksInBrowser } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

const PROJECT_NAME = `E2E Dispatch Leaderboard ${Date.now()}`
const MODELS = ['gpt-4-turbo', 'claude-3-sonnet', 'gemini-pro']

// rows="10" triggers LONG_TEXT detection so the text metrics below all apply.
const LABEL_CONFIG = `<View>
  <Text name="question" value="$question"/>
  <TextArea name="answer" toName="question" placeholder="Enter your answer" required="true" rows="10"/>
</View>`

const TEST_TASKS = [
  { data: { question: 'What are the requirements to form a GmbH in Germany?' } },
  { data: { question: 'How does German contract law handle breach of contract?' } },
  { data: { question: 'What is the limitation period for tort claims?' } },
]

const REFERENCE_ANSWERS = [
  'A GmbH requires minimum capital of €25,000, notarized articles, and commercial register entry.',
  'German contract law allows claims for damages, specific performance, or contract rescission.',
  'The standard limitation period for tort claims is 3 years from knowledge of the claim.',
]

const MODEL_RESPONSES: Record<string, string[]> = {
  'gpt-4-turbo': [
    'To form a GmbH: €25,000 minimum capital, notarized articles, commercial register entry required.',
    'Breach of contract under BGB: damages (§280), specific performance, or rescission (§323) available.',
    'Tort limitation: 3 years from year-end when claim arose and claimant had knowledge (§195, §199).',
  ],
  'claude-3-sonnet': [
    'GmbH formation requires: €25k capital, notarized founding docs, commercial register, German address.',
    'Contract breach under BGB: specific performance, damage compensation (§§280ff), termination rights.',
    'Standard tort limitation: 3 years starting from year-end when claim and knowledge arose.',
  ],
  'gemini-pro': [
    'GmbH needs: €25k capital, notarized articles, commercial register. Managing director required.',
    'Contract breach in BGB: Claims for damages, specific performance, or rescission available.',
    'Tort claims: 3-year limitation from end of year when claim arose and claimant knew.',
  ],
}

// Lightweight text metrics for LONG_TEXT — fast, deterministic, no API keys.
const EVAL_METRICS = ['bleu', 'rouge', 'meteor', 'chrf']

// State shared between serial steps.
let projectId: string | null = null
let tumOrgId: string | null = null
let taskIds: string[] = []

test.describe('Evaluation Dispatch → Leaderboard @extended', () => {
  test.describe.configure({ mode: 'serial' })

  test.beforeEach(async ({ page }) => {
    const helpers = new TestHelpers(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test('Step 1: Create QA project in TUM org', async ({ page }) => {
    test.setTimeout(60000)

    // Resolve the TUM org id so the project lands in the LLM leaderboard trust scope.
    tumOrgId = await page.evaluate(async () => {
      const response = await fetch('/api/organizations', { credentials: 'include' })
      if (!response.ok) return null
      const data = await response.json()
      const orgs = data.items || data.organizations || data || []
      const tum = orgs.find(
        (o: { name?: string; slug?: string }) =>
          o.name === 'TUM' || o.slug === 'tum'
      )
      return tum?.id || null
    })
    console.log(`[Step 1] TUM org id: ${tumOrgId}`)

    const createResult = await page.evaluate(
      async ({ name, labelConfig, orgId }) => {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        }
        if (orgId) headers['X-Organization-Context'] = orgId
        const response = await fetch('/api/projects', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({
            title: name,
            description: 'E2E dispatch → leaderboard journey',
            label_config: labelConfig,
          }),
        })
        if (!response.ok) {
          return { success: false, error: await response.text(), status: response.status }
        }
        const data = await response.json()
        return { success: true, projectId: data.id }
      },
      { name: PROJECT_NAME, labelConfig: LABEL_CONFIG, orgId: tumOrgId }
    )

    console.log(`[Step 1] Create project: ${JSON.stringify(createResult)}`)
    expect(createResult.success).toBeTruthy()
    projectId = createResult.projectId!
    expect(projectId).toBeTruthy()
  })

  test('Step 2: Import tasks + seed annotations + generations', async ({ page }) => {
    test.setTimeout(120000)
    test.skip(!projectId, 'Project not created in Step 1')

    // 2a. Import tasks (async object-storage flow).
    const importResult = await page.evaluate(importTasksInBrowser, {
      projectId: projectId!,
      tasks: TEST_TASKS,
    })
    console.log(`[Step 2] Import tasks: ${JSON.stringify(importResult)}`)
    expect(importResult.success).toBeTruthy()

    taskIds = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/projects/${pid}/tasks`, { credentials: 'include' })
      if (!response.ok) return []
      const data = await response.json()
      return (data.items || data.tasks || data || []).map((t: { id: string }) => t.id)
    }, projectId)
    expect(taskIds.length).toBe(TEST_TASKS.length)

    // 2b. Seed reference annotations (one per task — the evaluation ground truth).
    const annotations = taskIds.map((taskId, i) => ({
      task_id: taskId,
      annotator_username: 'admin',
      result: [
        {
          from_name: 'answer',
          to_name: 'question',
          type: 'textarea',
          value: { text: [REFERENCE_ANSWERS[i]] },
        },
      ],
    }))
    const annResult = await page.evaluate(
      async ({ pid, anns }) => {
        const response = await fetch('/api/test/seed/annotations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ project_id: pid, annotations: anns }),
        })
        if (!response.ok) return { success: false, error: await response.text() }
        return response.json()
      },
      { pid: projectId, anns: annotations }
    )
    console.log(`[Step 2] Seed annotations: ${JSON.stringify(annResult)}`)
    expect(annResult.created_count || 0).toBe(taskIds.length)

    // 2c. Seed mock LLM generations: 3 models × 3 tasks = 9 generations.
    const generations: Array<{ task_id: string; model_id: string; output: string }> = []
    for (const model of MODELS) {
      const responses = MODEL_RESPONSES[model]
      for (let i = 0; i < taskIds.length && i < responses.length; i++) {
        generations.push({ task_id: taskIds[i], model_id: model, output: responses[i] })
      }
    }
    const genResult = await page.evaluate(
      async ({ pid, gens }) => {
        const response = await fetch('/api/test/seed/generations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ project_id: pid, generations: gens }),
        })
        if (!response.ok) return { success: false, error: await response.text() }
        return response.json()
      },
      { pid: projectId, gens: generations }
    )
    console.log(`[Step 2] Seed generations: ${JSON.stringify(genResult)}`)
    expect(genResult.success).toBeTruthy()
    expect((genResult.ids || []).length).toBe(MODELS.length * taskIds.length)
  })

  test('Step 3: Dispatch real evaluation and poll to completion', async ({ page }) => {
    test.setTimeout(240000) // real evaluation via Celery worker
    test.skip(!projectId, 'Project not created in Step 1')

    // Build per-metric eval configs mapping the single answer field.
    const evaluationConfigs = EVAL_METRICS.map((metric) => ({
      id: `e2e-${metric}`,
      metric,
      display_name: metric,
      prediction_fields: ['answer'],
      reference_fields: ['answer'],
      enabled: true,
    }))

    const runResult = await page.evaluate(
      async ({ pid, evalCfgs }) => {
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
      },
      { pid: projectId, evalCfgs: evaluationConfigs }
    )
    console.log(`[Step 3] Dispatch evaluation: ${JSON.stringify(runResult)}`)
    expect(runResult.success).toBeTruthy()
    expect(runResult.evaluation_id).toBeTruthy()

    // Poll status every 3s up to ~180s.
    const pollResult = await page.evaluate(async (evalId: string) => {
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 3000))
        try {
          const response = await fetch(`/api/evaluations/evaluation/status/${evalId}`, {
            credentials: 'include',
          })
          if (!response.ok) continue
          const data = await response.json()
          if (data.status === 'completed') return { success: true, status: data.status, attempts: i + 1 }
          if (data.status === 'failed') {
            return { success: false, status: 'failed', error: data.message || 'failed', attempts: i + 1 }
          }
        } catch {
          /* keep polling */
        }
      }
      return { success: false, status: 'timeout', attempts: 60 }
    }, runResult.evaluation_id)

    console.log(`[Step 3] Poll result: ${JSON.stringify(pollResult)}`)
    expect(pollResult.success).toBeTruthy()
    expect(pollResult.status).toBe('completed')
  })

  test('Step 4: Evaluated results render (API + page)', async ({ page }) => {
    test.setTimeout(60000)
    test.skip(!projectId, 'Project not created in Step 1')

    // 4a. Aggregated per-task-model results exist via API.
    const byTaskModel = await page.evaluate(async (pid) => {
      const response = await fetch(
        `/api/evaluations/projects/${pid}/results/by-task-model`,
        { credentials: 'include' }
      )
      if (!response.ok) return { ok: false, status: response.status }
      const data = await response.json()
      return {
        ok: true,
        taskCount: data.tasks?.length || 0,
        modelCount: data.models?.length || 0,
        models: data.models || [],
      }
    }, projectId)

    console.log(`[Step 4] by-task-model: ${JSON.stringify(byTaskModel)}`)
    expect(byTaskModel.ok).toBe(true)
    expect(byTaskModel.taskCount).toBeGreaterThanOrEqual(TEST_TASKS.length)
    expect(byTaskModel.modelCount).toBeGreaterThanOrEqual(MODELS.length)

    // 4b. Evaluation results aggregate to completed with real metric values.
    const projectResults = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/evaluations/run/results/project/${pid}`, {
        credentials: 'include',
      })
      if (!response.ok) return { ok: false, status: response.status }
      const data = await response.json()
      const evaluations = data.evaluations || []
      const latest = evaluations[0]
      return {
        ok: true,
        evaluationCount: evaluations.length,
        latestStatus: latest?.status || null,
        samplesEvaluated: latest?.samples_evaluated || 0,
      }
    }, projectId)

    console.log(`[Step 4] project results: ${JSON.stringify(projectResults)}`)
    expect(projectResults.ok).toBe(true)
    expect(projectResults.evaluationCount).toBeGreaterThan(0)
    expect(projectResults.latestStatus).toBe('completed')
    expect(projectResults.samplesEvaluated).toBeGreaterThan(0)

    // 4c. Evaluations page surfaces the project (rendered result, not just a load).
    await page.goto(`${BASE_URL}/evaluations?project=${projectId}`)
    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasContent =
        bodyText?.includes('Statist') ||
        bodyText?.includes('Evaluation') ||
        bodyText?.includes('Bewertung') ||
        bodyText?.includes('Evaluierung')
      expect(hasContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('Step 5: Evaluated models appear on the LLM leaderboard', async ({ page }) => {
    test.setTimeout(60000)
    test.skip(!projectId, 'Project not created in Step 1')

    // 5a. API: the seeded models are present in the leaderboard for this project.
    // min thresholds set to 0 so the small seeded dataset isn't filtered out.
    const lbResult = await page.evaluate(
      async ({ pid, orgId }) => {
        const params = new URLSearchParams({
          project_ids: pid,
          min_generation_count: '0',
          min_samples_evaluated: '0',
        })
        const headers: Record<string, string> = {}
        if (orgId) headers['X-Organization-Context'] = orgId
        const response = await fetch(`/api/leaderboards/llm-models?${params.toString()}`, {
          credentials: 'include',
          headers,
        })
        if (!response.ok) return { ok: false, status: response.status, error: await response.text() }
        const data = await response.json()
        const board = data.leaderboard || []
        return {
          ok: true,
          modelIds: board.map((e: { model_id: string }) => e.model_id),
          totalModels: data.total_models ?? board.length,
        }
      },
      { pid: projectId, orgId: tumOrgId }
    )

    console.log(`[Step 5] LLM leaderboard models: ${JSON.stringify(lbResult)}`)
    expect(lbResult.ok).toBe(true)
    // At least one of the evaluated models must rank on the board for this project.
    const foundModels = MODELS.filter((m) => (lbResult.modelIds || []).includes(m))
    console.log(`[Step 5] Seeded models on board: ${foundModels.join(', ')}`)
    expect(foundModels.length).toBeGreaterThan(0)

    // 5b. UI: the /leaderboards page renders, and the LLMs tab shows model content.
    await page.goto(`${BASE_URL}/leaderboards`)
    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    const llmTab = page
      .locator('button')
      .filter({ hasText: /LLMs|LLM/i })
      .first()
    await expect(llmTab).toBeVisible({ timeout: 10000 })
    await llmTab.click()

    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasLLMContent =
        bodyText?.includes('Modell') ||
        bodyText?.includes('Model') ||
        bodyText?.includes('Score') ||
        bodyText?.includes('Bewertung') ||
        bodyText?.includes('LLM')
      expect(hasLLMContent).toBe(true)
    }).toPass({ timeout: 10000 })

    // No error alerts on the leaderboard.
    const errorAlert = page
      .locator('[role="alert"]')
      .filter({ hasText: /error|Error|Fehler/i })
    await expect(errorAlert).not.toBeVisible({ timeout: 5000 })
  })

  test('Step 6: Clean up test project', async ({ page }) => {
    test.skip(!projectId, 'Project not created — nothing to clean up')
    const cleanupResult = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/test/cleanup/${pid}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!response.ok) return { success: false, error: await response.text() }
      return response.json()
    }, projectId)
    console.log(`[Step 6] Cleanup: ${JSON.stringify(cleanupResult)}`)

    projectId = null
    taskIds = []
  })
})
