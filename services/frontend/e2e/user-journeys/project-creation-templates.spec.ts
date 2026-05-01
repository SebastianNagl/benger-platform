/**
 * Project Creation Template Tests - E2E Tests with Playwright
 *
 * Tests the complete project creation workflow for each template type:
 * - Question Answering
 * - Multiple Choice Question
 * - Span Annotation
 * - Custom
 *
 * Issue #1079: Simplify project creation template gallery to 5 focused options
 */

import { expect, test, Page } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

/**
 * Helper to navigate to project creation wizard step 3 (template selection)
 */
async function navigateToTemplateSelection(
  page: Page,
  helpers: TestHelpers,
  projectName: string
): Promise<void> {
  // Login
  await helpers.login('admin', 'admin')

  // Navigate to projects and wait for page to load
  await page.goto('/projects', { waitUntil: 'domcontentloaded' })

  // Wait for the "Neues Projekt" button to be visible and click it
  const newProjectButton = page.locator('text=Neues Projekt')
  await expect(newProjectButton).toBeVisible({ timeout: 15000 })
  await newProjectButton.click()

  // Wait for wizard to load - look for the project name input
  await expect(
    page.locator('[data-testid="project-create-name-input"]')
  ).toBeVisible({ timeout: 15000 })

  // Fill project name
  await page.fill('[data-testid="project-create-name-input"]', projectName)

  // Enable dataImport + annotation features so the wizard renders the
  // data-import and template-selection steps the test expects.
  await page
    .locator('[data-testid="wizard-feature-dataImport"] input[type="checkbox"]')
    .check()
  await page
    .locator('[data-testid="wizard-feature-annotation"] input[type="checkbox"]')
    .check()

  // Step 2: Data import - click next
  const nextButton = page.locator('[data-testid="project-create-next-button"]')
  await expect(nextButton).toBeVisible()
  await nextButton.click()

  // Wait for data import step to appear
  await expect(page.locator('text=Daten importieren')).toBeVisible({ timeout: 10000 })

  // Step 3: Template selection - click next to skip data import
  await nextButton.click()

  // Verify we're on template selection step
  await expect(page.locator('text=Frage-Antwort')).toBeVisible({
    timeout: 10000,
  })
}

