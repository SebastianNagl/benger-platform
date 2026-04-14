/**
 * E2E tests for task assignment workflow
 *
 * Tests that an admin can assign tasks to an annotator,
 * and the annotator can see them via the my-tasks API.
 * Also tests enforcement: annotators cannot access unassigned tasks in manual mode.
 */
import { expect, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

test.describe('Task Assignment Workflow', () => {
  test('admin assigns tasks and annotator sees them in my-tasks', async ({
    browser,
  }) => {
    test.setTimeout(120000)

    // --- Admin context: create project, import tasks, assign ---
    const adminContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    await adminHelpers.login('admin', 'admin')
    const seeder = new APISeedingHelper(adminPage)

    // Get TUM org ID (both admin and annotator are members)
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

    // Create project in TUM org so annotator has access
    const projectId = await adminPage.evaluate(
      async ({ name, description, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch('/api/projects', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({ title: name, description }),
        })
        if (!resp.ok) throw new Error(`Create project failed: ${resp.status}`)
        const data = await resp.json()
        return data.id
      },
      { name: 'Assignment E2E Test', description: 'Testing task assignment workflow', orgId }
    )
    await seeder.setLabelConfig(
      projectId,
      '<View><Text name="text" value="$text"/><Choices name="label" toName="text"><Choice value="Positive"/><Choice value="Negative"/></Choices></View>'
    )

    // Set project to manual assignment mode
    await adminPage.evaluate(
      async ({ projectId }) => {
        const resp = await fetch(`/api/projects/${projectId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ assignment_mode: 'manual' }),
        })
        if (!resp.ok) throw new Error(`Set assignment_mode failed: ${resp.status}`)
      },
      { projectId }
    )

    // Import tasks
    const tasks = await seeder.importTasks(projectId, [
      { data: { text: 'Assignment test task 1' } },
      { data: { text: 'Assignment test task 2' } },
      { data: { text: 'Assignment test task 3' } },
    ])
    expect(tasks.length).toBe(3)
    const taskIds = tasks.map((t) => t.id)

    // --- Annotator context: get real user ID ---
    // Must use separate context to get the annotator's actual session user ID,
    // because the test DB may have duplicate users with the same username
    const annotatorContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const annotatorPage = await annotatorContext.newPage()
    const annotatorHelpers = new TestHelpers(annotatorPage)
    await annotatorHelpers.login('annotator', 'admin')

    const annotatorUserId = await annotatorPage.evaluate(async () => {
      const resp = await fetch('/api/auth/profile', { credentials: 'include' })
      if (!resp.ok) return null
      const data = await resp.json()
      return data.id
    })
    expect(annotatorUserId).toBeTruthy()

    // Add annotator as project member (from admin context)
    await adminPage.evaluate(
      async ({ projectId, userId }) => {
        await fetch(`/api/projects/${projectId}/members/${userId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ role: 'ANNOTATOR' }),
        })
      },
      { projectId, userId: annotatorUserId }
    )

    // Assign tasks to annotator (from admin context)
    const assignResult = await seeder.assignTasks(
      projectId,
      taskIds,
      [annotatorUserId],
      'manual'
    )
    expect(assignResult.assignments_created).toBe(3)

    // --- Verify annotator sees assigned tasks via API ---
    const myTasks = await annotatorPage.evaluate(
      async ({ projectId, orgId }) => {
        const resp = await fetch(`/api/projects/${projectId}/my-tasks`, {
          credentials: 'include',
          headers: orgId ? { 'X-Organization-Context': orgId } : {},
        })
        if (!resp.ok) return { count: 0, status: resp.status }
        const data = await resp.json()
        return { count: data.tasks?.length || 0, status: resp.status }
      },
      { projectId, orgId }
    )
    expect(myTasks.count).toBe(3)
    console.log(`Annotator sees ${myTasks.count} assigned tasks`)

    // Cleanup
    await seeder.deleteProject(projectId)
    await adminContext.close()
    await annotatorContext.close()
  })

  test('annotator cannot access unassigned tasks in manual mode', async ({
    browser,
  }) => {
    test.setTimeout(120000)

    // --- Admin context ---
    const adminContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    await adminHelpers.login('admin', 'admin')
    const seeder = new APISeedingHelper(adminPage)

    // Get TUM org ID
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

    // Create project with manual assignment mode
    const projectId = await adminPage.evaluate(
      async ({ name, description, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch('/api/projects', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({ title: name, description }),
        })
        if (!resp.ok) throw new Error(`Create project failed: ${resp.status}`)
        const data = await resp.json()
        return data.id
      },
      { name: 'Assignment Enforcement E2E', description: 'Testing manual assignment enforcement', orgId }
    )

    await seeder.setLabelConfig(
      projectId,
      '<View><Text name="text" value="$text"/><Choices name="label" toName="text"><Choice value="Positive"/><Choice value="Negative"/></Choices></View>'
    )

    // Set manual assignment mode
    await adminPage.evaluate(
      async ({ projectId }) => {
        const resp = await fetch(`/api/projects/${projectId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ assignment_mode: 'manual' }),
        })
        if (!resp.ok) throw new Error(`Set assignment_mode failed: ${resp.status}`)
      },
      { projectId }
    )

    // Import 5 tasks
    const tasks = await seeder.importTasks(projectId, [
      { data: { text: 'Enforcement test task 1' } },
      { data: { text: 'Enforcement test task 2' } },
      { data: { text: 'Enforcement test task 3' } },
      { data: { text: 'Enforcement test task 4 (unassigned)' } },
      { data: { text: 'Enforcement test task 5 (unassigned)' } },
    ])
    expect(tasks.length).toBe(5)

    // --- Annotator context ---
    const annotatorContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const annotatorPage = await annotatorContext.newPage()
    const annotatorHelpers = new TestHelpers(annotatorPage)
    await annotatorHelpers.login('annotator', 'admin')

    const annotatorUserId = await annotatorPage.evaluate(async () => {
      const resp = await fetch('/api/auth/profile', { credentials: 'include' })
      if (!resp.ok) return null
      const data = await resp.json()
      return data.id
    })
    expect(annotatorUserId).toBeTruthy()

    // Add annotator as project member
    await adminPage.evaluate(
      async ({ projectId, userId }) => {
        await fetch(`/api/projects/${projectId}/members/${userId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ role: 'ANNOTATOR' }),
        })
      },
      { projectId, userId: annotatorUserId }
    )

    // Assign only first 3 tasks to annotator (tasks 4-5 remain unassigned)
    const assignedTaskIds = tasks.slice(0, 3).map((t) => t.id)
    const unassignedTaskIds = tasks.slice(3).map((t) => t.id)

    const assignResult = await seeder.assignTasks(
      projectId,
      assignedTaskIds,
      [annotatorUserId],
      'manual'
    )
    expect(assignResult.assignments_created).toBe(3)

    // --- Enforcement checks from annotator context ---

    // 1. Task listing returns only 3 assigned tasks (not 5)
    const taskListResult = await annotatorPage.evaluate(
      async ({ projectId, orgId }) => {
        const headers: Record<string, string> = {}
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/${projectId}/tasks`, {
          credentials: 'include',
          headers,
        })
        if (!resp.ok) return { total: -1, status: resp.status }
        const data = await resp.json()
        return { total: data.total, status: resp.status }
      },
      { projectId, orgId }
    )
    expect(taskListResult.total).toBe(3)
    console.log(`Task listing shows ${taskListResult.total} tasks (expected 3)`)

    // 2. GET unassigned task returns 404 (Label Studio aligned: invisible)
    const getUnassignedResult = await annotatorPage.evaluate(
      async ({ taskId, orgId }) => {
        const headers: Record<string, string> = {}
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/tasks/${taskId}`, {
          credentials: 'include',
          headers,
        })
        return { status: resp.status }
      },
      { taskId: unassignedTaskIds[0], orgId }
    )
    expect(getUnassignedResult.status).toBe(404)
    console.log(`GET unassigned task: ${getUnassignedResult.status} (expected 404)`)

    // 3. POST annotation on unassigned task returns 404 (Label Studio aligned: invisible)
    const annotateUnassignedResult = await annotatorPage.evaluate(
      async ({ taskId, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/tasks/${taskId}/annotations`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify({
            result: [{ type: 'choices', value: { choices: ['Positive'] } }],
          }),
        })
        return { status: resp.status }
      },
      { taskId: unassignedTaskIds[0], orgId }
    )
    expect(annotateUnassignedResult.status).toBe(404)
    console.log(`POST annotation on unassigned task: ${annotateUnassignedResult.status} (expected 404)`)

    // 4. GET assigned task works
    const getAssignedResult = await annotatorPage.evaluate(
      async ({ taskId, orgId }) => {
        const headers: Record<string, string> = {}
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/tasks/${taskId}`, {
          credentials: 'include',
          headers,
        })
        return { status: resp.status }
      },
      { taskId: assignedTaskIds[0], orgId }
    )
    expect(getAssignedResult.status).toBe(200)

    // 5. POST annotation on assigned task works
    const annotateAssignedResult = await annotatorPage.evaluate(
      async ({ taskId, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/tasks/${taskId}/annotations`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify({
            result: [{ type: 'choices', value: { choices: ['Positive'] } }],
          }),
        })
        return { status: resp.status }
      },
      { taskId: assignedTaskIds[0], orgId }
    )
    expect(annotateAssignedResult.status).toBe(200)
    console.log('Annotator can annotate assigned task: 200')

    // 6. Next task endpoint returns only assigned tasks
    const nextTaskResult = await annotatorPage.evaluate(
      async ({ projectId, orgId, assignedIds }) => {
        const headers: Record<string, string> = {}
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/${projectId}/next`, {
          credentials: 'include',
          headers,
        })
        const data = await resp.json()
        return {
          taskId: data.task?.id || null,
          isAssigned: assignedIds.includes(data.task?.id),
          status: resp.status,
        }
      },
      { projectId, orgId, assignedIds: assignedTaskIds }
    )
    expect(nextTaskResult.taskId).toBeTruthy()
    expect(nextTaskResult.isAssigned).toBe(true)
    console.log('Next task is from assigned set: OK')

    // Cleanup
    await seeder.deleteProject(projectId)
    await adminContext.close()
    await annotatorContext.close()
  })
})
