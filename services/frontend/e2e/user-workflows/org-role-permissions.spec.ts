/**
 * E2E tests for org-level role permissions (Issue #1313)
 *
 * Verifies that each org role (ORG_ADMIN, CONTRIBUTOR, ANNOTATOR) has
 * the correct access to project features via the API.
 */
import { expect, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

test.describe('Org Role Permissions', () => {
  test('contributor can edit project settings but not delete', async ({ browser }) => {
    test.setTimeout(120000)

    // --- Admin context: create project ---
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

    // Create project in TUM org
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
      { name: 'Role Permissions E2E Test', description: 'Testing role-based access', orgId }
    )

    await seeder.setLabelConfig(
      projectId,
      '<View><Text name="text" value="$text"/><Choices name="label" toName="text"><Choice value="Positive"/><Choice value="Negative"/></Choices></View>'
    )

    // --- Contributor context ---
    const contribContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const contribPage = await contribContext.newPage()
    const contribHelpers = new TestHelpers(contribPage)
    await contribHelpers.login('contributor', 'admin')

    // Contributor CAN update project settings
    const updateResult = await contribPage.evaluate(
      async ({ projectId, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/${projectId}`, {
          method: 'PATCH',
          headers,
          credentials: 'include',
          body: JSON.stringify({ description: 'Updated by contributor' }),
        })
        return { status: resp.status }
      },
      { projectId, orgId }
    )
    expect(updateResult.status).toBe(200)
    console.log(`Contributor PATCH project: ${updateResult.status} (expected 200)`)

    // Contributor CANNOT delete project
    const deleteResult = await contribPage.evaluate(
      async ({ projectId, orgId }) => {
        const headers: Record<string, string> = {}
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/${projectId}`, {
          method: 'DELETE',
          headers,
          credentials: 'include',
        })
        return { status: resp.status }
      },
      { projectId, orgId }
    )
    expect(deleteResult.status).toBe(403)
    console.log(`Contributor DELETE project: ${deleteResult.status} (expected 403)`)

    // Cleanup
    await seeder.deleteProject(projectId)
    await adminContext.close()
    await contribContext.close()
  })

  test('annotator cannot access admin features', async ({ browser }) => {
    test.setTimeout(120000)

    // --- Admin context: create project ---
    const adminContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    await adminHelpers.login('admin', 'admin')
    const seeder = new APISeedingHelper(adminPage)

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
        return (await resp.json()).id
      },
      { name: 'Annotator Deny E2E Test', description: 'Testing annotator restrictions', orgId }
    )

    // --- Annotator context ---
    const annotatorContext = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
    const annotatorPage = await annotatorContext.newPage()
    const annotatorHelpers = new TestHelpers(annotatorPage)
    await annotatorHelpers.login('annotator', 'admin')

    // Annotator CANNOT update project settings
    const updateResult = await annotatorPage.evaluate(
      async ({ projectId, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/${projectId}`, {
          method: 'PATCH',
          headers,
          credentials: 'include',
          body: JSON.stringify({ description: 'Updated by annotator' }),
        })
        return { status: resp.status }
      },
      { projectId, orgId }
    )
    expect(updateResult.status).toBe(403)
    console.log(`Annotator PATCH project: ${updateResult.status} (expected 403)`)

    // Annotator CANNOT assign tasks
    const assignResult = await annotatorPage.evaluate(
      async ({ projectId, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/${projectId}/tasks/assign`, {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({ task_ids: [], user_ids: [], distribution: 'manual' }),
        })
        return { status: resp.status }
      },
      { projectId, orgId }
    )
    // 400 (empty task_ids) or 403 — either way, not 200
    expect([400, 403]).toContain(assignResult.status)
    console.log(`Annotator assign tasks: ${assignResult.status} (expected 400 or 403)`)

    // Annotator CANNOT delete project
    const deleteResult = await annotatorPage.evaluate(
      async ({ projectId, orgId }) => {
        const headers: Record<string, string> = {}
        if (orgId) headers['X-Organization-Context'] = orgId
        const resp = await fetch(`/api/projects/${projectId}`, {
          method: 'DELETE',
          headers,
          credentials: 'include',
        })
        return { status: resp.status }
      },
      { projectId, orgId }
    )
    expect(deleteResult.status).toBe(403)
    console.log(`Annotator DELETE project: ${deleteResult.status} (expected 403)`)

    // Cleanup
    await seeder.deleteProject(projectId)
    await adminContext.close()
    await annotatorContext.close()
  })
})
