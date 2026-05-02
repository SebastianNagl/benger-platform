/**
 * E2E for the public project visibility tier.
 *
 * Verifies end-to-end:
 *   - Superadmin can flip a project to public via PATCH /visibility.
 *   - A different user (annotator role, no org overlap) can list and open
 *     the public project.
 *   - That user is forbidden from editing project settings or visibility.
 *
 * Multi-user flow uses browser.newContext() per Playwright convention in
 * this repo — sharing a single page would mix cookies between users.
 */

import { expect, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

test.describe('Public project visibility', () => {
  test('annotator visitor sees a public CONTRIBUTOR project and is settings-locked', async ({
    browser,
  }) => {
    test.setTimeout(60000)

    // ---- Admin context: create + publish ----
    const adminContext = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
    })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    const adminSeeder = new APISeedingHelper(adminPage)
    await adminHelpers.login('admin', 'admin')

    let projectId: string | null = null
    try {
      projectId = await adminSeeder.createProject('E2E Public Bench')

      const flip = await adminPage.evaluate(async (id) => {
        const r = await fetch(`/api/projects/${id}/visibility`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            is_public: true,
            public_role: 'CONTRIBUTOR',
          }),
        })
        return { ok: r.ok, status: r.status, body: await r.json() }
      }, projectId)
      expect(flip.ok).toBe(true)
      expect(flip.body.is_public).toBe(true)
      expect(flip.body.public_role).toBe('CONTRIBUTOR')
      expect(flip.body.is_private).toBe(false)

      // ---- Annotator context: list, view, edit-attempt ----
      const annContext = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
      })
      const annPage = await annContext.newPage()
      // Block dev auto-login (admin) so the annotator login below sticks.
      await annPage.addInitScript(() =>
        sessionStorage.setItem('e2e_test_mode', 'true')
      )
      const annHelpers = new TestHelpers(annPage)
      await annHelpers.login('annotator', 'admin')

      // Sanity: confirm the visitor session is actually the annotator.
      const me = await annPage.evaluate(async () => {
        const r = await fetch('/api/auth/me', { credentials: 'include' })
        return r.ok ? await r.json() : null
      })
      expect(me?.username).toBe('annotator')

      // 1. GET /projects/{id} → 200 with is_public=true.
      const getOne = await annPage.evaluate(async (id) => {
        const r = await fetch(`/api/projects/${id}`, {
          credentials: 'include',
        })
        return {
          status: r.status,
          body: r.ok ? await r.json() : null,
        }
      }, projectId)
      expect(getOne.status).toBe(200)
      expect(getOne.body?.is_public).toBe(true)
      expect(getOne.body?.public_role).toBe('CONTRIBUTOR')

      // 2. Project appears in the visitor's list under the private context.
      const listed = await annPage.evaluate(async (id) => {
        const r = await fetch('/api/projects/?page=1&page_size=100', {
          credentials: 'include',
          headers: { 'X-Organization-Context': 'private' },
        })
        const body = await r.json()
        const items = body.items ?? body.data ?? []
        return items.some((it: { id: string }) => it.id === id)
      }, projectId)
      expect(listed).toBe(true)

      // 3. PATCH project settings → 403.
      const patchSettings = await annPage.evaluate(async (id) => {
        const r = await fetch(`/api/projects/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ title: 'hijacked' }),
        })
        return r.status
      }, projectId)
      expect(patchSettings).toBe(403)

      // 4. PATCH /visibility → 403.
      const patchVis = await annPage.evaluate(async (id) => {
        const r = await fetch(`/api/projects/${id}/visibility`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ is_private: true }),
        })
        return r.status
      }, projectId)
      expect(patchVis).toBe(403)

      await annContext.close()
    } finally {
      if (projectId) {
        try {
          await adminSeeder.deleteProject(projectId)
        } catch (e) {
          console.log('Cleanup failed:', e)
        }
      }
      await adminContext.close()
    }
  })
})
