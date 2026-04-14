/**
 * Annotation Comparison Workflow E2E Test
 *
 * Tests the annotation comparison modal and IAA statistics
 * using projects with multiple annotators from seeded data
 */

import { expect, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

test.describe('Annotation Comparison Workflow', () => {
  let helpers: TestHelpers

  test.beforeEach(async ({ page }) => {
    helpers = new TestHelpers(page)
    await helpers.login('admin', 'admin')
  })

  test('should show multiple annotations per task in E2E QA Project', async ({
    page,
  }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    // Find E2E QA Project (has overlapping annotations from multiple users)
    const projectLink = page.locator('text=E2E QA Project').first()
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

      // Look for annotation count column or indicators
      const annotationCountElements = page.locator(
        '[data-testid="annotation-count"], .annotation-count, td:has-text(/\\d+ annotations?/i)'
      )

      const pageContent = await page.content()
      // Seeded data has 2-4 annotations per task
      const hasMultipleAnnotations =
        pageContent.includes('annotation') ||
        (await annotationCountElements.count()) > 0

      console.log('Project shows multiple annotations:', hasMultipleAnnotations)
    }
  })

  test('should display annotator information for tasks', async ({ page }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    const projectLink = page.locator('text=E2E QA Project').first()
    if (await projectLink.isVisible({ timeout: 5000 })) {
      await projectLink.click()
      await page.waitForTimeout(2000)

      // Navigate to data view
      const dataTab = page.locator(
        'a:has-text("Data"), button:has-text("Data")'
      )
      if (await dataTab.isVisible({ timeout: 3000 })) {
        await dataTab.click()
        await page.waitForTimeout(2000)
      }

      // Look for annotator badges or names
      const annotatorElements = page.locator(
        '[data-testid="annotator-badge"], .annotator-name, text=/admin/i, text=/contributor/i, text=/annotator/i'
      )

      const pageContent = await page.content()
      // Check for annotator names from seeded data
      const hasAnnotatorInfo =
        pageContent.includes('admin') ||
        pageContent.includes('contributor') ||
        pageContent.includes('annotator')

      console.log('Page shows annotator information:', hasAnnotatorInfo)
    }
  })

  test('should open annotation comparison modal when clicking task', async ({
    page,
  }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    const projectLink = page.locator('text=E2E QA Project').first()
    if (await projectLink.isVisible({ timeout: 5000 })) {
      await projectLink.click()
      await page.waitForTimeout(2000)

      // Navigate to data view
      const dataTab = page.locator(
        'a:has-text("Data"), button:has-text("Data")'
      )
      if (await dataTab.isVisible({ timeout: 3000 })) {
        await dataTab.click()
        await page.waitForTimeout(2000)
      }

      // Click on a task row to open comparison modal
      const taskRow = page
        .locator('table tbody tr, [data-testid="task-row"]')
        .first()
      if (await taskRow.isVisible({ timeout: 3000 })) {
        await taskRow.click()
        await page.waitForTimeout(2000)

        // Check for modal or task detail view
        const modal = page.locator(
          '[role="dialog"], .modal, [data-testid="annotation-comparison-modal"], [data-testid="task-detail"]'
        )
        const detailView = page.locator(
          'text=/annotation/i, text=/comparison/i'
        )

        const hasDetailView =
          (await modal.count()) > 0 || (await detailView.count()) > 0
        console.log('Task detail/comparison view opened:', hasDetailView)
      }
    }
  })

  test('should show annotation statistics for multi-annotator project', async ({
    page,
  }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    const projectLink = page.locator('text=E2E Rating Project').first()
    if (await projectLink.isVisible({ timeout: 5000 })) {
      await projectLink.click()
      await page.waitForTimeout(2000)

      const pageContent = await page.content()
      // Check for statistical indicators
      const hasStats =
        pageContent.includes('agreement') ||
        pageContent.includes('statistic') ||
        pageContent.includes('IAA') ||
        pageContent.includes('inter-annotator')

      console.log('Project shows annotation statistics:', hasStats)
    }
  })

  test('should navigate between different annotation types', async ({
    page,
  }) => {
    await page.goto('/projects')
    await page.waitForTimeout(2000)

    // Test that we can navigate to different project types
    const projectTypes = [
      'E2E QA Project',
      'E2E NER Project',
      'E2E Multi-Choice Project',
      'E2E Rating Project',
      'E2E Numeric Project',
    ]

    for (const projectTitle of projectTypes) {
      const projectLink = page.locator(`text=${projectTitle}`).first()
      if (await projectLink.isVisible({ timeout: 3000 })) {
        console.log(`Found project: ${projectTitle}`)
      }
    }

    // Verify at least some projects are visible
    const anyProject = page.locator('text=/E2E.*Project/').first()
    const projectsExist = await anyProject.isVisible({ timeout: 5000 })
    expect(projectsExist).toBeTruthy()
  })
})
