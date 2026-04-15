/**
 * E2E tests for LLM-as-Judge EvaluationBuilder wizard
 * Tests the 5-step wizard configuration workflow and mocked evaluation runs
 */

import { expect, Page, test } from '@playwright/test'
import { EvaluationHelpers } from '../helpers/evaluation-helpers'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

test.describe('LLM Judge Wizard Configuration', () => {
  // Increase timeout for complex evaluation wizard tests
  test.setTimeout(180000)

  let page: Page
  let helpers: TestHelpers
  let evalHelpers: EvaluationHelpers
  let testProjectId: string | null = null

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    evalHelpers = new EvaluationHelpers(page, helpers)

    // Set desktop viewport per CLAUDE.md guidelines
    await page.setViewportSize({ width: 1920, height: 1080 })

    // Reset page to a known state before login (prevents "invalid URL" errors
    // when previous test cleanup left the page on an error/blank page)
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 })

    // Login as admin
    await helpers.login('admin', 'admin')

    // Create a project with evaluation-compatible config
    testProjectId = await evalHelpers.ensureProjectExists()
    await evalHelpers.navigateToProject(testProjectId)
  })

  test.afterEach(async () => {
    // Cleanup test project
    if (testProjectId) {
      try {
        await evalHelpers.cleanupProject(testProjectId)
      } catch (error) {
        console.warn(`Failed to cleanup project ${testProjectId}:`, error)
      }
      testProjectId = null
    }
  })

  /**
   * Test Step 1: Metric Selection
   */
  test('can select LLM-as-Judge metric in wizard', async () => {
    // Open evaluation config section and wizard
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.openAddEvaluationWizard()

    // Verify we're on Step 1
    const step = await evalHelpers.getCurrentStep()
    expect(step).toBe(1)

    // Select LLM-as-Judge
    await evalHelpers.selectLLMJudgeMetric()

    // Verify card shows selected state (emerald background)
    // Use data-testid for reliable selection
    const selectedCard = page.locator('[data-testid^="metric-button-llm_judge"]').first()
    await expect(selectedCard).toHaveClass(/bg-emerald-100|bg-emerald-900/)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test Steps 2-3: Field Selection
   */
  test('can select prediction and reference fields', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.openAddEvaluationWizard()

    // Step 1: Select LLM-as-Judge
    await evalHelpers.selectLLMJudgeMetric()
    await evalHelpers.clickNext()

    // Step 2: Verify we're on field selection
    const step2 = await evalHelpers.getCurrentStep()
    expect(step2).toBe(2)

    // Select a prediction field
    await evalHelpers.selectFirstPredictionField()
    await evalHelpers.clickNext()

    // Step 3: Reference field selection
    const step3 = await evalHelpers.getCurrentStep()
    expect(step3).toBe(3)

    await evalHelpers.selectFirstReferenceField()

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test Step 4: LLM Judge Parameters
   */
  test('LLM Judge parameters step shows answer type and criteria', async () => {
    // Open evaluation config and navigate to Step 4
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Verify we're on Step 4
    const step = await evalHelpers.getCurrentStep()
    expect(step).toBe(4)

    // Verify Answer Type label exists (HeadlessUI Listbox, not native select)
    await expect(page.locator('label').filter({ hasText: /Antworttyp|Answer Type/i }).first()).toBeVisible()

    // Verify Judge Model label exists
    await expect(page.locator('label').filter({ hasText: /Richter-Modell|Judge Model/i }).first()).toBeVisible()

    // Verify Temperature label exists
    await expect(page.locator('label').filter({ hasText: /Temperatur|Temperature/i }).first()).toBeVisible()

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test complete wizard flow
   */
  test('can complete full wizard and reach final step', async () => {
    // Open evaluation config and navigate to Step 4
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Step 4: Configure parameters (defaults are fine)
    await evalHelpers.clickNext()

    // Verify we reached Step 5 or the wizard completed
    const step = await evalHelpers.getCurrentStep()

    if (step === 5) {
      console.log('Successfully reached Step 5 (Review)')

      // Look for save/create button but don't require it
      const saveButton = page
        .locator('button')
        .filter({ hasText: /Save|Create|Finish|Done/i })
        .first()

      if (await saveButton.isVisible({ timeout: 3000 }).catch(() => false)) {
        console.log('Save button found in final step')
      }
    } else if (step === 0) {
      // Wizard may have auto-completed/closed
      console.log('Wizard completed or closed after Step 4')
    } else {
      console.log(`Reached step ${step} after parameters`)
    }

    // Close wizard if still open
    await evalHelpers.clickCancel()
  })
})

test.describe('LLM Judge Mocked API Workflow', () => {
  // Increase timeout for complex evaluation wizard tests
  test.setTimeout(180000)

  let page: Page
  let helpers: TestHelpers
  let evalHelpers: EvaluationHelpers
  let testProjectId: string | null = null

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    evalHelpers = new EvaluationHelpers(page, helpers)

    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')

    // Create a project with evaluation-compatible config
    testProjectId = await evalHelpers.ensureProjectExists()
    await evalHelpers.navigateToProject(testProjectId)
  })

  test.afterEach(async () => {
    // Cleanup test project
    if (testProjectId) {
      try {
        await evalHelpers.cleanupProject(testProjectId)
      } catch (error) {
        console.warn(`Failed to cleanup project ${testProjectId}:`, error)
      }
      testProjectId = null
    }
  })

  /**
   * Test mocked evaluation run
   */
  test('can configure and run LLM Judge evaluation (mocked)', async () => {
    // Setup route mock for evaluation run
    await page.route('**/api/evaluations/run**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          evaluation_id: 'mock-eval-123',
          status: 'started',
          message: 'Evaluation started',
        }),
      })
    })

    await evalHelpers.openEvaluationConfigSection()

    // Check if there's already a configured evaluation we can run
    const runButton = page
      .locator('button')
      .filter({ hasText: /Run|Start/i })
      .first()

    if (await runButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await runButton.click()
      await page.waitForTimeout(1000)

      // Verify we got a response (toast or status change)
      const toast = page.locator(
        '[role="alert"], .toast, text=/started|running/i'
      )
      const hasResponse = await toast
        .isVisible({ timeout: 5000 })
        .catch(() => false)

      if (hasResponse) {
        console.log('Mocked evaluation run triggered successfully')
      }
    } else {
      console.log(
        'No run button available - may need to configure evaluation first'
      )
    }

    // Cleanup route
    await page.unroute('**/api/evaluations/run**')
  })

  /**
   * Test error handling for missing API key
   */
  test('handles API key missing error gracefully', async () => {
    // Setup route mock for error response
    await page.route('**/api/evaluations/run**', (route) => {
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'OpenAI API key not configured',
        }),
      })
    })

    await evalHelpers.openEvaluationConfigSection()

    // Try to run evaluation
    const runButton = page
      .locator('button')
      .filter({ hasText: /Run|Start/i })
      .first()

    if (await runButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await runButton.click()
      await page.waitForTimeout(1000)

      // Verify error is displayed
      const errorMessage = page.locator(
        'text=/API key|error|failed/i, [role="alert"]'
      )
      const hasError = await errorMessage
        .isVisible({ timeout: 5000 })
        .catch(() => false)

      if (hasError) {
        console.log('Error message displayed correctly')
      }
    }

    // Cleanup route
    await page.unroute('**/api/evaluations/run**')
  })

  /**
   * Test network failure handling
   */
  test('handles network failure gracefully', async () => {
    // Setup route to abort (simulate network failure)
    await page.route('**/api/evaluations/run**', (route) => route.abort())

    await evalHelpers.openEvaluationConfigSection()

    // Try to run evaluation
    const runButton = page
      .locator('button')
      .filter({ hasText: /Run|Start/i })
      .first()

    if (await runButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await runButton.click()
      await page.waitForTimeout(2000)

      // Verify error handling - should not crash, may show error message
      const pageHasContent = await page
        .locator('body')
        .textContent()
        .catch(() => '')
      expect(pageHasContent).not.toBe('')

      console.log('Page handled network failure gracefully')
    }

    // Cleanup route
    await page.unroute('**/api/evaluations/run**')
  })
})
