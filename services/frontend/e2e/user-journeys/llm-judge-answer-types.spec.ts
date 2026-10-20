/**
 * E2E tests for LLM-as-Judge answer type detection and criteria selection
 * Tests the new answer-type-aware feature in the EvaluationBuilder wizard
 */

import { expect, Page, test } from '@playwright/test'
import { EvaluationHelpers } from '../helpers/evaluation-helpers'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

// Expected answer type option values (keys of LLM_JUDGE_TEMPLATES). The
// displayed labels are localized, so tests assert on the values.
const EXPECTED_ANSWER_TYPE_VALUES = [
  'text',
  'short_text',
  'long_text',
  'choices',
  'single_choice',
  'binary',
  'multiple_choice',
  'span_selection',
  'rating',
  'numeric',
]

// Expected criteria for each type (must match getDimensionDisplayName output)
const EXPECTED_CRITERIA = {
  text: ['Helpfulness', 'Correctness', 'Fluency', 'Coherence', 'Relevance'],
  span_selection: ['Boundary Accuracy', 'Label Accuracy', 'Entity Coverage'],
  choices: ['Selection Accuracy', 'Reasoning Quality'],
}

test.describe('LLM Judge Answer Type Detection', () => {
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
   * Test that all 10 answer type options are available
   */
  test('answer type dropdown has all 10 options', async () => {
    // Open evaluation config and navigate to Step 4 (Parameters)
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Get all options from Answer Type dropdown
    const options = await evalHelpers.getAnswerTypeOptionEntries()
    console.log('Found answer type options:', options)

    // Verify we have at least 10 options (the main types)
    expect(options.length).toBeGreaterThanOrEqual(10)

    // Every template key is offered, and every option has a visible label
    const values = options.map((o) => o.value)
    for (const expected of EXPECTED_ANSWER_TYPE_VALUES) {
      expect(values).toContain(expected)
    }
    for (const option of options) {
      expect(option.label.length).toBeGreaterThan(0)
    }

    console.log(`Verified ${options.length} answer type options`)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that selecting span_selection shows NER-specific criteria
   */
  test('selecting span_selection configures NER template', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(1000)

    // Verify NER template is active (text or banner confirms selection)
    const nerText = page.locator('text=/NER|Named Entity|span_selection/i')
    const hasNerText = await nerText
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()

    console.log('NER selection:', { hasNerText, bannerVisible })
    expect(hasNerText || bannerVisible).toBe(true)

    await evalHelpers.clickCancel()
  })

  /**
   * Test that selecting text shows text-specific criteria
   */
  test('selecting text configures text template', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(1000)

    // Verify text template is active
    const textLabel = page.locator('text=/Text|Freeform|Freitext/i')
    const hasTextLabel = await textLabel
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()

    console.log('Text selection:', { hasTextLabel, bannerVisible })
    expect(hasTextLabel || bannerVisible).toBe(true)

    await evalHelpers.clickCancel()
  })

  /**
   * Test that selecting choices shows classification criteria
   */
  test('selecting choices configures classification template', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    await evalHelpers.selectAnswerType('choices')
    await page.waitForTimeout(1000)

    // Verify classification template is active
    const classText = page.locator(
      'text=/Classification|choices|Klassifikation/i',
    )
    const hasClassText = await classText
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()

    console.log('Classification selection:', { hasClassText, bannerVisible })
    expect(hasClassText || bannerVisible).toBe(true)

    await evalHelpers.clickCancel()
  })

  /**
   * Test that user can override detected answer type
   */
  test('can override detected answer type', async () => {
    // Open evaluation config and navigate to Step 4
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Get current answer type
    const initialValue = await evalHelpers.getSelectedAnswerTypeValue()
    console.log('Initial answer type:', initialValue)

    // Change to a different type
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(500)

    const newValue = await evalHelpers.getSelectedAnswerTypeValue()
    console.log('New answer type:', newValue)

    // Verify it changed (the trigger carries the value key as data-value)
    expect(newValue).toBe('span_selection')

    // Change again to verify flexibility
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(500)

    const finalValue = await evalHelpers.getSelectedAnswerTypeValue()
    expect(finalValue).toBe('text')

    console.log('Successfully overrode answer type multiple times')

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test criteria checkboxes update when type changes
   */
  test('switching answer types updates displayed template', async () => {
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select text type first
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(500)
    const textValue = await evalHelpers.getSelectedAnswerType()
    console.log('Text type selected:', textValue)
    expect(await evalHelpers.getSelectedAnswerTypeValue()).toBe('text')

    // Change to span_selection
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(500)
    const spanValue = await evalHelpers.getSelectedAnswerType()
    console.log('Span type selected:', spanValue)
    expect(await evalHelpers.getSelectedAnswerTypeValue()).toBe(
      'span_selection',
    )

    // Verify the displayed label actually changed
    expect(textValue).not.toBe(spanValue)
    console.log(`Template updated: "${textValue}" → "${spanValue}"`)

    await evalHelpers.clickCancel()
  })
})
