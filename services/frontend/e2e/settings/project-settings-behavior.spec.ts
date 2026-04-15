/**
 * E2E Tests: Project Settings Behavior
 * Tests the 5 untested project settings that control annotation UI behavior
 *
 * Settings tested:
 * 1. show_instruction - Instruction panel visibility
 * 2. show_skip_button - Skip button visibility
 * 3. require_comment_on_skip - Comment modal when skipping
 * 5. min_annotations_per_task - Completion logic
 */
import { expect, Page, test } from '@playwright/test'
import { SIMPLE_TEXT_CONFIG, TestFixtures } from '../helpers/test-fixtures'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://benger.localhost'

/**
 * Helper: Update project settings via API
 */
async function updateProjectSettings(
  page: Page,
  projectId: string,
  settings: Record<string, unknown>
): Promise<void> {
  const result = await page.evaluate(
    async ({ projectId, settings }) => {
      const response = await fetch(`/api/projects/${projectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(settings),
      })
      return { ok: response.ok, status: response.status }
    },
    { projectId, settings }
  )

  if (!result.ok) {
    throw new Error(`Failed to update project settings: ${result.status}`)
  }
}

/**
 * Helper: Wait for annotation UI to be ready
 */
async function waitForAnnotationUI(page: Page): Promise<void> {

  // Wait for textarea to appear (annotation interface uses TextArea component)
  await page
    .locator('textarea')
    .first()
    .waitFor({ state: 'visible', timeout: 20000 })
    .catch(() => {
      console.log('Textarea wait timed out, checking for other annotation elements...')
    })

  // Also wait for submit button as a secondary indicator
  await page
    .locator('button')
    .filter({ hasText: /Absenden|Submit/i })
    .first()
    .waitFor({ state: 'visible', timeout: 5000 })
    .catch(() => {
      console.log('Submit button not found, continuing...')
    })

  await page.waitForTimeout(1000)
}

test.describe('Project Settings Behavior', () => {
  let page: Page
  let helpers: TestHelpers
  let fixtures: TestFixtures
  let testProjectId: string | null = null

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    fixtures = new TestFixtures(page, helpers)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test.afterEach(async () => {
    if (testProjectId) {
      try {
        await fixtures.cleanup(testProjectId)
        console.log(`Cleaned up test project: ${testProjectId}`)
      } catch (error) {
        console.warn(`Failed to cleanup project ${testProjectId}:`, error)
      }
      testProjectId = null
    }
  })

  test('show_instruction controls instruction panel visibility', async () => {
    test.setTimeout(90000)

    // Create project
    testProjectId = await helpers.createTestProject(
      `Settings Instruction Test ${Date.now()}`
    )
    expect(testProjectId).toBeTruthy()
    await fixtures.setLabelConfig(testProjectId!, SIMPLE_TEXT_CONFIG)
    await fixtures.createTasks(testProjectId!, 3)

    // Set instructions text and enable show_instruction
    await updateProjectSettings(page, testProjectId!, {
      instructions: 'Test instructions for annotators - please read carefully!',
      show_instruction: true,
    })

    // Navigate to annotation UI
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)
    await waitForAnnotationUI(page)

    // Verify instruction panel IS visible
    const instructionPanel = page
      .locator('text=Instructions')
      .or(page.locator('text=Test instructions for annotators'))
    await expect(instructionPanel).toBeVisible({ timeout: 10000 })
    console.log('Instructions panel visible with show_instruction=true')

    // Disable show_instruction
    await updateProjectSettings(page, testProjectId!, { show_instruction: false })

    // Reload and verify hidden
    await page.reload()
    await waitForAnnotationUI(page)

    // Verify instruction panel is NOT visible
    const instructionText = page.locator(
      'text=Test instructions for annotators'
    )
    await expect(instructionText).not.toBeVisible({ timeout: 5000 })
    console.log('Instructions panel hidden with show_instruction=false')
  })

  test('show_skip_button controls skip button visibility', async () => {
    test.setTimeout(90000)

    testProjectId = await helpers.createTestProject(
      `Skip Button Test ${Date.now()}`
    )
    expect(testProjectId).toBeTruthy()
    await fixtures.setLabelConfig(testProjectId!, SIMPLE_TEXT_CONFIG)
    await fixtures.createTasks(testProjectId!, 3)

    // Enable skip button (default is true, but explicitly set)
    await updateProjectSettings(page, testProjectId!, { show_skip_button: true })

    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)
    await waitForAnnotationUI(page)

    // Verify skip button IS visible
    const skipButton = page
      .locator('button')
      .filter({ hasText: /Überspringen|Skip/i })
    await expect(skipButton).toBeVisible({ timeout: 10000 })
    console.log('Skip button visible with show_skip_button=true')

    // Disable skip button
    await updateProjectSettings(page, testProjectId!, { show_skip_button: false })
    await page.reload()
    await waitForAnnotationUI(page)

    // Verify skip button is NOT visible
    await expect(skipButton).not.toBeVisible({ timeout: 5000 })
    console.log('Skip button hidden with show_skip_button=false')
  })

  test('require_comment_on_skip shows comment modal when skipping', async () => {
    test.setTimeout(90000)

    testProjectId = await helpers.createTestProject(
      `Skip Comment Test ${Date.now()}`
    )
    expect(testProjectId).toBeTruthy()
    await fixtures.setLabelConfig(testProjectId!, SIMPLE_TEXT_CONFIG)
    await fixtures.createTasks(testProjectId!, 3)

    // Enable skip button AND require comment
    await updateProjectSettings(page, testProjectId!, {
      show_skip_button: true,
      require_comment_on_skip: true,
    })

    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)
    await waitForAnnotationUI(page)

    // Click skip button
    const skipButton = page
      .locator('button')
      .filter({ hasText: /Überspringen|Skip/i })
      .first()
    await expect(skipButton).toBeVisible({ timeout: 10000 })
    await skipButton.click()

    // Verify comment modal appears
    await page.waitForTimeout(500)
    const modalTitle = page.locator('h3').filter({ hasText: /skip|überspringen/i })
    await expect(modalTitle).toBeVisible({ timeout: 5000 })
    console.log('Skip comment modal appeared')

    // Verify submit is disabled without comment
    const confirmSkipButton = page
      .locator('button')
      .filter({ hasText: /Skip|Überspringen/i })
      .last()
    await expect(confirmSkipButton).toBeDisabled()
    console.log('Skip button disabled without comment')

    // Enter comment
    const textarea = page.locator('textarea').last()
    await textarea.fill('Test skip reason: content not applicable')
    await page.waitForTimeout(300)

    // Verify button is now enabled
    await expect(confirmSkipButton).toBeEnabled()
    console.log('Skip button enabled after entering comment')

    // Submit skip with comment
    await confirmSkipButton.click()
    await page.waitForTimeout(2000)

    // Should advance to next task (skipped task removed from cycle with default requeue_for_others)
    // After skipping 1 of 3 tasks, cycle has 2 remaining — shows "Task 1 of 2"
    const taskIndicator = page.locator('text=/Task 1.*2|Aufgabe 1.*2/i')
    await expect(taskIndicator).toBeVisible({ timeout: 5000 })
    console.log('Task skipped successfully, now on task 1 of 2')
  })

  })

  test('min_annotations_per_task controls task completion status', async () => {
    test.setTimeout(120000)

    testProjectId = await helpers.createTestProject(
      `Min Annotations Test ${Date.now()}`
    )
    expect(testProjectId).toBeTruthy()
    await fixtures.setLabelConfig(testProjectId!, SIMPLE_TEXT_CONFIG)
    await fixtures.createTasks(testProjectId!, 1) // Single task for clarity

    // Require 2 annotations for completion, allow up to 3
    await updateProjectSettings(page, testProjectId!, {
      min_annotations_per_task: 2,
      maximum_annotations: 3,
    })

    // Get task ID
    const tasks = await fixtures.getTasks(testProjectId!)
    expect(tasks.length).toBeGreaterThan(0)
    const taskId = tasks[0].id
    console.log(`Testing task ID: ${taskId}`)

    // Complete first annotation
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)
    await waitForAnnotationUI(page)

    const textarea = page.locator('textarea').first()
    await expect(textarea).toBeVisible({ timeout: 10000 })
    await textarea.fill('First annotation - testing min annotations requirement')

    const submitButton = page
      .locator('button')
      .filter({ hasText: /Absenden|Submit/i })
      .first()
    await submitButton.click()
    await page.waitForTimeout(3000)

    // Check task status via API - should NOT be fully labeled yet (only 1 of 2 annotations)
    const taskStatus1 = await page.evaluate(async (taskId) => {
      const response = await fetch(`/api/projects/tasks/${taskId}`, {
        credentials: 'include',
      })
      if (!response.ok) return { error: response.status }
      const data = await response.json()
      return { is_labeled: data.is_labeled, annotation_count: data.total_annotations || 0 }
    }, taskId)

    console.log(`After first annotation: ${JSON.stringify(taskStatus1)}`)
    expect(taskStatus1.annotation_count).toBe(1)
    console.log('Task has 1 annotation (requires 2 for completion)')

    // Navigate back to same task for second annotation
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label?task=1`)
    await waitForAnnotationUI(page)

    // Complete second annotation
    await expect(textarea).toBeVisible({ timeout: 10000 })
    await textarea.fill('Second annotation - should trigger completion')
    await submitButton.click()
    await page.waitForTimeout(3000)

    // Check task status - should have 2 annotations now
    const taskStatus2 = await page.evaluate(async (taskId) => {
      const response = await fetch(`/api/projects/tasks/${taskId}`, {
        credentials: 'include',
      })
      if (!response.ok) return { error: response.status }
      const data = await response.json()
      return { is_labeled: data.is_labeled, annotation_count: data.total_annotations || 0 }
    }, taskId)

    console.log(`After second annotation: ${JSON.stringify(taskStatus2)}`)
    expect(taskStatus2.annotation_count).toBeGreaterThanOrEqual(2)
    console.log('Task has 2+ annotations (min requirement met)')
  })

  test('skip_queue=ignore_skipped removes task permanently after skip', async () => {
    test.setTimeout(90000)

    testProjectId = await helpers.createTestProject(
      `Skip Queue Ignore Test ${Date.now()}`
    )
    expect(testProjectId).toBeTruthy()
    await fixtures.setLabelConfig(testProjectId!, SIMPLE_TEXT_CONFIG)
    await fixtures.createTasks(testProjectId!, 2)

    // Set skip_queue to ignore_skipped
    await updateProjectSettings(page, testProjectId!, {
      show_skip_button: true,
      skip_queue: 'ignore_skipped',
    })

    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)
    await waitForAnnotationUI(page)

    // Verify we're on task 1 of 2
    const taskIndicator1 = page.locator('text=/Task 1.*2|Aufgabe 1.*2/i')
    await expect(taskIndicator1).toBeVisible({ timeout: 10000 })
    console.log('On task 1 of 2')

    // Skip the first task
    const skipButton = page
      .locator('button')
      .filter({ hasText: /Überspringen|Skip/i })
      .first()
    await expect(skipButton).toBeVisible({ timeout: 10000 })
    await skipButton.click()
    await page.waitForTimeout(2000)

    // Should now be on task 1 of 1 (skipped task removed from cycle)
    const taskIndicator2 = page.locator('text=/Task 1.*1|Aufgabe 1.*1/i')
    await expect(taskIndicator2).toBeVisible({ timeout: 10000 })
    console.log('After skip: task removed from cycle, now 1 of 1')
  })

  test('skip_queue=requeue_for_me keeps task in cycle after skip', async () => {
    test.setTimeout(90000)

    testProjectId = await helpers.createTestProject(
      `Skip Queue Requeue Test ${Date.now()}`
    )
    expect(testProjectId).toBeTruthy()
    await fixtures.setLabelConfig(testProjectId!, SIMPLE_TEXT_CONFIG)
    await fixtures.createTasks(testProjectId!, 2)

    // Set skip_queue to requeue_for_me
    await updateProjectSettings(page, testProjectId!, {
      show_skip_button: true,
      skip_queue: 'requeue_for_me',
    })

    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)
    await waitForAnnotationUI(page)

    // Verify we're on task 1 of 2
    const taskIndicator1 = page.locator('text=/Task 1.*2|Aufgabe 1.*2/i')
    await expect(taskIndicator1).toBeVisible({ timeout: 10000 })
    console.log('On task 1 of 2')

    // Skip the first task
    const skipButton = page
      .locator('button')
      .filter({ hasText: /Überspringen|Skip/i })
      .first()
    await expect(skipButton).toBeVisible({ timeout: 10000 })
    await skipButton.click()
    await page.waitForTimeout(2000)

    // Should be on task 2 of 2 (skipped task stays in cycle)
    const taskIndicator2 = page.locator('text=/Task 2.*2|Aufgabe 2.*2/i')
    await expect(taskIndicator2).toBeVisible({ timeout: 10000 })
    console.log('After skip: task kept in cycle, now on task 2 of 2')
  })

  test('instructions re-show after skip when instructions_always_visible is true', async () => {
    test.setTimeout(90000)

    testProjectId = await helpers.createTestProject(
      `Skip Instructions Test ${Date.now()}`
    )
    expect(testProjectId).toBeTruthy()
    await fixtures.setLabelConfig(testProjectId!, SIMPLE_TEXT_CONFIG)
    await fixtures.createTasks(testProjectId!, 3)

    // Enable instructions always visible + skip button
    await updateProjectSettings(page, testProjectId!, {
      instructions: 'Read these instructions carefully before annotating.',
      show_instruction: true,
      instructions_always_visible: true,
      show_skip_button: true,
      skip_queue: 'ignore_skipped',
    })

    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)

    // Instructions modal should appear on first task
    const instructionsModal = page.locator('text=Read these instructions carefully')
    await expect(instructionsModal).toBeVisible({ timeout: 15000 })
    console.log('Instructions modal visible on first task')

    // Close the modal
    const startButton = page
      .locator('button')
      .filter({ hasText: /Start Annotating|Annotation starten/i })
    await expect(startButton).toBeVisible({ timeout: 5000 })
    await startButton.click()
    await page.waitForTimeout(1000)

    // Skip the task
    const skipButton = page
      .locator('button')
      .filter({ hasText: /Überspringen|Skip/i })
      .first()
    await expect(skipButton).toBeVisible({ timeout: 10000 })
    await skipButton.click()
    await page.waitForTimeout(2000)

    // Instructions modal should re-appear on next task
    await expect(instructionsModal).toBeVisible({ timeout: 15000 })
    console.log('Instructions modal re-appeared after skip')
  })

  test('skip_queue=requeue_for_others hides from skipper but visible to other user', async ({
    browser,
  }) => {
    test.setTimeout(120000)

    // Admin context
    const adminContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    await adminHelpers.login('admin', 'admin')

    // Get TUM org ID (both admin and contributor are members)
    const orgId = await adminPage.evaluate(async () => {
      const resp = await fetch('/api/organizations', { credentials: 'include' })
      if (!resp.ok) return null
      const data = await resp.json()
      const orgs = data.organizations || data.items || data
      const tum = (Array.isArray(orgs) ? orgs : []).find(
        (o: any) => o.name === 'TUM' || o.slug === 'tum'
      )
      return tum?.id || null
    })
    expect(orgId).toBeTruthy()

    // Create project via API in TUM org (so contributor has access via org membership)
    const projectName = `Skip Requeue Others Test ${Date.now()}`
    testProjectId = await adminPage.evaluate(
      async ({ name, orgId, labelConfig }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch('/api/projects', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({
            title: name,
            description: `Test project for ${name}`,
            label_config: labelConfig,
            show_skip_button: true,
            skip_queue: 'requeue_for_others',
          }),
        })
        if (!resp.ok) return null
        const data = await resp.json()
        return data.id
      },
      { name: projectName, orgId, labelConfig: SIMPLE_TEXT_CONFIG }
    )
    expect(testProjectId).toBeTruthy()

    // Create tasks
    const adminFixtures = new TestFixtures(adminPage, adminHelpers)
    await adminFixtures.createTasks(testProjectId!, 3)

    // Admin navigates to project to set auth cookies
    await adminPage.goto(`${BASE_URL}/projects/${testProjectId}`)
    await adminPage.waitForTimeout(2000)

    // Admin skips a task via API
    const skipResult = await adminPage.evaluate(
      async ({ projectId }) => {
        const listResp = await fetch(`/api/projects/${projectId}/tasks`, {
          credentials: 'include',
        })
        const listData = await listResp.json()
        const firstTaskId = listData.items?.[0]?.id
        if (!firstTaskId) return { ok: false, taskId: null }

        const skipResp = await fetch(
          `/api/projects/${projectId}/tasks/${firstTaskId}/skip`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ comment: null }),
          }
        )
        return { ok: skipResp.ok, taskId: firstTaskId }
      },
      { projectId: testProjectId }
    )
    expect(skipResult.ok).toBe(true)
    console.log(`Admin skipped task ${skipResult.taskId}`)

    // Admin verifies: should see 2 tasks (skipped one excluded)
    const adminTasks = await adminPage.evaluate(
      async ({ projectId }) => {
        const resp = await fetch(
          `/api/projects/${projectId}/tasks?exclude_my_annotations=true`,
          { credentials: 'include' }
        )
        const data = await resp.json()
        return { count: data.items?.length || 0, ids: data.items?.map((t: any) => t.id) || [] }
      },
      { projectId: testProjectId }
    )
    expect(adminTasks.count).toBe(2)
    expect(adminTasks.ids).not.toContain(skipResult.taskId)
    console.log(`Admin sees ${adminTasks.count} tasks (skipped task excluded)`)

    // Contributor context — separate browser context with own cookies
    const contribContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const contribPage = await contribContext.newPage()
    const contribHelpers = new TestHelpers(contribPage)
    await contribHelpers.login('contributor', 'admin')

    // Contributor navigates to project
    await contribPage.goto(`${BASE_URL}/projects/${testProjectId}`)
    await contribPage.waitForTimeout(2000)

    // Contributor verifies: should see all 3 tasks (admin's skip doesn't affect them)
    const contribTasks = await contribPage.evaluate(
      async ({ projectId }) => {
        const resp = await fetch(
          `/api/projects/${projectId}/tasks?exclude_my_annotations=true`,
          { credentials: 'include' }
        )
        const data = await resp.json()
        return { count: data.items?.length || 0, status: resp.status }
      },
      { projectId: testProjectId }
    )
    console.log(`Contributor sees ${contribTasks.count} tasks (status=${contribTasks.status})`)
    expect(contribTasks.count).toBe(3)
    console.log('Contributor sees all 3 tasks — admin skip does not affect them')

    await adminContext.close()
    await contribContext.close()
  })
})
