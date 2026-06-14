/**
 * E2E tests for the editable task-data modal (Issue #159).
 *
 * Covers:
 *   - Superadmin edits task data via the pencil on the per-project
 *     annotation/data tab (/projects/{id}/data) and the edit persists
 *     across a full page reload.
 *   - Superadmin edits task data via the pencil on the global /data page
 *     and the edit persists across a full page reload.
 *   - An annotator sees the task table WITHOUT the edit pencil (the
 *     view eye stays visible) — multi-user flow uses browser.newContext()
 *     per repo convention so each user gets an isolated cookie jar.
 *
 * Self-contained: every test creates its own project + task via API and
 * cleans it up afterwards; shared seeded projects are never mutated.
 *
 * Selector note: the app's i18n defaults to German ('de' in I18nContext),
 * so all string-based selectors accept BOTH the German and English strings
 * (convention from bulk-export-functionality.spec.ts).
 */

import { expect, Page, test } from '@playwright/test'
import { APISeedingHelper } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

// Pencil / eye buttons on the per-project annotation tab (ProjectDataTab.tsx,
// titles from annotation.editTaskData / annotation.viewTaskData).
const PROJECT_EDIT_PENCIL =
  'button[title="Aufgabendaten bearbeiten"], button[title="Edit task data"]'
const PROJECT_VIEW_EYE =
  'button[title="Vollständige Aufgabendaten anzeigen"], button[title="View complete task data"]'

// Pencil on the global /data page (GlobalDataTab.tsx, title from
// data.management.columnEdit). Generic "Edit"/"Bearbeiten", so always
// scope this selector to a table row.
const GLOBAL_EDIT_PENCIL = 'button[title="Bearbeiten"], button[title="Edit"]'

// FilterToolbar search on /data (data.management.search / searchPlaceholder).
const GLOBAL_SEARCH_TOGGLE = 'button[title="Suchen"], button[title="Search"]'
const GLOBAL_SEARCH_INPUT =
  'input[placeholder="Aufgaben suchen..."], input[placeholder="Search tasks..."]'

// TaskDataViewModal (HeadlessUI Dialog renders role="dialog").
const DIALOG = '[role="dialog"]'
const SAVE_BUTTON = /^(Save|Speichern)$/

const LABEL_CONFIG =
  '<View><Text name="text" value="$text"/><Choices name="sentiment" toName="text"><Choice value="positive"/><Choice value="negative"/></Choices></View>'

/**
 * Create a fresh project with a single task whose data is `{ text: taskText }`.
 * A single string field means the modal's edit mode renders exactly one
 * textarea, which keeps the strict-mode locators below unambiguous.
 */
async function seedProjectWithTask(
  seeder: APISeedingHelper,
  namePrefix: string,
  taskText: string
): Promise<{ projectId: string; taskId: string }> {
  const projectId = await seeder.createProject(`${namePrefix} ${Date.now()}`)
  await seeder.setLabelConfig(projectId, LABEL_CONFIG)
  const tasks = await seeder.importTasks(projectId, [
    { data: { text: taskText } },
  ])
  expect(tasks.length).toBe(1)
  return { projectId, taskId: String(tasks[0].id) }
}

/**
 * The edit modal is already open (pencil was clicked): verify the original
 * value, type the new one, save, and wait until the modal flips back to
 * view mode showing the edited value.
 */
async function editValueInOpenModal(
  page: Page,
  originalText: string,
  editedText: string
) {
  // Don't gate on the Dialog ROOT's visibility: HeadlessUI's root div is a
  // zero-size positioning wrapper that Playwright reports as hidden even
  // while the panel inside is fully rendered. Anchor on panel content.
  const dialog = page.locator(DIALOG)

  // Edit mode renders one textarea per data field; our task has exactly one
  // string field, so this resolves to a single element.
  const textarea = dialog.locator('textarea')
  await textarea.waitFor({ state: 'visible', timeout: 30000 })
  await expect(textarea).toHaveValue(originalText, { timeout: 30000 })

  await textarea.fill(editedText)
  await dialog.getByRole('button', { name: SAVE_BUTTON }).click()

  // A successful PUT flips the modal back to view mode: the edit textareas
  // unmount and the formatted view shows the new value.
  await expect(dialog.locator('textarea')).toHaveCount(0, { timeout: 30000 })
  await expect(dialog).toContainText(editedText, { timeout: 30000 })
}

