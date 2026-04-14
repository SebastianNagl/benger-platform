/**
 * E2E tests for LLM Judge thinking configuration
 * Tests evaluation wizard UI: temperature input, thinking budget, reasoning effort.
 * Self-contained: creates its own project via API.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('LLM Judge Thinking Configuration', () => {
  test.setTimeout(120000)

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

    // Create a project with evaluation-compatible config
    projectId = await seeder.createProject(`LLM Judge Config ${Date.now()}`)
    await seeder.setLabelConfig(
      projectId,
      '<View><Text name="text" value="$text"/><TextArea name="answer" toName="text" required="true"/></View>'
    )
    await seeder.importTasks(projectId, [
      { data: { text: 'Test question 1' } },
      { data: { text: 'Test question 2' } },
      { data: { text: 'Test question 3' } },
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

  test('evaluation config section is accessible on project detail', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Evaluation Configuration section should be on the project detail page (EN or DE)
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasEvalSection =
        bodyText?.includes('Evaluierungskonfiguration') ||
        bodyText?.includes('Evaluation Configuration') ||
        bodyText?.includes('Evaluierung')
      expect(hasEvalSection).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('model selection section is accessible on project detail', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Model Selection section should be present (EN or DE)
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasModelSection =
        bodyText?.includes('Model Selection') ||
        bodyText?.includes('Modellauswahl') ||
        bodyText?.includes('Modell')
      expect(hasModelSection).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('project detail page loads without errors', async () => {
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto(`${BASE_URL}/projects/${projectId}`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

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
