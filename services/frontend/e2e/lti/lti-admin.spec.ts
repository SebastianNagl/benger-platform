/**
 * E2E: superadmin LTI registrations console (/admin/lti) against the LIVE
 * local dev stack (issue #61). Gated behind LTI_E2E=1 like the launch spec
 * — it needs the dev stack's seeded state and cleans up through the dev
 * database container.
 *
 * Run:
 *   LTI_E2E=1 PLAYWRIGHT_BASE_URL=http://vertretbar.localhost \
 *     npx playwright test e2e/lti --reporter=line
 *
 * Journey (serial): open the panel → create a registration for a fake
 * Moodle (URL prefill helper derives the three Moodle endpoints from the
 * issuer) → verify the tool-config panel's copy-paste URLs → add a
 * deployment id → disable the registration via edit. The registrations
 * admin UI has no delete, so afterAll removes the E2E rows via psql in the
 * dev DB container (cascade covers the deployments), keeping the dev DB
 * tidy across runs.
 *
 * The panel ships in the extended edition (LtiRegistrationsAdmin slot),
 * hence the @extended tag per suite convention.
 */
import {
  BrowserContext,
  expect,
  Page,
  test,
} from '@playwright/test'

import { TestHelpers } from '../helpers/test-helpers'
import { bengerDbSql, gotoWithRetry, warmAppRoutes } from './moodle-helpers'

/** The registrations console lives on the admin host, not the student host. */
const ADMIN_BASE = process.env.LTI_E2E_ADMIN_URL || 'http://benger.localhost'

const E2E_ISSUER = 'https://moodle.e2e.invalid'

test.describe.configure({ mode: 'serial' })

