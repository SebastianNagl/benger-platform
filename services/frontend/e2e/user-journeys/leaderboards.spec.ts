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

  test('leaderboards page loads with tabs', async () => {
    await page.goto(`${BASE_URL}/leaderboards`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Human annotators tab (DE: "Menschliche Annotatoren")
    const humanTab = page
      .locator('button')
      .filter({ hasText: /Menschliche Annotatoren|Human Annotators|Annotator/i })
      .first()
    await expect(humanTab).toBeVisible({ timeout: 10000 })
  })

  test('switches between Human Annotators and LLMs tabs', async () => {
    await page.goto(`${BASE_URL}/leaderboards`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    const humanTab = page
      .locator('button')
      .filter({ hasText: /Menschliche Annotatoren|Human Annotators/i })
      .first()

    const llmTab = page
      .locator('button')
      .filter({ hasText: /LLMs|LLM/i })
      .first()

    // Click Human tab and verify content
    await expect(humanTab).toBeVisible({ timeout: 10000 })
    await humanTab.click()

    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasHumanContent =
        bodyText?.includes('Rang') ||
        bodyText?.includes('Rank') ||
        bodyText?.includes('Annotator') ||
        bodyText?.includes('Annotationen') ||
        bodyText?.includes('Annotations')
      expect(hasHumanContent).toBe(true)
    }).toPass({ timeout: 10000 })

    // Click LLM tab and verify content
    await expect(llmTab).toBeVisible({ timeout: 5000 })
    await llmTab.click()

    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasLLMContent =
        bodyText?.includes('Modell') ||
        bodyText?.includes('Model') ||
        bodyText?.includes('Score') ||
        bodyText?.includes('Bewertung') ||
        bodyText?.includes('LLM')
      expect(hasLLMContent).toBe(true)
    }).toPass({ timeout: 10000 })
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
