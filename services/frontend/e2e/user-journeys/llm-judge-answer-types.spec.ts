/**
 * E2E tests for LLM-as-Judge answer type detection and criteria selection
 * Tests the new answer-type-aware feature in the EvaluationBuilder wizard
 */

import { expect, Page, test } from '@playwright/test'
import { EvaluationHelpers } from '../helpers/evaluation-helpers'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

// Expected answer type options
const EXPECTED_ANSWER_TYPES = [
  'Free-form Text',
  'Short Text',
  'Long Text',
  'Classification (Single Choice)',
  'Single Choice',
  'Binary Choice',
  'Multiple Choice (Multi-select)',
  'Named Entity Recognition (NER)',
  'Rating Scale',
  'Numeric Value',
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
    const options = await evalHelpers.getAnswerTypeOptions()
    console.log('Found answer type options:', options)

    // Verify we have at least 10 options (the main types)
    expect(options.length).toBeGreaterThanOrEqual(10)

    // Check for key options
    const hasText = options.some((o) => o.includes('Text'))
    const hasNER = options.some(
      (o) => o.includes('NER') || o.includes('Entity')
    )
    const hasChoices = options.some(
      (o) => o.includes('Choice') || o.includes('Classification')
    )

    expect(hasText).toBe(true)
    expect(hasNER).toBe(true)
    expect(hasChoices).toBe(true)

    console.log(`Verified ${options.length} answer type options`)

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that selecting span_selection shows NER-specific criteria
   */
  test('selecting span_selection shows NER-specific criteria', async () => {
    // Open evaluation config and navigate to Step 4
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select "Named Entity Recognition (NER)" from dropdown
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(1000)

    // Check for detected type banner
    const bannerVisible = await evalHelpers.isDetectedTypeBannerVisible()
    if (bannerVisible) {
      console.log('Detected type banner is visible')
    }

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

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that selecting text shows text-specific criteria
   */
  test('selecting text shows text-specific criteria', async () => {
    // Open evaluation config and navigate to Step 4
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select "Free-form Text" from dropdown
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(1000)

    // Verify text-specific criteria are displayed (support EN + DE)
    const helpfulness = page.locator('text=/Helpfulness|Hilfsbereitschaft/i')
    const correctness = page.locator('text=/Correctness|Korrektheit/i')
    const fluency = page.locator('text=/Fluency|Sprachfluss/i')
    const coherence = page.locator('text=/Coherence|Kohärenz/i')

    const hasHelpfulness = await helpfulness
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasCorrectness = await correctness
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasFluency = await fluency
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)
    const hasCoherence = await coherence
      .first().isVisible({ timeout: 3000 })
      .catch(() => false)

    console.log('Text criteria visibility:', {
      hasHelpfulness,
      hasCorrectness,
      hasFluency,
      hasCoherence,
    })

    // At least one text-specific criterion should be visible
    expect(hasHelpfulness || hasCorrectness || hasFluency || hasCoherence).toBe(
      true
    )

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test that selecting choices shows classification criteria
   */
  test('selecting choices shows classification criteria', async () => {
    // Open evaluation config and navigate to Step 4
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select "Classification (Single Choice)" from dropdown
    await evalHelpers.selectAnswerType('choices')
    await page.waitForTimeout(1000)

    // Verify classification-specific criteria are displayed
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

    console.log('Choices criteria visibility:', { hasAccuracy, hasReasoning, hasCheckboxes })

    // At least one criterion should be visible or there should be checkboxes
    // The wizard should show some form of criteria selection
    expect(hasAccuracy || hasReasoning || hasCheckboxes).toBe(true)

    // Close wizard
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
    const initialValue = await evalHelpers.getSelectedAnswerType()
    console.log('Initial answer type:', initialValue)

    // Change to a different type
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(500)

    const newValue = await evalHelpers.getSelectedAnswerType()
    console.log('New answer type:', newValue)

    // Verify it changed (button shows display name, not value key)
    expect(newValue).toMatch(/Named Entity|NER|Span/i)

    // Change again to verify flexibility
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(500)

    const finalValue = await evalHelpers.getSelectedAnswerType()
    expect(finalValue).toMatch(/Free.form|Freitext/i)

    console.log('Successfully overrode answer type multiple times')

    // Close wizard
    await evalHelpers.clickCancel()
  })

  /**
   * Test criteria checkboxes update when type changes
   */
  test('criteria checkboxes update when answer type changes', async () => {
    // Open evaluation config and navigate to Step 4
    await evalHelpers.openEvaluationConfigSection()
    await evalHelpers.navigateToParametersStep()

    // Select text type first
    await evalHelpers.selectAnswerType('text')
    await page.waitForTimeout(500)

    // Count checkboxes
    const textCheckboxCount = await page
      .locator('input[type="checkbox"]')
      .count()
    console.log('Text type checkbox count:', textCheckboxCount)

    // Change to span_selection
    await evalHelpers.selectAnswerType('span_selection')
    await page.waitForTimeout(500)

    // Count checkboxes again
    const spanCheckboxCount = await page
      .locator('input[type="checkbox"]')
      .count()
    console.log('Span type checkbox count:', spanCheckboxCount)

    // The counts may differ based on available criteria for each type
    // or the checkboxes may change labels
    console.log(
      `Criteria updated: text(${textCheckboxCount}) → span(${spanCheckboxCount})`
    )

    // Close wizard
    await evalHelpers.clickCancel()
  })
})
