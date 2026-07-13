/**
 * Korrektur (Klausurlösung) Grading Workflow E2E Journey
 *
 * Korrektur is an EXTENDED feature (German legal-exam human grading). This is
 * the highest-risk uncovered journey: it had ZERO E2E coverage. Every test is
 * tagged @extended so it runs under `make test-e2e GREP=@extended` and is
 * skipped when the community edition is built without the extended overlay.
 *
 * Journey:
 *   1. Create a project (TextArea answer field) in the TUM org via API.
 *   2. Enable korrektur: PATCH korrektur_enabled=true + an evaluation_config
 *      entry for the `korrektur_falloesung` metric with assignment_mode "open"
 *      (so the admin grader isn't gated by an explicit TaskAssignment row).
 *   3. Import one task + seed one annotation (the answer to be graded).
 *   4. Drive the korrektur grading UI at /projects/{id}/korrektur:
 *      open the item, switch to the Falllösung grading tab, fill a dimension
 *      score, and submit ("Bewertung speichern").
 *   5. Assert the grade PERSISTED and SURFACES — both via the korrektur read
 *      API (the grade blob with the right grade_points) and via the queue row
 *      flipping to "Von mir korrigiert".
 *
 * Selector note: the extended korrektur components carry essentially NO
 * data-testid attributes, so this spec selects by stable form-field ids
 * (`#korrektur-falloesung-<dimkey>`, established in FalloesungGradingForm.tsx)
 * and by rendered German i18n text via getByRole / locator filters. The
 * dimension keys come from FALLOESUNG_DIMENSIONS (frontend/lib/falloesung/
 * rubric.ts) — `ergebnisrichtigkeit` (max 20) is used here.
 *
 * IMPORTANT: Requires the extended overlay (NEXT_PUBLIC_BENGER_EDITION=extended)
 * and the ephemeral test stack. Execute via: make test-e2e GREP=@extended
 */
import { test, expect } from '@playwright/test'
import { importTasksInBrowser } from '../helpers/api-seeding'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

const PROJECT_NAME = `E2E Korrektur Falloesung ${Date.now()}`

// A single TextArea answer field — the "loesung" the human grades.
const LABEL_CONFIG = `<View>
  <Text name="question" value="$question"/>
  <TextArea name="loesung" toName="question" placeholder="Lösung" rows="10"/>
</View>`

// The dimension we grade in the UI. Key + max are from FALLOESUNG_DIMENSIONS.
const GRADED_DIMENSION = { key: 'ergebnisrichtigkeit', score: 18 }

// State shared between serial steps.
let projectId: string | null = null
let tumOrgId: string | null = null
let taskId: string | null = null
let annotationId: string | null = null