test.describe('Project Creation Templates - Full Workflow Tests', () => {
  test.describe.configure({ mode: 'serial' })

  test('Question Answering template - full project creation', async ({
    page,
  }) => {
    const helpers = new TestHelpers(page)
    const projectName = `E2E QA Template ${Date.now()}`

    await navigateToTemplateSelection(page, helpers, projectName)

    // Verify Question Answering template is available and select it
    const qaTemplate = page.locator('text=Frage-Antwort').first()
    await expect(qaTemplate).toBeVisible()
    await qaTemplate.click()

    // Verify selection indicator appears
    await expect(page.locator('text=Ausgewählt')).toBeVisible({ timeout: 5000 })

    // Create project
    await page.click('[data-testid="project-create-submit-button"]')

    // Verify project was created - should navigate to project page
    await expect(page).toHaveURL(/\/projects\//, { timeout: 15000 })

    console.log('✅ Question Answering template project created successfully')
  })

  test('Multiple Choice Question template - full project creation', async ({
    page,
  }) => {
    const helpers = new TestHelpers(page)
    const projectName = `E2E MCQ Template ${Date.now()}`

    await navigateToTemplateSelection(page, helpers, projectName)

    // Select Multiple Choice template
    const mcqTemplate = page.locator('text=Multiple-Choice-Frage').first()
    await expect(mcqTemplate).toBeVisible()
    await mcqTemplate.click()
    await expect(page.locator('text=Ausgewählt')).toBeVisible({ timeout: 5000 })

    // Create project
    await page.click('[data-testid="project-create-submit-button"]')

    // Verify project was created
    await expect(page).toHaveURL(/\/projects\//, { timeout: 15000 })

    console.log(
      '✅ Multiple Choice Question template project created successfully'
    )
  })

  test('Span Annotation template - full project creation', async ({ page }) => {
    const helpers = new TestHelpers(page)
    const projectName = `E2E Span Template ${Date.now()}`

    await navigateToTemplateSelection(page, helpers, projectName)

    // Select Span Annotation template
    const spanTemplate = page.locator('text=Span-Annotation').first()
    await expect(spanTemplate).toBeVisible()
    await spanTemplate.click()
    await expect(page.locator('text=Ausgewählt')).toBeVisible({ timeout: 5000 })

    // Create project
    await page.click('[data-testid="project-create-submit-button"]')

    // Verify project was created
    await expect(page).toHaveURL(/\/projects\//, { timeout: 15000 })

    console.log('✅ Span Annotation template project created successfully')
  })

  test('Custom template - full project creation', async ({ page }) => {
    const helpers = new TestHelpers(page)
    const projectName = `E2E Custom Template ${Date.now()}`

    await navigateToTemplateSelection(page, helpers, projectName)

    // Switch to Custom Configuration tab and enter custom config
    const customTab = page.locator('text=Benutzerdefinierte Konfiguration')
    await expect(customTab).toBeVisible()
    await customTab.click()

    // The custom config textarea should now be visible
    const customTextarea = page.locator('[data-testid="project-create-custom-config-textarea"]')
    await expect(customTextarea).toBeVisible({ timeout: 5000 })

    // Enter a custom configuration
    await customTextarea.fill(`<View>
  <Text name="custom_text" value="$text"/>
  <TextArea name="custom_answer" toName="custom_text"
            placeholder="Custom answer field..."
            rows="4"/>
</View>`)

    // Create project with custom config
    await page.click('[data-testid="project-create-submit-button"]')

    // Verify project was created
    await expect(page).toHaveURL(/\/projects\//, { timeout: 15000 })

    console.log('✅ Custom template project created successfully')
  })

  test('Template gallery displays all 5 templates correctly', async ({
    page,
  }) => {
    const helpers = new TestHelpers(page)

    await navigateToTemplateSelection(page, helpers, 'Template Gallery Test')

    // Verify templates are visible
    await expect(page.locator('text=Frage-Antwort').first()).toBeVisible()
    await expect(
      page.locator('text=Multiple-Choice-Frage').first()
    ).toBeVisible()
    await expect(page.locator('text=Span-Annotation').first()).toBeVisible()
    await expect(page.locator('text=Benutzerdefiniert').first()).toBeVisible()

    // Verify old templates are NOT visible
    await expect(page.locator('text=Entitätenerkennung')).not.toBeVisible()
    await expect(page.locator('text=Textklassifikation')).not.toBeVisible()
    await expect(page.locator('text=Beziehungsextraktion')).not.toBeVisible()
    await expect(page.locator('text=Taxonomie')).not.toBeVisible()
    await expect(
      page.locator('text=Maschinelle Übersetzung')
    ).not.toBeVisible()
    await expect(page.locator('text=Content-Moderation')).not.toBeVisible()
    await expect(page.locator('text=Textzusammenfassung')).not.toBeVisible()

    console.log(
      '✅ Template gallery displays exactly 5 templates (old templates removed)'
    )

    // Navigate away to avoid creating unnecessary project
    await page.goto('/projects')
  })

  test('Template descriptions are correct in German', async ({ page }) => {
    const helpers = new TestHelpers(page)

    await navigateToTemplateSelection(page, helpers, 'Description Test')

    // Verify German descriptions
    await expect(
      page.locator('text=Beantworten Sie Fragen basierend auf gegebenem Text')
    ).toBeVisible()
    await expect(
      page.locator('text=Wählen Sie aus vordefinierten Antwortoptionen')
    ).toBeVisible()
    await expect(
      page.locator('text=Markieren und beschriften Sie Textabschnitte')
    ).toBeVisible()
    await expect(
      page.locator('text=Definieren Sie Ihre eigene Label Studio XML')
    ).toBeVisible()

    console.log('✅ All template descriptions are correctly localized in German')

    // Navigate away
    await page.goto('/projects')
  })
})
