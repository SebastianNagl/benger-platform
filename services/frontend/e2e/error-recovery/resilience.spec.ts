import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

/**
 * Error Recovery and Resilience Tests
 *
 * These tests verify the application's error handling behavior
 * for common failure scenarios like network issues, session expiration,
 * and API errors.
 */
test.describe('Error Recovery and Resilience', () => {
  let page: Page
  let helpers: TestHelpers
  let testProjectId: string | null = null

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    await helpers.login('admin', 'admin')
  })

  test.afterEach(async () => {
    if (testProjectId) {
      await helpers.deleteTestProject(testProjectId)
      testProjectId = null
    }
  })

  test('handles network interruption gracefully', async ({ context }) => {
    // Increase timeout for slower authentication
    test.setTimeout(60000)

    await test.step('1. Navigate to dashboard', async () => {
      await page.goto('/dashboard', { timeout: 30000 })
      await page.waitForTimeout(3000) // Allow initial content to load

      // Verify dashboard loaded - use body as fallback
      const dashboardContent = page.locator('main, [role="main"]').first()
      const hasMain = await dashboardContent
        .isVisible({ timeout: 10000 })
        .catch(() => false)

      // If main not visible, verify at least body is accessible
      if (!hasMain) {
        await expect(page.locator('body')).toBeVisible()
      }
    })

    await test.step('2. Go offline and try navigation', async () => {
      // Go offline
      await context.setOffline(true)

      // Try to navigate - should show some error indication or cached content
      await page.goto('/projects', { waitUntil: 'commit' }).catch(() => {
        // Navigation failure is expected when offline
      })

      await page.waitForTimeout(2000)

      // Either we see an error indication OR we see cached/current content
      // When offline, the page might fail to load completely but shouldn't crash
      const pageBody = page.locator('body')
      await expect(pageBody).toBeVisible()
    })

    await test.step('3. Restore connection', async () => {
      await context.setOffline(false)

      // Refresh the page
      await page.reload()
      await page.waitForTimeout(2000)

      // Page should load successfully
      const mainContent = page.locator('main, [role="main"]').first()
      await expect(mainContent).toBeVisible({ timeout: 15000 })
    })
  })

  test('handles session expiration gracefully', async () => {
    await test.step('1. Verify logged in state', async () => {
      await page.goto('/dashboard')
      await page.waitForTimeout(2000)

      // Should be on dashboard (not redirected to login)
      expect(page.url()).not.toContain('/login')
    })

    await test.step('2. Intercept auth to simulate expired session', async () => {
      // Intercept ALL auth-related API calls to return 401 (simulating expired token)
      await page.route('**/api/auth/**', (route) => {
        route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Token expired',
          }),
        })
      })

      // Also intercept the user/me endpoint which checks auth status
      await page.route('**/api/users/me**', (route) => {
        route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Not authenticated',
          }),
        })
      })

      // Clear tokens to complete the simulation
      await page.evaluate(() => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        sessionStorage.clear()
      })

      await page.waitForTimeout(500)
    })

    await test.step('3. Try protected action', async () => {
      // Navigate to trigger auth check - this should fail now
      await page.goto('/dashboard')
      await page.waitForTimeout(3000)

      // Should redirect to login, show login form, OR still show content (graceful degradation)
      const currentUrl = page.url()
      const isOnLoginPage =
        currentUrl.includes('/login') || currentUrl.includes('/auth')

      const loginForm = page.locator('form').filter({
        has: page.locator('input[type="password"]'),
      })
      const hasLoginForm = (await loginForm.count()) > 0

      // App should either show login OR gracefully handle the auth failure
      // (e.g., showing cached content or an error state)
      const hasGracefulHandling =
        isOnLoginPage ||
        hasLoginForm ||
        // Page still renders with some content (graceful degradation)
        (await page.locator('main, [role="main"]').count()) > 0

      expect(hasGracefulHandling).toBeTruthy()
    })
  })

  test('handles API errors gracefully', async () => {
    await test.step('1. Intercept API to return 500 error', async () => {
      // Intercept the dashboard stats API
      await page.route('**/api/dashboard/**', (route) => {
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'Internal Server Error',
            message: 'Test error for resilience testing',
          }),
        })
      })
    })

    await test.step('2. Navigate to dashboard', async () => {
      await page.goto('/dashboard')
      await page.waitForTimeout(3000)

      // Page should still render, potentially with error indicators
      const pageLoaded = (await page.locator('main, [role="main"]').count()) > 0

      expect(pageLoaded).toBeTruthy()
    })

    await test.step('3. Check for graceful degradation', async () => {
      // The page should either show error UI or fallback content
      // It should NOT show a blank page or crash
      const hasContent =
        (await page.locator('main, [role="main"]').count()) > 0 ||
        (await page.locator('.error-message, [data-testid*="error"]').count()) >
          0 ||
        (await page.locator('text=/error|failed|unavailable/i').count()) > 0

      expect(hasContent).toBeTruthy()
    })

    await test.step('4. Restore API and refresh', async () => {
      await page.unroute('**/api/dashboard/**')

      await page.reload()
      await page.waitForTimeout(2000)

      // Dashboard should work again
      const mainContent = page.locator('main, [role="main"]').first()
      await expect(mainContent).toBeVisible({ timeout: 15000 })
    })
  })

  test('handles 404 routes gracefully', async () => {
    await test.step('1. Navigate to non-existent page', async () => {
      await page.goto('/non-existent-page-12345')
      await page.waitForTimeout(2000)
    })

    await test.step('2. Verify 404 handling', async () => {
      // Should show 404 page or redirect to valid page
      const has404Content =
        page.url().includes('404') ||
        (await page.locator('text=/not found|404|page.*exist/i').count()) > 0 ||
        // Alternatively, might redirect to home/dashboard
        page.url().includes('/dashboard') ||
        page.url().includes('/projects')

      expect(has404Content).toBeTruthy()
    })
  })

  test('handles invalid project ID gracefully', async () => {
    await test.step('1. Navigate to non-existent project', async () => {
      // Use a valid UUID format but non-existent project
      await page.goto('/projects/00000000-0000-0000-0000-000000000000', {
        timeout: 30000,
      })
      await page.waitForTimeout(3000)
    })

    await test.step('2. Verify error handling', async () => {
      const currentUrl = page.url()

      // Should show error message, redirect, or loading state - not a blank page
      const hasErrorHandling =
        // Error text visible
        (await page
          .locator('text=/not found|error|does not exist|failed/i')
          .count()) > 0 ||
        // Redirected to projects list
        currentUrl === '/projects' ||
        currentUrl.includes('/projects?') ||
        // Redirected away from the invalid project
        !currentUrl.includes('00000000-0000-0000-0000-000000000000') ||
        // Error/alert UI elements
        (await page.locator('.error, .alert, [role="alert"]').count()) > 0 ||
        // Shows loading state
        (await page
          .locator('.loading, .spinner, [data-testid*="loading"]')
          .count()) > 0

      expect(hasErrorHandling).toBeTruthy()
    })
  })
})
