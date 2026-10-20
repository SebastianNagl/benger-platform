/**
 * E2E: per-organization LMS panel on the organizations page (the
 * OrgLtiPanel slot).
 *
 * Self-contained: it creates its own organization and removes it and its
 * registrations afterwards. No LMS is involved (fake `.invalid` issuer).
 * Runs against the dev stack or the test stack, see lti-helpers.ts:
 *
 *   npx playwright test e2e/lti/org-lti-admin.spec.ts --project=lti   # dev
 *   make test-e2e GREP=@extended                                      # test stack
 *
 * Entry point: the organizations toolbar mounts the slot with `hideTrigger`
 * and opens it from its "Mehr" menu (`org-more-button` -> `org-lti-button`).
 * "Connect" (`lti-org-new`) opens the connect wizard; Moodle there means a
 * self-registration invite link, so the manual form is reached through the
 * "other" choice (`lti-connect-other`), which is the path this spec drives.
 *
 * Journey (serial): the panel shows the empty state for a fresh org ->
 * create a registration through the wizard's manual form (no org field, it
 * is pinned to the selected org) -> its switch is on and the API reports
 * "active" -> disable via the fail-closed toggle (confirm step) -> switch
 * off, API "disabled" -> re-enable. The panel only deletes switched-off
 * connections, so afterAll removes the E2E rows directly (cascade covers
 * deployments), which also works after a failed step.
 */
import { BrowserContext, expect, Page, test } from '@playwright/test'

import { TestHelpers } from '../helpers/test-helpers'
import {
  ADMIN_BASE,
  cleanupLtiFixtures,
  createE2eOrganization,
  disableAutoLogin,
  gotoWithRetry,
  warmAppRoutes,
} from './lti-helpers'

const E2E_ISSUER = 'https://moodle.org-panel.e2e.invalid'

test.describe.configure({ mode: 'serial' })

test.describe('Org LTI panel @extended', () => {
  // issuer+client_id is globally unique: a per-run client id keeps the
  // spec re-runnable even when an aborted earlier run left its row behind.
  const runId = Date.now().toString(36)
  const clientId = `e2e-org-client-${runId}`
  const registrationName = `E2E Org-Panel Uni ${runId}`

  let context: BrowserContext | undefined
  let page: Page
  let organizationId: string | undefined
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
   *  registrations to load (the connect button renders only after loading). */
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

  /** The org's registrations as the admin API reports them. */
  const apiRegistrations = async () => {
    const response = await page.request.get(
      `${ADMIN_BASE}/api/admin/lti/registrations?organization_id=${organizationId}`,
    )
    expect(response.ok(), await response.text()).toBe(true)
    return (await response.json()) as Array<{
      id: string
      client_id: string
      organization_id: string
      status: string
    }>
  }

  const apiStatus = async () =>
    (await apiRegistrations()).find((r) => r.id === registrationId)?.status

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({ baseURL: ADMIN_BASE })
    await disableAutoLogin(context)
    page = await context.newPage()
    await warmAppRoutes(page, ADMIN_BASE, ['/login', '/users-organizations'])

    await new TestHelpers(page).login('admin', 'admin')
    // A dedicated org keeps the assertions deterministic (seeded orgs may
    // carry registrations from the dev harness or earlier runs).
    organizationId = await createE2eOrganization(page.request, runId, 'org')
  })

  test.afterAll(async () => {
    // The fixed fake issuer also sweeps strays left by earlier aborted runs.
    await cleanupLtiFixtures(page?.request, E2E_ISSUER, organizationId)
    await context?.close()
  })

  test('shows the empty state for an org without registrations', async () => {
    await openPanel()

    await expect(page.getByTestId('lti-org-empty')).toBeVisible()
    await expect(page.locator('[data-testid^="lti-org-reg-"]')).toHaveCount(0)
    expect(await apiRegistrations()).toHaveLength(0)
  })

  test('creates a registration pinned to the selected org (no org field)', async () => {
    await openPanel()

    // Connect opens the wizard on the LMS choice.
    await page.getByTestId('lti-org-new').click()
    await expect(page.getByTestId('lti-connect')).toBeVisible()
    await expect(page.getByTestId('lti-connect-moodle')).toBeVisible()
    await expect(page.getByTestId('lti-connect-ilias')).toBeVisible()
    await page.getByTestId('lti-connect-other').click()

    const form = page.getByTestId('lti-form-create')
    await expect(form).toBeVisible()
    // The org is pinned by the panel: the free-text org field of the
    // global console must not render here.
    await expect(page.getByTestId('lti-form-organization_id')).toHaveCount(0)

    await page.getByTestId('lti-form-name').fill(registrationName)
    await page.getByTestId('lti-form-issuer').fill(E2E_ISSUER)
    await page.getByTestId('lti-form-client_id').fill(clientId)

    // The prefill helper derives Moodle's endpoints from the issuer.
    await expect(page.getByTestId('lti-form-lms_family')).toHaveValue('moodle')
    await page.getByTestId('lti-form-moodle-defaults').click()
    await expect(page.getByTestId('lti-form-auth_login_url')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/auth.php`,
    )

    await page.getByTestId('lti-form-submit').click()
    await expect(form).toBeHidden({ timeout: 20_000 })

    // Bound to OUR org (API cross-check) and active right away.
    const mine = (await apiRegistrations()).find(
      (registration) => registration.client_id === clientId,
    )
    expect(mine, 'registration listed under the panel org').toBeTruthy()
    expect(mine!.organization_id).toBe(organizationId)
    expect(mine!.status).toBe('active')
    registrationId = mine!.id

    // The new registration appears as a card in the panel, switch on.
    await expect(
      page.getByTestId(`lti-org-reg-${registrationId}`),
    ).toContainText(clientId, { timeout: 20_000 })
    await expect(page.getByTestId('lti-org-empty')).toHaveCount(0)
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
    await expect(
      page.getByTestId(`lti-org-reg-off-${registrationId}`),
    ).toBeVisible()
    await expect.poll(apiStatus).toBe('disabled')
  })

  test('re-enable restores the connection', async () => {
    const toggle = registrationSwitch()
    await toggle.click()
    await page.getByTestId(`lti-org-confirm-yes-${registrationId}`).click()
    await expect(toggle).toHaveAttribute('aria-checked', 'true', {
      timeout: 10_000,
    })
    await expect.poll(apiStatus).toBe('active')
  })
})
