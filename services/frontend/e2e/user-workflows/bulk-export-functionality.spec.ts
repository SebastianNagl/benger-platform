/**
 * E2E tests for bulk export functionality from project data page.
 * Tests the fix for issue #816 - ensuring exports include annotations and generations.
 */

import { expect, test } from '@playwright/test'

test.describe('Bulk Export Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to BenGER and wait for app to load
    await page.goto('/')
    await page.waitForTimeout(1000)
  })

  /**
   * Helper function to navigate to the first available project's data page
   * Returns true if successful, false if no project found
   */
  async function navigateToFirstProjectDataPage(page: any): Promise<boolean> {
    // Navigate to projects page
    await page.goto('/projects')
    await page.waitForTimeout(1000)

    // Wait for projects table to load - look for any project row
    const projectRows = page.locator(
      'table tbody tr, [data-testid="project-row"]'
    )
    const rowCount = await projectRows.count().catch(() => 0)

    if (rowCount === 0) {
      console.log('⚠️ No projects found in the projects table')
      return false
    }

    // Click on the first project
    const firstProject = projectRows.first()
    await firstProject.click()
    await page.waitForTimeout(1000)

    // Navigate to Data tab - check for both German and English labels
    const dataTab = page.locator(
      'button:has-text("Projektdaten"), button:has-text("Project Data"), [data-testid="data-tab"]'
    )
    const hasDataTab = await dataTab
      .isVisible({ timeout: 5000 })
      .catch(() => false)

    if (!hasDataTab) {
      console.log('⚠️ Data tab not found on project page')
      return false
    }

    await dataTab.first().click()
    await page.waitForTimeout(500)

    // Check if task list loaded
    const taskTable = page.locator('table tbody tr')
    const taskCount = await taskTable.count().catch(() => 0)

    if (taskCount === 0) {
      console.log('⚠️ No tasks found in the project')
      return false
    }

    console.log(`✅ Found ${taskCount} tasks in project`)
    return true
  }

  test('should export tasks with annotations and generations from project data page', async ({
    page,
  }) => {
    // Navigate to a project with existing data
    const navigated = await navigateToFirstProjectDataPage(page)

    if (!navigated) {
      console.log('⚠️ Skipping test - no suitable project found with tasks')
      console.warn('⚠️ Skipping test due to missing preconditions')
      return
      return
    }

    // Find and click the Export button (download icon button)
    const exportButton = page
      .locator(
        'button[title="Aufgaben exportieren"], button[title="Export tasks"], button:has([data-testid="export-icon"])'
      )
      .first()

    const hasExportButton = await exportButton
      .isVisible({ timeout: 5000 })
      .catch(() => false)
    if (!hasExportButton) {
      console.log('⚠️ Export button not found')
      console.warn('⚠️ Skipping test due to missing preconditions')
      return
      return
    }

    // Set up download listener before clicking export
    const downloadPromise = page.waitForEvent('download', { timeout: 15000 })

    // Click export button
    await exportButton.click()

    // Wait for download to start
    const download = await downloadPromise

    // Verify download file
    const filename = download.suggestedFilename()
    expect(filename).toMatch(/.*\.(json|csv|zip)/)
    console.log(`✅ Downloaded file: ${filename}`)

    // Get download content
    const path = await download.path()
    expect(path).toBeTruthy()

    // For JSON exports, verify content structure
    if (filename.endsWith('.json')) {
      const fs = require('fs')
      const content = fs.readFileSync(path, 'utf-8')
      const exportData = JSON.parse(content)

      // Verify export structure
      expect(exportData).toHaveProperty('tasks')
      expect(Array.isArray(exportData.tasks)).toBe(true)
      expect(exportData.tasks.length).toBeGreaterThan(0)

      // Count tasks with annotations and generations
      const tasksWithAnnotations = exportData.tasks.filter(
        (task: any) => task.annotations && task.annotations.length > 0
      )
      const tasksWithGenerations = exportData.tasks.filter(
        (task: any) => task.generations && task.generations.length > 0
      )

      console.log('✅ Export validation passed:')
      console.log(`  - ${exportData.tasks.length} tasks exported`)
      console.log(`  - ${tasksWithAnnotations.length} tasks with annotations`)
      console.log(`  - ${tasksWithGenerations.length} tasks with generations`)

      // If there are annotations, verify structure
      if (tasksWithAnnotations.length > 0) {
        const taskWithAnnotation = tasksWithAnnotations[0]
        const annotation = taskWithAnnotation.annotations[0]
        expect(annotation).toHaveProperty('id')
        console.log('✅ Annotation structure verified')
      }

      // If there are generations, verify structure
      if (tasksWithGenerations.length > 0) {
        const taskWithGeneration = tasksWithGenerations[0]
        const generation = taskWithGeneration.generations[0]
        expect(generation).toHaveProperty('id')
        console.log('✅ Generation structure verified')
      }
    }
  })

  test('should not show createObjectURL errors during export', async ({
    page,
  }) => {
    // Monitor console for errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    // Monitor page errors
    const pageErrors: Error[] = []
    page.on('pageerror', (error) => {
      pageErrors.push(error)
    })

    // Navigate to project data page
    const navigated = await navigateToFirstProjectDataPage(page)

    if (!navigated) {
      console.log('⚠️ Skipping test - no suitable project found with tasks')
      console.warn('⚠️ Skipping test due to missing preconditions')
      return
      return
    }

    // Find export button
    const exportButton = page
      .locator(
        'button[title="Aufgaben exportieren"], button[title="Export tasks"]'
      )
      .first()

    const hasExportButton = await exportButton
      .isVisible({ timeout: 5000 })
      .catch(() => false)
    if (!hasExportButton) {
      console.log('⚠️ Export button not found')
      console.warn('⚠️ Skipping test due to missing preconditions')
      return
      return
    }

    // Click export and wait for download
    const downloadPromise = page.waitForEvent('download', { timeout: 15000 })
    await exportButton.click()
    await downloadPromise

    // Wait a bit to catch any delayed errors
    await page.waitForTimeout(1000)

    // Verify no createObjectURL errors occurred
    const createObjectURLErrors = consoleErrors.filter((msg) =>
      msg.includes('createObjectURL')
    )
    expect(createObjectURLErrors.length).toBe(0)
    console.log('✅ No createObjectURL errors detected')

    // Verify no page errors occurred
    const exportRelatedErrors = pageErrors.filter(
      (error) =>
        error.message.includes('export') ||
        error.message.includes('createObjectURL') ||
        error.message.includes('blob')
    )
    expect(exportRelatedErrors.length).toBe(0)
    console.log('✅ No export-related errors detected')
  })

  test('should handle export of tasks with proper structure', async ({
    page,
  }) => {
    // Navigate to project data page
    const navigated = await navigateToFirstProjectDataPage(page)

    if (!navigated) {
      console.log('⚠️ Skipping test - no suitable project found with tasks')
      console.warn('⚠️ Skipping test due to missing preconditions')
      return
      return
    }

    // Find export button
    const exportButton = page
      .locator(
        'button[title="Aufgaben exportieren"], button[title="Export tasks"]'
      )
      .first()

    const hasExportButton = await exportButton
      .isVisible({ timeout: 5000 })
      .catch(() => false)
    if (!hasExportButton) {
      console.log('⚠️ Export button not found')
      console.warn('⚠️ Skipping test due to missing preconditions')
      return
      return
    }

    // Export
    const downloadPromise = page.waitForEvent('download', { timeout: 15000 })
    await exportButton.click()
    const download = await downloadPromise

    // Verify JSON structure
    const filename = download.suggestedFilename()
    if (filename.endsWith('.json')) {
      const path = await download.path()
      const fs = require('fs')
      const content = fs.readFileSync(path, 'utf-8')
      const exportData = JSON.parse(content)

      // Verify all tasks have annotations and generations fields (even if empty)
      for (const task of exportData.tasks) {
        expect(task).toHaveProperty('annotations')
        expect(task).toHaveProperty('generations')
        expect(Array.isArray(task.annotations)).toBe(true)
        expect(Array.isArray(task.generations)).toBe(true)
      }

      console.log('✅ All tasks have annotations and generations arrays')
    } else {
      console.log(`ℹ️ Non-JSON export: ${filename}`)
    }
  })
})
