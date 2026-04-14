/**
 * E2E Tests: Randomize Task Order
 * Tests the randomize_task_order project setting and per-user annotation filtering.
 *
 * Verifies:
 * 1. Setting toggle persists via API
 * 2. Different users see different task orderings when enabled
 * 3. Sequential ordering when disabled
 * 4. Submitted tasks are excluded from the user's task list (exclude_my_annotations)
 * 5. Task count decreases after annotation submission
 * 6. Page reload preserves task position
 */
import { expect, Page, test } from '@playwright/test'
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
 * Helper: Get project task IDs via API with optional per-user filtering
 */
async function getTaskIds(
  page: Page,
  projectId: string,
  excludeMyAnnotations: boolean = false
): Promise<string[]> {
  return await page.evaluate(
    async ({ projectId, excludeMyAnnotations }) => {
      const params = new URLSearchParams({ page_size: '50' })
      if (excludeMyAnnotations) {
        params.append('exclude_my_annotations', 'true')
      }
      const response = await fetch(
        `/api/projects/${projectId}/tasks?${params}`,
        { credentials: 'include' }
      )
      if (!response.ok) return []
      const data = await response.json()
      const items = data.items || data.tasks || []
      return items.map((t: { id: string }) => t.id)
    },
    { projectId, excludeMyAnnotations }
  )
}

/**
 * Helper: Create project with tasks via API (logged in as admin)
 */
