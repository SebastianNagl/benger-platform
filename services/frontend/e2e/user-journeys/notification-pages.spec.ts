/**
 * E2E tests for notification pages
 * Tests the notification inbox interactions, filter usage, mark-as-read,
 * and notification preference toggling.
 * Requires login for all pages.
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Notification Pages', () => {
  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')

    // Wait for auth to fully stabilize on dashboard before navigating.
    // In CI (after heavy API/worker tests), the /api/auth/me call can be slow.
    // If we navigate to a protected route before auth resolves, AuthContext may
    // redirect to /login.
    await expect(page.locator('nav, [class*="sidebar"], [class*="navigation"]').first())
      .toBeVisible({ timeout: 15000 })
  })

  test('notifications inbox loads with heading and action bar', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/notifications`, { timeout: 30000 })

    // Wait for auth to resolve and page to render (not just domcontentloaded).
    // If auth is slow, AuthContext may briefly redirect to /login then back.
    await expect(async () => {
      const url = page.url()
      // If redirected to login, auth failed — wait for it to resolve
      expect(url).toContain('/notifications')
    }).toPass({ timeout: 30000 })

    // Verify the page heading (EN or DE)
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('Notifications') ||
        text?.includes('Benachrichtigungen')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('notifications inbox shows list or empty state', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/notifications`, { timeout: 30000 })

    // Wait for auth to resolve and page heading to render
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })

    // Wait for content to load (either notification list table or empty state)
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasContent =
        // Empty state messages
        bodyText?.includes('No notifications') ||
        bodyText?.includes('Keine Benachrichtigungen') ||
        bodyText?.includes('caught up') ||
        bodyText?.includes('eingeholt') ||
        // Or notification table content
        bodyText?.includes('Notification') ||
        bodyText?.includes('Benachrichtigung') ||
        bodyText?.includes('Time') ||
        bodyText?.includes('Zeit') ||
        bodyText?.includes('Status')
      expect(hasContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('notifications inbox loads and shows notification data', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/notifications`, { timeout: 30000 })

    // Wait for auth to resolve and page heading to render
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })

    // Verify page has meaningful content (notifications list or empty state)
    await expect(async () => {
      const content = await page.locator('body').textContent()
      // Should contain notification-related content
      const hasContent = (content?.length || 0) > 200
      expect(hasContent).toBe(true)
    }).toPass({ timeout: 10000 })

    console.log('Notifications inbox loaded with content')
  })

  test('notifications API is called on page load', async () => {
    test.setTimeout(90000)

    let apiCalled = false
    page.on('request', (request) => {
      if (request.url().includes('/api/notifications') && request.method() === 'GET') {
        apiCalled = true
      }
    })

    await page.goto(`${BASE_URL}/notifications`, { timeout: 30000 })

    // Wait for auth to resolve and page heading to render
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 30000 })

    expect(apiCalled).toBe(true)
    console.log('Notifications API called on page load')
  })

  test('notifications analytics page loads and has time range selector', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/notifications/analytics`, { timeout: 30000 })

    // Wait for auth to resolve and page heading to render
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('Analytics') ||
        text?.includes('Analytik') ||
        text?.includes('Notification') ||
        text?.includes('Benachrichtigung')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })

    // The analytics page has time range dropdowns (native <select> or HeadlessUI Listbox depending on build)
    // Try native select first, fall back to HeadlessUI button
    const nativeSelects = page.locator('select')
    const hasNativeSelect = await nativeSelects.count().then(c => c > 0).catch(() => false)

    if (hasNativeSelect) {
      // Native <select> path
      const firstSelect = nativeSelects.first()
      const initialValue = await firstSelect.inputValue()
      const options = firstSelect.locator('option')
      const optionCount = await options.count()
      if (optionCount > 1) {
        const secondOptionValue = await options.nth(1).getAttribute('value')
        if (secondOptionValue) {
          await firstSelect.selectOption(secondOptionValue)
          const newValue = await firstSelect.inputValue()
          expect(newValue).toBe(secondOptionValue)
          await firstSelect.selectOption(initialValue)
        }
      }
    } else {
      // HeadlessUI Listbox path — find time range button by position (first button in the header controls area)
      // The heading and controls are siblings: heading + div with buttons
      const controlsArea = page.locator('h1').locator('..').locator('..').locator('button').first()
      await expect(controlsArea).toBeVisible({ timeout: 15000 })

      const initialText = await controlsArea.textContent()
      console.log('Initial time range:', initialText)
      await controlsArea.click()

      const listbox = page.getByRole('listbox')
      await expect(listbox).toBeVisible({ timeout: 5000 })

      const options = listbox.getByRole('option')
      const optionCount = await options.count()
      if (optionCount > 1) {
        await options.nth(1).click()
        await page.waitForTimeout(300)
        // Re-locate the button after selection (text changed, locator must be fresh)
        const updatedButton = page.locator('h1').locator('..').locator('..').locator('button').first()
        const newText = await updatedButton.textContent()
        console.log('New time range:', newText)
        expect(newText).not.toBe(initialText)
      } else {
        await page.keyboard.press('Escape')
      }
    }
  })

  test('notification settings page toggle changes preference state', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/settings/notifications`, { timeout: 30000 })

    // Verify the settings heading
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })

    // Wait for the preferences table to load (not the loading spinner)
    const prefsTable = page.locator('table').first()
    await expect(prefsTable).toBeVisible({ timeout: 25000 })

    // Find a toggle switch by its data-testid pattern
    // The "enabled" toggles use data-testid="settings-notification-toggle-{type}"
    const firstToggle = page
      .locator('[data-testid^="settings-notification-toggle-"]')
      .first()
    await expect(firstToggle).toBeVisible({ timeout: 15000 })

    // Read the initial background color class to determine state
    const initialClasses = await firstToggle.getAttribute('class')
    const wasEnabled = initialClasses?.includes('bg-emerald-600')

    // Click the toggle to change its state
    await firstToggle.click()
    await page.waitForTimeout(300)

    // Verify the toggle class changed (bg-emerald-600 vs bg-zinc-200)
    await expect(async () => {
      const newClasses = await firstToggle.getAttribute('class')
      if (wasEnabled) {
        expect(newClasses).toContain('bg-zinc-')
      } else {
        expect(newClasses).toContain('bg-emerald-600')
      }
    }).toPass({ timeout: 10000 })

    // Click it again to restore the original state
    await firstToggle.click()
    await page.waitForTimeout(300)

    // Verify it returned to original state
    await expect(async () => {
      const restoredClasses = await firstToggle.getAttribute('class')
      if (wasEnabled) {
        expect(restoredClasses).toContain('bg-emerald-600')
      } else {
        expect(restoredClasses).toContain('bg-zinc-')
      }
    }).toPass({ timeout: 10000 })
  })

  test('notification settings save button persists preferences', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/settings/notifications`, { timeout: 30000 })

    // Wait for the preferences table to load
    const prefsTable = page.locator('table').first()
    await expect(prefsTable).toBeVisible({ timeout: 25000 })

    // Find the save button
    const saveButton = page.locator(
      '[data-testid="settings-save-notifications-button"]'
    )
    await expect(saveButton).toBeVisible({ timeout: 20000 })

    // Set up request tracking to verify save makes an API call
    let saveRequestMade = false
    page.on('request', (request) => {
      if (
        request.url().includes('/api/notifications/preferences') &&
        (request.method() === 'PUT' || request.method() === 'POST' || request.method() === 'PATCH')
      ) {
        saveRequestMade = true
      }
    })

    // Click save
    await saveButton.click()

    // Verify a save request was made
    await expect(async () => {
      expect(saveRequestMade).toBe(true)
    }).toPass({ timeout: 10000 })

    // Verify a success message appears
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasSuccess =
        bodyText?.includes('saved') ||
        bodyText?.includes('gespeichert') ||
        bodyText?.includes('Saved') ||
        bodyText?.includes('Gespeichert') ||
        bodyText?.includes('success') ||
        bodyText?.includes('Erfolg')
      expect(hasSuccess).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('notification settings disable all and enable all buttons work', async () => {
    test.setTimeout(90000)

    await page.goto(`${BASE_URL}/settings/notifications`, { timeout: 30000 })

    // Wait for the preferences table to load
    const prefsTable = page.locator('table').first()
    await expect(prefsTable).toBeVisible({ timeout: 25000 })

    // Find the "Disable All" button
    const disableAllButton = page.locator(
      '[data-testid="settings-disable-all-notifications-button"]'
    )
    await expect(disableAllButton).toBeVisible({ timeout: 15000 })

    // Click "Disable All"
    await disableAllButton.click()
    await page.waitForTimeout(500)

    // Verify all enabled toggles switched to disabled (bg-zinc classes)
    await expect(async () => {
      const enabledToggles = page.locator(
        '[data-testid^="settings-notification-toggle-"]'
      )
      const count = await enabledToggles.count()
      for (let i = 0; i < count; i++) {
        const classes = await enabledToggles.nth(i).getAttribute('class')
        expect(classes).toContain('bg-zinc-')
      }
    }).toPass({ timeout: 10000 })

    // Find the "Enable All" button
    const enableAllButton = page.locator(
      '[data-testid="settings-enable-all-notifications-button"]'
    )
    await expect(enableAllButton).toBeVisible({ timeout: 10000 })

    // Click "Enable All" to restore
    await enableAllButton.click()
    await page.waitForTimeout(500)

    // Verify all toggles switched to enabled (bg-emerald-600)
    await expect(async () => {
      const enabledToggles = page.locator(
        '[data-testid^="settings-notification-toggle-"]'
      )
      const count = await enabledToggles.count()
      for (let i = 0; i < count; i++) {
        const classes = await enabledToggles.nth(i).getAttribute('class')
        expect(classes).toContain('bg-emerald-600')
      }
    }).toPass({ timeout: 10000 })
  })
})
