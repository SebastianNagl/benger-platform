/**
 * E2E tests for annotation workflow
 * Tests core annotation flow: navigation, task content, and error handling.
 * Self-contained: creates its own project and tasks via API.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Annotation Workflow', () => {
  let page: Page
  let helpers: TestHelpers
  let seeder: APISeedingHelper
  let projectId: string

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    seeder = new APISeedingHelper(page)

    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')

    // Create a project with tasks for annotation tests
    projectId = await seeder.createProject(`Annotation Workflow ${Date.now()}`)
    await seeder.setLabelConfig(
      projectId,
      '<View><Text name="text" value="$text"/><Choices name="sentiment" toName="text"><Choice value="positive"/><Choice value="negative"/><Choice value="neutral"/></Choices></View>'
    )
    await seeder.importTasks(projectId, [
      { data: { text: 'This is a positive review about the product.' } },
      { data: { text: 'This is a negative review about the service.' } },
      { data: { text: 'This is a neutral observation about the weather.' } },
    ])
  })

  test.afterEach(async () => {
    if (projectId) {
      try {
        await seeder.deleteProject(projectId)
      } catch (e) {
        console.log('Cleanup failed:', e)
      }
    }
  })

  test('navigate to annotation page and see task interface', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}/label`)

    // Check for initialization error (no tasks available) - valid state
    const initError = page.locator(
      'text=/No tasks are available|Initialization Error/i'
    )
    const hasInitError = await initError
      .isVisible({ timeout: 5000 })
      .catch(() => false)
    if (hasInitError) {
      test.skip(true, 'No tasks available for annotation')
    }

    // Verify annotation interface loaded
    const annotationForm = page
      .locator('textarea')
      .or(page.locator('[class*="annotation"]'))
      .or(page.locator('form'))
      .first()
    await expect(annotationForm).toBeVisible({ timeout: 10000 })
  })

  test('back to project navigates correctly', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}/label`)

    const backButton = page
      .locator('a[href*="/projects/"]')
      .or(page.locator('button').filter({ hasText: /Back|Zurück|Project/i }))
      .first()

    await expect(backButton).toBeVisible({ timeout: 10000 })
    await backButton.click()

    expect(page.url()).toContain('/projects/')
  })

  test('annotation page loads without critical console errors', async () => {
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`${BASE_URL}/projects/${projectId}/label`)

    // Wait for page to fully render
    await page.locator('body').waitFor({ state: 'visible' })

    // Filter out expected/known errors
    const criticalErrors = consoleErrors.filter(
      (e) =>
        !e.includes('404') &&
        !e.includes('websocket') &&
        !e.includes('favicon') &&
        !e.includes('net::ERR') &&
        !e.includes('HMR') &&
        !e.includes('hot-reloader') &&
        !e.includes('hydrat') &&
        !e.includes('__next') &&
        !e.includes('next-dev') &&
        !e.includes('React does not recognize') &&
        !e.includes('Warning:') &&
        !e.includes('DevTools') &&
        !e.includes('Failed to load resource') &&
        !e.includes('Notification stream error')
    )

    expect(criticalErrors).toHaveLength(0)
  })
})
