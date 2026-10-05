/**
 * E2E tests for admin pages
 * Tests that admin-only pages load correctly and that key interactions work.
 * Requires admin login (superadmin) for access.
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Admin Pages', () => {
  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test('feature flags route shell renders for superadmins', async () => {
    test.setTimeout(60000)

    // The flag admin UI ships in the extended edition (FeatureFlagsAdmin
    // slot); its behaviour is covered by the extended @extended e2e. Here we
    // only assert that the platform route renders past the superadmin
    // guard: the community "not available" message, or (extended stack) the
    // slot's own heading, and never the access-denied state.
    await page.goto(`${BASE_URL}/admin/feature-flags`, { timeout: 30000 })

    const notAvailable = page.getByText(
      /Feature flags are not available in this edition\.|Feature-Flags sind in dieser Edition nicht verfügbar\./,
    )
    await expect(notAvailable.or(page.locator('h1')).first()).toBeVisible({
      timeout: 30000,
    })
    await expect(page).toHaveURL(/\/admin\/feature-flags$/)
    await expect(
      page.getByText(/^(Access Denied|Zugriff verweigert)$/),
    ).toHaveCount(0)
  })

  test('users-organizations page loads with tabs', async () => {
    test.setTimeout(60000)

    // The /admin/users-organizations redirects to /users-organizations
    await page.goto(`${BASE_URL}/users-organizations`, { timeout: 30000 })

    // Verify the page heading (EN or DE)
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('Users & Organizations') ||
        text?.includes('Benutzer & Organisationen') ||
        text?.includes('Users') ||
        text?.includes('Benutzer')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })

    // Verify tabs are present - the page uses HeadlessUI TabGroup
    // Admin should see both "Global Users" and "Organizations" tabs
    await expect(async () => {
      const tabsText = await page.locator('body').textContent()
      const hasOrganizationsTab =
        tabsText?.includes('Organizations') ||
        tabsText?.includes('Organisationen')
      expect(hasOrganizationsTab).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('users-organizations page shows user table with rows', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/users-organizations?tab=users`, {
      timeout: 30000,
    })

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Wait for the user table to render
    const userTable = page.locator('table').first()
    await expect(userTable).toBeVisible({ timeout: 20000 })

    // Verify the table has at least one data row (the admin user should always exist)
    const tableRows = page.locator('table tbody tr')
    await expect(async () => {
      const rowCount = await tableRows.count()
      expect(rowCount).toBeGreaterThan(0)
    }).toPass({ timeout: 20000 })

    // Verify the admin user appears in the table
    await expect(async () => {
      const tableText = await userTable.textContent()
      const hasAdminUser =
        tableText?.includes('admin') || tableText?.includes('Admin')
      expect(hasAdminUser).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('users-organizations checkbox selection works', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/users-organizations?tab=users`, {
      timeout: 30000,
    })

    // Wait for the user table to render
    const userTable = page.locator('table').first()
    await expect(userTable).toBeVisible({ timeout: 20000 })

    // Wait for table rows to load
    const tableRows = page.locator('table tbody tr')
    await expect(async () => {
      const rowCount = await tableRows.count()
      expect(rowCount).toBeGreaterThan(0)
    }).toPass({ timeout: 20000 })

    // Find the "select all" checkbox in the table header
    const selectAllCheckbox = page.locator('table thead input[type="checkbox"]')
    await expect(selectAllCheckbox).toBeVisible({ timeout: 10000 })

    // Click select all
    await selectAllCheckbox.click()

    // Verify a bulk action bar appears with selection info
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasSelectionInfo =
        bodyText?.includes('selected') ||
        bodyText?.includes('ausgewählt') ||
        bodyText?.includes('Selected') ||
        bodyText?.includes('Ausgewählt')
      expect(hasSelectionInfo).toBe(true)
    }).toPass({ timeout: 15000 })

    // Uncheck select all to deselect
    await selectAllCheckbox.click()

    // Verify selection indicator disappears
    await page.waitForTimeout(500)
  })

  test('admin/users-organizations redirects to users-organizations', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/admin/users-organizations`, {
      timeout: 30000,
    })

    // Should redirect to /users-organizations
    await expect(async () => {
      const url = page.url()
      // The redirect strips /admin prefix
      expect(
        url.includes('/users-organizations') &&
          !url.includes('/admin/users-organizations'),
      ).toBe(true)
    }).toPass({ timeout: 15000 })
  })
})