/** Close the task-data modal via Escape (the X button has no i18n title). */
async function closeModal(page: Page) {
  await page.keyboard.press('Escape')
  // 'detached', not 'hidden': the zero-size dialog root already counts as
  // hidden while open; HeadlessUI unmounts it on close.
  await page.locator(DIALOG).waitFor({ state: 'detached', timeout: 15000 })
}

/**
 * On the global /data page: open the collapsed FilterToolbar search, filter
 * by the task id (the backend matches Task.id ilike), and return the row.
 * The /data table shows no task-data column, so the id is the only stable
 * row anchor — and it stays stable across edits, unlike the data text.
 */
async function searchGlobalDataForTask(page: Page, taskId: string) {
  const searchToggle = page.locator(GLOBAL_SEARCH_TOGGLE).first()
  await searchToggle.waitFor({ state: 'visible', timeout: 45000 })
  await searchToggle.click()

  const searchInput = page.locator(GLOBAL_SEARCH_INPUT)
  await searchInput.waitFor({ state: 'visible', timeout: 15000 })
  await searchInput.fill(taskId)

  // 300ms debounce + refetch before the filtered row appears.
  const row = page.locator('tbody tr').filter({ hasText: taskId })
  await row.waitFor({ state: 'visible', timeout: 30000 })
  return row
}

