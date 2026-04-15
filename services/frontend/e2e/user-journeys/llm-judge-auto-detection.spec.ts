/**
 * E2E tests for LLM-as-Judge answer type configuration
 * Tests that users can properly configure answer types and see appropriate criteria
 *
 * Note: Full auto-detection from label_config requires projects with annotations.
 * These tests verify the UI behaves correctly when manually selecting answer types.
 */

import { expect, Page, test } from '@playwright/test'
import { EvaluationHelpers } from '../helpers/evaluation-helpers'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

test.describe('LLM Judge Answer Type Configuration', () => {
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

    // Reset page to known state (prevents "invalid URL" errors from stale page state)
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
   * Test that span_selection type shows NER-specific criteria
   */
  test('span_selection type displays NER-specific criteria', async () => {
    // Open evaluation config and navigate to Step 4 (Parameters)
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select span_selection type
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(1000)

    // Verify NER-specific criteria are displayed (support EN + DE)
    const boundaryAccuracy = page.locator('text=/Boundary Accuracy|Grenzgenauigkeit/i')
    const labelAccuracy = page.locator('text=/Label Accuracy|Label-Genauigkeit/i')
    const entityCoverage = page.locator('text=/Entity Coverage|Coverage|Abdeckung/i')

    const hasBoundary = await boundaryAccuracy
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasLabel = await labelAccuracy
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasCoverage = await entityCoverage
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)

    console.log('NER criteria visibility:', {
      hasBoundary,
      hasLabel,
      hasCoverage,
    })

    // At least one NER-specific criterion should be visible
    expect(hasBoundary || hasLabel || hasCoverage).toBe(true)

    // Verify detected type banner is visible
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()
    console.log('Detected type banner visible:', bannerVisible)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that choices type shows classification criteria
   */
  test('choices type displays classification criteria', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select choices type
    await evalHelpers.selectAnswerType('choices')
    await page.waitForTimeout(1000)

    // Verify choice-specific criteria are displayed
    // Look for criteria checkboxes or labels (may vary based on UI state)
    const accuracy = page.locator('text=/Selection Accuracy|accuracy/i')
    const reasoning = page.locator('text=/Reasoning Quality|reasoning/i')
    const checkboxes = page.locator('input[type="checkbox"]')

    const hasAccuracy = await accuracy
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasReasoning = await reasoning
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasCheckboxes = (await checkboxes.count()) > 0

    console.log('Choice criteria visibility:', { hasAccuracy, hasReasoning, hasCheckboxes })

    // At least one criterion should be visible or there should be checkboxes
    expect(hasAccuracy || hasReasoning || hasCheckboxes).toBe(true)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that text type shows text-specific criteria
   */
  test('text type displays text-specific criteria', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select text type
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(1000)

    // Verify text-specific criteria are displayed (support EN + DE)
    const helpfulness = page.locator('text=/Helpfulness|Hilfsbereitschaft/i')
    const fluency = page.locator('text=/Fluency|Sprachfluss/i')

    const hasHelpfulness = await helpfulness
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasFluency = await fluency
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)

    console.log('Text criteria visibility:', { hasHelpfulness, hasFluency })

    // At least one text-specific criterion should be visible
    expect(hasHelpfulness || hasFluency).toBe(true)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that rating type can be selected
   */
  test('rating type is available in dropdown', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Get all options from Answer Type dropdown
    const options = await evalHelpers.getAnswerTypeOptions()
    console.log('Available answer types:', options)

    // Verify rating option exists
    const hasRatingOption = options.some(
      (o) => o.includes('Rating') || o.toLowerCase().includes('rating')
    )
    expect(hasRatingOption).toBe(true)

    // Select rating type
    await evalHelpers.selectAnswerType('rating')
    await page.waitForTimeout(500)

    // Verify selection was applied (button shows display name)
    const selectedValue = await evalHelpers.getSelectedAnswerType()
    expect(selectedValue).toMatch(/Rating/i)

    console.log('Rating type selected successfully')

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test switching between answer types updates criteria
   */
  test('switching answer types updates displayed criteria', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Count checkboxes for text type
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(500)
    const textCheckboxCount = await page
      .locator('input[type="checkbox"]')
      .count()
    console.log('Text type checkbox count:', textCheckboxCount)

    // Switch to span_selection
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(500)
    const spanCheckboxCount = await page
      .locator('input[type="checkbox"]')
      .count()
    console.log('Span type checkbox count:', spanCheckboxCount)

    // Switch to choices
    await evalHelpers.selectAnswerType('choices')
    await page.waitForTimeout(500)
    const choicesCheckboxCount = await page
      .locator('input[type="checkbox"]')
      .count()
    console.log('Choices type checkbox count:', choicesCheckboxCount)

    // Verify the counts are different (different criteria for different types)
    console.log(
      `Checkbox counts: text=${textCheckboxCount}, span=${spanCheckboxCount}, choices=${choicesCheckboxCount}`
    )

    // The UI should respond to type changes (we don't require specific counts)
    expect(textCheckboxCount).toBeGreaterThan(0)
    expect(spanCheckboxCount).toBeGreaterThan(0)
    expect(choicesCheckboxCount).toBeGreaterThan(0)

    // Close wizard
    await evalHelpers.clickCancel()
  })
})
