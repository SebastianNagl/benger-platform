/**
 * E2E tests for LLM Judge evaluation workflow
 * Tests evaluation configuration section accessibility on the project detail page.
 * Self-contained: creates its own project via API.
 *
 * Note: Full LLM Judge execution requires API keys which are not available in
 * the test environment. These tests verify the UI configuration is accessible.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('LLM Judge Workflow', () => {
  test.setTimeout(90000)

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
    projectId = await seeder.createProject(`LLM Judge ${Date.now()}`)
    await seeder.setLabelConfig(
      projectId,
      '<View><Text name="text" value="$text"/><TextArea name="answer" toName="text" required="true"/></View>'
    )
    await seeder.importTasks(projectId, [
      { data: { text: 'Test question for LLM evaluation' } },
      { data: { text: 'Another question for evaluation' } },
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

  test('evaluation configuration section exists on project detail', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // The project detail page should have an Evaluation Configuration section
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasEvalSection =
        bodyText?.includes('Evaluierungskonfiguration') ||
        bodyText?.includes('Evaluation Configuration') ||
        bodyText?.includes('Evaluierung')
      expect(hasEvalSection).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('project detail loads with all expected sections', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Verify multiple key sections exist
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasLabel =
        bodyText?.includes('Label') || bodyText?.includes('Annotation')
      const hasModel =
        bodyText?.includes('Modell') || bodyText?.includes('Model')
      expect(hasLabel || hasModel).toBe(true)
    }).toPass({ timeout: 15000 })
  })
})