test.describe('Task Data Edit Modal (#159)', () => {
  test('superadmin edits task data via the pencil on the project annotation tab and the edit persists after reload', async ({
    page,
  }) => {
    test.setTimeout(180000)

    const helpers = new TestHelpers(page)
    const seeder = new APISeedingHelper(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')

    const marker = `E2E159-project-tab-${Date.now()}`
    const originalText = `${marker} original`
    const editedText = `${marker} edited`

    let projectId: string | null = null
    try {
      const seeded = await seedProjectWithTask(
        seeder,
        'Task Data Edit Project Tab',
        originalText
      )
      projectId = seeded.projectId

      // Open the per-project annotation/data tab. Docker hydration is slow,
      // so wait directly on the task row with a generous timeout.
      await page.goto(`${BASE_URL}/projects/${projectId}/data`)
      const row = page.locator('tbody tr').filter({ hasText: originalText })
      await row.waitFor({ state: 'visible', timeout: 45000 })

      // Pencil opens the modal straight in edit mode.
      const pencil = row.locator(PROJECT_EDIT_PENCIL)
      await pencil.waitFor({ state: 'visible', timeout: 30000 })
      await pencil.click()

      await editValueInOpenModal(page, originalText, editedText)
      await closeModal(page)
      console.log('Project tab: edit saved, verifying persistence...')

      // Persistence proof: full reload (fresh server fetch), then re-open
      // the VIEW modal via the eye and assert the edited value is shown.
      await page.reload()
      const editedRow = page.locator('tbody tr').filter({ hasText: editedText })
      await editedRow.waitFor({ state: 'visible', timeout: 45000 })

      await editedRow.locator(PROJECT_VIEW_EYE).click()
      const dialog = page.locator(DIALOG)
      await expect(dialog).toContainText(editedText, { timeout: 30000 })
      await expect(dialog).not.toContainText(originalText)
      await closeModal(page)
      console.log('Project tab: edited value persisted across reload')
    } finally {
      if (projectId) {
        try {
          await seeder.deleteProject(projectId)
        } catch (e) {
          console.log('Cleanup failed:', e)
        }
      }
    }
  })

  test('superadmin edits task data via the pencil on the global /data page and the edit persists after reload', async ({
    page,
  }) => {
    test.setTimeout(180000)

    const helpers = new TestHelpers(page)
    const seeder = new APISeedingHelper(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')

    const marker = `E2E159-global-data-${Date.now()}`
    const originalText = `${marker} original`
    const editedText = `${marker} edited`

    let projectId: string | null = null
    try {
      const seeded = await seedProjectWithTask(
        seeder,
        'Task Data Edit Global Data',
        originalText
      )
      projectId = seeded.projectId

      await page.goto(`${BASE_URL}/data`)
      let row = await searchGlobalDataForTask(page, seeded.taskId)

      // The Edit column pencil opens the modal in edit mode.
      await row.locator(GLOBAL_EDIT_PENCIL).click()
      await editValueInOpenModal(page, originalText, editedText)
      await closeModal(page)
      console.log('Global /data: edit saved, verifying persistence...')

      // Persistence proof: reload, re-filter by the (stable) task id and
      // re-open the modal — the edit buffer is built from the freshly
      // fetched row, so the textarea value reflects the server state.
      await page.reload()
      row = await searchGlobalDataForTask(page, seeded.taskId)
      await row.locator(GLOBAL_EDIT_PENCIL).click()

      const dialog = page.locator(DIALOG)
      await expect(dialog.locator('textarea')).toHaveValue(editedText, {
        timeout: 30000,
      })
      await closeModal(page)
      console.log('Global /data: edited value persisted across reload')
    } finally {
      if (projectId) {
        try {
          await seeder.deleteProject(projectId)
        } catch (e) {
          console.log('Cleanup failed:', e)
        }
      }
    }
  })

  test('annotator sees the task table on the project annotation tab without the edit pencil', async ({
    browser,
  }) => {
    test.setTimeout(180000)

    // --- Admin context: create project + task, then make it public ---
    const adminContext = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
    })
    const adminPage = await adminContext.newPage()
    const adminHelpers = new TestHelpers(adminPage)
    const seeder = new APISeedingHelper(adminPage)
    await adminHelpers.login('admin', 'admin')

    const marker = `E2E159-annotator-${Date.now()}`
    const taskText = `${marker} read only`

    let projectId: string | null = null
    let annotatorContext: Awaited<ReturnType<typeof browser.newContext>> | null =
      null
    try {
      const seeded = await seedProjectWithTask(
        seeder,
        'Task Data Edit Annotator View',
        taskText
      )
      projectId = seeded.projectId

      // Grant the annotator access via the public ANNOTATOR tier (pattern
      // from public-project-visibility.spec.ts). The E2E host runs in
      // private mode, where the UI sends X-Organization-Context: private —
      // org-scoped access paths are unreachable from the browser, so a
      // public project is the way an annotator can open this page in the UI.
      const flip = await adminPage.evaluate(async (id) => {
        const r = await fetch(`/api/projects/${id}/visibility`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ is_public: true, public_role: 'ANNOTATOR' }),
        })
        return { ok: r.ok, status: r.status }
      }, projectId)
      expect(flip.ok).toBe(true)

      // --- Annotator context: separate cookie jar (repo convention —
      // Bearer tokens via page.evaluate don't work, cookies override) ---
      annotatorContext = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
      })
      const annotatorPage = await annotatorContext.newPage()
      // Block dev auto-login (admin) so the annotator login below sticks.
      await annotatorPage.addInitScript(() =>
        sessionStorage.setItem('e2e_test_mode', 'true')
      )
      const annotatorHelpers = new TestHelpers(annotatorPage)
      await annotatorHelpers.login('annotator', 'admin')

      // Sanity: confirm the session is actually the annotator, not admin.
      const me = await annotatorPage.evaluate(async () => {
        const r = await fetch('/api/auth/me', { credentials: 'include' })
        return r.ok ? await r.json() : null
      })
      expect(me?.username).toBe('annotator')

      // The table must actually render for the annotator — an access error
      // or redirect here would prove nothing about the pencil.
      await annotatorPage.goto(`${BASE_URL}/projects/${projectId}/data`)
      const row = annotatorPage.locator('tbody tr').filter({ hasText: taskText })
      await row.waitFor({ state: 'visible', timeout: 45000 })

      // The view (eye) affordance is there for everyone...
      await expect(row.locator(PROJECT_VIEW_EYE)).toBeVisible({
        timeout: 30000,
      })
      await expect(
        annotatorPage
          .locator('thead th')
          .filter({ hasText: /^(View|Ansicht)$/ })
      ).toHaveCount(1)

      // ...but the edit pencil (and its column header) must not be.
      await expect(annotatorPage.locator(PROJECT_EDIT_PENCIL)).toHaveCount(0)
      await expect(
        annotatorPage
          .locator('thead th')
          .filter({ hasText: /^(Edit|Bearbeiten)$/ })
      ).toHaveCount(0)
      console.log('Annotator: table rendered, no edit pencil present')

      // Control: the same project shows the pencil to the superadmin, so
      // the zero-count above can't pass because of a renamed title.
      await adminPage.goto(`${BASE_URL}/projects/${projectId}/data`)
      const adminRow = adminPage
        .locator('tbody tr')
        .filter({ hasText: taskText })
      await adminRow.waitFor({ state: 'visible', timeout: 45000 })
      await expect(adminRow.locator(PROJECT_EDIT_PENCIL)).toBeVisible({
        timeout: 30000,
      })
      console.log('Control: superadmin sees the pencil on the same project')
    } finally {
      if (projectId) {
        try {
          await seeder.deleteProject(projectId)
        } catch (e) {
          console.log('Cleanup failed:', e)
        }
      }
      if (annotatorContext) {
        await annotatorContext.close()
      }
      await adminContext.close()
    }
  })
})
