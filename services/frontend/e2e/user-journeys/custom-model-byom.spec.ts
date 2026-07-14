/**
 * E2E tests for the BYOM (bring-your-own-model) journey:
 * register a custom model → share it with an organization → store a
 * per-user credential (connection test route-intercepted so no real
 * endpoint is contacted) → the model shows up in the generation picker's
 * Custom section.
 *
 * NOTE: written against the /custom-models backend contract; the /test
 * call is the only intercepted route - register/visibility/credential go
 * against the real API. Requires a live stack (make dev) and the admin
 * dev user. This spec was authored alongside the frontend implementation
 * and has not been executed yet - do a live run before relying on it in CI.
 */

import { expect, Page, test } from '@playwright/test'
import { TestFixtures } from '../helpers/test-fixtures'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Custom Model (BYOM) journey', () => {
  let page: Page
  let helpers: TestHelpers
  let fixtures: TestFixtures
  let testProjectId: string | null = null
  let customModelId: string | null = null

  const modelName = `E2E BYOM ${Date.now()}`
  const baseUrl = 'https://byom-e2e.invalid/v1'

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    fixtures = new TestFixtures(page, helpers)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test.afterEach(async () => {
    // Cleanup: delete the custom model and the test project via the API.
    if (customModelId) {
      await page.evaluate(async (id) => {
        await fetch(`/api/custom-models/${id}`, {
          method: 'DELETE',
          credentials: 'include',
        })
      }, customModelId)
      customModelId = null
    }
    if (testProjectId) {
      try {
        await fixtures.cleanup(testProjectId)
      } catch {
        console.log('Cleanup failed, project may already be deleted')
      }
      testProjectId = null
    }
  })

  test('register → share with org → add credential → appears in generation picker', async () => {
    test.setTimeout(180000)

    // ── 1. Register the model on /settings/models ──────────────────────
    await page.goto(`${BASE_URL}/settings/models`, { timeout: 30000 })
    await expect(
      page.getByTestId('custom-model-register-button')
    ).toBeVisible({ timeout: 30000 })

    await page.getByTestId('custom-model-register-button').click()
    await expect(page.getByTestId('custom-model-form-modal')).toBeVisible()

    await page.getByTestId('custom-model-name-input').fill(modelName)
    await page.getByTestId('custom-model-base-url-input').fill(baseUrl)
    await page
      .getByTestId('custom-model-endpoint-name-input')
      .fill('llama-3.3-70b-instruct')

    // Capture the created id from the POST response (201 per contract, but
    // stay tolerant of proxies normalizing to 200).
    const createResponsePromise = page.waitForResponse(
      (res) =>
        new URL(res.url()).pathname.endsWith('/custom-models') &&
        res.request().method() === 'POST' &&
        res.ok()
    )
    await page.getByTestId('custom-model-form-submit').click()
    const createResponse = await createResponsePromise
    const created = await createResponse.json()
    customModelId = created.id
    expect(customModelId).toBeTruthy()

    // Success step offers a connection test; close instead (endpoint is fake).
    await expect(
      page.getByTestId('custom-model-form-success')
    ).toBeVisible({ timeout: 15000 })
    await page.getByTestId('custom-model-form-close-button').click()

    // The new model shows up in "Meine Modelle".
    await expect(
      page.getByTestId(`custom-model-row-${customModelId}`)
    ).toBeVisible({ timeout: 15000 })

    // ── 2. Share the model with an organization ────────────────────────
    await page
      .getByTestId(`custom-model-visibility-${customModelId}`)
      .click()
    await expect(
      page.getByTestId(`custom-model-visibility-panel-${customModelId}`)
    ).toBeVisible({ timeout: 10000 })

    await page.getByTestId('model-visibility-organization-option').click()

    // Pick the first available organization checkbox. If the dev stack has
    // no organizations, fall back to public so the journey still proceeds.
    const orgCheckboxes = page.locator(
      '[data-testid^="model-permissions-organization-checkbox-"]'
    )
    if ((await orgCheckboxes.count()) > 0) {
      await orgCheckboxes.first().check()
    } else {
      console.log('No organizations available - falling back to public')
      await page.getByTestId('model-visibility-public-option').click()
    }

    const visibilityResponsePromise = page.waitForResponse(
      (res) =>
        res.url().includes(`/api/custom-models/${customModelId}/visibility`) &&
        res.request().method() === 'PATCH' &&
        res.ok()
    )
    await page.getByTestId('model-permissions-save-button').click()
    await visibilityResponsePromise

    // ── 3. Store a per-user credential (test call intercepted) ─────────
    // Intercept the connection test so no request leaves toward the fake
    // endpoint; the credential PUT itself goes against the real API.
    await page.route(`**/api/custom-models/${customModelId}/test`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          message: 'Connection successful (intercepted)',
        }),
      })
    )

    // Expand the row to reveal the credential section (the visibility save
    // collapsed the panel but the row may still be expanded - make sure).
    const detail = page.getByTestId(`custom-model-detail-${customModelId}`)
    if (!(await detail.isVisible().catch(() => false))) {
      await page
        .getByTestId(`custom-model-expand-${customModelId}`)
        .click()
    }
    await expect(detail).toBeVisible({ timeout: 10000 })

    await page.getByTestId('credential-key-input').fill('sk-e2e-test-key')
    await page.getByTestId('credential-test-button').click()
    await expect(page.getByTestId('credential-test-result')).toContainText(
      'Connection successful',
      { timeout: 10000 }
    )

    const credentialPutPromise = page.waitForResponse(
      (res) =>
        res.url().includes(`/api/custom-models/${customModelId}/credential`) &&
        res.request().method() === 'PUT' &&
        res.ok()
    )
    await page.getByTestId('credential-save-button').click()
    await credentialPutPromise

    await expect(
      page.getByTestId('credential-status-pill')
    ).toContainText(/Hinterlegt|Configured/, { timeout: 10000 })

    await page.unroute(`**/api/custom-models/${customModelId}/test`)

    // ── 4. Model appears in the generation picker's Custom section ─────
    testProjectId = await fixtures.createGenerationTestProject(1)

    // Put the custom model into the project's selected generation config so
    // the trigger modal lists it (the modal's pool comes from
    // generation_config.selected_configuration.models).
    await page.evaluate(
      async ({ projectId, modelId }) => {
        await fetch(`/api/projects/${projectId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            generation_config: {
              selected_configuration: { models: [modelId, 'gpt-4o-mini'] },
            },
          }),
        })
      },
      { projectId: testProjectId, modelId: customModelId }
    )

    await page.goto(`${BASE_URL}/projects/${testProjectId}`, {
      timeout: 60000,
    })

    // Open the generation trigger modal via the footer CTA.
    const generateCta = page.getByRole('button', {
      name: /Generierung starten|Start Generation/,
    })
    await expect(generateCta.first()).toBeVisible({ timeout: 30000 })
    await generateCta.first().click()

    // The modal groups models: the Custom section header and the model's
    // display name (with Custom badge) must be present, and the checkbox
    // must be enabled because the credential was stored in step 3.
    await expect(
      page.getByText(/Eigene Modelle|Custom models/).first()
    ).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(modelName).first()).toBeVisible()

    const customCheckbox = page.locator(`#model-${customModelId}`)
    await expect(customCheckbox).toBeEnabled()
    await customCheckbox.check()
    await expect(customCheckbox).toBeChecked()

    // IMPORTANT: do NOT click "Start Generation" - the endpoint is fake and
    // we must not enqueue real generation jobs (see generation-ui.spec.ts).
  })
})
