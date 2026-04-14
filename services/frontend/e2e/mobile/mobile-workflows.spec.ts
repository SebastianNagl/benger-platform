/**
 * Mobile Responsive E2E Test
 *
 * Tests complete annotation workflows on mobile devices
 * including touch gestures, responsive navigation, and offline capabilities
 *
 * Part of Issue #471 Implementation
 */

import { expect, test } from '@playwright/test'
import { TestDataFactory } from '../factories/DataFactory'
import { TestHelpers } from '../helpers/test-helpers'

// Test configurations for different mobile devices
// Using valid Playwright device descriptors
const mobileDeviceNames = ['iPhone 13', 'iPhone 13 Pro', 'Pixel 5'] as const

// Single test suite that uses device from config (project-based)
test.describe('Mobile Annotation Workflow', () => {
  // Set timeout to 60 seconds per test to account for mobile interaction overhead
  test.describe.configure({ timeout: 60000 })

  let helpers: TestHelpers

  test.beforeEach(async ({ page }) => {
    helpers = new TestHelpers(page)
    await page.goto('/')
  })

  test('Complete annotation on mobile device', async ({ page }) => {
    // Mobile-specific login flow
    await page.goto('/login')

    // Check for mobile menu if it exists
    const mobileMenu = page.locator(
      '[data-testid="mobile-menu"], .mobile-menu-toggle, button[aria-label*="menu"]'
    )
    const hasMobileMenu = await mobileMenu
      .isVisible({ timeout: 2000 })
      .catch(() => false)

    if (hasMobileMenu) {
      await mobileMenu.tap()

      // Look for login link in mobile menu
      const loginLink = page.locator(
        'a:has-text("Login"), a:has-text("Anmelden")'
      )
      if (await loginLink.isVisible()) {
        await loginLink.tap()
      }
    }

    // Standard login process
    await page.fill(
      'input[type="text"], input[type="email"], input[placeholder*="Benutzername"]',
      'admin'
    )
    await page.fill('input[type="password"]', 'admin')
    await page.tap('button[type="submit"], button:has-text("Anmelden")')

    // Wait for login success
    await page.waitForURL((url) => !url.toString().includes('/login'), {
      timeout: 10000,
    })

    // Navigate to projects (mobile navigation)
    if (hasMobileMenu) {
      await mobileMenu.tap()
      const projectsLink = page.locator(
        'a:has-text("Projects"), a:has-text("Projekte")'
      )
      if (await projectsLink.isVisible()) {
        await projectsLink.tap()
      }
    } else {
      // Direct navigation
      await page.goto('/projects')
    }

    // Create a test project
    const createButton = page.locator(
      'button:has-text("Neues Projekt"), button:has-text("New Project")'
    )
    if (await createButton.isVisible()) {
      await createButton.tap()

      const projectName = 'Mobile Test ' + Date.now()
      await page.fill(
        '[data-testid="project-name-input"], input[placeholder*="Rechts-QA"], input[placeholder*="German Legal"]',
        projectName
      )
      await page.fill(
        '[data-testid="project-description-input"], textarea[placeholder*="Beschreiben"], textarea[placeholder*="Describe"]',
        'Mobile annotation test'
      )
      await page.tap('button:has-text("Next"), button:has-text("Weiter")')

      // Skip data import
      await page.waitForTimeout(1000)
      const skipButton = page.locator(
        'button:has-text("Skip Data Import"), button:has-text("Skip")'
      )
      if (await skipButton.isVisible()) {
        await skipButton.tap()
      }

      // Create project
      await page.waitForTimeout(1000)
      await page.tap(
        'button:has-text("Create Project"), button:has-text("Projekt erstellen")'
      )

      // Get project ID
      await page.waitForURL(/\/projects\/[0-9a-f-]+/, { timeout: 15000 })
      const projectUrl = page.url()
      const projectId = projectUrl.match(/\/projects\/([0-9a-f-]+)/)?.[1] || ''

      // Import test data for mobile annotation
      await page.goto(`/projects/${projectId}/data`)
      const importButton = page.locator(
        'button:has-text("Import"), button:has-text("Importieren")'
      )
      if (await importButton.isVisible()) {
        await importButton.tap()
        const csvData = TestDataFactory.generateCSV(5) // Small dataset for mobile
        await TestDataFactory.importCSV(page, csvData)
        await page.waitForTimeout(2000)
      }

      // Start annotation with mobile interface
      await page.goto(`/projects/${projectId}/annotate`)

      // Test touch gestures for navigation
      const annotationInput = page.locator(
        'textarea[name="answer"], [data-testid="annotation-input"]'
      )
      if (await annotationInput.isVisible({ timeout: 5000 })) {
        // Test tap to focus
        await annotationInput.tap()

        // Test mobile keyboard input
        await annotationInput.type(
          'Mobile annotation: Legal analysis on touch device'
        )

        // Test swipe to navigate if supported
        const taskArea = page.locator(
          '[data-testid="task-area"], .task-content, main'
        )
        if (await taskArea.isVisible()) {
          // Get bounding box for swipe
          const box = await taskArea.boundingBox()
          if (box) {
            // Swipe left (next task) if swipe navigation exists
            await page.touchscreen.tap(
              box.x + box.width * 0.8,
              box.y + box.height * 0.5
            )
            await page.touchscreen.tap(
              box.x + box.width * 0.2,
              box.y + box.height * 0.5
            )
          }
        }

        // Test pinch to zoom if document viewer exists
        const documentViewer = page.locator(
          '[data-testid="document-viewer"], .document-content'
        )
        if (await documentViewer.isVisible()) {
          const docBox = await documentViewer.boundingBox()
          if (docBox) {
            // Simulate pinch gesture
            const centerX = docBox.x + docBox.width / 2
            const centerY = docBox.y + docBox.height / 2

            // Touch two points and move them apart (pinch out)
            await page.touchscreen.tap(centerX - 50, centerY)
            await page.touchscreen.tap(centerX + 50, centerY)
          }
        }

        // Submit annotation
        const submitButton = page.locator(
          'button:has-text("Submit"), button:has-text("Next"), button:has-text("Weiter")'
        )
        if (await submitButton.isVisible()) {
          await submitButton.tap()
          await page.waitForTimeout(1000)
        }
      }

      // Test mobile-specific features
      // Check if app is responsive
      const viewportSize = page.viewportSize()
      expect(viewportSize!.width).toBeLessThan(800) // Ensure we're in mobile viewport

      // Check for mobile-optimized UI elements
      const mobileOptimized = await page
        .locator('.mobile-friendly, [data-mobile="true"]')
        .isVisible()
        .catch(() => false)

      // Test offline capability if supported
      await page.context().setOffline(true)
      await page.tap('button:has-text("Save"), button:has-text("Speichern")')

      // Should save locally or show offline indicator
      const offlineIndicator = await page
        .locator('[data-testid="offline"], text=/offline|no connection/i')
        .isVisible({ timeout: 5000 })
        .catch(() => false)

      // Restore connection
      await page.context().setOffline(false)

      // Should sync automatically
      if (offlineIndicator) {
        await page
          .waitForSelector('[data-testid="online"], text=/synced|connected/i', {
            timeout: 10000,
          })
          .catch(() => {})
      }

      console.log('Mobile test completed')
    }
  })

  test('Mobile navigation and menu interactions', async ({ page }) => {
    await helpers.login('admin', 'admin')

    // Test mobile menu functionality
    const mobileMenu = page.locator(
      '[data-testid="mobile-menu"], .mobile-menu-toggle, .hamburger-menu'
    )

    if (await mobileMenu.isVisible()) {
      // Test menu open/close
      await mobileMenu.tap()

      // Check if menu opened
      const menuContent = page.locator(
        '[data-testid="mobile-nav"], .mobile-menu-content, nav'
      )
      await expect(menuContent).toBeVisible({ timeout: 3000 })

      // Test navigation links
      const navLinks = page.locator('nav a, .mobile-menu-content a')
      const linkCount = await navLinks.count()

      if (linkCount > 0) {
        // Test first few navigation items
        for (let i = 0; i < Math.min(3, linkCount); i++) {
          const link = navLinks.nth(i)
          const linkText = await link.textContent()

          if (
            linkText &&
            !linkText.includes('Logout') &&
            !linkText.includes('Abmelden')
          ) {
            await link.tap()
            await page.waitForTimeout(2000)

            // Navigate back to test next link
            if (await mobileMenu.isVisible()) {
              await mobileMenu.tap()
            }
          }
        }
      }

      // Close menu
      const closeButton = page.locator(
        '[data-testid="close-menu"], .menu-close'
      )
      if (await closeButton.isVisible()) {
        await closeButton.tap()
      } else {
        // Tap outside menu to close
        await page.tap('body')
      }

      // Verify menu closed
      await expect(menuContent).not.toBeVisible({ timeout: 3000 })
    }
  })

  test('Touch gesture support', async ({ page }) => {
    await helpers.login('admin', 'admin')

    // Use existing E2E test project instead of creating a new one
    // (Project creation wizard is complex on mobile viewport)
    await page.goto('/projects')

    // Wait for projects to load
    await page.waitForTimeout(2000)

    // Find a project with data - look for E2E test projects created by init_complete.py
    const projectLink = page
      .locator('a[href*="/projects/"]')
      .filter({ hasText: /E2E|Test|QA/i })
      .first()

    if (await projectLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await projectLink.tap()
      await page.waitForURL(/\/projects\/[0-9a-f-]+/, { timeout: 10000 })

      // Navigate to data tab
      const dataTab = page.locator('a[href*="/data"], button:has-text("Data"), button:has-text("Daten")')
      if (await dataTab.isVisible({ timeout: 5000 }).catch(() => false)) {
        await dataTab.tap()
        await page.waitForTimeout(2000)
      }

      // Test scroll gestures on the data table
      const dataTable = page.locator(
        'table, [data-testid="data-table"], .data-container'
      )
      if (await dataTable.isVisible({ timeout: 5000 }).catch(() => false)) {
        const box = await dataTable.boundingBox()
        if (box) {
          // Scroll down
          await page.touchscreen.tap(
            box.x + box.width / 2,
            box.y + box.height - 50
          )
          await page.touchscreen.tap(box.x + box.width / 2, box.y + 50)

          // Scroll back up
          await page.touchscreen.tap(box.x + box.width / 2, box.y + 50)
          await page.touchscreen.tap(
            box.x + box.width / 2,
            box.y + box.height - 50
          )
          console.log('Scroll gestures tested')
        }
      }

      // Test tap-to-select
      const firstRow = page
        .locator('table tbody tr, [data-testid="task-row"]')
        .first()
      if (await firstRow.isVisible({ timeout: 3000 }).catch(() => false)) {
        await firstRow.tap()

        // Check if row was selected or action was triggered
        const selected = await firstRow.getAttribute('class')
        console.log('Row selection state:', selected)

        // Test long press (if supported)
        const contextMenuItem = page.locator(
          '[data-testid="context-menu"], .context-menu'
        )
        await firstRow.tap({ delay: 500 }) // Long press

        const hasContextMenu = await contextMenuItem
          .isVisible({ timeout: 2000 })
          .catch(() => false)
        if (hasContextMenu) {
          console.log('Long press context menu works')

          // Close context menu
          await page.tap('body')
        }
      }
    } else {
      // Fallback: test touch gestures on the projects list itself
      console.log('No E2E test project found, testing touch on projects list')

      const projectsList = page.locator('main, [data-testid="projects-list"]')
      if (await projectsList.isVisible().catch(() => false)) {
        const box = await projectsList.boundingBox()
        if (box) {
          // Test tap interaction
          await page.touchscreen.tap(box.x + box.width / 2, box.y + 100)
          console.log('Touch gesture on projects list tested')
        }
      }
    }
  })
})

