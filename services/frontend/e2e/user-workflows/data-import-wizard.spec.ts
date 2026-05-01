/**
 * Focused coverage for the project-creation wizard's data-import step.
 *
 * Other specs walk past data-import as setup with `if visible` branches
 * and no assertions, so a regression in the import step itself (line
 * counting, format detection, validation toast, end-to-end submission
 * with imported data) wouldn't fail any other spec. This spec exists
 * to catch that.
 */

import { expect, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'
import {
  clickSubmitFromAnyStep,
  enableWizardFeatures,
} from '../helpers/wizard-helpers'

const TEST_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Data Import Wizard Step', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    const helpers = new TestHelpers(page)
    await helpers.login('admin', 'admin')
  })

  test('paste-tab: line counter matches input row count', async ({ page }) => {
    test.setTimeout(60000)

    await page.goto(`${TEST_URL}/projects/create`)

    const projectName = `DataImport_LineCount_${Date.now()}`
    await page
      .locator('[data-testid="project-create-name-input"]')
      .fill(projectName)
    await enableWizardFeatures(page, ['dataImport'])

    // Advance to step 2 (dataImport)
    await page.locator('[data-testid="project-create-next-button"]').click()
    await expect(
      page.locator('[data-testid="project-create-step-indicator"]')
    ).toHaveAttribute('data-step', '2')

    // Switch to the paste tab
    await page.locator('[data-testid="project-create-paste-tab"]').click()

    // Paste a known-shape JSON array with 5 entries
    const sampleRows = Array.from({ length: 5 }, (_, i) => ({
      text: `Row ${i + 1} for line-counter assertion`,
    }))
    const pasted = JSON.stringify(sampleRows, null, 2)
    await page
      .locator('[data-testid="project-create-paste-data-textarea"]')
      .fill(pasted)

    // The line-count display has a data-line-count attribute that mirrors
    // the number of lines in the textarea. Assert it equals the pasted
    // line count exactly — uses the explicit testid so unrelated text on
    // the page can't false-match.
    const expectedLineCount = pasted.split('\n').length
    await expect(
      page.locator('[data-testid="project-create-paste-line-count"]')
    ).toHaveAttribute('data-line-count', String(expectedLineCount))

    // Validate button should now be enabled (was disabled with no data)
    const validate = page.locator(
      '[data-testid="project-create-validate-data-button"]'
    )
    await expect(validate).toBeEnabled()
    await validate.click()

    // The validate button shows a success toast naming the detected
    // format. Scope to the app's Toast container testid so unrelated
    // page text containing "JSON" can't false-match.
    const toast = page.locator(
      '[data-testid="toast-item"][data-toast-type="success"]'
    )
    await expect(toast).toBeVisible({ timeout: 5000 })
    await expect(toast).toContainText(/JSON/i)
  })

  test('clear-button removes pasted data and re-disables validate', async ({
    page,
  }) => {
    test.setTimeout(60000)

    await page.goto(`${TEST_URL}/projects/create`)

    await page
      .locator('[data-testid="project-create-name-input"]')
      .fill(`DataImport_Clear_${Date.now()}`)
    await enableWizardFeatures(page, ['dataImport'])
    await page.locator('[data-testid="project-create-next-button"]').click()

    await page.locator('[data-testid="project-create-paste-tab"]').click()

    const textarea = page.locator(
      '[data-testid="project-create-paste-data-textarea"]'
    )
    await textarea.fill('one\ntwo\nthree')

    const clear = page.locator(
      '[data-testid="project-create-clear-data-button"]'
    )
    await expect(clear).toBeEnabled()
    await clear.click()

    await expect(textarea).toHaveValue('')
    await expect(clear).toBeDisabled()
    await expect(
      page.locator('[data-testid="project-create-validate-data-button"]')
    ).toBeDisabled()
  })

  test('full path: paste data then submit lands on project detail', async ({
    page,
  }) => {
    test.setTimeout(90000)

    await page.goto(`${TEST_URL}/projects/create`)

    const projectName = `DataImport_Submit_${Date.now()}`
    await page
      .locator('[data-testid="project-create-name-input"]')
      .fill(projectName)
    await enableWizardFeatures(page, ['dataImport'])

    await page.locator('[data-testid="project-create-next-button"]').click()
    await page.locator('[data-testid="project-create-paste-tab"]').click()
    await page
      .locator('[data-testid="project-create-paste-data-textarea"]')
      .fill(JSON.stringify([{ text: 'sample row' }]))

    // Walk to submit. The helper asserts each step transition.
    await clickSubmitFromAnyStep(page)

    await page.waitForURL(/\/projects\/[a-f0-9-]+/, { timeout: 30000 })
    expect(page.url()).toMatch(/\/projects\/[a-f0-9-]+/)
  })
})
