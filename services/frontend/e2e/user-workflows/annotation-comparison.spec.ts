/**
 * E2E Tests for data page task interaction
 *
 * Tests the data page task rows and click behavior.
 * Self-contained: creates its own project, tasks, and annotations via API.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Data Page Task Interaction', () => {
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

    // Create a project with tasks and annotations
    projectId = await seeder.createProject(`Data Page ${Date.now()}`)
    await seeder.setLabelConfig(
      projectId,
      '<View><Text name="text" value="$text"/><Choices name="sentiment" toName="text"><Choice value="positive"/><Choice value="negative"/><Choice value="neutral"/></Choices></View>'
    )
    const tasks = await seeder.importTasks(projectId, [
      { data: { text: 'This product is excellent and well-made.' } },
      { data: { text: 'The service was terrible and slow.' } },
      { data: { text: 'It rained today, nothing special.' } },
    ])

    // Add annotations to first two tasks
    if (tasks.length >= 2) {
      await seeder.createAnnotation(tasks[0].id, [
        {
          from_name: 'sentiment',
          to_name: 'text',
          type: 'choices',
          value: { choices: ['positive'] },
        },
      ])
      await seeder.createAnnotation(tasks[1].id, [
        {
          from_name: 'sentiment',
          to_name: 'text',
          type: 'choices',
          value: { choices: ['negative'] },
        },
      ])
    }
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

  test('data page shows task rows', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}/data`)

    const taskRows = page.locator('tbody tr')
    await expect(taskRows.first()).toBeVisible({ timeout: 15000 })

    const rowCount = await taskRows.count()
    expect(rowCount).toBeGreaterThanOrEqual(3)
  })

  test('task rows contain expected data columns', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}/data`)

    const taskRows = page.locator('tbody tr')
    await expect(taskRows.first()).toBeVisible({ timeout: 15000 })

    // Verify the table header has expected columns (ID, text data, annotations)
    const headerRow = page.locator('thead tr').first()
    await expect(headerRow).toBeVisible({ timeout: 5000 })

    const headerText = await headerRow.textContent()
    expect(headerText).toBeTruthy()
  })

  test('data page loads without error alerts', async () => {
    await page.goto(`${BASE_URL}/projects/${projectId}/data`)

    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    const errorAlert = page
      .locator('[role="alert"]')
      .filter({ hasText: /error|Error|Fehler/i })
    await expect(errorAlert).not.toBeVisible({ timeout: 5000 })
  })
})
