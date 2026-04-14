/**
 * E2E tests for dashboard analytics
 * Tests dashboard loading, error handling, and navigation.
 * Self-contained: creates its own project to guarantee dashboard content.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Dashboard Analytics', () => {
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

  test('dashboard loads without error alerts', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/dashboard`, { timeout: 30000 })

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // No error alerts
    const errorAlert = page
      .locator('[role="alert"]')
      .filter({ hasText: /error|Error|Fehler/i })
    await expect(errorAlert).not.toBeVisible({ timeout: 5000 })
  })

  test('dashboard shows stat cards', async () => {
    // Ensure at least one project exists
    projectId = await seeder.createProject('Dashboard Stats Test')

    await page.goto(`${BASE_URL}/dashboard`, { timeout: 30000 })

    // Wait for dashboard content to render (stats cards load asynchronously)
    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Look for any stat-related text (EN or DE)
    // Stats labels: Projects/Projekte, Tasks/Aufgaben, Annotations/Annotationen,
    //               Generations/Generierungen, Evaluations/Evaluierungen
    await expect(async () => {
      const bodyText = await page.locator('main').textContent()
      const hasStats =
        bodyText?.includes('Projekte') ||
        bodyText?.includes('Projects') ||
        bodyText?.includes('Aufgaben') ||
        bodyText?.includes('Tasks') ||
        bodyText?.includes('Annotationen') ||
        bodyText?.includes('Annotations')
      expect(hasStats).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('clicking project link navigates to project detail', async () => {
    projectId = await seeder.createProject('Dashboard Navigation Test')

    await page.goto(`${BASE_URL}/dashboard`)

    const projectLink = page.locator('a[href*="/projects/"]').first()
    await expect(projectLink).toBeVisible({ timeout: 15000 })

    await projectLink.click()
    await page.waitForURL(/\/projects\//, { timeout: 10000 }).catch(() => {})

    expect(page.url()).toContain('/projects/')
  })

  test('create project link navigates to create page', async () => {
    await page.goto(`${BASE_URL}/dashboard`)

    // The dashboard has a "Create New Project" card with an <a> styled as Button
    // Matches: "Projekt erstellen", "Create Your First Project", "Neues Projekt erstellen"
    const createLink = page
      .locator('a[href="/projects/create"]')
      .first()

    await expect(createLink).toBeVisible({ timeout: 15000 })

    await createLink.click()
    await page.waitForURL(/\/projects\/create/, { timeout: 15000 })

    expect(page.url()).toContain('/projects/create')
  })
})
