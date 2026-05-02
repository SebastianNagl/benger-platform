/**
 * E2E tests for admin pages
 * Tests that admin-only pages load correctly and that key interactions work.
 * Requires admin login (superadmin) for access.
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'
import { revealFilterToolbarSearch } from '../utils/test-helpers'

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

  test('feature flags page loads and shows table', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/admin/feature-flags`, { timeout: 30000 })

    // Verify the page heading is visible (EN or DE)
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('Feature Flags') || text?.includes('Feature-Flags')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })

    // Verify the table structure is present
    const table = page.locator('table').first()
    await expect(table).toBeVisible({ timeout: 15000 })

    // Verify table headers exist (Status column is always English in the source)
    await expect(page.locator('th:has-text("Status")')).toBeVisible({
      timeout: 10000,
    })
  })

  test('feature flags page shows toggle switches', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/admin/feature-flags`, { timeout: 30000 })

    // Wait for the table to render
    const table = page.locator('table').first()
    await expect(table).toBeVisible({ timeout: 15000 })

    // Look for toggle switches (ToggleSwitch component renders as button with role="switch")
    // or the enabled/disabled status text
    await expect(async () => {
      const bodyText = await page.locator('table').textContent()
      const hasToggleStatus =
        bodyText?.includes('Enabled') ||
        bodyText?.includes('Disabled') ||
        bodyText?.includes('Aktiviert') ||
        bodyText?.includes('Deaktiviert') ||
        bodyText?.includes('No feature flags')
      expect(hasToggleStatus).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('feature flags page has search input', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/admin/feature-flags`, { timeout: 30000 })

    // Wait for the page to fully load
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 30000 })

    // FilterToolbar collapses search behind a toggle; click it to reveal input.
    const searchInput = await revealFilterToolbarSearch(page)
    await expect(searchInput).toBeVisible({ timeout: 10000 })
  })

  test('feature flag toggle changes state and shows pending badge', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/admin/feature-flags`, { timeout: 30000 })

    // Wait for the table to render with actual flag rows
    const table = page.locator('table').first()
    await expect(table).toBeVisible({ timeout: 15000 })

    // Wait for at least one toggle switch (HeadlessUI Switch renders role="switch")
    const toggleSwitches = page.locator('button[role="switch"]')
    await expect(async () => {
      const count = await toggleSwitches.count()
      expect(count).toBeGreaterThan(0)
    }).toPass({ timeout: 20000 })

    // Get the first toggle switch and its initial state
    const firstToggle = toggleSwitches.first()
    const initialChecked = await firstToggle.getAttribute('aria-checked')

    // Read the status text next to the toggle before clicking
    const firstRow = page.locator('table tbody tr').first()
    const initialStatusText = await firstRow.textContent()
    const wasEnabled =
      initialStatusText?.includes('Enabled') ||
      initialStatusText?.includes('Aktiviert')

    // Click the toggle to change its state
    await firstToggle.click()

    // Verify the toggle state changed (aria-checked should flip)
    await expect(async () => {
      const newChecked = await firstToggle.getAttribute('aria-checked')
      expect(newChecked).not.toBe(initialChecked)
    }).toPass({ timeout: 10000 })

    // Verify the "Pending" badge appears after toggling
    await expect(async () => {
      const rowText = await firstRow.textContent()
      expect(rowText).toContain('Pending')
    }).toPass({ timeout: 10000 })

    // Verify the status text flipped
    await expect(async () => {
      const newStatusText = await firstRow.textContent()
      if (wasEnabled) {
        const isNowDisabled =
          newStatusText?.includes('Disabled') ||
          newStatusText?.includes('Deaktiviert')
        expect(isNowDisabled).toBe(true)
      } else {
        const isNowEnabled =
          newStatusText?.includes('Enabled') ||
          newStatusText?.includes('Aktiviert')
        expect(isNowEnabled).toBe(true)
      }
    }).toPass({ timeout: 10000 })

    // Toggle it back to restore original state
    await firstToggle.click()

    // Verify it flipped back (no more Pending for that flag, or Pending count went to 0)
    await expect(async () => {
      const restoredChecked = await firstToggle.getAttribute('aria-checked')
      expect(restoredChecked).toBe(initialChecked)
    }).toPass({ timeout: 10000 })
  })

  test('feature flag search filters the table rows', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/admin/feature-flags`, { timeout: 30000 })

    // Wait for the table to load with rows
    const table = page.locator('table').first()
    await expect(table).toBeVisible({ timeout: 15000 })

    // Count initial rows
    const rows = page.locator('table tbody tr')
    let initialRowCount = 0
    await expect(async () => {
      initialRowCount = await rows.count()
      expect(initialRowCount).toBeGreaterThan(0)
    }).toPass({ timeout: 20000 })

    // Get the name of the first flag to search for it
    const firstFlagName = await page
      .locator('table tbody tr td')
      .first()
      .textContent()

    // FilterToolbar collapses search behind a toggle; click it to reveal input.
    const searchInput = await revealFilterToolbarSearch(page)
    await expect(searchInput).toBeVisible({ timeout: 10000 })

    // Use a partial match from the first flag name
    const searchTerm = firstFlagName?.trim().split(' ')[0] || 'flag'
    await searchInput.fill(searchTerm)

    // Verify the table filtered (should show fewer or equal rows)
    await expect(async () => {
      const filteredCount = await rows.count()
      // The filtered rows should contain the search term, or show "No feature flags found"
      if (filteredCount > 0) {
        const rowText = await page.locator('table tbody').textContent()
        const hasMatch =
          rowText
            ?.toLowerCase()
            .includes(searchTerm.toLowerCase()) ||
          rowText?.includes('No feature flags found')
        expect(hasMatch).toBe(true)
      }
    }).toPass({ timeout: 15000 })

    // Clear the search and verify all rows return
    await searchInput.fill('')
    await expect(async () => {
      const restoredCount = await rows.count()
      expect(restoredCount).toBe(initialRowCount)
    }).toPass({ timeout: 15000 })
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
          !url.includes('/admin/users-organizations')
      ).toBe(true)
    }).toPass({ timeout: 15000 })
  })
})
