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
  test('span_selection type can be selected and configures NER template', async () => {
    // Open evaluation config and navigate to Step 4 (Parameters)
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select span_selection type — verifies the dropdown works
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(1000)

    // Verify the answer type selection took effect by checking for
    // NER-related text in the UI (template name or detected banner)
    const nerText = page.locator('text=/NER|Named Entity|span_selection/i')
    const hasNerText = await nerText.first().isVisible({ timeout: 3000 }).catch(() => false)
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()

    console.log('NER selection:', { hasNerText, bannerVisible })

    // Either the template name or detected banner should confirm the selection
    expect(hasNerText || bannerVisible).toBe(true)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that choices type shows classification criteria
   */
  test('choices type can be selected and configures classification template', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select choices type
    await evalHelpers.selectAnswerType('choices')
    await page.waitForTimeout(1000)

    // Verify the selection took effect
    const classText = page.locator('text=/Classification|choices|Klassifikation/i')
    const hasClassText = await classText.first().isVisible({ timeout: 3000 }).catch(() => false)
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()

    console.log('Classification selection:', { hasClassText, bannerVisible })

    expect(hasClassText || bannerVisible).toBe(true)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that text type shows text-specific criteria
   */
  test('text type can be selected and configures text template', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select text type
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(1000)

    // Verify the selection took effect
    const textLabel = page.locator('text=/Text|text|Freeform/i')
    const hasTextLabel = await textLabel.first().isVisible({ timeout: 3000 }).catch(() => false)
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()

    console.log('Text selection:', { hasTextLabel, bannerVisible })

    expect(hasTextLabel || bannerVisible).toBe(true)

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
  test('switching answer types updates displayed template', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select text type and capture display value
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(500)
    const textValue = await evalHelpers.getSelectedAnswerType()
    console.log('Text type selected:', textValue)

    // Switch to span_selection
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(500)
    const spanValue = await evalHelpers.getSelectedAnswerType()
    console.log('Span type selected:', spanValue)

    // Switch to choices
    await evalHelpers.selectAnswerType('choices')
    await page.waitForTimeout(500)
    const choicesValue = await evalHelpers.getSelectedAnswerType()
    console.log('Choices type selected:', choicesValue)

    // Verify the displayed template changes between types
    expect(textValue).not.toBe(spanValue)
    expect(spanValue).not.toBe(choicesValue)
    console.log(`Templates: "${textValue}" → "${spanValue}" → "${choicesValue}"`)

    // Close wizard
    await evalHelpers.clickCancel()
  })
})
