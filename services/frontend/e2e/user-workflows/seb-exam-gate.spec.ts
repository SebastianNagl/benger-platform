/**
 * E2E tests for the Safe Exam Browser (SEB) exam gate (issue #135).
 *
 * A project with SEB switched on refuses exam content to non-editors unless
 * the request proves it comes from SEB running the exam's configuration.
 * Real SEB cannot run in Playwright, so the tests fake its JavaScript API:
 * `window.SafeExamBrowser.security.configKey` holds
 * `sha256(pageUrlWithoutFragment + ConfigKey)` as lowercase hex, exactly what
 * SEB for macOS / iOS exposes. The platform client forwards it as
 * `X-Benger-SEB-CK` together with the page URL (services/frontend/src/lib/seb.ts)
 * and the API verifies it (services/shared/seb.py).
 *
 * The hash covers the page URL, so every exam visit is a hard `page.goto` of
 * the exact URL the hash was computed for.
 *
 * Extended only: the gate UI (SebGate) and the settings router live in
 * benger-extended.
 */
import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
  type Response,
} from '@playwright/test'
import { createHash } from 'crypto'
import { APISeedingHelper } from '../helpers/api-seeding'
import { SIMPLE_TEXT_CONFIG } from '../helpers/test-fixtures'
import { TestHelpers } from '../helpers/test-helpers'

const HEX_KEY = /^[0-9a-f]{64}$/
const VIEWPORT = { width: 1920, height: 1080 }
// The docker test stack hydrates slowly.
const UI_TIMEOUT = 60000

interface ApiResult {
  status: number
  body: any
}

