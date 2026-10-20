/**
 * E2E: superadmin LTI registrations console (/admin/lti), issue #61.
 *
 * Self-contained: it creates its own organization and registration through
 * the UI/API and removes both afterwards, so it runs on any database with a
 * superadmin `admin`/`admin`. No LMS is involved (the issuer is a fake
 * `.invalid` host). Runs against the dev stack or the test stack, see
 * lti-helpers.ts for the environment:
 *
 *   npx playwright test e2e/lti/lti-admin.spec.ts --project=lti   # dev
 *   make test-e2e GREP=@extended                                  # test stack
 *
 * Journey (serial): open the panel -> create a registration (URL prefill
 * helper derives the three Moodle endpoints from the issuer) -> verify the
 * tool-config panel's copy-paste URLs -> add a deployment id -> disable the
 * registration via edit. The registrations admin UI only deletes switched-off
 * connections, so afterAll removes the E2E rows directly (cascade covers the
 * deployments), which also tidies up after a failed step.
 *
 * The panel ships in the extended edition (LtiRegistrationsAdmin slot),
 * hence the @extended tag per suite convention.
 */
import { BrowserContext, expect, Page, test } from '@playwright/test'

import { TestHelpers } from '../helpers/test-helpers'
import {
  ADMIN_BASE,
  cleanupLtiFixtures,
  createE2eOrganization,
  disableAutoLogin,
  germanCopy,
  gotoWithRetry,
  warmAppRoutes,
} from './lti-helpers'

const E2E_ISSUER = 'https://moodle.e2e.invalid'

test.describe.configure({ mode: 'serial' })

