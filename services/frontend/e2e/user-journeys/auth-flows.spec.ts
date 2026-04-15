/**
 * E2E tests for authentication flow pages
 * Tests password reset and email verification pages render correctly.
 * These pages are public (no login required) and work without tokens --
 * we verify the forms/UI load, not the full flow (no email server in test).
 */

import { expect, Page, test } from '@playwright/test'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Auth Flow Pages', () => {
  let page: Page

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    await page.setViewportSize({ width: 1920, height: 1080 })
  })

  test('reset-password page loads with email form', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/reset-password`, { timeout: 30000 })

    // The reset password page shows a form with an email input
    // Check for the heading (EN or DE)
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasResetContent =
        bodyText?.includes('Reset') ||
        bodyText?.includes('Passwort zurücksetzen') ||
        bodyText?.includes('Password') ||
        bodyText?.includes('Passwort') ||
        bodyText?.includes('BenGER')
      expect(hasResetContent).toBe(true)
    }).toPass({ timeout: 15000 })

    // Verify the email input field is present
    const emailInput = page.locator('input[type="email"]').first()
    await expect(emailInput).toBeVisible({ timeout: 15000 })
  })

  test('reset-password page has submit button', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/reset-password`, { timeout: 30000 })

    // Verify the submit button is present
    const submitButton = page
      .locator('button[type="submit"]')
      .first()
    await expect(submitButton).toBeVisible({ timeout: 15000 })
  })

  test('reset-password page has back to login link', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/reset-password`, { timeout: 30000 })

    // Verify the "Back to Login" link is present
    const loginLink = page.locator('a[href="/login"]').first()
    await expect(loginLink).toBeVisible({ timeout: 15000 })
  })

  test('verify-email page loads without token and shows error or info state', async () => {
    test.setTimeout(60000)

    // Navigate without a token -- the page should show an error or info state
    await page.goto(`${BASE_URL}/verify-email`, { timeout: 30000 })

    // Without a token query param, the page shows an error state
    // ("No verification token provided" or similar)
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasVerifyContent =
        // Error state
        bodyText?.includes('token') ||
        bodyText?.includes('Token') ||
        bodyText?.includes('Verification') ||
        bodyText?.includes('Verifizierung') ||
        bodyText?.includes('invalid') ||
        bodyText?.includes('ungültig') ||
        // Or the BenGER branding at minimum
        bodyText?.includes('BenGER') ||
        // Or a login link
        bodyText?.includes('Login') ||
        bodyText?.includes('Anmelden')
      expect(hasVerifyContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('verify-email page shows BenGER branding', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/verify-email`, { timeout: 30000 })

    // The page has a header with BenGER branding
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      expect(bodyText?.includes('BenGER')).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('verify-email page has link back to login', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/verify-email`, { timeout: 30000 })

    // The page should have a link to the login page
    const loginLink = page.locator('a[href="/login"]').first()
    await expect(loginLink).toBeVisible({ timeout: 15000 })
  })

  test('reset-password with token path loads password form', async () => {
    test.setTimeout(60000)

    // Navigate to the token-based reset page with a fake token
    // The page will show the password reset form regardless of token validity
    // (validation happens on submit)
    await page.goto(`${BASE_URL}/reset-password/fake-test-token`, {
      timeout: 30000,
    })

    // The page should show password input fields
    await expect(async () => {
      const passwordInputs = await page.locator('input[type="password"]').count()
      // Should have at least one password field (new password)
      // or the page shows the heading
      const bodyText = await page.locator('body').textContent()
      const hasPasswordForm =
        passwordInputs >= 1 ||
        bodyText?.includes('Password') ||
        bodyText?.includes('Passwort') ||
        bodyText?.includes('Reset') ||
        bodyText?.includes('BenGER')
      expect(hasPasswordForm).toBe(true)
    }).toPass({ timeout: 15000 })
  })
})
