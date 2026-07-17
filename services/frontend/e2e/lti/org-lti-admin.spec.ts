/**
 * E2E: per-organization Moodle/LTI panel on the organizations page (the
 * OrgLtiPanel slot) against the LIVE local dev stack. Gated behind
 * LTI_E2E=1 like the other lti specs — it needs the extended edition and
 * cleans up through the dev database container.
 *
 * Run:
 *   LTI_E2E=1 npx playwright test e2e/lti/org-lti-admin.spec.ts --reporter=line
 *
 * Journey (serial): open the org page as superadmin → the Moodle button
 * shows "nicht verbunden" for a fresh org → create a registration through
 * the panel (no org field — it is pinned to the selected org) → badge flips
 * to "aktiv" → disable via the fail-closed toggle (confirm step) → badge
 * "deaktiviert" → re-enable. The panel has no delete (by design), so
 * afterAll removes the E2E rows via psql (cascade covers deployments).
 */
import {
  BrowserContext,
  expect,
  Page,
  test,
} from '@playwright/test'

import { TestHelpers } from '../helpers/test-helpers'
import { bengerDbSql, gotoWithRetry, warmAppRoutes } from './moodle-helpers'

/** The organizations page lives on the admin host, not the student host. */
const ADMIN_BASE = process.env.LTI_E2E_ADMIN_URL || 'http://benger.localhost'

const E2E_ISSUER = 'https://moodle.org-panel.e2e.invalid'

test.describe.configure({ mode: 'serial' })

test.describe('Org LTI panel @extended', () => {
  test.skip(!process.env.LTI_E2E, 'needs the lti-dev stack (LTI_E2E=1)')

  // issuer+client_id is globally unique — a per-run client id keeps the
  // spec re-runnable even when an aborted earlier run left its row behind.
  const runId = Date.now().toString(36)
  const clientId = `e2e-org-client-${runId}`
  const registrationName = 'E2E Org-Panel Uni'

  let context: BrowserContext | undefined
  let page: Page
  let organizationId: string
  let registrationId: string

  const openPanel = async () => {
    await gotoWithRetry(page, `${ADMIN_BASE}/users-organizations?org=${organizationId}`)
    const trigger = page.getByTestId('lti-org-open')
    await expect(trigger).toBeVisible({ timeout: 20_000 })
    await trigger.click()
  }

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({ baseURL: ADMIN_BASE })
    // Keep the dev auto-login out of the way (suite convention) — we log in
    // explicitly through the form as the superadmin.
    await context.addInitScript(() => {
      try {
        sessionStorage.setItem('e2e_test_mode', 'true')
      } catch {
        /* ignore */
      }
    })
    page = await context.newPage()
    await warmAppRoutes(page, ADMIN_BASE, ['/login', '/users-organizations'])

    const helpers = new TestHelpers(page)
    await helpers.login('admin', 'admin')

    // A dedicated org keeps the badge assertions deterministic (the seeded
    // orgs may carry registrations from the harness or earlier runs).
    const created = await page.request.post(`${ADMIN_BASE}/api/organizations`, {
      data: {
        name: `E2E LTI Org ${runId}`,
        description: 'Org-LTI-panel e2e — safe to delete',
      },
    })
    expect(created.ok(), await created.text()).toBe(true)
    organizationId = (await created.json()).id
    expect(organizationId).toBeTruthy()
  })

  test.afterAll(async () => {
    // The panel (deliberately) has no registration delete — tidy the dev DB
    // directly; ON DELETE CASCADE removes the deployments. The fixed fake
    // issuer also sweeps strays left by earlier aborted runs.
    bengerDbSql(
      `DELETE FROM lti_platform_registrations WHERE issuer = '${E2E_ISSUER}'`
    )
    if (organizationId) {
      await page.request
        .delete(`${ADMIN_BASE}/api/organizations/${organizationId}`)
        .catch(() => undefined)
    }
    await context?.close()
  })

  test('shows "nicht verbunden" for an org without registrations', async () => {
    await gotoWithRetry(page, `${ADMIN_BASE}/users-organizations?org=${organizationId}`)

    const trigger = page.getByTestId('lti-org-open')
    await expect(trigger).toBeVisible({ timeout: 20_000 })
    await expect(page.getByTestId('lti-org-status')).toContainText(
      'nicht verbunden'
    )
  })

  test('creates a registration pinned to the selected org (no org field)', async () => {
    await openPanel()

    await page.getByTestId('lti-org-new').click()

    // The org is pinned by the panel — the free-text org field of the
    // global console must not render here.
    await expect(page.getByTestId('lti-form-organization_id')).toHaveCount(0)

    await page.getByTestId('lti-form-name').fill(registrationName)
    await page.getByTestId('lti-form-issuer').fill(E2E_ISSUER)
    await page.getByTestId('lti-form-client_id').fill(clientId)

    // The prefill helper derives Moodle's three endpoints from the issuer.
    await page.getByTestId('lti-form-moodle-defaults').click()
    await expect(page.getByTestId('lti-form-auth_login_url')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/auth.php`
    )

    await page.getByTestId('lti-form-submit').click()

    // The new registration appears as a card in the panel...
    await expect(
      page.locator('[data-testid^="lti-org-reg-"]').filter({ hasText: clientId })
    ).toBeVisible({ timeout: 20_000 })

    // ...bound to OUR org (API cross-check), and the badge flips to aktiv.
    const registrations = await (
      await page.request.get(
        `${ADMIN_BASE}/api/admin/lti/registrations?organization_id=${organizationId}`
      )
    ).json()
    const mine = registrations.find(
      (registration: { client_id: string }) =>
        registration.client_id === clientId
    )
    expect(mine, 'registration listed under the panel org').toBeTruthy()
    expect(mine.organization_id).toBe(organizationId)
    registrationId = mine.id

    await expect(page.getByTestId('lti-org-status')).toContainText('aktiv')
  })

  test('disable toggle is fail-closed behind a confirm step', async () => {
    const toggle = page.getByTestId(`lti-org-toggle-${registrationId}`)
    await toggle.click()

    // Nothing changes until the confirm step is answered.
    const confirm = page.getByTestId(`lti-org-confirm-${registrationId}`)
    await expect(confirm).toBeVisible()
    await page.getByTestId(`lti-org-confirm-no-${registrationId}`).click()
    await expect(page.getByTestId('lti-org-status')).toContainText('aktiv')

    // Confirmed disable flips the badge and persists.
    await toggle.click()
    await page.getByTestId(`lti-org-confirm-yes-${registrationId}`).click()
    await expect(page.getByTestId('lti-org-status')).toContainText(
      'deaktiviert',
      { timeout: 10_000 }
    )

    const after = await (
      await page.request.get(
        `${ADMIN_BASE}/api/admin/lti/registrations?organization_id=${organizationId}`
      )
    ).json()
    expect(after.find((r: { id: string }) => r.id === registrationId)?.status).toBe(
      'disabled'
    )
  })

  test('re-enable restores the connection', async () => {
    await page.getByTestId(`lti-org-toggle-${registrationId}`).click()
    await page.getByTestId(`lti-org-confirm-yes-${registrationId}`).click()
    await expect(page.getByTestId('lti-org-status')).toContainText('aktiv', {
      timeout: 10_000,
    })
  })
})
