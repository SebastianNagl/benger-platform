/**
 * E2E tests for reports flow
 * Tests reports page load and access permissions.
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Reports Flow', () => {
  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)

    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test('reports page loads successfully', async () => {
    await page.goto(`${BASE_URL}/reports`, { timeout: 30000 })

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Should show either report cards or empty state (EN or DE)
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasContent =
        bodyText?.includes('Report') ||
        bodyText?.includes('Bericht') ||
        bodyText?.includes('published') ||
        bodyText?.includes('veröffentlicht') ||
        bodyText?.includes('No') ||
        bodyText?.includes('Keine')
      expect(hasContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('admin has access to reports page', async () => {
    await page.goto(`${BASE_URL}/reports`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // No permission error should be shown for admin
    const permissionError = page.locator(
      'text=/Permission denied|Access denied|Zugriff verweigert/i'
    )
    await expect(permissionError).not.toBeVisible({ timeout: 5000 })
  })
})
