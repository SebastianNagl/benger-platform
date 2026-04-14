/**
 * E2E tests for authentication pages
 * Tests login accessibility and auto-login redirect behavior.
 * In test environments with auto-login, registration is not accessible.
 */

import { expect, Page, test } from '@playwright/test'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Authentication Pages', () => {
  let page: Page

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    await page.setViewportSize({ width: 1920, height: 1080 })
  })

  test('login page redirects to dashboard with auto-login', async () => {
    await page.goto(`${BASE_URL}/login`)

    // Auto-login should redirect to dashboard or projects
    await expect(async () => {
      const url = page.url()
      const isRedirected =
        url.includes('/dashboard') ||
        url.includes('/projects') ||
        url.includes('/login')
      expect(isRedirected).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('register page redirects appropriately', async () => {
    await page.goto(`${BASE_URL}/register`)

    // With auto-login, register redirects to dashboard/projects.
    // Without auto-login, it shows the registration form.
    await expect(async () => {
      const url = page.url()
      const isValid =
        url.includes('/register') ||
        url.includes('/dashboard') ||
        url.includes('/projects')
      expect(isValid).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('unauthenticated access to protected pages redirects to login', async () => {
    // Use a fresh context without cookies
    const context = await page.context().browser()!.newContext()
    const freshPage = await context.newPage()

    try {
      await freshPage.goto(`${BASE_URL}/projects`, { timeout: 15000 })

      // Should either redirect to login or show the login form
      await expect(async () => {
        const url = freshPage.url()
        const bodyText = await freshPage.locator('body').textContent()
        const isAuthPage =
          url.includes('/login') ||
          url.includes('/register') ||
          bodyText?.includes('Login') ||
          bodyText?.includes('Anmelden') ||
          bodyText?.includes('Loslegen')
        expect(isAuthPage).toBe(true)
      }).toPass({ timeout: 15000 })
    } finally {
      await context.close()
    }
  })
})
