/**
 * E2E: per-organization Moodle/LTI panel on the organizations page (the
 * OrgLtiPanel slot) against the LIVE local dev stack. Gated behind
 * LTI_E2E=1 like the other lti specs — it needs the extended edition and
 * cleans up through the dev database container.
 *
 * Run:
 *   LTI_E2E=1 npx playwright test e2e/lti/org-lti-admin.spec.ts --reporter=line
 *
 * Entry point: the organizations toolbar mounts the slot with `hideTrigger`
 * and opens it from its "Mehr" menu (`org-more-button` → `org-lti-button`).
 * The slot's own trigger and status badge (`lti-org-open`,
 * `lti-org-status`) therefore never render on this page; the connection
 * state is read from the panel itself (empty state, the per-registration
 * switch's `aria-checked`) and cross-checked through the admin API.
 *
 * Journey (serial): open the org page as superadmin → the panel shows the
 * empty state for a fresh org → create a registration through the panel (no
 * org field — it is pinned to the selected org) → its switch is on and the
 * API reports "active" → disable via the fail-closed toggle (confirm step) →
 * switch off, API "disabled" → re-enable. The panel has no delete (by
 * design), so afterAll removes the E2E rows via psql (cascade covers
 * deployments).
 */
import { BrowserContext, expect, Page, test } from '@playwright/test'

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

  /** Open the organizations tab with our org selected via the ?org= param. */
  const gotoOrgTab = async () => {
    await gotoWithRetry(
      page,
      `${ADMIN_BASE}/users-organizations?org=${organizationId}`,
    )
    // Superadmins land on the Global Users tab by default; the ?org= param
    // only takes effect inside the Organizations tab.
    await page
      .getByRole('tab', { name: /Organisationen|Organizations/ })
      .click()
  }

  /** Open the panel through the toolbar's "Mehr" menu and wait for its
   *  registrations to load (the "new" button renders only after loading). */
  const openPanel = async () => {
    await gotoOrgTab()
    const more = page.getByTestId('org-more-button')
    await expect(more).toBeVisible({ timeout: 20_000 })
    await more.click()
    await page.getByTestId('org-lti-button').click()
    await expect(page.getByTestId('lti-org-close')).toBeVisible()
    await expect(page.getByTestId('lti-org-new')).toBeVisible({
      timeout: 20_000,
    })
  }

  /** The registration's enable/disable switch (role="switch"). */
  const registrationSwitch = () =>
    page.getByTestId(`lti-org-toggle-${registrationId}`)

  /** The registration's status as the admin API reports it. */
  const apiStatus = async () => {
    const rows = await (
      await page.request.get(
        `${ADMIN_BASE}/api/admin/lti/registrations?organization_id=${organizationId}`,
      )
    ).json()
    return rows.find((r: { id: string }) => r.id === registrationId)?.status
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
        display_name: `E2E LTI Org ${runId}`,
        slug: `e2e-lti-org-${runId}`,
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
      `DELETE FROM lti_platform_registrations WHERE issuer = '${E2E_ISSUER}'`,
    )
    if (organizationId) {
      await page.request
        .delete(`${ADMIN_BASE}/api/organizations/${organizationId}`)
        .catch(() => undefined)
    }
    await context?.close()
  })

  test('shows the empty state for an org without registrations', async () => {
    await openPanel()

    await expect(page.getByRole('dialog')).toContainText(
      /noch mit keiner Lernplattform verbunden|not connected to any learning platform/,
    )
    await expect(page.locator('[data-testid^="lti-org-reg-"]')).toHaveCount(0)
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
      `${E2E_ISSUER}/mod/lti/auth.php`,
    )

    await page.getByTestId('lti-form-submit').click()

    // The new registration appears as a card in the panel...
    await expect(
      page
        .locator('[data-testid^="lti-org-reg-"]')
        .filter({ hasText: clientId }),
    ).toBeVisible({ timeout: 20_000 })

    // ...bound to OUR org (API cross-check) and active right away.
    const registrations = await (
      await page.request.get(
        `${ADMIN_BASE}/api/admin/lti/registrations?organization_id=${organizationId}`,
      )
    ).json()
    const mine = registrations.find(
      (registration: { client_id: string }) =>
        registration.client_id === clientId,
    )
    expect(mine, 'registration listed under the panel org').toBeTruthy()
    expect(mine.organization_id).toBe(organizationId)
    expect(mine.status).toBe('active')
    registrationId = mine.id

    // The card's switch reflects the active connection.
    await expect(registrationSwitch()).toHaveAttribute('aria-checked', 'true')
  })

  test('disable toggle is fail-closed behind a confirm step', async () => {
    const toggle = registrationSwitch()
    await toggle.click()

    // Nothing changes until the confirm step is answered.
    const confirm = page.getByTestId(`lti-org-confirm-${registrationId}`)
    await expect(confirm).toBeVisible()
    await page.getByTestId(`lti-org-confirm-no-${registrationId}`).click()
    await expect(confirm).toHaveCount(0)
    await expect(toggle).toHaveAttribute('aria-checked', 'true')
    expect(await apiStatus()).toBe('active')

    // Confirmed disable flips the switch and persists.
    await toggle.click()
    await page.getByTestId(`lti-org-confirm-yes-${registrationId}`).click()
    await expect(toggle).toHaveAttribute('aria-checked', 'false', {
      timeout: 10_000,
    })
    expect(await apiStatus()).toBe('disabled')
  })

  test('re-enable restores the connection', async () => {
    const toggle = registrationSwitch()
    await toggle.click()
    await page.getByTestId(`lti-org-confirm-yes-${registrationId}`).click()
    await expect(toggle).toHaveAttribute('aria-checked', 'true', {
      timeout: 10_000,
    })
    expect(await apiStatus()).toBe('active')
  })
})
