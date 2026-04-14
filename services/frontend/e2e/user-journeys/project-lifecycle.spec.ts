/**
 * E2E tests for project lifecycle
 * Tests project creation, navigation, and basic management.
 * Self-contained: creates its own test data via API.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Project Lifecycle', () => {
  let page: Page
  let helpers: TestHelpers
  let seeder: APISeedingHelper
  let seededProjectId: string | null = null

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    seeder = new APISeedingHelper(page)

    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test.afterEach(async () => {
    if (seededProjectId) {
      try {
        await seeder.deleteProject(seededProjectId)
      } catch (e) {
        console.log('Cleanup failed:', e)
      }
      seededProjectId = null
    }
  })

  test('create new project via wizard', async () => {
    await page.goto(`${BASE_URL}/projects`)

    // ProjectList uses <Button onClick={handleCreateProject}> with text from
    // t('projects.list.newProject') = "New Project" / "Neues Projekt"
    const createButton = page
      .getByRole('button', { name: /new project|Neues Projekt/i })
      .first()

    await expect(createButton).toBeVisible({ timeout: 15000 })
    await createButton.click()
    await page.waitForURL(/\/projects\/create/, { timeout: 15000 })

    expect(page.url()).toContain('/projects/create')

    const nameInput = page.locator(
      '[data-testid="project-create-name-input"]'
    )
    await expect(nameInput).toBeVisible({ timeout: 10000 })

    const projectName = `E2E Lifecycle ${Date.now()}`
    await nameInput.fill(projectName)

    const descInput = page.locator(
      '[data-testid="project-create-description-textarea"]'
    )
    if (await descInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await descInput.fill('Test project created by E2E lifecycle test')
    }

    const nextButton = page.locator(
      '[data-testid="project-create-next-button"]'
    )
    if (await nextButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await nextButton.click()
    }

    const skipButton = page.locator(
      '[data-testid="project-create-skip-data-button"]'
    )
    if (await skipButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await skipButton.click()
    }

    const submitButton = page.locator(
      '[data-testid="project-create-submit-button"]'
    )
    if (await submitButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await submitButton.click()
    }

    // Wait for redirect to project detail
    await page
      .waitForURL(/\/projects\/[a-f0-9-]+/, { timeout: 15000 })
      .catch(() => {})

    const projectUrl = page.url()
    const match = projectUrl.match(/\/projects\/([a-f0-9-]+)/)
    if (match) {
      seededProjectId = match[1]
    }

    expect(seededProjectId).toBeTruthy()
  })

  test('project detail page shows sections', async () => {
    seededProjectId = await seeder.createProject('Lifecycle Sections Test')
    await seeder.setLabelConfig(
      seededProjectId,
      '<View><Text name="text" value="$text"/><Choices name="label" toName="text"><Choice value="A"/><Choice value="B"/></Choices></View>'
    )

    await page.goto(`${BASE_URL}/projects/${seededProjectId}`)

    // The project detail page is a single scrollable page with sections.
    // Verify the page loaded by checking for the project content area.
    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    // Check that some key project elements are present (EN or DE)
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasSections =
        bodyText?.includes('Label') ||
        bodyText?.includes('Annotation') ||
        bodyText?.includes('Settings') ||
        bodyText?.includes('Einstellungen') ||
        bodyText?.includes('Konfiguration')
      expect(hasSections).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('project settings section is accessible', async () => {
    seededProjectId = await seeder.createProject('Lifecycle Settings Test')

    await page.goto(`${BASE_URL}/projects/${seededProjectId}`)

    // Settings is an inline section on the project detail page.
    // Look for settings-related text/elements.
    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 15000 })

    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasSettings =
        bodyText?.includes('Settings') ||
        bodyText?.includes('Einstellungen') ||
        bodyText?.includes('Assignment') ||
        bodyText?.includes('Zuweisung')
      expect(hasSettings).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('project list shows projects', async () => {
    // Ensure at least one project exists
    seededProjectId = await seeder.createProject('Lifecycle List Test')

    await page.goto(`${BASE_URL}/projects`)

    const projectRows = page.locator('tr[data-testid^="projects-table-row"]')
    await expect(projectRows.first()).toBeVisible({ timeout: 15000 })

    const rowCount = await projectRows.count()
    expect(rowCount).toBeGreaterThan(0)
  })

  test('project search/filter works', async () => {
    const uniqueName = `SearchTest-${Date.now()}`
    seededProjectId = await seeder.createProject(uniqueName)

    await page.goto(`${BASE_URL}/projects`)

    const searchInput = page
      .locator('input[placeholder*="Search"]')
      .or(page.locator('input[placeholder*="Suchen"]'))
      .or(page.locator('input[type="search"]'))
      .first()

    await expect(searchInput).toBeVisible({ timeout: 10000 })
    await searchInput.fill(uniqueName)

    // Wait for filter to take effect
    await expect(
      page.locator('tr').filter({ hasText: uniqueName }).first()
    ).toBeVisible({ timeout: 10000 })
  })

  test('quick action navigates to data page', async () => {
    seededProjectId = await seeder.createProject('Lifecycle Data Nav Test')
    await seeder.setLabelConfig(
      seededProjectId,
      '<View><Text name="text" value="$text"/><Choices name="label" toName="text"><Choice value="A"/><Choice value="B"/></Choices></View>'
    )
    await seeder.importTasks(seededProjectId, [
      { data: { text: 'Navigation test task' } },
    ])

    await page.goto(`${BASE_URL}/projects/${seededProjectId}`)

    // The project detail has a "Project Data" quick action button
    // Use specific href to avoid matching other /data links
    const dataLink = page
      .locator(`a[href="/projects/${seededProjectId}/data"]`)
      .first()

    await expect(dataLink).toBeVisible({ timeout: 15000 })
    await dataLink.click()
    await page.waitForURL(`**/projects/${seededProjectId}/data`, { timeout: 15000 })

    expect(page.url()).toContain(`/projects/${seededProjectId}/data`)
  })
})
