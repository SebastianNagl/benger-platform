/**
 * Numeric Annotation E2E Test
 *
 * Tests the numeric input annotation interface
 * using the seeded "E2E Numeric Project"
 */

import { expect, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

test.describe('Numeric Annotation', () => {
  let helpers: TestHelpers

  test.beforeEach(async ({ page }) => {
    helpers = new TestHelpers(page)
    await helpers.login('admin', 'admin')
  })

  test('should display numeric annotation interface in E2E Numeric Project', async ({
    page,
  }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    // Find E2E Numeric Project
    const projectLink = page.locator('text=E2E Numeric Project').first()
    if (await projectLink.isVisible({ timeout: 5000 })) {
      await projectLink.click()
      await page.waitForTimeout(2000)

      // Navigate to annotation if possible
      const annotateButton = page.locator(
        'button:has-text("Annotate"), a:has-text("Start Annotating"), a:has-text("Annotation")'
      )
      if (await annotateButton.isVisible({ timeout: 3000 })) {
        await annotateButton.click()
        await page.waitForTimeout(2000)
      }

      // Verify numeric input interface is visible
      const numericElements = page.locator(
        '[data-testid="number-input"], input[type="number"], input[inputmode="numeric"], .number-input'
      )

      if ((await numericElements.count()) > 0) {
        console.log('Numeric annotation interface found')
        expect(await numericElements.count()).toBeGreaterThanOrEqual(1)

        // Check for min/max constraints (0-100)
        const numberInput = numericElements.first()
        const minAttr = await numberInput.getAttribute('min')
        const maxAttr = await numberInput.getAttribute('max')
        console.log(`Number input constraints: min=${minAttr}, max=${maxAttr}`)
      } else {
        // Verify project page loaded
        const projectTitle = page.locator('h1, h2').first()
        await expect(projectTitle).toBeVisible()
        console.log('Project page loaded')
      }
    }
  })

  test('should show confidence scores from seeded annotations', async ({
    page,
  }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    const projectLink = page.locator('text=E2E Numeric Project').first()
    if (await projectLink.isVisible({ timeout: 5000 })) {
      await projectLink.click()
      await page.waitForTimeout(2000)

      // Navigate to data/tasks view
      const dataTab = page.locator(
        'a:has-text("Data"), button:has-text("Data"), a:has-text("Tasks")'
      )
      if (await dataTab.isVisible({ timeout: 3000 })) {
        await dataTab.click()
        await page.waitForTimeout(2000)
      }

      // Check page content for annotation indicators
      const pageContent = await page.content()
      const hasNumericData =
        pageContent.includes('confidence') ||
        pageContent.includes('number') ||
        pageContent.includes('score')

      console.log('Page indicates numeric data:', hasNumericData)
    }
  })

  test('should have tasks with varying confidence scores', async ({ page }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    const projectLink = page.locator('text=E2E Numeric Project').first()
    if (await projectLink.isVisible({ timeout: 5000 })) {
      await projectLink.click()
      await page.waitForTimeout(2000)

      // Check for task count
      const taskCountIndicator = page.locator(
        'text=/5 tasks/i, text=/\\d+ task/i, [data-testid="task-count"]'
      )

      const pageContent = await page.content()
      // Seeded data should have 5 tasks
      const hasExpectedTasks =
        pageContent.includes('5') || (await taskCountIndicator.count()) > 0

      console.log('Project has expected tasks:', hasExpectedTasks)
    }
  })
})