/** fetch() from the page's origin with the page's session cookies. */
async function apiCall(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<ApiResult> {
  return page.evaluate(
    async ({ method, path, body }) => {
      const resp = await fetch(path, {
        method,
        credentials: 'include',
        headers:
          body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      const text = await resp.text()
      let parsed: unknown = text
      try {
        parsed = JSON.parse(text)
      } catch {
        // Not JSON: keep the text.
      }
      return { status: resp.status, body: parsed }
    },
    { method, path, body },
  )
}

/**
 * Make the user an ANNOTATOR of the project's org (see task-assignment.spec).
 * 400 means "already a member", which is fine.
 */
async function ensureOrgMember(page: Page, orgId: string, userId: string) {
  const result = await apiCall(
    page,
    'POST',
    `/api/organizations/${orgId}/members`,
    {
      user_id: userId,
      role: 'ANNOTATOR',
    },
  )
  if (result.status !== 200 && result.status !== 400) {
    throw new Error(`Adding org member failed: ${result.status}`)
  }
}

/** What SEB puts into `SafeExamBrowser.security.configKey` on `url`. */
function sebConfigKeyHash(url: string, configKey: string): string {
  return createHash('sha256')
    .update(url.split('#', 1)[0] + configKey)
    .digest('hex')
}

/**
 * A logged-in browser context that looks like Safe Exam Browser from the
 * page's point of view. The login happens first, in a normal page; the fake
 * SEB API is installed for every document loaded afterwards.
 */
async function openFakeSebContext(
  browser: Browser,
  configKeyHash: string,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport: VIEWPORT })
  const page = await context.newPage()
  await new TestHelpers(page).login('annotator', 'admin')
  await context.addInitScript((hash: string) => {
    ;(window as unknown as { SafeExamBrowser: unknown }).SafeExamBrowser = {
      version: '3.7.1',
      security: { configKey: hash },
    }
  }, configKeyHash)
  return { context, page }
}

function isStatusResponse(projectId: string) {
  return (r: Response) =>
    r.url().includes(`/api/seb/projects/${projectId}/status`) &&
    r.request().method() === 'GET'
}

function isAnnotationPost(r: Response): boolean {
  return (
    /\/api\/projects\/tasks\/[^/]+\/annotations$/.test(
      new URL(r.url()).pathname,
    ) && r.request().method() === 'POST'
  )
}

function taskIdOfAnnotationPost(r: Response): string {
  const match = new URL(r.url()).pathname.match(
    /\/api\/projects\/tasks\/([^/]+)\/annotations$/,
  )
  if (!match) throw new Error(`Not an annotation POST: ${r.url()}`)
  return match[1]
}

/** Fills the exam's answer field and submits it through the UI. */
async function answerAndSubmit(page: Page, text: string): Promise<Response> {
  const answer = page.locator('textarea').first()
  await expect(answer).toBeVisible({ timeout: UI_TIMEOUT })
  await answer.fill(text)
  const submit = page
    .locator('button')
    .filter({ hasText: /Absenden|Submit/i })
    .first()
  await expect(submit).toBeEnabled({ timeout: 10000 })
  const posted = page.waitForResponse(isAnnotationPost, { timeout: 30000 })
  await submit.click()
  return posted
}

test.describe('Safe Exam Browser exam gate @extended', () => {
  test.describe.configure({ mode: 'serial', timeout: 180000 })

  let adminContext: BrowserContext
  let adminPage: Page
  let seeder: APISeedingHelper
  // The annotator in a normal browser (no SEB).
  let plainContext: BrowserContext
  let plainPage: Page

  let projectId = ''
  let taskIds: string[] = []
  let annotatorUserId = ''
  let examUrl = ''
  let configKey = ''
  let launchUrl = ''
  // Tasks the annotator submitted inside (fake) SEB, in order.
  const submittedTaskIds: string[] = []

  /**
   * The annotator's own, not cancelled annotation on a task (admin read).
   * The list defaults to the caller's own rows, so ask for everyone's.
   */
  async function annotatorAnnotation(taskId: string) {
    const result = await apiCall(
      adminPage,
      'GET',
      `/api/projects/tasks/${taskId}/annotations?all_users=true`,
    )
    expect(result.status).toBe(200)
    const rows: any[] = Array.isArray(result.body)
      ? result.body
      : result.body?.items || []
    return rows.find(
      (a) => a.completed_by === annotatorUserId && !a.was_cancelled,
    )
  }

  async function saveSebSettings(body: Record<string, unknown>) {
    const result = await apiCall(
      adminPage,
      'PUT',
      `/api/seb/projects/${projectId}/settings`,
      body,
    )
    expect(result.status, JSON.stringify(result.body)).toBe(200)
    return result.body
  }

  test.beforeAll(async ({ browser }) => {
    adminContext = await browser.newContext({ viewport: VIEWPORT })
    adminPage = await adminContext.newPage()
    await new TestHelpers(adminPage).login('admin', 'admin')
    seeder = new APISeedingHelper(adminPage)

    const orgs = await apiCall(adminPage, 'GET', '/api/organizations')
    expect(orgs.status).toBe(200)
    const orgList = orgs.body.organizations || orgs.body.items || orgs.body
    const tum = (Array.isArray(orgList) ? orgList : []).find(
      (o: any) => o.name === 'TUM' || o.slug === 'tum',
    )
    expect(tum?.id, 'seeded TUM organization').toBeTruthy()

    const created = await apiCall(adminPage, 'POST', '/api/projects', {
      title: `SEB Exam Gate E2E ${Date.now()}`,
      description: 'Safe Exam Browser gate e2e (issue #135)',
      organization_id: tum.id,
    })
    expect(created.status, JSON.stringify(created.body)).toBeLessThan(300)
    projectId = created.body.id
    expect(projectId).toBeTruthy()

    await seeder.setLabelConfig(projectId, SIMPLE_TEXT_CONFIG)
    const mode = await apiCall(
      adminPage,
      'PATCH',
      `/api/projects/${projectId}`,
      {
        assignment_mode: 'manual',
      },
    )
    expect(mode.status).toBe(200)

    const tasks = await seeder.importTasks(projectId, [
      { data: { text: 'SEB exam task one: explain the gate.' } },
      { data: { text: 'SEB exam task two: explain the key.' } },
    ])
    expect(tasks.length).toBe(2)
    taskIds = tasks.map((t) => t.id)

    plainContext = await browser.newContext({ viewport: VIEWPORT })
    plainPage = await plainContext.newPage()
    await new TestHelpers(plainPage).login('annotator', 'admin')
    const profile = await apiCall(plainPage, 'GET', '/api/auth/profile')
    expect(profile.status).toBe(200)
    annotatorUserId = profile.body.id
    expect(annotatorUserId).toBeTruthy()

    await ensureOrgMember(adminPage, tum.id, annotatorUserId)
    const assigned = await seeder.assignTasks(
      projectId,
      taskIds,
      [annotatorUserId],
      'manual',
    )
    expect(assigned.assignments_created).toBe(2)

    examUrl = `${new URL(adminPage.url()).origin}/projects/${projectId}/label`
  })

  test.afterAll(async () => {
    if (projectId && adminPage) {
      await seeder.cleanupTestProject(projectId)
      await seeder.deleteProject(projectId)
    }
    await plainContext?.close()
    await adminContext?.close()
  })

  test('admin enables SEB and receives a Config Key and launch link', async () => {
    const before = await apiCall(
      adminPage,
      'GET',
      `/api/seb/projects/${projectId}/status`,
    )
    expect(before.status).toBe(200)
    expect(before.body.required).toBe(false)

    const saved = await saveSebSettings({ enabled: true })
    expect(saved.seb_required).toBe(true)
    expect(saved.generated_config_key).toMatch(HEX_KEY)
    expect(saved.config_url).toContain(`/api/seb/config/${projectId}/`)
    expect(saved.config_url).toMatch(/\.seb$/)
    // seb:// on the plain-http test host, sebs:// behind https.
    expect(saved.launch_url).toMatch(/^sebs?:\/\//)
    expect(saved.launch_url).toContain(`/api/seb/config/${projectId}/`)
    configKey = saved.generated_config_key
    launchUrl = saved.launch_url

    // Editors are exempt from the gate.
    const status = await apiCall(
      adminPage,
      'GET',
      `/api/seb/projects/${projectId}/status`,
    )
    expect(status.status).toBe(200)
    expect(status.body.required).toBe(true)
    expect(status.body.editor).toBe(true)
    expect(status.body.blocked).toBe(false)
    expect(status.body.launch_url).toBe(launchUrl)
  })

  test('outside SEB the annotator sees the gate and the API refuses exam reads and writes', async () => {
    const statusSeen = plainPage.waitForResponse(isStatusResponse(projectId), {
      timeout: UI_TIMEOUT,
    })
    await plainPage.goto(examUrl)
    const statusBody = await (await statusSeen).json()
    expect(statusBody.required).toBe(true)
    expect(statusBody.editor).toBe(false)
    expect(statusBody.blocked).toBe(true)
    expect(statusBody.ok).toBe(false)
    expect(statusBody.code).toBe('seb_required')

    await expect(plainPage.getByTestId('seb-gate')).toBeVisible({
      timeout: UI_TIMEOUT,
    })
    // Playwright's Desktop Chrome user agent reports Windows: SEB exists there.
    const launch = plainPage.getByTestId('seb-gate-launch')
    await expect(launch).toBeVisible()
    await expect(launch).toHaveAttribute('href', launchUrl)
    await expect(plainPage.getByTestId('seb-gate-guide')).toBeVisible()
    await expect(plainPage.getByTestId('seb-gate-notice')).toHaveCount(0)
    await expect(plainPage.getByTestId('seb-active-bar')).toHaveCount(0)
    // The exam itself is not rendered.
    await expect(plainPage.locator('textarea')).toHaveCount(0)

    const next = await apiCall(
      plainPage,
      'GET',
      `/api/projects/${projectId}/next`,
    )
    expect(next.status).toBe(403)
    expect(next.body.detail?.code).toBe('seb_required')

    const read = await apiCall(
      plainPage,
      'GET',
      `/api/projects/tasks/${taskIds[0]}`,
    )
    expect(read.status).toBe(403)
    expect(read.body.detail?.code).toBe('seb_required')

    const draft = await apiCall(
      plainPage,
      'PUT',
      `/api/projects/${projectId}/tasks/${taskIds[0]}/draft`,
      {
        result: [
          {
            from_name: 'answer',
            to_name: 'text',
            type: 'textarea',
            value: { text: ['draft written outside SEB'] },
          },
        ],
      },
    )
    expect(draft.status).toBe(403)
    expect(draft.body.detail?.code).toBe('seb_required')

    const submit = await apiCall(
      plainPage,
      'POST',
      `/api/projects/tasks/${taskIds[0]}/annotations`,
      {
        result: [
          {
            from_name: 'answer',
            to_name: 'text',
            type: 'textarea',
            value: { text: ['answer written outside SEB'] },
          },
        ],
        was_cancelled: false,
      },
    )
    expect(submit.status).toBe(403)
    expect(submit.body.detail?.code).toBe('seb_required')
    expect(await annotatorAnnotation(taskIds[0])).toBeUndefined()
  })

  test('inside SEB with the exam configuration the annotator writes and submits', async ({
    browser,
  }) => {
    const { context, page } = await openFakeSebContext(
      browser,
      sebConfigKeyHash(examUrl, configKey),
    )
    try {
      const statusSeen = page.waitForResponse(isStatusResponse(projectId), {
        timeout: UI_TIMEOUT,
      })
      await page.goto(examUrl)
      const statusResponse = await statusSeen
      // The client forwarded the JavaScript API proof for this page.
      const sent = statusResponse.request().headers()
      expect(sent['x-benger-seb-ck']).toBe(sebConfigKeyHash(examUrl, configKey))
      expect(sent['x-benger-seb-url']).toBe(examUrl)
      const statusBody = await statusResponse.json()
      expect(statusBody.required).toBe(true)
      expect(statusBody.ok).toBe(true)
      expect(statusBody.via).toBe('js')
      expect(statusBody.blocked).toBe(false)

      await expect(page.getByTestId('seb-active-bar')).toBeVisible({
        timeout: UI_TIMEOUT,
      })
      await expect(page.getByTestId('seb-gate')).toHaveCount(0)

      const posted = await answerAndSubmit(page, 'Submitted inside SEB.')
      expect(posted.status()).toBeLessThan(300)
      const taskId = taskIdOfAnnotationPost(posted)
      expect(taskIds).toContain(taskId)
      submittedTaskIds.push(taskId)

      const stored = await annotatorAnnotation(taskId)
      expect(stored, 'annotation stored for the annotator').toBeTruthy()
      expect(JSON.stringify(stored.result)).toContain('Submitted inside SEB.')
    } finally {
      await context.close()
    }
  })

  test('inside SEB with a different configuration the gate explains the mismatch', async ({
    browser,
  }) => {
    const wrongKey = createHash('sha256').update('not the exam').digest('hex')
    const { context, page } = await openFakeSebContext(
      browser,
      sebConfigKeyHash(examUrl, wrongKey),
    )
    try {
      const statusSeen = page.waitForResponse(isStatusResponse(projectId), {
        timeout: UI_TIMEOUT,
      })
      await page.goto(examUrl)
      const statusBody = await (await statusSeen).json()
      expect(statusBody.blocked).toBe(true)
      expect(statusBody.ok).toBe(false)
      expect(statusBody.code).toBe('seb_required')

      await expect(page.getByTestId('seb-gate')).toBeVisible({
        timeout: UI_TIMEOUT,
      })
      await expect(page.getByTestId('seb-gate-notice')).toBeVisible()
      // Already inside SEB: no "open in SEB" link, no outside-SEB guide.
      await expect(page.getByTestId('seb-gate-launch')).toHaveCount(0)
      await expect(page.getByTestId('seb-active-bar')).toHaveCount(0)
      await expect(page.locator('textarea')).toHaveCount(0)
    } finally {
      await context.close()
    }
  })

  test('a Config Key change mid-exam flips the open exam to the gate without a reload', async ({
    browser,
  }) => {
    const { context, page } = await openFakeSebContext(
      browser,
      sebConfigKeyHash(examUrl, configKey),
    )
    try {
      await page.goto(examUrl)
      await expect(page.getByTestId('seb-active-bar')).toBeVisible({
        timeout: UI_TIMEOUT,
      })
      const answer = page.locator('textarea').first()
      await expect(answer).toBeVisible({ timeout: UI_TIMEOUT })
      // Survives only as long as the document does.
      await page.evaluate(() => {
        ;(window as unknown as { __sebE2eMarker: string }).__sebE2eMarker =
          'same-document'
      })

      // The organizer changes the configuration while the student writes.
      // Any change regenerates the Config Key; confirm_lockout skips the
      // "students are writing" 409.
      const rotated = await saveSebSettings({
        enabled: true,
        extra_hosts: ['example.org'],
        confirm_lockout: true,
      })
      expect(rotated.generated_config_key).toMatch(HEX_KEY)
      expect(rotated.generated_config_key).not.toBe(configKey)
      configKey = rotated.generated_config_key

      const posted = await answerAndSubmit(
        page,
        'Submitted after the key change.',
      )
      expect(posted.status()).toBe(403)
      expect((await posted.json()).detail?.code).toBe('seb_required')
      const refusedTaskId = taskIdOfAnnotationPost(posted)

      await expect(page.getByTestId('seb-gate')).toBeVisible({ timeout: 15000 })
      await expect(page.getByTestId('seb-gate-notice')).toBeVisible()
      await expect(page.getByTestId('seb-gate-launch')).toHaveCount(0)
      expect(
        await page.evaluate(
          () =>
            (window as unknown as { __sebE2eMarker?: string }).__sebE2eMarker,
        ),
      ).toBe('same-document')
      expect(page.url()).toBe(examUrl)

      // Nothing was stored.
      expect(await annotatorAnnotation(refusedTaskId)).toBeUndefined()
    } finally {
      await context.close()
    }
  })

  test('after submitting every task the annotator reaches their work in a normal browser', async ({
    browser,
  }) => {
    // The student restarts SEB with the new configuration and finishes.
    const { context, page } = await openFakeSebContext(
      browser,
      sebConfigKeyHash(examUrl, configKey),
    )
    try {
      await page.goto(examUrl)
      await expect(page.getByTestId('seb-active-bar')).toBeVisible({
        timeout: UI_TIMEOUT,
      })
      const posted = await answerAndSubmit(page, 'Finished with the new key.')
      expect(posted.status()).toBeLessThan(300)
      submittedTaskIds.push(taskIdOfAnnotationPost(posted))
    } finally {
      await context.close()
    }
    expect([...submittedTaskIds].sort()).toEqual([...taskIds].sort())

    const status = await apiCall(
      plainPage,
      'GET',
      `/api/seb/projects/${projectId}/status`,
    )
    expect(status.status).toBe(200)
    expect(status.body.required).toBe(true)
    expect(status.body.ok).toBe(false)
    expect(status.body.blocked).toBe(false)

    // Submitted tasks stay readable outside SEB.
    for (const taskId of taskIds) {
      const read = await apiCall(
        plainPage,
        'GET',
        `/api/projects/tasks/${taskId}`,
      )
      expect(read.status, `task ${taskId}`).toBe(200)
      expect(read.body.id).toBe(taskId)
      const own = await apiCall(
        plainPage,
        'GET',
        `/api/projects/tasks/${taskId}/annotations`,
      )
      expect(own.status).toBe(200)
      const rows: any[] = Array.isArray(own.body)
        ? own.body
        : own.body?.items || []
      expect(
        rows.some(
          (a) => a.completed_by === annotatorUserId && !a.was_cancelled,
        ),
      ).toBe(true)
    }

    const statusSeen = plainPage.waitForResponse(isStatusResponse(projectId), {
      timeout: UI_TIMEOUT,
    })
    await plainPage.goto(examUrl)
    expect((await (await statusSeen).json()).blocked).toBe(false)
    await expect(plainPage.getByTestId('seb-gate-checking')).toHaveCount(0, {
      timeout: UI_TIMEOUT,
    })
    await expect(plainPage.getByTestId('seb-gate')).toHaveCount(0)
    // Nothing left to write: the labeling page says so instead of the gate.
    await expect(
      plainPage.getByText(
        /No tasks are available for annotation|Keine Aufgaben zur Annotation/,
      ),
    ).toBeVisible({ timeout: UI_TIMEOUT })
  })
})