async function createProjectWithTasks(
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
          description: `Test project: ${name}`,
        }),
      })
      if (!projectResp.ok) {
        return { error: `Create failed: ${projectResp.status}` }
      }
      const project = await projectResp.json()
      const projectId = project.id

      // Set label config
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
        }),
      })
      if (!configResp.ok) {
        return { error: `Config failed: ${configResp.status}` }
      }

      // Import tasks with unique text per task
      const tasks = Array.from({ length: taskCount }, (_, i) => ({
        data: { text: `Task ${i + 1}: Legal analysis question number ${i + 1}` },
      }))
      const importResp = await fetch(`/api/projects/${projectId}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ data: tasks }),
      })
      if (!importResp.ok) {
        return { error: `Import failed: ${importResp.status}` }
      }

      return { projectId }
    },
    { name, taskCount }
  )

  if ('error' in result) {
    throw new Error(result.error as string)
  }
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

test.describe('Randomize Task Order', () => {
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
        console.log(`Cleaned up test project: ${testProjectId}`)
      } catch (error) {
        console.warn(`Failed to cleanup project ${testProjectId}:`, error)
      }
      testProjectId = null
    }
  })

  test('randomize_task_order setting persists and affects task ordering', async () => {
    test.setTimeout(90000)

    // Create project with 10 tasks
    testProjectId = await createProjectWithTasks(
      page,
      `E2E Randomize Order ${Date.now()}`,
      10
    )
    expect(testProjectId).toBeTruthy()

    // Get sequential order (default: randomize_task_order=false)
    const sequentialIds = await getTaskIds(page, testProjectId!)
    expect(sequentialIds.length).toBe(10)
    console.log('Sequential IDs (first 5):', sequentialIds.slice(0, 5).map(id => id.substring(0, 8)))

    // Enable randomize_task_order
    await updateProjectSettings(page, testProjectId!, {
      randomize_task_order: true,
    })

    // Get randomized order
    const randomizedIds = await getTaskIds(page, testProjectId!)
    expect(randomizedIds.length).toBe(10)
    console.log('Randomized IDs (first 5):', randomizedIds.slice(0, 5).map(id => id.substring(0, 8)))

    // Verify the orderings are different
    // (With 10 tasks, the probability of identical ordering is 1/10! = ~0.00003%)
    const orderChanged = sequentialIds.some((id, i) => id !== randomizedIds[i])
    expect(orderChanged).toBe(true)
    console.log('Randomized order differs from sequential order')

    // Verify randomized order is deterministic (same request = same order)
    const randomizedIds2 = await getTaskIds(page, testProjectId!)
    expect(randomizedIds2).toEqual(randomizedIds)
    console.log('Randomized order is deterministic (same on repeat request)')
  })

  test('different users see different task orderings when randomized', async ({
    browser,
  }) => {
    test.setTimeout(120000)

    // Admin context
    const adminContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    await adminHelpers.login('admin', 'admin')

    // Get TUM org ID so all users have access via org membership
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

    // Create project in TUM org
    testProjectId = await adminPage.evaluate(
      async ({ name, taskCount, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId

        // Create project
        const projectResp = await fetch('/api/projects', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({
            title: name,
            description: `Test project: ${name}`,
          }),
        })
        if (!projectResp.ok) return null
        const project = await projectResp.json()
        const projectId = project.id

        // Set label config
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
          }),
        })
        if (!configResp.ok) return null

        // Import tasks
        const tasks = Array.from({ length: taskCount }, (_, i) => ({
          data: { text: `Task ${i + 1}: Legal analysis question number ${i + 1}` },
        }))
        const importResp = await fetch(`/api/projects/${projectId}/import`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ data: tasks }),
        })
        if (!importResp.ok) return null

        return projectId
      },
      { name: `E2E Multi-User Order ${Date.now()}`, taskCount: 10, orgId }
    )
    expect(testProjectId).toBeTruthy()

    // Enable randomization
    await updateProjectSettings(adminPage, testProjectId!, {
      randomize_task_order: true,
    })

    // Get task order for admin
    const adminIds = await getTaskIds(adminPage, testProjectId!)
    expect(adminIds.length).toBe(10)

    // Contributor context
    const contribContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const contribPage = await contribContext.newPage()
    const contribHelpers = new TestHelpers(contribPage)
    await contribHelpers.login('contributor', 'admin')

    const contributorIds = await getTaskIds(contribPage, testProjectId!)
    expect(contributorIds.length).toBe(10)

    // Annotator context
    const annotatorContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const annotatorPage = await annotatorContext.newPage()
    const annotatorHelpers = new TestHelpers(annotatorPage)
    await annotatorHelpers.login('annotator', 'admin')

    const annotatorIds = await getTaskIds(annotatorPage, testProjectId!)
    expect(annotatorIds.length).toBe(10)

    console.log('Admin first 3:', adminIds.slice(0, 3).map(id => id.substring(0, 8)))
    console.log('Contributor first 3:', contributorIds.slice(0, 3).map(id => id.substring(0, 8)))
    console.log('Annotator first 3:', annotatorIds.slice(0, 3).map(id => id.substring(0, 8)))

    // At least 2 of 3 users should have different orderings
    // (probability of all 3 being identical is astronomically low)
    const adminVsContributor = adminIds.some((id, i) => id !== contributorIds[i])
    const adminVsAnnotator = adminIds.some((id, i) => id !== annotatorIds[i])
    const diffCount = [adminVsContributor, adminVsAnnotator].filter(Boolean).length
    expect(diffCount).toBeGreaterThanOrEqual(1)
    console.log(`Different orderings: admin vs contributor=${adminVsContributor}, admin vs annotator=${adminVsAnnotator}`)

    // All users see the same set of tasks (just different order)
    expect([...adminIds].sort()).toEqual([...contributorIds].sort())
    expect([...adminIds].sort()).toEqual([...annotatorIds].sort())
    console.log('All users see the same set of tasks')

    // Cleanup
    await deleteProject(adminPage, testProjectId!)
    testProjectId = null
    await adminContext.close()
    await contribContext.close()
    await annotatorContext.close()
  })

  test('exclude_my_annotations filters submitted tasks per user', async ({
    browser,
  }) => {
    test.setTimeout(120000)

    // Admin context
    const adminContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    await adminHelpers.login('admin', 'admin')

    // Get TUM org ID so annotator has access via org membership
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

    // Create project in TUM org
    testProjectId = await adminPage.evaluate(
      async ({ name, taskCount, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId

        const projectResp = await fetch('/api/projects', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({
            title: name,
            description: `Test project: ${name}`,
          }),
        })
        if (!projectResp.ok) return null
        const project = await projectResp.json()
        const projectId = project.id

        // Set label config
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
          }),
        })
        if (!configResp.ok) return null

        // Import tasks
        const tasks = Array.from({ length: taskCount }, (_, i) => ({
          data: { text: `Task ${i + 1}: Legal analysis question number ${i + 1}` },
        }))
        const importResp = await fetch(`/api/projects/${projectId}/import`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ data: tasks }),
        })
        if (!importResp.ok) return null

        return projectId
      },
      { name: `E2E Exclude Annotations ${Date.now()}`, taskCount: 5, orgId }
    )
    expect(testProjectId).toBeTruthy()

    // Get all task IDs before annotation (admin context)
    const allTasks = await getTaskIds(adminPage, testProjectId!)
    expect(allTasks.length).toBe(5)
    const taskToAnnotate = allTasks[0]

    // Submit an annotation on the first task as admin
    const annotationResult = await adminPage.evaluate(
      async ({ taskId }) => {
        const response = await fetch(`/api/projects/tasks/${taskId}/annotations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            result: [
              {
                from_name: 'sentiment',
                to_name: 'text',
                type: 'choices',
                value: { choices: ['positive'] },
              },
            ],
          }),
        })
        return { ok: response.ok, status: response.status }
      },
      { taskId: taskToAnnotate }
    )
    expect(annotationResult.ok).toBe(true)
    console.log(`Submitted annotation on task ${taskToAnnotate.substring(0, 8)}`)

    // Get tasks WITHOUT per-user filtering (admin sees all)
    const allTasksAfter = await getTaskIds(adminPage, testProjectId!)
    expect(allTasksAfter.length).toBe(5)
    console.log('Without filter: still 5 tasks')

    // Get tasks WITH per-user filtering (admin's annotated task excluded)
    const filteredTasks = await getTaskIds(adminPage, testProjectId!, true)
    expect(filteredTasks.length).toBe(4)
    expect(filteredTasks).not.toContain(taskToAnnotate)
    console.log('With exclude_my_annotations: 4 tasks (annotated task excluded)')

    // Annotator context — separate browser context with own cookies
    const annotatorContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const annotatorPage = await annotatorContext.newPage()
    const annotatorHelpers = new TestHelpers(annotatorPage)
    await annotatorHelpers.login('annotator', 'admin')

    // Verify the annotator still sees all 5 tasks (per-user, not global)
    const annotatorFiltered = await annotatorPage.evaluate(
      async ({ projectId }) => {
        const response = await fetch(
          `/api/projects/${projectId}/tasks?page_size=50&exclude_my_annotations=true`,
          { credentials: 'include' }
        )
        if (!response.ok) return { total: 0 }
        const data = await response.json()
        return { total: data.total || (data.items || []).length }
      },
      { projectId: testProjectId! }
    )
    expect(annotatorFiltered.total).toBe(5)
    console.log('Annotator with filter: still 5 tasks (per-user, not global)')

    // Cleanup
    await deleteProject(adminPage, testProjectId!)
    testProjectId = null
    await adminContext.close()
    await annotatorContext.close()
  })

  test('annotation UI shows correct task count with randomized order', async () => {
    test.setTimeout(120000)

    testProjectId = await createProjectWithTasks(
      page,
      `E2E UI Task Count ${Date.now()}`,
      6
    )
    expect(testProjectId).toBeTruthy()

    // Enable randomization
    await updateProjectSettings(page, testProjectId!, {
      randomize_task_order: true,
    })

    // Navigate to annotation UI
    await page.goto(`${BASE_URL}/projects/${testProjectId}/label`)

    // Wait for annotation interface to load
    const taskCounter = page.locator('text=/Task \\d+ of \\d+/i')
    await expect(taskCounter).toBeVisible({ timeout: 20000 })

    // Verify it shows "Task 1 of 6"
    const counterText = await taskCounter.textContent()
    expect(counterText).toMatch(/Task 1 of 6/i)
    console.log(`Task counter: ${counterText}`)

    // Reload and verify position persists
    await page.reload()

    const taskCounterAfterReload = page.locator('text=/Task \\d+ of \\d+/i')
    await expect(taskCounterAfterReload).toBeVisible({ timeout: 20000 })

    const counterTextAfterReload = await taskCounterAfterReload.textContent()
    expect(counterTextAfterReload).toMatch(/Task 1 of 6/i)
    console.log(`After reload: ${counterTextAfterReload}`)
  })
})