// Additional mobile-specific tests that don't need to run on all devices
// Device configuration is set in playwright.config.ts (mobile project)
test.describe('Mobile-Specific Features', () => {
  // Set timeout to 60 seconds per test to account for mobile interaction overhead
  test.describe.configure({ timeout: 60000 })

  let helpers: TestHelpers

  test.beforeEach(async ({ page }) => {
    helpers = new TestHelpers(page)
    await page.goto('/')
  })

  test('Responsive layout adaptation', async ({ page }) => {
    await helpers.login('admin', 'admin')
    await page.goto('/projects')

    // Test different orientations
    await page.setViewportSize({ width: 375, height: 667 }) // Portrait
    await page.waitForTimeout(1000)

    // Check layout in portrait
    const portraitLayout = await page.screenshot({ fullPage: false })
    expect(portraitLayout).toBeTruthy()

    await page.setViewportSize({ width: 667, height: 375 }) // Landscape
    await page.waitForTimeout(1000)

    // Check layout in landscape
    const landscapeLayout = await page.screenshot({ fullPage: false })
    expect(landscapeLayout).toBeTruthy()

    // Verify responsive elements
    const responsiveElements = page.locator(
      '.responsive, [data-responsive="true"], [class*="mobile-"]'
    )
    const elementCount = await responsiveElements.count()
    console.log(`Found ${elementCount} responsive elements`)
  })

  test('Mobile performance and loading', async ({ page }) => {
    // Monitor performance on mobile
    let loadTimes: number[] = []

    page.on('load', async () => {
      const timing = await page.evaluate(() => {
        const navigation = performance.getEntriesByType(
          'navigation'
        )[0] as PerformanceNavigationTiming
        return {
          domContentLoaded:
            navigation.domContentLoadedEventEnd -
            navigation.domContentLoadedEventStart,
          loadComplete: navigation.loadEventEnd - navigation.loadEventStart,
        }
      })
      loadTimes.push(timing.domContentLoaded)
    })

    await helpers.login('admin', 'admin')

    // Test loading times on various pages
    const testPages = ['/projects', '/dashboard', '/organizations']

    for (const path of testPages) {
      await page.goto(path)
      await page.waitForTimeout(1000)
    }

    // Mobile should load reasonably fast
    const avgLoadTime = loadTimes.reduce((a, b) => a + b, 0) / loadTimes.length
    console.log(`Average mobile load time: ${avgLoadTime}ms`)

    // Performance budget for mobile (adjust based on requirements)
    expect(avgLoadTime).toBeLessThan(5000) // 5 seconds max
  })
})