test.describe('LTI registrations admin @extended', () => {
  // issuer+client_id is globally unique: a per-run client id keeps the spec
  // re-runnable even when an aborted earlier run left its row behind.
  const runId = Date.now().toString(36)
  const clientId = `e2e-client-${runId}`
  const registrationName = `E2E Uni ${runId}`

  let context: BrowserContext | undefined
  let page: Page
  let organizationId: string | undefined
  let registrationId: string

  const registrationRow = () =>
    page.getByTestId(`lti-reg-row-${registrationId}`)
  const registrationStatus = () =>
    page.getByTestId(`lti-reg-status-${registrationId}`)

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({ baseURL: ADMIN_BASE })
    await disableAutoLogin(context)
    page = await context.newPage()
    await warmAppRoutes(page, ADMIN_BASE, ['/login', '/admin/lti'])

    await new TestHelpers(page).login('admin', 'admin')
    organizationId = await createE2eOrganization(page.request, runId, 'admin')
  })

  test.afterAll(async () => {
    // The fixed fake issuer also sweeps strays left by earlier aborted runs.
    await cleanupLtiFixtures(page?.request, E2E_ISSUER, organizationId)
    await context?.close()
  })

  test('renders the registrations panel for a superadmin', async () => {
    await gotoWithRetry(page, `${ADMIN_BASE}/admin/lti`)

    await expect(page.getByTestId('lti-admin-title')).toBeVisible({
      timeout: 20_000,
    })
    await expect(page.getByTestId('lti-admin-title')).toHaveText(
      germanCopy('extended.lti.admin.title'),
    )
    await expect(page.getByTestId('lti-admin-registrations')).toBeVisible()
    await expect(page.getByTestId('lti-admin-new')).toBeEnabled()
    // Either the table or the empty state, never a load error.
    await expect(
      page
        .getByTestId('lti-admin-table')
        .or(page.getByTestId('lti-admin-empty')),
    ).toBeVisible({ timeout: 20_000 })
  })

  test('creates a registration, deriving the Moodle URLs from the issuer', async () => {
    await page.getByTestId('lti-admin-new').click()
    const form = page.getByTestId('lti-form-create')
    await expect(form).toBeVisible()

    // Moodle is the default family of a new connection.
    await expect(page.getByTestId('lti-form-lms_family')).toHaveValue('moodle')
    await page.getByTestId('lti-form-organization_id').fill(organizationId!)
    await page.getByTestId('lti-form-name').fill(registrationName)
    await page.getByTestId('lti-form-issuer').fill(E2E_ISSUER)
    await page.getByTestId('lti-form-client_id').fill(clientId)

    // The prefill helper derives Moodle's three endpoints from the issuer.
    await page.getByTestId('lti-form-moodle-defaults').click()
    await expect(page.getByTestId('lti-form-auth_login_url')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/auth.php`,
    )
    await expect(page.getByTestId('lti-form-auth_token_url')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/token.php`,
    )
    await expect(page.getByTestId('lti-form-jwks_uri')).toHaveValue(
      `${E2E_ISSUER}/mod/lti/certs.php`,
    )

    await page.getByTestId('lti-form-submit').click()
    await expect(form).toBeHidden({ timeout: 20_000 })

    // The API lists the new registration under our org, active right away.
    const listResponse = await page.request.get(
      `${ADMIN_BASE}/api/admin/lti/registrations?organization_id=${organizationId}`,
    )
    expect(listResponse.ok(), await listResponse.text()).toBe(true)
    const created = (await listResponse.json()).find(
      (registration: { client_id: string }) =>
        registration.client_id === clientId,
    )
    expect(created, 'created registration present in the API list').toBeTruthy()
    expect(created.organization_id).toBe(organizationId)
    expect(created.status).toBe('active')
    expect(created.lms_family).toBe('moodle')
    registrationId = created.id

    // ...and the table shows it, active and deployment-less.
    const row = registrationRow()
    await expect(row).toBeVisible({ timeout: 20_000 })
    await expect(row).toContainText(registrationName)
    await expect(row).toContainText(E2E_ISSUER)
    await expect(registrationStatus()).toHaveText('active')
    await expect(
      page.getByTestId(`lti-reg-deployment-count-${registrationId}`),
    ).toHaveText('0')
  })

  test('tool-config panel shows the tool URLs for the Moodle admin', async () => {
    await page.getByTestId(`lti-reg-config-${registrationId}`).click()
    await expect(page.getByTestId('lti-tool-config')).toBeVisible()

    // Copy-paste values derive from the connection's tool host (the
    // student host where the deployment has one, else the main host), not
    // from the admin host the page runs on. The API names that base URL.
    const configResponse = await page.request.get(
      `${ADMIN_BASE}/api/admin/lti/registrations/${registrationId}/tool-config`,
    )
    expect(configResponse.ok(), await configResponse.text()).toBe(true)
    const { base_url: toolBase } = await configResponse.json()
    expect(toolBase, 'tool-config names the base URL').toBeTruthy()
    for (const [field, path] of [
      ['login_url', '/api/lti/login'],
      ['launch_url', '/api/lti/launch'],
      ['jwks_url', '/api/lti/jwks'],
    ]) {
      await expect(page.getByTestId(`lti-tool-config-${field}`)).toHaveValue(
        `${toolBase}${path}`,
        { timeout: 15_000 },
      )
    }
  })

  test('adds a deployment id', async () => {
    await page.getByTestId(`lti-reg-deployments-${registrationId}`).click()
    const panel = page.getByTestId('lti-deployments')
    await expect(panel).toBeVisible()
    await expect(page.getByTestId('lti-deployments-empty')).toBeVisible()

    await page.getByTestId('lti-deployment-new-id').fill('e2e-dep-1')
    await page.getByTestId('lti-deployment-add').click()
    // Success signal that doesn't depend on the reloaded list: the editor
    // clears its input once the POST has landed.
    await expect(page.getByTestId('lti-deployment-new-id')).toHaveValue('', {
      timeout: 15_000,
    })

    // Assert persistence against a fresh page load, so the check never
    // depends on the client's GET cache.
    await gotoWithRetry(page, `${ADMIN_BASE}/admin/lti`)
    await expect(registrationRow()).toBeVisible({ timeout: 20_000 })
    await expect(
      page.getByTestId(`lti-reg-deployment-count-${registrationId}`),
    ).toHaveText('1')
    await page.getByTestId(`lti-reg-deployments-${registrationId}`).click()
    await expect(
      page
        .getByTestId('lti-deployments')
        .locator('li', { hasText: 'e2e-dep-1' }),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('disables the registration via edit', async () => {
    await page.getByTestId(`lti-reg-edit-${registrationId}`).click()
    const form = page.getByTestId('lti-form-edit')
    await expect(form).toBeVisible()
    // The organization of an existing connection is read-only.
    await expect(page.getByTestId('lti-form-organization_id')).toBeDisabled()
    await expect(page.getByTestId('lti-form-organization_id')).toHaveValue(
      organizationId!,
    )

    await page.getByTestId('lti-form-status').selectOption('disabled')
    await page.getByTestId('lti-form-submit').click()
    // The edit panel closes once the PUT has landed.
    await expect(form).toBeHidden({ timeout: 15_000 })

    // Fresh page load, same GET-cache caveat as above.
    await gotoWithRetry(page, `${ADMIN_BASE}/admin/lti`)
    await expect(registrationStatus()).toHaveText('disabled', {
      timeout: 20_000,
    })
  })
})