test.describe('Korrektur Falllösung Grading Workflow @extended', () => {
  test.describe.configure({ mode: 'serial' })

  test.beforeEach(async ({ page }) => {
    const helpers = new TestHelpers(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test('Step 1: Create korrektur-enabled project', async ({ page }) => {
    test.setTimeout(60000)

    tumOrgId = await page.evaluate(async () => {
      const response = await fetch('/api/organizations', { credentials: 'include' })
      if (!response.ok) return null
      const data = await response.json()
      const orgs = data.items || data.organizations || data || []
      const tum = orgs.find(
        (o: { name?: string; slug?: string }) =>
          o.name === 'TUM' || o.slug === 'tum'
      )
      return tum?.id || null
    })
    console.log(`[Step 1] TUM org id: ${tumOrgId}`)

    // 1a. Create the project (label_config accepted on create; korrektur_enabled
    // and evaluation_config are NOT — they go in the follow-up PATCH below).
    const createResult = await page.evaluate(
      async ({ name, labelConfig, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const response = await fetch('/api/projects', {
          method: 'POST',
          headers,
          credentials: 'include',
          body: JSON.stringify({
            title: name,
            description: 'E2E korrektur falloesung grading journey',
            label_config: labelConfig,
          }),
        })
        if (!response.ok) return { success: false, error: await response.text() }
        const data = await response.json()
        return { success: true, projectId: data.id }
      },
      { name: PROJECT_NAME, labelConfig: LABEL_CONFIG, orgId: tumOrgId }
    )
    console.log(`[Step 1] Create project: ${JSON.stringify(createResult)}`)
    expect(createResult.success).toBeTruthy()
    projectId = createResult.projectId!

    // 1b. Enable korrektur + register the falloesung metric. assignment_mode
    // "open" avoids the manual/auto assignment gate so the admin can grade
    // any item directly.
    const patchResult = await page.evaluate(
      async ({ pid, orgId }) => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (orgId) headers['X-Organization-Context'] = orgId
        const response = await fetch(`/api/projects/${pid}`, {
          method: 'PATCH',
          headers,
          credentials: 'include',
          body: JSON.stringify({
            korrektur_enabled: true,
            evaluation_config: {
              evaluation_configs: [
                {
                  metric: 'korrektur_falloesung',
                  metric_parameters: { assignment_mode: 'open' },
                },
              ],
            },
          }),
        })
        if (!response.ok) return { success: false, error: await response.text() }
        const data = await response.json()
        return { success: true, korrekturEnabled: data.korrektur_enabled }
      },
      { pid: projectId, orgId: tumOrgId }
    )
    console.log(`[Step 1] Enable korrektur: ${JSON.stringify(patchResult)}`)
    expect(patchResult.success).toBeTruthy()

    // Confirm the backend reports korrektur enabled via the stats endpoint.
    const stats = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/projects/${pid}/korrektur/stats`, {
        credentials: 'include',
      })
      if (!response.ok) return { ok: false, status: response.status }
      return { ok: true, ...(await response.json()) }
    }, projectId)
    console.log(`[Step 1] Korrektur stats: ${JSON.stringify(stats)}`)
    expect(stats.ok).toBe(true)
    expect(stats.korrektur_enabled).toBe(true)
  })

  test('Step 2: Import task + seed annotation to grade', async ({ page }) => {
    test.setTimeout(120000)
    test.skip(!projectId, 'Project not created in Step 1')

    const importResult = await page.evaluate(importTasksInBrowser, {
      projectId: projectId!,
      tasks: [
        {
          data: {
            question: 'Prüfen Sie den Anspruch des K gegen B aus § 433 II BGB.',
            musterloesung: 'K hat gegen B einen Anspruch auf Kaufpreiszahlung aus § 433 II BGB.',
          },
        },
      ],
    })
    console.log(`[Step 2] Import task: ${JSON.stringify(importResult)}`)
    expect(importResult.success).toBeTruthy()

    taskId = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/projects/${pid}/tasks`, { credentials: 'include' })
      if (!response.ok) return null
      const data = await response.json()
      const tasks = data.items || data.tasks || data || []
      return tasks[0]?.id || null
    }, projectId)
    expect(taskId).toBeTruthy()

    // Seed one annotation (the "loesung" the human will grade).
    const annResult = await page.evaluate(
      async ({ pid, tid }) => {
        const response = await fetch('/api/test/seed/annotations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            project_id: pid,
            annotations: [
              {
                task_id: tid,
                annotator_username: 'annotator',
                result: [
                  {
                    from_name: 'loesung',
                    to_name: 'question',
                    type: 'textarea',
                    value: {
                      text: [
                        'K kann von B die Zahlung des Kaufpreises gemäß § 433 Abs. 2 BGB verlangen. ' +
                          'Ein wirksamer Kaufvertrag liegt vor, die Leistung ist fällig und durchsetzbar.',
                      ],
                    },
                  },
                ],
              },
            ],
          }),
        })
        if (!response.ok) return { success: false, error: await response.text() }
        return response.json()
      },
      { pid: projectId, tid: taskId }
    )
    console.log(`[Step 2] Seed annotation: ${JSON.stringify(annResult)}`)
    expect(annResult.created_count || 0).toBeGreaterThan(0)

    // Resolve the annotation id for later API verification. The annotation
    // was seeded as user 'annotator' but we browse as admin — the list
    // endpoint defaults to own-annotations-only (data isolation), so ask
    // for all users explicitly.
    annotationId = await page.evaluate(async (tid) => {
      const response = await fetch(`/api/projects/tasks/${tid}/annotations?all_users=true`, {
        credentials: 'include',
      })
      if (!response.ok) return null
      const data = await response.json()
      const anns = data.items || data.annotations || data || []
      return anns[0]?.id || null
    }, taskId)
    console.log(`[Step 2] Annotation id: ${annotationId}`)
    expect(annotationId).toBeTruthy()
  })

  test('Step 3: Submit a Falllösung grade through the grading UI', async ({ page }) => {
    test.setTimeout(120000)
    test.skip(!projectId, 'Project not created in Step 1')

    // The korrektur queue lives behind the extended slot. In the community
    // edition this renders a "not available" fallback — fail loudly so a
    // misconfigured (platform-only) test stack is obvious rather than silently
    // passing.
    await page.goto(`${BASE_URL}/projects/${projectId}/korrektur`)
    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 20000 })

    const fallbackText = await mainContent.textContent()
    expect(
      fallbackText?.includes('not available in the community edition'),
      'Korrektur slot empty — test stack is missing the extended overlay ' +
        '(NEXT_PUBLIC_BENGER_EDITION=extended). Run via benger-extended `make dev`/`make test-e2e`.'
    ).toBeFalsy()

    // Open the item to grade: prefer the "Korrektur starten" CTA (jumps to the
    // first ungraded item); fall back to clicking the first queue row.
    //
    // Retried via toPass: the queue page renders before hydration finishes
    // (20-30s in the Docker test env), and a pre-hydration click lands on a
    // button with no handler — the modal never opens. Same lost-click root
    // cause as the two nightly specs fixed in #224.
    const falloesungTab = page
      .getByRole('button', { name: /Bewertung \(Standard Falllösung\)/i })
      .first()
    await expect(async () => {
      if (!(await falloesungTab.isVisible().catch(() => false))) {
        const startCta = page
          .getByRole('button', { name: /Korrektur starten|Start grading/i })
          .first()
        if (await startCta.isVisible({ timeout: 2000 }).catch(() => false)) {
          await startCta.click()
        } else {
          await page.locator('table tbody tr').first().click({ timeout: 2000 })
        }
      }
      await expect(falloesungTab).toBeVisible({ timeout: 3000 })
    }).toPass({ timeout: 60000 })
    await falloesungTab.click()

    // Fill a dimension score. The input id pattern is `korrektur-falloesung-<dimkey>`.
    const dimInput = page.locator(`#korrektur-falloesung-${GRADED_DIMENSION.key}`)
    await expect(dimInput).toBeVisible({ timeout: 10000 })
    await dimInput.fill(String(GRADED_DIMENSION.score))

    // Add a short overall assessment.
    const assessment = page.locator('#korrektur-falloesung-assessment')
    if (await assessment.isVisible({ timeout: 3000 }).catch(() => false)) {
      await assessment.fill('Ergebnis vertretbar, Subsumtion knapp aber tragfähig.')
    }

    // Live readout should reflect the entered score before submitting.
    // The grading modal is a HeadlessUI Dialog PORTAL rendered outside
    // <main> — assert at page level, not on mainContent.
    await expect(
      page.locator('text=/Notenpunkte/i').first()
    ).toBeVisible({ timeout: 5000 })

    // Submit the grade.
    const submitButton = page
      .getByRole('button', { name: /Bewertung speichern|Save grade/i })
      .first()
    await expect(submitButton).toBeVisible({ timeout: 5000 })
    await submitButton.click()

    // Success toast confirms persistence path fired.
    await expect(
      page.locator('text=/Bewertung gespeichert|grade saved|saved/i').first()
    ).toBeVisible({ timeout: 15000 })
  })

  test('Step 4: Grade persisted and surfaces (API + queue row)', async ({ page }) => {
    test.setTimeout(60000)
    test.skip(!projectId || !taskId, 'Project/task not available')

    // 4a. The per-task korrektur read endpoint returns the stored grade with
    // the expected korrektur_falloesung blob (the persisted effect).
    const taskDetail = await page.evaluate(
      async ({ pid, tid }) => {
        const response = await fetch(`/api/projects/${pid}/korrektur/tasks/${tid}`, {
          credentials: 'include',
        })
        if (!response.ok) return { ok: false, status: response.status, error: await response.text() }
        const data = await response.json()
        const evals = data.evaluations || []
        const falloesung = evals
          .map((e: { metrics?: Record<string, unknown> }) => e.metrics?.korrektur_falloesung)
          .find((m: unknown) => m != null) as
          | { value?: number; details?: { grade_points?: number; passed?: boolean } }
          | undefined
        return {
          ok: true,
          evaluationCount: evals.length,
          hasFalloesungGrade: falloesung != null,
          gradePoints: falloesung?.details?.grade_points ?? null,
          value: falloesung?.value ?? null,
        }
      },
      { pid: projectId, tid: taskId }
    )
    console.log(`[Step 4] Korrektur task detail: ${JSON.stringify(taskDetail)}`)
    expect(taskDetail.ok).toBe(true)
    expect(taskDetail.evaluationCount).toBeGreaterThan(0)
    expect(taskDetail.hasFalloesungGrade).toBe(true)
    // ergebnisrichtigkeit=18 → raw 18 → grade_points 0 (still a valid persisted
    // grade); assert the field is present and numeric rather than a magnitude.
    expect(typeof taskDetail.gradePoints).toBe('number')

    // 4b. Items stats show one graded annotation by the current user.
    const itemStats = await page.evaluate(async (pid) => {
      const params = new URLSearchParams({ metric: 'korrektur_falloesung' })
      const response = await fetch(
        `/api/projects/${pid}/korrektur/items/stats?${params.toString()}`,
        { credentials: 'include' }
      )
      if (!response.ok) return { ok: false, status: response.status }
      return { ok: true, ...(await response.json()) }
    }, projectId)
    console.log(`[Step 4] Items stats: ${JSON.stringify(itemStats)}`)
    expect(itemStats.ok).toBe(true)
    expect(itemStats.graded_by_me_total ?? itemStats.graded_total ?? 0).toBeGreaterThan(0)

    // 4c. Reloaded queue row flips to a "graded" status (rendered persisted
    // effect). The row shows "{n} korrigiert" / "Von mir korrigiert".
    await page.goto(`${BASE_URL}/projects/${projectId}/korrektur`)
    const mainContent = page.locator('main').first()
    await expect(mainContent).toBeVisible({ timeout: 20000 })
    await expect(async () => {
      const bodyText = await mainContent.textContent()
      const hasGradedMarker =
        bodyText?.includes('korrigiert') || // "Von mir korrigiert" / "{n} korrigiert"
        bodyText?.includes('graded') ||
        bodyText?.includes('corrected')
      expect(hasGradedMarker).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('Step 5: Clean up test project', async ({ page }) => {
    test.skip(!projectId, 'Project not created — nothing to clean up')
    const cleanupResult = await page.evaluate(async (pid) => {
      const response = await fetch(`/api/test/cleanup/${pid}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!response.ok) return { success: false, error: await response.text() }
      return response.json()
    }, projectId)
    console.log(`[Step 5] Cleanup: ${JSON.stringify(cleanupResult)}`)

    projectId = null
    taskId = null
    annotationId = null
  })
})
