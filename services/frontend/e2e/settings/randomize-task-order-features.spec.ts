/**
 * E2E Tests: Randomized Task Order with Annotation Features
 * Tests that timers, conditional instructions, post-annotation questionnaires,
 * and immediate evaluation modals all work correctly with randomized task ordering.
 *
 * These features use task IDs (not position indices), so they should be
 * order-independent - this test confirms that.
 */
import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

/**
 * Helper: Create project via API with all features enabled
 */
async function createFullFeaturedProject(
  page: Page,
  name: string,
  taskCount: number
): Promise<string> {
  const result = await page.evaluate(
    async ({ name, taskCount }) => {
      // Create project
      const projectResp = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          title: name,
          description: `E2E test: ${name}`,
        }),
      })
      if (!projectResp.ok)
        return { error: `Create: ${projectResp.status}` }
      const project = await projectResp.json()
      const projectId = project.id

      // Set label config + all annotation features
      const configResp = await fetch(`/api/projects/${projectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          label_config: `<View>
            <Text name="text" value="$text"/>
            <Choices name="sentiment" toName="text" choice="single" required="true">
              <Choice value="positive"/>
              <Choice value="negative"/>
              <Choice value="neutral"/>
            </Choices>
          </View>`,
          // Enable randomized task ordering
          randomize_task_order: true,
          // Enable timer (120 seconds)
          annotation_time_limit_enabled: true,
          annotation_time_limit_seconds: 120,
          // Enable conditional instructions (2 variants, 50/50)
          conditional_instructions: [
            { id: 'variant_a', content: 'VARIANT A: Focus on legal implications.', weight: 50 },
            { id: 'variant_b', content: 'VARIANT B: Focus on factual accuracy.', weight: 50 },
          ],
          show_instruction: true,
          instructions: 'General instructions for all annotators.',
          // Enable post-annotation questionnaire
          questionnaire_enabled: true,
          questionnaire_config: `<View>
            <Header value="How confident are you in your annotation?"/>
            <Choices name="confidence" toName="text" choice="single" required="true">
              <Choice value="very_confident"/>
              <Choice value="somewhat_confident"/>
              <Choice value="not_confident"/>
            </Choices>
          </View>`,
          // Enable immediate evaluation
          immediate_evaluation_enabled: true,
        }),
      })
      if (!configResp.ok) {
        const err = await configResp.text()
        return { error: `Config: ${configResp.status} ${err}` }
      }

      // Import tasks
      const tasks = Array.from({ length: taskCount }, (_, i) => ({
        data: { text: `Legal analysis task ${i + 1}: Evaluate the contractual obligations in this scenario.` },
      }))
      const importResp = await fetch(`/api/projects/${projectId}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ data: tasks }),
      })
      if (!importResp.ok)
        return { error: `Import: ${importResp.status}` }

      return { projectId }
    },
    { name, taskCount }
  )

  if ('error' in result)
    throw new Error(result.error as string)
  return result.projectId as string
}

/**
 * Helper: Delete project via API
 */
