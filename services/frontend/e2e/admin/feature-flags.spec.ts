/**
 * E2E: superadmin feature flag console (/admin/feature-flags).
 *
 * The console ships in the extended edition (FeatureFlagsAdmin slot) and
 * the flags it switches gate extended features, hence the @extended tag per
 * suite convention.
 *
 * Journey (serial) on synthetic_generation: switch it off in the console ->
 * the caller's /me reports it off and the generator endpoint answers 404
 * feature_disabled -> switch it to the allowlist and add the admin user ->
 * it is on again for that user only. afterAll puts the flag back to its
 * default (everyone, no targets) through the API, so a failed step does not
 * leave the generator switched off on the stack.
 */
import { BrowserContext, expect, Page, test } from '@playwright/test'

import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'
const FLAG = 'synthetic_generation'

test.describe.configure({ mode: 'serial' })

test.describe('Feature flag console @extended', () => {
  let context: BrowserContext | undefined
  let page: Page
  let adminId: string

  /** The caller's evaluated flags. */
  const myFlags = () =>
    page.evaluate(async () => {
      const resp = await fetch('/api/ext/feature-flags/me', {
        credentials: 'include',
      })
      return (await resp.json()) as Record<string, boolean>
    })

  /** Restore the registry default: everyone, empty allowlist. */
  const resetFlag = () =>
    page.evaluate(async (flag) => {
      const list = await (
        await fetch('/api/ext/feature-flags', { credentials: 'include' })
      ).json()
      const row = list.find((f: { name: string }) => f.name === flag)
      for (const target of row?.targets ?? []) {
        await fetch(`/api/ext/feature-flags/${flag}/targets/${target.id}`, {
          method: 'DELETE',
          credentials: 'include',
        })
      }
      await fetch(`/api/ext/feature-flags/${flag}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: 'everyone' }),
      })
    }, FLAG)

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({ baseURL: BASE_URL })
    await context.addInitScript(() => {
      try {
        sessionStorage.setItem('e2e_test_mode', 'true')
      } catch {
        /* ignore */
      }
    })
    page = await context.newPage()
    await new TestHelpers(page).login('admin', 'admin')
    adminId = await page.evaluate(async () => {
      const resp = await fetch('/api/auth/me', { credentials: 'include' })
      return (await resp.json()).id as string
    })
    await resetFlag()
  })

  test.afterAll(async () => {
    if (page) await resetFlag()
    await context?.close()
  })

  test('lists the registered flags with their states', async () => {
    await page.goto('/admin/feature-flags', { timeout: 30000 })
    await expect(page.getByTestId('feature-flags-admin')).toBeVisible({
      timeout: 30000,
    })
    for (const name of [
      'rubric_generation',
      'synthetic_generation',
      'billing_ui',
      'graded_review',
      'plan_modal',
    ]) {
      await expect(page.getByTestId(`ff-row-${name}`)).toBeVisible()
    }
    await expect(page.getByTestId(`ff-state-${FLAG}-everyone`)).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  test('switching a flag off closes the feature for the caller', async () => {
    await page.getByTestId(`ff-state-${FLAG}-off`).click()
    await expect(page.getByTestId(`ff-state-${FLAG}-off`)).toHaveAttribute(
      'aria-checked',
      'true',
    )

    await expect.poll(async () => (await myFlags())[FLAG]).toBe(false)
    const blocked = await page.evaluate(async () => {
      const resp = await fetch('/api/student/synthetic', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      })
      return { status: resp.status, body: await resp.json() }
    })
    expect(blocked.status).toBe(404)
    expect(blocked.body.detail.code).toBe('feature_disabled')
    expect(blocked.body.detail.flag).toBe(FLAG)
  })

  test('an allowlisted user gets the feature back', async () => {
    await page.getByTestId(`ff-state-${FLAG}-allowlist`).click()
    await expect(page.getByTestId(`ff-allowlist-${FLAG}`)).toBeVisible()
    // An empty allowlist opens the feature for nobody.
    await expect.poll(async () => (await myFlags())[FLAG]).toBe(false)

    await page.getByTestId(`ff-user-search-${FLAG}`).fill('admin')
    const option = page.getByTestId(`ff-user-option-${adminId}`)
    await expect(option).toBeVisible({ timeout: 15000 })
    await option.click()

    const allowlist = page.getByTestId(`ff-allowlist-${FLAG}`)
    await expect(
      allowlist.locator('[data-testid^="ff-target-remove-"]'),
    ).toHaveCount(1)
    await expect.poll(async () => (await myFlags())[FLAG]).toBe(true)
  })
})
