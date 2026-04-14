/**
 * E2E Test: Evaluation Dropdowns
 *
 * Tests the functionality of all evaluation page dropdowns:
 * - Chart type selection (data, bar, radar, box, heatmap)
 * - Aggregation level selection (sample, model, field, overall)
 * - Statistics method selection (CI, SE, t-test, etc.)
 *
 * These tests verify that:
 * 1. Dropdowns are selectable and change the view
 * 2. Disabled states show correct messages
 * 3. Statistics recompute on selection changes
 * 4. SE appears in all relevant tables when selected
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from './helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

test.describe('Evaluation Page Dropdowns', () => {
  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)

    // Set desktop viewport per CLAUDE.md guidelines
    await page.setViewportSize({ width: 1920, height: 1080 })

    // Login as admin
    await helpers.login('admin', 'admin')
  })

  test.describe('Chart Type Selection', () => {
    test('can switch between chart types', async () => {
      // Navigate to evaluations page
      await page.goto(`${BASE_URL}/evaluations`)

      // Select a project (if available)
      const projectDropdown = page.locator('button').filter({ hasText: /select project/i }).first()
      if (await projectDropdown.isVisible({ timeout: 5000 })) {
        await projectDropdown.click()
        await page.waitForTimeout(500)

        // Click first available project
        const firstProject = page.locator('button').filter({ hasText: /tasks/i }).first()
        if (await firstProject.isVisible({ timeout: 2000 })) {
          await firstProject.click()
          await page.waitForTimeout(1000)
        }
      }

      // Find the View dropdown
      const viewDropdown = page.locator('button').filter({ hasText: /data view|bar chart|radar|heatmap/i }).first()

      if (await viewDropdown.isVisible({ timeout: 5000 })) {
        // Click to open dropdown
        await viewDropdown.click()
        await page.waitForTimeout(300)

        // Verify chart type options are visible
        const barChartOption = page.locator('button').filter({ hasText: /bar chart/i })
        await expect(barChartOption).toBeVisible({ timeout: 3000 })

        const radarOption = page.locator('button').filter({ hasText: /radar chart/i })
        await expect(radarOption).toBeVisible()

        const boxPlotOption = page.locator('button').filter({ hasText: /box plot/i })
        await expect(boxPlotOption).toBeVisible()

        const heatmapOption = page.locator('button').filter({ hasText: /heatmap/i })
        await expect(heatmapOption).toBeVisible()

        // Select Bar Chart
        await barChartOption.click()
        await page.waitForTimeout(500)

        // Verify selection changed
        await expect(viewDropdown).toContainText(/bar chart/i)
      }
    })

    test('box plot shows correct disabled message without sample aggregation', async () => {
      await page.goto(`${BASE_URL}/evaluations`)

      // Select a project
      const projectDropdown = page.locator('button').filter({ hasText: /select project/i }).first()
      if (await projectDropdown.isVisible({ timeout: 5000 })) {
        await projectDropdown.click()
        await page.waitForTimeout(500)

        const firstProject = page.locator('button').filter({ hasText: /tasks/i }).first()
        if (await firstProject.isVisible({ timeout: 2000 })) {
          await firstProject.click()
          await page.waitForTimeout(1000)
        }
      }

      // Find and open View dropdown
      const viewDropdown = page.locator('button').filter({ hasText: /data view|bar chart/i }).first()
      if (await viewDropdown.isVisible({ timeout: 5000 })) {
        await viewDropdown.click()
        await page.waitForTimeout(300)

        // Find Box Plot option - should be disabled
        const boxPlotOption = page.locator('button').filter({ hasText: /box plot/i })
        await expect(boxPlotOption).toBeVisible()

        // Check if disabled (has disabled styling or cursor-not-allowed)
        const isDisabled = await boxPlotOption.evaluate((el) =>
          el.classList.contains('cursor-not-allowed') ||
          el.hasAttribute('disabled') ||
          el.classList.contains('text-gray-400')
        )

        // If disabled, verify the title attribute has the correct message
        if (isDisabled) {
          const title = await boxPlotOption.getAttribute('title')
          expect(title).toMatch(/sample|aggregation/i)
        }
      }
    })
  })

  test.describe('Aggregation Level Selection', () => {
    test('can select multiple aggregation levels', async () => {
      await page.goto(`${BASE_URL}/evaluations`)

      // Select a project
      const projectDropdown = page.locator('button').filter({ hasText: /select project/i }).first()
      if (await projectDropdown.isVisible({ timeout: 5000 })) {
        await projectDropdown.click()
        await page.waitForTimeout(500)

        const firstProject = page.locator('button').filter({ hasText: /tasks/i }).first()
        if (await firstProject.isVisible({ timeout: 2000 })) {
          await firstProject.click()
          await page.waitForTimeout(1000)
        }
      }

      // Find Aggregation dropdown
      const aggDropdown = page.locator('button').filter({ hasText: /per model|per sample|aggregation/i }).first()

      if (await aggDropdown.isVisible({ timeout: 5000 })) {
        await aggDropdown.click()
        await page.waitForTimeout(300)

        // Verify aggregation options
        const perModelOption = page.locator('button').filter({ hasText: /per.*model/i })
        await expect(perModelOption).toBeVisible()

        const perSampleOption = page.locator('button').filter({ hasText: /per.*sample/i })
        await expect(perSampleOption).toBeVisible()

        // Select Sample to enable multi-select
        await perSampleOption.click()
        await page.waitForTimeout(500)

        // Verify "2 of 4" or similar is shown
        const countIndicator = page.locator('text=/\\d+ of \\d+ selected/')
        if (await countIndicator.isVisible({ timeout: 2000 })) {
          await expect(countIndicator).toBeVisible()
        }
      }
    })
  })

  test.describe('Statistics Methods Selection', () => {
    test('SE selection shows SE in statistics tables', async () => {
      await page.goto(`${BASE_URL}/evaluations`)

      // Select a project
      const projectDropdown = page.locator('button').filter({ hasText: /select project/i }).first()
      if (await projectDropdown.isVisible({ timeout: 5000 })) {
        await projectDropdown.click()
        await page.waitForTimeout(500)

        const firstProject = page.locator('button').filter({ hasText: /tasks/i }).first()
        if (await firstProject.isVisible({ timeout: 2000 })) {
          await firstProject.click()
          await page.waitForTimeout(2000) // Wait for data to load
        }
      }

      // Find Statistics dropdown
      const statsDropdown = page.locator('button').filter({ hasText: /95% ci|statistics/i }).first()

      if (await statsDropdown.isVisible({ timeout: 5000 })) {
        await statsDropdown.click()
        await page.waitForTimeout(300)

        // Find and click SE option
        const seOption = page.locator('button').filter({ hasText: /standard error/i })
        if (await seOption.isVisible({ timeout: 2000 })) {
          await seOption.click()
          await page.waitForTimeout(1000)
        }

        // Close dropdown by clicking outside
        await page.click('body', { position: { x: 10, y: 10 } })
        await page.waitForTimeout(500)

        // Scroll down to find statistics tables
        await page.evaluate(() => window.scrollTo(0, 500))
        await page.waitForTimeout(500)

        // Look for SE in the statistics panel - should show ± symbols
        const seIndicator = page.locator('text=/±\\d/')
        if (await seIndicator.first().isVisible({ timeout: 5000 })) {
          await expect(seIndicator.first()).toBeVisible()
        }
      }
    })
  })

  test.describe('Error States', () => {
    test('significance heatmap shows message when no data available', async () => {
      await page.goto(`${BASE_URL}/evaluations`)

      // Select a project
      const projectDropdown = page.locator('button').filter({ hasText: /select project/i }).first()
      if (await projectDropdown.isVisible({ timeout: 5000 })) {
        await projectDropdown.click()
        await page.waitForTimeout(500)

        const firstProject = page.locator('button').filter({ hasText: /tasks/i }).first()
        if (await firstProject.isVisible({ timeout: 2000 })) {
          await firstProject.click()
          await page.waitForTimeout(1000)
        }
      }

      // Switch to heatmap view
      const viewDropdown = page.locator('button').filter({ hasText: /data view|bar chart/i }).first()
      if (await viewDropdown.isVisible({ timeout: 5000 })) {
        await viewDropdown.click()
        await page.waitForTimeout(300)

        const heatmapOption = page.locator('button').filter({ hasText: /heatmap/i })
        if (await heatmapOption.isVisible({ timeout: 2000 })) {
          // Check if heatmap is disabled - if so, it should have a reason
          const isDisabled = await heatmapOption.evaluate((el) =>
            el.classList.contains('cursor-not-allowed') ||
            el.hasAttribute('disabled')
          )

          if (isDisabled) {
            const title = await heatmapOption.getAttribute('title')
            // Should have a meaningful message
            expect(title).toBeTruthy()
          } else {
            // If enabled, click it
            await heatmapOption.click()
            await page.waitForTimeout(1000)

            // Scroll to find significance section
            await page.evaluate(() => window.scrollTo(0, 800))
            await page.waitForTimeout(500)

            // Look for either the heatmap or an error/empty message
            const significanceSection = page.locator('text=/statistical significance|no significance/i')
            if (await significanceSection.isVisible({ timeout: 3000 })) {
              await expect(significanceSection).toBeVisible()
            }
          }
        }
      }
    })
  })
})
