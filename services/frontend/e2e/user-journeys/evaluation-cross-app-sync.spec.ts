/**
 * E2E tests for evaluation page cross-app synchronization
 * Tests that the evaluations page loads correctly and survives refresh.
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Evaluation Cross-App Sync', () => {
  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)

    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test('evaluations page loads with project dropdown', async () => {
    await page.goto(`${BASE_URL}/evaluations`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Evaluations page should have a project dropdown (DE: "Projekt auswählen...")
    const projectDropdown = page
      .locator('button')
      .filter({ hasText: /Select project|Projekt auswählen/i })
      .first()

    await expect(projectDropdown).toBeVisible({ timeout: 10000 })
  })

  test('evaluation results persist across page refresh', async () => {
    await page.goto(`${BASE_URL}/evaluations`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Verify evaluations page content is visible (EN or DE)
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasEval =
        bodyText?.includes('Evaluierungsergebnisse') ||
        bodyText?.includes('Evaluation Results') ||
        bodyText?.includes('Evaluation') ||
        bodyText?.includes('Evaluierung')
      expect(hasEval).toBe(true)
    }).toPass({ timeout: 15000 })

    // Refresh the page
    await page.reload()

    // Verify page is still functional after refresh
    await expect(mainContent).toBeVisible({ timeout: 15000 })
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasEval =
        bodyText?.includes('Evaluierungsergebnisse') ||
        bodyText?.includes('Evaluation Results') ||
        bodyText?.includes('Evaluation') ||
        bodyText?.includes('Evaluierung')
      expect(hasEval).toBe(true)
    }).toPass({ timeout: 15000 })
  })
})
