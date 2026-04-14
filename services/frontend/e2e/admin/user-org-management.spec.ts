import { expect, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

test.describe('Unified Admin Interface', () => {
  test('Admin user should always see Users & Organizations in dropdown', async ({
    page,
  }) => {
    const helpers = new TestHelpers(page)

    // Login as admin
    await helpers.login('admin', 'admin')

    // Navigate to dashboard after login
    await page.goto('/dashboard')

    // Look for the user dropdown button - it should show the username
    await expect(
      page.locator('[data-testid="user-menu-button"], button:has-text("admin")')
    ).toBeVisible({ timeout: 10000 })

    // Click on the user dropdown to open it
    await page.click(
      '[data-testid="user-menu-button"], button:has-text("admin")'
    )

    // Wait for dropdown to be visible - look for profile settings link which appears in dropdown
    await page.waitForSelector(
      '[href="/profile"], [href="/settings/notifications"]',
      {
        timeout: 5000,
      }
    )

    // Check that admin-specific links are visible (handles both English and German)
    const adminLink = page
      .locator('[href="/admin/users-organizations"]')
      .or(page.locator('text=Users & Organizations'))
      .or(page.locator('text=Benutzer & Organisationen'))
    await expect(adminLink.first()).toBeVisible({ timeout: 5000 })

    console.log('Admin options visible as expected')
  })
})