test.describe('LTI registrations admin @extended', () => {
  test.skip(!process.env.LTI_E2E, 'needs the lti-dev Moodle harness (LTI_E2E=1)')

  // issuer+client_id is globally unique — a per-run client id keeps the spec
  // re-runnable even when an aborted earlier run left its row behind.
  const runId = Date.now().toString(36)
  const clientId = `e2e-client-${runId}`
  const registrationName = 'E2E Uni'

  let context: BrowserContext | undefined
  let page: Page
  let registrationId: string

  /** The created registration's main table row. */
  const registrationRow = () =>
    page.locator('tr').filter({ hasText: clientId }).first()

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
    await warmAppRoutes(page, ADMIN_BASE, ['/login', '/admin/lti'])

    const helpers = new TestHelpers(page)
    await helpers.login('admin', 'admin')
  })

  test.afterAll(async () => {
    // The UI (deliberately) has no registration delete — tidy the dev DB
    // directly; ON DELETE CASCADE removes the deployments. The fixed fake
    // issuer also sweeps strays left by earlier aborted runs.
    bengerDbSql(
      `DELETE FROM lti_platform_registrations WHERE issuer = '${E2E_ISSUER}'`
    )
    await context?.close()
  })

  test('renders the registrations panel for a superadmin', async () => {
    await gotoWithRetry(page, `${ADMIN_BASE}/admin/lti`)

    await expect(
      page.getByRole('heading', { name: 'LTI-Registrierungen (Moodle)' })
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      page.getByRole('heading', { name: 'Registrierungen', exact: true })
    ).toBeVisible()
    // The dev harness seeds one registration, so the table (not the empty
    // state) is showing.
    await expect(page.getByRole('button', { name: 'Neue Registrierung' })).toBeVisible()
  })

  test('creates a registration, deriving the Moodle URLs from the issuer', async () => {
    // Any existing organization works for the fake university; the seeded
    // lti-dev registration's org is guaranteed by the harness.
    const listResponse = await page.request.get(
      `${ADMIN_BASE}/api/admin/lti/registrations`
    )
    expect(listResponse.ok(), await listResponse.text()).toBe(true)
    const registrations = await listResponse.json()
    const organizationId = registrations[0]?.organization_id
    expect(
      organizationId,
      'the lti-dev harness must have seeded a registration to borrow an org id from'
    ).toBeTruthy()

    await page.getByRole('button', { name: 'Neue Registrierung' }).click()
    await expect(
      page.getByRole('heading', { name: 'Neue Registrierung' })
    ).toBeVisible()

    await page.getByTestId('lti-form-organization_id').fill(organizationId)
    await page.getByTestId('lti-form-name').fill(registrationName)
    await page.getByTestId('lti-form-issuer').fill(E2E_ISSUER)
    await page.getByTestId('lti-form-client_id').fill(clientId)

    // The prefill helper derives Moodle's three endpoints from the issuer.
    await page.getByTestId('lti-form-moodle-defaults').click()
    await expect(page.getByTestId('lti-form-auth_login_url')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/auth.php`
    )
    await expect(page.getByTestId('lti-form-auth_token_url')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/token.php`
    )
    await expect(page.getByTestId('lti-form-jwks_uri')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/certs.php`
    )

    await page.getByTestId('lti-form-submit').click()

    // The new registration appears in the table, active and deployment-less.
    const row = registrationRow()
    await expect(row).toBeVisible({ timeout: 20_000 })
    await expect(row).toContainText(registrationName)
    await expect(row).toContainText(E2E_ISSUER)
    await expect(row).toContainText('active')

    const created = await (
      await page.request.get(`${ADMIN_BASE}/api/admin/lti/registrations`)
    ).json()
    registrationId = created.find(
      (registration: { client_id: string }) => registration.client_id === clientId
    )?.id
    expect(registrationId, 'created registration present in the API list').toBeTruthy()
  })

  test('tool-config panel shows the tool URLs for the Moodle admin', async () => {
    await page.getByTestId(`lti-reg-config-${registrationId}`).click()
    await expect(
      page.getByRole('heading', { name: 'Tool-Konfiguration' })
    ).toBeVisible()

    // Copy-paste values derive from the admin host's origin.
    const expected: Array<[string, string]> = [
      ['Initiate-Login-URL', `${ADMIN_BASE}/api/lti/login`],
      ['Weiterleitungs-URL (Launch)', `${ADMIN_BASE}/api/lti/launch`],
      ['Öffentliche JWKS-URL', `${ADMIN_BASE}/api/lti/jwks`],
    ]
    for (const [label, url] of expected) {
      // Innermost div containing the row's copy button = the CopyField row;
      // its readonly input carries the URL.
      const fieldRow = page
        .locator('div')
        .filter({ has: page.getByTestId(`lti-copy-${label}`) })
        .last()
      await expect(fieldRow.locator('input')).toHaveValue(url, {
        timeout: 15_000,
      })
    }
  })

  test('adds a deployment id', async () => {
    await page.getByTestId(`lti-reg-deployments-${registrationId}`).click()
    await expect(
      page.getByRole('heading', { name: 'Deployments', exact: true })
    ).toBeVisible()

    await page.getByTestId('lti-deployment-new-id').fill('e2e-dep-1')
    await page.getByTestId('lti-deployment-add').click()
    // Success signal that doesn't depend on the reloaded list: the editor
    // clears its input once the POST has landed.
    await expect(page.getByTestId('lti-deployment-new-id')).toHaveValue('', {
      timeout: 15_000,
    })

    // Assert persistence against a fresh page load: the platform
    // apiClient's ~30s GET cache served the panel's in-place reload a
    // pre-mutation registrations list (bug found by this spec; fixed in
    // benger-extended `feat/lti-e2e-testids` by invalidating the admin-lti
    // cache on mutation), so an in-place assertion would tie the spec to
    // whichever build is running.
    await gotoWithRetry(page, `${ADMIN_BASE}/admin/lti`)
    const row = registrationRow()
    await expect(row).toBeVisible({ timeout: 20_000 })
    // The row's deployment counter reflects the addition …
    await expect(row.locator('td').nth(4)).toHaveText('1')
    // … and the deployments panel lists the new id.
    await page.getByTestId(`lti-reg-deployments-${registrationId}`).click()
    await expect(
      page.locator('li').filter({ hasText: 'e2e-dep-1' })
    ).toBeVisible({ timeout: 15_000 })
  })

  test('disables the registration via edit', async () => {
    await page.getByTestId(`lti-reg-edit-${registrationId}`).click()
    await expect(
      page.getByRole('heading', { name: 'Registrierung bearbeiten' })
    ).toBeVisible()

    await page.getByTestId('lti-form-status').selectOption('disabled')
    await page.getByTestId('lti-form-submit').click()
    // The edit panel closes once the PUT has landed.
    await expect(
      page.getByRole('heading', { name: 'Registrierung bearbeiten' })
    ).toBeHidden({ timeout: 15_000 })

    // Fresh page load — same GET-cache staleness caveat as above.
    await gotoWithRetry(page, `${ADMIN_BASE}/admin/lti`)
    await expect(registrationRow()).toContainText('disabled', {
      timeout: 20_000,
    })
    await expect(registrationRow()).not.toContainText(/\bactive\b/)
  })
})
