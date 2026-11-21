/**
 * E2E tests for leaderboards
 * Tests human annotator and LLM leaderboard views.
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Leaderboards', () => {
  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)

    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test('leaderboard page loads without error alerts', async () => {
    await page.goto(`${BASE_URL}/leaderboards`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // No error alerts
    const errorAlert = page
      .locator('[role="alert"]')
      .filter({ hasText: /error|Error|Fehler/i })
    await expect(errorAlert).not.toBeVisible({ timeout: 5000 })
  })
})
