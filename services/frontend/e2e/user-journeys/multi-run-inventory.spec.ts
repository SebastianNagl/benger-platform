/**
 * E2E for the multi-run feature's user-visible surface:
 *   - /runs inventory loads, tab switching works, project filter narrows results
 *   - clicking an evaluation row opens /evaluations/[id] with the Judges tab
 *   - clicking a generation row opens /generations/[id] with per-trial breakdown
 *   - notification dropdown contains the "Läufe" entry for direct navigation
 *
 * Stays read-only against the seeded dev database — no LLM calls — so the
 * test exercises the routing + rendering plumbing without needing a mock
 * provider. The fan-out + variance behavior itself is covered by the API
 * + worker unit tests.
 */
import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

test.describe('Multi-run inventory + detail pages', () => {
  test.setTimeout(120000)

  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    await page.setViewportSize({ width: 1600, height: 1000 })
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 })
    await helpers.login('admin', 'admin')
  })

  test('/runs inventory shows evaluation tab with at least one row', async () => {
    await page.goto(`${BASE_URL}/runs?type=evaluation`, {
      waitUntil: 'domcontentloaded',
    })
    await expect(page.getByRole('heading', { name: /Läufe|Runs/ })).toBeVisible({
      timeout: 30000,
    })
    // The table renders within ~10s after the API returns.
    const rowLocator = page.locator('tbody tr')
    await expect(rowLocator.first()).toBeVisible({ timeout: 30000 })
    const rowCount = await rowLocator.count()
    expect(rowCount).toBeGreaterThan(0)
  })

  test('switches between evaluation and generation tabs', async () => {
    await page.goto(`${BASE_URL}/runs?type=evaluation`, {
      waitUntil: 'domcontentloaded',
    })
    await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 30000 })

    // Click the Generation tab (German UI ships by default).
    await page.getByRole('button', { name: /Generierungen|Generations/ }).click()
    await page.waitForURL(/type=generation/, { timeout: 15000 })
    // Generation tab columns include "Läufe" / "Runs" — distinct from
    // evaluation columns, so its presence proves the tab swapped.
    await expect(
      page.locator('thead').getByText(/Läufe|Runs/i).first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('project filter narrows the row set + persists in URL', async () => {
    await page.goto(`${BASE_URL}/runs?type=evaluation`, {
      waitUntil: 'domcontentloaded',
    })
    await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 30000 })

    const allRows = await page.locator('tbody tr').count()

    // Pick the second option in the project filter (first is "Alle Projekte"
    // / "All projects"). The dropdown is populated by a SEPARATE async projects
    // fetch (runs/page.tsx useEffect), independent of the rows above, so its
    // <option> list lags the table — reading it mid-flight used to see only the
    // placeholder and silently skip. The seed always provides multiple
    // projects, so wait for the list to settle and treat a still-empty dropdown
    // as a real failure rather than a skip.
    const projectSelect = page.locator('select').first()
    await expect
      .poll(() => projectSelect.locator('option').count(), { timeout: 15000 })
      .toBeGreaterThanOrEqual(2)

    const targetValue = await projectSelect
      .locator('option')
      .nth(1)
      .getAttribute('value')
    expect(targetValue, 'second project option should carry a project id').toBeTruthy()
    await projectSelect.selectOption(targetValue!)

    await expect(page).toHaveURL(/project_id=/, { timeout: 10000 })
    // After narrowing to one project the row count should be ≤ the unfiltered
    // count (it can equal if every run is in that project — still valid).
    await page.waitForTimeout(800) // allow refetch
    const filteredRows = await page.locator('tbody tr').count()
    expect(filteredRows).toBeLessThanOrEqual(allRows)
  })

  test('clicking a generation row opens its detail page', async () => {
    await page.goto(`${BASE_URL}/runs?type=generation`, {
      waitUntil: 'domcontentloaded',
    })
    const firstRow = page.locator('tbody tr').first()
    await expect(firstRow).toBeVisible({ timeout: 30000 })

    // Rows navigate via a client-side onClick → router.push (no <a href>), so a
    // click only works once React has hydrated and wired the handler. In the
    // loaded Docker test env hydration can take 20-30s, and a click issued
    // before then is silently dropped (verified: the 1st click never navigates;
    // a click once hydrated lands in ~400ms). Retry the click until the URL
    // actually changes, rather than clicking once and racing hydration.
    await expect(async () => {
      if (!/\/generations\/[a-f0-9-]+$/.test(page.url())) {
        await firstRow.click({ timeout: 5000 })
      }
      expect(page.url()).toMatch(/\/generations\/[a-f0-9-]+$/)
    }).toPass({ timeout: 60000, intervals: [500, 1000, 2000, 3000] })
    // Detail page shows the generation-run heading.
    await expect(
      page.getByRole('heading', { name: /Generierungs-Lauf|Generation Run/ }),
    ).toBeVisible({ timeout: 10000 })
    // Status / Modell / Läufe summary tiles render.
    await expect(page.getByText(/^STATUS$/i).first()).toBeVisible()
  })

  test('user dropdown contains Läufe link for direct navigation', async () => {
    await page.goto(`${BASE_URL}/dashboard`, {
      waitUntil: 'domcontentloaded',
    })
    // Open the AuthButton dropdown by clicking the user trigger.
    await page.getByRole('button', { name: /admin/i }).first().click()
    const runsLink = page.getByRole('link', { name: /^Läufe$|^Runs$/ })
    await expect(runsLink).toBeVisible({ timeout: 5000 })
    await runsLink.click()
    await page.waitForURL(/\/runs/, { timeout: 10000 })
  })
})