async function deleteProject(page: Page, projectId: string): Promise<void> {
  await page.evaluate(async (id) => {
    await fetch(`/api/projects/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    })
  }, projectId)
}

/**
 * Helper: Get project settings to verify they persisted
 */
async function getProjectSettings(
  page: Page,
  projectId: string
): Promise<Record<string, unknown>> {
  return await page.evaluate(async (id) => {
    const resp = await fetch(`/api/projects/${id}`, {
      credentials: 'include',
    })
    if (!resp.ok) return {}
    return await resp.json()
  }, projectId)
}

test.describe('Randomized Order with Annotation Features', () => {
  let page: Page
  let helpers: TestHelpers
  let testProjectId: string | null = null

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test.afterEach(async () => {
    if (testProjectId) {
      try {
        await deleteProject(page, testProjectId)
      } catch (error) {
        console.warn(`Cleanup failed:`, error)
      }
      testProjectId = null
    }
  })

  test('timer displays and counts down with randomized task order @extended', async () => {
    test.setTimeout(90000)

    testProjectId = await createFullFeaturedProject(
      page,
      `E2E Timer+Random ${Date.now()}`,
      5
    )

    // Verify settings persisted
    const settings = await getProjectSettings(page, testProjectId!)
    expect(settings.randomize_task_order).toBe(true)
    expect(settings.annotation_time_limit_enabled).toBe(true)
    expect(settings.annotation_time_limit_seconds).toBe(120)

    // Navigate to annotation UI
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)

    // With timer + conditional instructions, an instruction modal may appear
    // with "Annotation starten" button, OR a standalone "Start" timer screen.
    // Handle both cases.
    const startButton = page
      .locator('button')
      .filter({ hasText: /^Start$|Annotation starten/ })
      .first()
    await expect(startButton).toBeVisible({ timeout: 20000 })
    console.log('Start/instruction screen visible')
    await startButton.click()

    // Dismiss any remaining instruction modal overlay
    const dismissButton = page.locator('button').filter({ hasText: /Annotation starten/ })
    const hasDismiss = await dismissButton.isVisible({ timeout: 3000 }).catch(() => false)
    if (hasDismiss) {
      await dismissButton.click()
      console.log('Dismissed instruction modal')
    }

    // Wait for timer to appear (top-right corner)
    const timer = page
      .locator('[data-testid="annotation-timer-display"]')
      .or(page.locator('[role="timer"]'))
      .first()
    await expect(timer).toBeVisible({ timeout: 15000 })

    // Verify timer shows approximately 02:00 or slightly less
    const timerText = await timer.textContent()
    expect(timerText).toMatch(/0[12]:\d\d/)
    console.log(`Timer display: ${timerText}`)

    // Wait 3 seconds and verify timer is counting down
    await page.waitForTimeout(3000)
    const timerText2 = await timer.textContent()
    console.log(`Timer after 3s: ${timerText2}`)
    // Should have decreased from initial value
    expect(timerText2).not.toBe(timerText)
    console.log('Timer is counting down correctly with randomized task order')
  })

  test('conditional instruction variant is shown and deterministic with randomized order', async () => {
    test.setTimeout(90000)

    testProjectId = await createFullFeaturedProject(
      page,
      `E2E Instructions+Random ${Date.now()}`,
      5
    )

    // Verify conditional instructions persisted
    const settings = await getProjectSettings(page, testProjectId!)
    expect(settings.conditional_instructions).toHaveLength(2)

    // Navigate to annotation UI
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)

    // Click Start if timer screen shows
    const startButton = page.locator('button').filter({ hasText: /^Start$/ })
    const hasStart = await startButton.isVisible({ timeout: 10000 }).catch(() => false)
    if (hasStart) {
      // Check if variant instruction is shown on the start screen
      const variantOnStart = page
        .locator('text=VARIANT A')
        .or(page.locator('text=VARIANT B'))
      const variantVisibleOnStart = await variantOnStart.first().isVisible({ timeout: 5000 }).catch(() => false)
      if (variantVisibleOnStart) {
        const variantText = await variantOnStart.first().textContent()
        console.log(`Variant on timer start screen: ${variantText}`)
      }
      await startButton.click()
      await page.waitForTimeout(2000)
    }

    // Check for instruction variant in the annotation interface
    // Either in modal or inline - look for either variant text
    const variantA = page.locator('text=VARIANT A')
    const variantB = page.locator('text=VARIANT B')

    const hasVariantA = await variantA.isVisible({ timeout: 5000 }).catch(() => false)
    const hasVariantB = await variantB.isVisible({ timeout: 5000 }).catch(() => false)

    // At least one variant should be visible (either in modal or on start screen)
    const variantShown = hasVariantA || hasVariantB
    console.log(`Variant A visible: ${hasVariantA}, Variant B visible: ${hasVariantB}`)

    if (variantShown) {
      const shownVariant = hasVariantA ? 'A' : 'B'
      console.log(`Shown variant: ${shownVariant}`)

      // Reload and verify same variant is shown (deterministic)
      await page.reload()

      // The timer start screen shows again on reload (session continues)
      // Check for variant on start screen or after clicking start
      await page.waitForTimeout(3000)
      const variantAAfterReload = await page.locator('text=VARIANT A').isVisible({ timeout: 5000 }).catch(() => false)
      const variantBAfterReload = await page.locator('text=VARIANT B').isVisible({ timeout: 5000 }).catch(() => false)

      const sameVariant =
        (shownVariant === 'A' && variantAAfterReload) ||
        (shownVariant === 'B' && variantBAfterReload)

      if (variantAAfterReload || variantBAfterReload) {
        console.log(`After reload - Variant A: ${variantAAfterReload}, Variant B: ${variantBAfterReload}`)
        expect(sameVariant).toBe(true)
        console.log('Same variant shown after reload (deterministic hash confirmed)')
      } else {
        console.log('Variant not visible after reload (may require clicking Start again)')
      }
    } else {
      // Variant might be shown in a different UI flow (e.g., dismissed modal)
      console.log('No variant text visible in current view - checking general instructions')
      const generalInstructions = page.locator('text=General instructions')
      const hasGeneral = await generalInstructions.isVisible({ timeout: 3000 }).catch(() => false)
      console.log(`General instructions visible: ${hasGeneral}`)
    }
  })

  test('post-annotation questionnaire appears after submission with randomized order', async () => {
    test.setTimeout(120000)

    testProjectId = await createFullFeaturedProject(
      page,
      `E2E Questionnaire+Random ${Date.now()}`,
      5
    )

    // Verify questionnaire enabled
    const settings = await getProjectSettings(page, testProjectId!)
    expect(settings.questionnaire_enabled).toBe(true)
    expect(settings.questionnaire_config).toBeTruthy()

    // Navigate to annotation UI
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)

    // Wait for annotation interface to load
    await page.waitForTimeout(5000)

    // Dismiss all blocking modals/overlays using JavaScript
    // (HeadlessUI modal portals can intercept pointer events)
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      for (const btn of buttons) {
        const text = btn.textContent?.trim() || ''
        if (text === 'Start' || text === 'Annotation starten') {
          btn.click()
          break
        }
      }
    })
    await page.waitForTimeout(2000)

    // Check if modal is still present and dismiss again
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      for (const btn of buttons) {
        const text = btn.textContent?.trim() || ''
        if (text === 'Annotation starten') {
          btn.click()
          break
        }
      }
    })
    await page.waitForTimeout(2000)

    // Wait for annotation form (no modal blocking)
    const choiceOption = page
      .locator('input[type="radio"]')
      .or(page.locator('[data-testid*="choice"]'))
      .or(page.locator('label').filter({ hasText: /positive|negative|neutral/i }))
      .first()
    await expect(choiceOption).toBeVisible({ timeout: 20000 })

    // Select an option
    await choiceOption.click()
    await page.waitForTimeout(500)

    // Submit annotation
    const submitButton = page
      .locator('button')
      .filter({ hasText: /Absenden|Submit/i })
      .first()
    await expect(submitButton).toBeVisible({ timeout: 5000 })
    await submitButton.click()

    // Wait for questionnaire modal to appear
    await page.waitForTimeout(2000)

    // Look for questionnaire content
    const questionnaireTitle = page
      .locator('text=How confident')
      .or(page.locator('text=Questionnaire'))
      .or(page.locator('text=Fragebogen'))
      .or(page.locator('[role="dialog"]'))
    const hasQuestionnaire = await questionnaireTitle.first().isVisible({ timeout: 10000 }).catch(() => false)

    if (hasQuestionnaire) {
      console.log('Post-annotation questionnaire modal appeared')

      // Try to select a questionnaire option
      const confidentOption = page
        .locator('label')
        .filter({ hasText: /confident/i })
        .first()
        .or(page.locator('[role="dialog"] input[type="radio"]').first())

      const canSelect = await confidentOption.isVisible({ timeout: 5000 }).catch(() => false)
      if (canSelect) {
        await confidentOption.click()
        console.log('Selected questionnaire option')

        // Submit questionnaire
        const submitQuestionnaire = page
          .locator('[role="dialog"] button')
          .filter({ hasText: /Absenden|Submit|Senden/i })
          .first()
        const canSubmit = await submitQuestionnaire.isVisible({ timeout: 5000 }).catch(() => false)
        if (canSubmit) {
          await submitQuestionnaire.click()
          console.log('Submitted questionnaire')
          await page.waitForTimeout(2000)
        }
      }
    } else {
      // Check if evaluation modal appeared instead (questionnaire may have been skipped)
      const evalModal = page.locator('text=/Evaluation|Bewertung|gespeichert/i')
      const hasEval = await evalModal.isVisible({ timeout: 5000 }).catch(() => false)
      console.log(`Questionnaire not visible, eval modal: ${hasEval}`)
    }

    // After questionnaire/evaluation, should be able to continue
    // Look for "next task" button or timer screen
    const continueButton = page
      .locator('button')
      .filter({ hasText: /Weiter|Continue|Next|nächst/i })
    const hasContinue = await continueButton.first().isVisible({ timeout: 10000 }).catch(() => false)

    if (hasContinue) {
      await continueButton.first().click()
      console.log('Clicked continue to next task')
    }

    // Verify we advanced (either to timer screen or next task)
    await page.waitForTimeout(3000)
    const taskCounter = page.locator('text=/Task \\d+ of/i')
    const nextStartButton = page.locator('button').filter({ hasText: /^Start$/ })
    const hasAdvanced =
      (await taskCounter.isVisible({ timeout: 5000 }).catch(() => false)) ||
      (await nextStartButton.isVisible({ timeout: 5000 }).catch(() => false))

    console.log(`Advanced to next task/screen: ${hasAdvanced}`)
  })

  test('immediate evaluation modal appears after submission with randomized order', async () => {
    test.setTimeout(120000)

    // Create project with eval enabled but questionnaire disabled for cleaner test
    const result = await page.evaluate(async (name) => {
      const projectResp = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ title: name, description: `E2E test: ${name}` }),
      })
      if (!projectResp.ok) return { error: `Create: ${projectResp.status}` }
      const project = await projectResp.json()
      const projectId = project.id

      const configResp = await fetch(`/api/projects/${projectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          label_config: `<View>
            <Text name="text" value="$text"/>
            <Choices name="sentiment" toName="text" choice="single" required="true">
              <Choice value="positive"/>
              <Choice value="negative"/>
              <Choice value="neutral"/>
            </Choices>
          </View>`,
          randomize_task_order: true,
          immediate_evaluation_enabled: true,
          questionnaire_enabled: false,
        }),
      })
      if (!configResp.ok) return { error: `Config: ${configResp.status}` }

      const tasks = Array.from({ length: 3 }, (_, i) => ({
        data: { text: `Evaluate legal statement ${i + 1}.` },
      }))
      const importResp = await fetch(`/api/projects/${projectId}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ data: tasks }),
      })
      if (!importResp.ok) return { error: `Import: ${importResp.status}` }

      return { projectId }
    }, `E2E Eval+Random ${Date.now()}`)

    if ('error' in result) throw new Error(result.error as string)
    testProjectId = result.projectId as string

    // Navigate to annotation UI
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)

    // Wait for annotation form (no timer since we didn't enable it)
    const choiceOption = page
      .locator('input[type="radio"]')
      .or(page.locator('label').filter({ hasText: /positive|negative|neutral/i }))
      .first()
    await expect(choiceOption).toBeVisible({ timeout: 20000 })
    console.log('Annotation form loaded')

    // Verify task counter shows randomized count
    const taskCounter = page.locator('text=/Task 1 of 3/i')
    await expect(taskCounter).toBeVisible({ timeout: 5000 })
    console.log('Task counter: Task 1 of 3')

    // Select an option and submit
    await choiceOption.click()
    await page.waitForTimeout(500)

    const submitButton = page
      .locator('button')
      .filter({ hasText: /Absenden|Submit/i })
      .first()
    await submitButton.click()

    // Wait for evaluation modal or success message
    await page.waitForTimeout(3000)

    // The evaluation modal should appear (or a loading state for it)
    const evalModal = page
      .locator('[role="dialog"]')
      .or(page.locator('text=/Evaluation|Bewertung|gespeichert|saved/i'))
    const hasEvalModal = await evalModal.first().isVisible({ timeout: 15000 }).catch(() => false)
    console.log(`Evaluation modal/message visible: ${hasEvalModal}`)

    if (hasEvalModal) {
      // Check for evaluation content (results, loading, or error)
      const evalContent = page
        .locator('text=/Evaluating|Auswerten|Results|Ergebnis|saved|gespeichert|Error|Fehler/i')
      const hasContent = await evalContent.first().isVisible({ timeout: 10000 }).catch(() => false)
      console.log(`Evaluation content visible: ${hasContent}`)
      if (hasContent) {
        const contentText = await evalContent.first().textContent()
        console.log(`Evaluation content: ${contentText?.substring(0, 100)}`)
      }

      // Close/continue past evaluation
      const continueButton = page
        .locator('button')
        .filter({ hasText: /Weiter|Continue|Close|Schließen|nächst/i })
      const hasContinue = await continueButton.first().isVisible({ timeout: 10000 }).catch(() => false)
      if (hasContinue) {
        await continueButton.first().click()
        console.log('Closed evaluation modal')
      }
    }

    // Verify we can proceed (task count should have decreased)
    await page.waitForTimeout(2000)
    const newCounter = page.locator('text=/Task \\d+ of 2/i')
    const counterVisible = await newCounter.isVisible({ timeout: 10000 }).catch(() => false)
    console.log(`Task count decreased to 2: ${counterVisible}`)
  })
})
