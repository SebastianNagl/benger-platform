/**
 * Phone-width layout (rubric e2e D02).
 *
 * At 390 px the project wizard scrolled sideways on every step, with step dot
 * 1 off screen, and the task page was 594 px wide because of the breadcrumb
 * with the full task UUID and the unwrapped action row. The acceptance
 * criterion measured here: the document is never wider than the viewport and
 * dot 1 lies inside it.
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'
import { enableWizardFeatures } from '../helpers/wizard-helpers'

const PHONE = { width: 390, height: 844 }

test.use({ viewport: PHONE })

async function expectNoSidewaysScroll(page: Page, where: string) {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }))
  expect(innerWidth, `viewport width on ${where}`).toBe(PHONE.width)
  expect(scrollWidth, `document width on ${where}`).toBeLessThanOrEqual(
    innerWidth,
  )
}

test.describe('Phone width (390 px)', () => {
  test.describe.configure({ timeout: 90000 })

  test.beforeEach(async ({ page }) => {
    await new TestHelpers(page).login('admin', 'admin')
  })

  test('the project wizard fits on every step with dot 1 on screen', async ({
    page,
  }) => {
    await page.goto('/projects/create')
    await page
      .locator('[data-testid="project-create-name-input"]')
      .fill(`PhoneWidth_${Date.now()}`)
    await enableWizardFeatures(page, [
      'annotation',
      'dataImport',
      'llmGeneration',
      'evaluation',
    ])

    const indicator = page.locator(
      '[data-testid="project-create-step-indicator"]',
    )
    const next = page.locator('[data-testid="project-create-next-button"]')
    const total = Number(await indicator.getAttribute('data-total-steps'))
    expect(total).toBeGreaterThan(4)

    for (let step = 1; step <= total; step++) {
      await expect(indicator).toHaveAttribute('data-step', String(step))
      const stepId = await indicator.getAttribute('data-current-step-id')
      const where = `wizard step ${step} (${stepId})`

      await expectNoSidewaysScroll(page, where)
      const dot1 = await page
        .locator('[data-testid="wizard-step-dot-1"]')
        .boundingBox()
      expect(dot1, `dot 1 on ${where}`).not.toBeNull()
      expect(dot1!.x, `dot 1 left edge on ${where}`).toBeGreaterThanOrEqual(0)
      expect(
        dot1!.x + dot1!.width,
        `dot 1 right edge on ${where}`,
      ).toBeLessThanOrEqual(PHONE.width)

      if (step < total) await next.click()
    }
  })

  test('the task page fits with its UUID breadcrumb and action row', async ({
    page,
  }) => {
    const seeding = new APISeedingHelper(page)
    const projectId = await seeding.createProject(`PhoneWidth_${Date.now()}`)
    try {
      const [task] = await seeding.importTasks(projectId, [
        { data: { text: 'Sachverhalt für die Breitenprüfung' } },
      ])
      await page.goto(`/projects/${projectId}/tasks/${task.id}`)

      await expect(
        page.getByRole('heading', { level: 2, name: new RegExp(task.id) }),
      ).toBeVisible({ timeout: 20000 })
      await expect(page.locator('nav', { hasText: task.id })).toBeVisible()

      await expectNoSidewaysScroll(page, 'the task page')
    } finally {
      await seeding.cleanupTestProject(projectId)
    }
  })
})
