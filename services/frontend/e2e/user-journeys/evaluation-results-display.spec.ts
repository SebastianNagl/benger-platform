/**
 * Evaluation Results Display E2E Tests
 *
 * Self-contained: creates its own project with tasks, generations,
 * and evaluation results via the test seeding API.
 *
 * Tests the evaluation results display functionality including
 * API data availability and UI rendering.
 */
import { test, expect, Page } from '@playwright/test'
import { APISeedingHelper, SeededTask } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

const MODELS = ['gpt-4-turbo', 'claude-3-sonnet', 'gemini-pro']
const LABEL_CONFIG =
  '<View><Text name="text" value="$text"/><TextArea name="answer" toName="text"/></View>'

test.describe('Evaluation Results Display', () => {
  let page: Page
  let helpers: TestHelpers
  let seeder: APISeedingHelper
  let projectId: string
  let tasks: SeededTask[]
  let generationIds: string[]

  test.beforeAll(async ({ browser }) => {
    // Use a single browser context for all tests in this describe block
    const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    page = await context.newPage()
    helpers = new TestHelpers(page)
    seeder = new APISeedingHelper(page)

    await helpers.login('admin', 'admin')

    // Create project with QA-style config
    projectId = await seeder.createProject(`Eval Display ${Date.now()}`)
    await seeder.setLabelConfig(projectId, LABEL_CONFIG)

    // Import 5 tasks
    tasks = await seeder.importTasks(projectId, [
      { data: { text: 'What is the capital of Germany?' } },
      { data: { text: 'Explain the concept of federalism.' } },
      { data: { text: 'What are fundamental rights?' } },
      { data: { text: 'Describe the legislative process.' } },
      { data: { text: 'What is judicial review?' } },
    ])

    // Create annotations for each task
    for (const task of tasks) {
      await seeder.createAnnotation(task.id, [
        {
          from_name: 'answer',
          to_name: 'text',
          type: 'textarea',
          value: { text: ['Reference answer for evaluation'] },
        },
      ])
    }

    // Seed generations: 3 models x 5 tasks = 15 generations
    const genData = tasks.flatMap((task) =>
      MODELS.map((model) => ({
        task_id: task.id,
        model_id: model,
        output: `Generated answer from ${model} for task ${task.id}`,
      }))
    )
    generationIds = await seeder.seedGenerations(projectId, genData)

    // Seed evaluation results for all generations
    const evalResults = generationIds.map((genId, i) => ({
      generation_id: genId,
      metric: 'llm_judge_custom',
      score: 0.3 + (i % 5) * 0.15, // Scores from 0.3 to 0.9
    }))
    await seeder.seedEvaluation(projectId, evalResults, 'E2E Display Test')
  })

  test.afterAll(async () => {
    if (projectId) {
      try {
        await seeder.cleanupTestProject(projectId)
      } catch (e) {
        console.log('Cleanup failed:', e)
      }
    }
    await page.context().close()
  })

  test('evaluation data exists in API', async () => {
    const evalResult = await page.evaluate(async (pid) => {
      const response = await fetch(
        `/api/evaluations/projects/${pid}/results/by-task-model`,
        { credentials: 'include' }
      )
      if (!response.ok) return { hasData: false, status: response.status }
      const data = await response.json()
      return {
        hasData:
          (data.tasks?.length || 0) > 0 && (data.models?.length || 0) > 0,
        taskCount: data.tasks?.length || 0,
        modelCount: data.models?.length || 0,
      }
    }, projectId)

    expect(evalResult.hasData).toBe(true)
    expect(evalResult.taskCount).toBeGreaterThan(0)
    expect(evalResult.modelCount).toBeGreaterThan(0)
  })

  test('evaluations page loads with project', async () => {
    await page.goto(`${BASE_URL}/evaluations?project=${projectId}`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Page should show either evaluation data or a valid configuration message
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasContent =
        bodyText?.includes('Statist') || // Statistics/Statistiken
        bodyText?.includes('Evaluation') ||
        bodyText?.includes('Bewertung') ||
        bodyText?.includes('Evaluierung') ||
        bodyText?.includes('configured') ||
        bodyText?.includes('konfiguriert')
      expect(hasContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('by-task-model API returns seeded data', async () => {
    const taskModelResult = await page.evaluate(async (pid) => {
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

    expect(taskModelResult.ok).toBe(true)
    expect(taskModelResult.taskCount).toBeGreaterThanOrEqual(5)
    expect(taskModelResult.modelCount).toBeGreaterThanOrEqual(3)
  })

  test('project selector shows project on evaluations page', async () => {
    await page.goto(`${BASE_URL}/evaluations`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Look for project selector (combobox or button with "select" text)
    const selector = page
      .locator('button, [role="combobox"]')
      .filter({ hasText: /select|auswählen|projekt/i })
      .first()

    await expect(selector).toBeVisible({ timeout: 10000 })
  })

  test('dashboard shows evaluation count', async () => {
    await page.goto(`${BASE_URL}/dashboard`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Dashboard should show evaluations stat (EN or DE)
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasEvals =
        bodyText?.includes('Evaluierung') ||
        bodyText?.includes('Evaluation') ||
        bodyText?.includes('Bewertung')
      expect(hasEvals).toBe(true)
    }).toPass({ timeout: 15000 })
  })
})
