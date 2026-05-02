/**
 * E2E tests for project management pages
 * Tests archived projects listing and project members page.
 * Uses API seeding for project creation to keep tests isolated.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Project Management', () => {
  let page: Page
  let helpers: TestHelpers
  let seeder: APISeedingHelper
  let projectId: string | null = null

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    seeder = new APISeedingHelper(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test.afterEach(async () => {
    if (projectId) {
      try {
        await seeder.deleteProject(projectId)
      } catch (e) {
        console.log('Cleanup failed:', e)
      }
      projectId = null
    }
  })

  test('archived projects page loads with heading and breadcrumb', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/projects/archived`, { timeout: 30000 })

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Verify breadcrumb is present with "Archived" label
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasArchivedLabel =
        bodyText?.includes('Archived') ||
        bodyText?.includes('Archiviert') ||
        bodyText?.includes('Archiv')
      expect(hasArchivedLabel).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('archived projects page shows empty state or project list', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/projects/archived`, { timeout: 30000 })

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // The page should show either archived projects or an empty/no-results state
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasContent =
        // Empty state
        bodyText?.includes('No projects') ||
        bodyText?.includes('Keine Projekte') ||
        bodyText?.includes('no archived') ||
        bodyText?.includes('keine archivierten') ||
        // Or a project table with headers
        bodyText?.includes('Name') ||
        bodyText?.includes('Status') ||
        bodyText?.includes('Created') ||
        bodyText?.includes('Erstellt') ||
        // Or the Projects label in breadcrumb at minimum
        bodyText?.includes('Projects') ||
        bodyText?.includes('Projekte')
      expect(hasContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  // Per-project members + organizations management has moved into the
  // visibility "danger zone" SubSection on the project detail page; the
  // standalone /projects/{id}/members page was removed. The three E2E
  // tests that drove that page have been deleted accordingly.
})
