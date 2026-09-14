/**
 * Bewertungsbogen grading, end to end
 *
 * Proves that grading a Klausur against its Bewertungsbogen works by checking
 * the stored grade field by field. A run status alone proves nothing: a run
 * that matched no answer at all used to report `completed` as well.
 *
 * LLM lane:
 *   1. The Klausur is created through the creation WIZARD inside the TUM
 *      organization. The wizard must preselect the organization, and for the
 *      Bewertungsbogen judge it must preselect the submitted answer
 *      (`human:loesung`) graded against the `musterloesung` column.
 *   2. A Korrekturbogen written as Markdown goes through the platform importer
 *      and is activated as the task's Bewertungsbogen. The exam's
 *      Notenschluessel was set in the wizard.
 *   3. A participant submits an answer.
 *   4. A batch evaluation runs through the Celery worker. In E2E_TEST_MODE the
 *      judge returns a deterministic filled sheet, so no API key is needed.
 *   5. The stored grade is checked: one score per step, a total equal to their
 *      sum, total_max equal to the sheet total, integer Notenpunkte derived
 *      through the exam's Notenschluessel, and `passed` consistent with them.
 *   6. The same judge aimed at model generations, which an exam never has,
 *      must fail loudly: status `failed`, a diagnostic naming the config, and
 *      the run page showing both. An empty field list is rejected on save.
 *
 * Human lane: a grader fills the same sheet for the same answer in the
 * Korrektur UI, and the stored grade carries exactly the entered points, their
 * total and the Notenpunkte from the same Notenschluessel.
 *
 * The admin works on tum.benger.localhost, forwarded to the unmodified test
 * stack, because the app only knows an organization context from an org
 * subdomain. See helpers/org-host.ts.
 *
 * Runs only against the ephemeral test stack with the extended edition
 * frontend. From benger-extended:
 *   make test-build-frontend
 *   make test-e2e FILE=e2e/user-journeys/bewertungsbogen-grading.spec.ts
 */
import {
  expect,
  test,
  type BrowserContext,
  type Locator,
  type Page,
} from '@playwright/test'
import { startOrgHost, type OrgHost } from '../helpers/org-host'
import { TestHelpers } from '../helpers/test-helpers'
import { clickSubmitFromAnyStep } from '../helpers/wizard-helpers'

const BASE_URL =
  process.env.PLAYWRIGHT_BASE_URL || 'http://benger-test.localhost:8090'

const PROJECT_NAME = `E2E Bewertungsbogen ${Date.now()}`

const TASK = {
  sachverhalt:
    'K verkauft B am 2. Mai ein gebrauchtes Fahrrad für 500 Euro. B nimmt das Rad mit, zahlt aber trotz Mahnung nicht.',
  musterloesung:
    'K hat gegen B einen Anspruch auf Zahlung von 500 Euro aus § 433 II BGB. Ein wirksamer Kaufvertrag liegt vor, Nichtigkeitsgründe sind nicht ersichtlich, und der Anspruch ist fällig und durchsetzbar.',
}

const ANSWER_GLIEDERUNG =
  'A. Anspruch aus § 433 II BGB\nI. Anspruch entstanden\nII. Anspruch durchsetzbar\nB. Ergebnis'
const ANSWER_LOESUNG =
  'K könnte gegen B einen Anspruch auf Zahlung von 500 Euro aus § 433 II BGB haben. K und B haben sich über Kaufsache und Preis geeinigt, ein wirksamer Kaufvertrag liegt vor. Gründe für eine Nichtigkeit sind nicht ersichtlich. Der Anspruch ist fällig und durchsetzbar. K kann von B Zahlung von 500 Euro verlangen.'

// A Korrekturbogen as a chair would write it out: an outline column and a
// points column. The importer derives the step structure from the labels.
const KORREKTURBOGEN_MD = `| Gliederung | BE |
|---|---|
| A. Anspruch des K gegen B auf Kaufpreiszahlung aus § 433 II BGB | |
| I. Anspruch entstanden | |
| 1. Wirksamer Kaufvertrag | 20 |
| 2. Keine Nichtigkeit | 10 |
| II. Anspruch durchsetzbar | 15 |
| B. Ergebnis | 5 |
| Gesamt | 50 |
`
const SHEET_STEP_MAXIMA = [20, 10, 15, 5]
const SHEET_TOTAL = 50

// What the grader enters in the Korrektur UI, in outline order. 20 of 50 BE
// is 40 %, below the pass mark of the standard key, so this lane also covers
// a failing grade. The mock judge's sheet always lands at 60 % or more.
const HUMAN_POINTS = [10, 5, 3.5, 1.5]

interface ApiResult<T> {
  status: number
  body: T
}

interface GradeScale {
  unit?: string
  thresholds: number[]
  rounding?: string
  pass_grade?: number
}

interface RubricNode {
  kind: string
  key?: string
  max_score?: number
}

interface StoredRubric {
  id: string
  status: string
  total_points: number
  structure: { nodes: RubricNode[] }
}

interface EvalConfig {
  id: string
  metric: string
  display_name?: string
  prediction_fields: string[]
  reference_fields: string[]
  [key: string]: unknown
}

interface FilledSheet {
  scores: Record<string, { score: number; max: number }>
  total_score: number
  total_max: number
  grade_points: number
  passed: boolean
  rubric_id: string
  grade_scale_source?: string
}

interface StoredProject {
  kind: string | null
  is_private: boolean
  korrektur_enabled?: boolean
  organizations?: Array<{ id: string }>
  evaluation_config?: {
    evaluation_configs?: EvalConfig[]
    grade_scale?: GradeScale
  }
}

// State shared between the two serial tests.
let orgHost: OrgHost | null = null
let adminContext: BrowserContext | null = null
let adminPage: Page
let tumOrgId = ''
let projectId = ''
let taskId = ''
let annotationId = ''
let rubric: StoredRubric | null = null
let gradeScale: GradeScale | null = null

/** A JSON API call from inside the page, so it carries the session cookie. */
async function api<T>(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  const result = await page.evaluate(
    async ({ method, path, body, orgId }) => {
      const headers: Record<string, string> = {}
      if (orgId) headers['X-Organization-Context'] = orgId
      if (body !== undefined) headers['Content-Type'] = 'application/json'
      const response = await fetch(path, {
        method,
        headers,
        credentials: 'include',
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      const text = await response.text()
      let parsed: unknown = text
      try {
        parsed = text ? JSON.parse(text) : null
      } catch {
        // Not JSON: keep the raw text for the failure message.
      }
      return { status: response.status, body: parsed }
    },
    { method, path, body, orgId: tumOrgId },
  )
  return result as ApiResult<T>
}

async function loadProject(page: Page): Promise<StoredProject> {
  const project = await api<StoredProject>(
    page,
    'GET',
    `/api/projects/${projectId}`,
  )
  expect(project.status, JSON.stringify(project.body)).toBe(200)
  return project.body
}

function configFor(project: StoredProject, metric: string): EvalConfig {
  const config = (project.evaluation_config?.evaluation_configs ?? []).find(
    (c) => c.metric === metric,
  )
  expect(config, `no ${metric} config on the project`).toBeTruthy()
  return config as EvalConfig
}

/** Click Next until `target` shows up. Each click must advance the step. */
async function advanceWizardUntil(page: Page, target: Locator): Promise<void> {
  const next = page.locator('[data-testid="project-create-next-button"]')
  const indicator = page.locator(
    '[data-testid="project-create-step-indicator"]',
  )
  for (let i = 0; i < 8; i++) {
    const shown = await target
      .waitFor({ state: 'visible', timeout: 3000 })
      .then(
        () => true,
        () => false,
      )
    if (shown) return
    const step = (await indicator.getAttribute('data-step')) ?? ''
    await next.click()
    await expect(indicator).not.toHaveAttribute('data-step', step, {
      timeout: 10000,
    })
  }
  await expect(target).toBeVisible()
}

/**
 * Switch a metric on in the wizard's evaluation step and check the fields it
 * starts with: the submitted answer, graded against the model solution.
 */
async function chooseMetricExpectingAnswerFields(
  page: Page,
  metric: string,
): Promise<void> {
  const row = page.locator(`[data-testid="wizard-metric-${metric}"]`)
  await row.scrollIntoViewIfNeeded()
  await row.locator('input[type="checkbox"]').check()
  // The expand chevron is the row's only button; it appears once the metric
  // is on.
  await row.locator('button').click()
  const config = page.locator(
    `[data-testid="wizard-metric-config-${metric}-0"]`,
  )
  await expect(config).toBeVisible()
  const fieldSelects = config.getByRole('button')
  await expect(fieldSelects.nth(0)).toHaveText('loesung (Loesung)')
  await expect(fieldSelects.nth(1)).toHaveText('musterloesung (data)')
}

/**
 * Notenpunkte for `points` on a sheet worth `total`, computed independently
 * of the app: thresholds are minimum points per grade (a percent key is
 * projected onto the total), rounding applies first, the grade is the number
 * of thresholds reached, and `passed` means reaching the pass grade.
 */
function expectedGrade(
  points: number,
  total: number,
  scale: GradeScale,
): { grade: number; passed: boolean } {
  const factor =
    (scale.unit ?? '').toLowerCase() === 'percent' ? total / 100 : 1
  const thresholds = scale.thresholds.map(
    (t) => Math.round(t * factor * 1e6) / 1e6,
  )
  const value = Math.max(0, points)
  const rounding = scale.rounding ?? 'floor'
  const rounded =
    rounding === 'floor'
      ? Math.floor(value)
      : rounding === 'ceil'
        ? Math.ceil(value)
        : rounding === 'nearest'
          ? Math.floor(value + 0.5)
          : value
  const grade = Math.min(18, thresholds.filter((t) => t <= rounded).length)
  return { grade, passed: grade >= (scale.pass_grade ?? 4) }
}

/** The filled sheet matches the Bewertungsbogen and the Notenschluessel. */
function expectFilledSheet(
  sheet: FilledSheet,
  sheetRow: StoredRubric,
  scale: GradeScale,
): void {
  const steps = sheetRow.structure.nodes.filter((n) => n.kind === 'step')
  expect(Object.keys(sheet.scores).sort()).toEqual(
    steps.map((s) => s.key as string).sort(),
  )
  let sum = 0
  for (const step of steps) {
    const entry = sheet.scores[step.key as string]
    expect(entry.max).toBe(step.max_score)
    expect(entry.score).toBeGreaterThanOrEqual(0)
    expect(entry.score).toBeLessThanOrEqual(step.max_score as number)
    expect(Number.isInteger(entry.score * 2)).toBe(true)
    sum += entry.score
  }
  expect(sheet.total_score).toBeCloseTo(sum, 6)
  expect(sheet.total_max).toBe(sheetRow.total_points)
  expect(Number.isInteger(sheet.grade_points)).toBe(true)
  expect(sheet.grade_points).toBeGreaterThanOrEqual(0)
  expect(sheet.grade_points).toBeLessThanOrEqual(18)
  const expected = expectedGrade(
    sheet.total_score,
    sheetRow.total_points,
    scale,
  )
  expect(sheet.grade_points).toBe(expected.grade)
  expect(sheet.passed).toBe(expected.passed)
  expect(sheet.rubric_id).toBe(sheetRow.id)
}

async function dispatchRun(page: Page, config: EvalConfig): Promise<string> {
  const run = await api<{ evaluation_id?: string }>(
    page,
    'POST',
    '/api/evaluations/run',
    {
      project_id: projectId,
      evaluation_configs: [config],
      force_rerun: true,
      batch_size: 100,
    },
  )
  expect(run.status, JSON.stringify(run.body)).toBe(200)
  expect(run.body.evaluation_id).toBeTruthy()
  return run.body.evaluation_id as string
}

async function waitForRunEnd(
  page: Page,
  evaluationId: string,
  timeoutMs = 240000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs
  let last = 'unknown'
  while (Date.now() < deadline) {
    const res = await api<{ status?: string }>(
      page,
      'GET',
      `/api/evaluations/evaluation/status/${evaluationId}`,
    )
    last = res.body?.status ?? last
    if (['completed', 'failed', 'cancelled'].includes(last)) return last
    await page.waitForTimeout(2000)
  }
  throw new Error(
    `evaluation ${evaluationId} was still "${last}" after ${timeoutMs} ms`,
  )
}

test.describe('Bewertungsbogen grading @extended', () => {
  test.describe.configure({ mode: 'serial' })

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120000)
    orgHost = await startOrgHost('tum', BASE_URL)
    adminContext = await browser.newContext({
      baseURL: orgHost.origin,
      viewport: { width: 1920, height: 1080 },
    })
    adminPage = await adminContext.newPage()
    await new TestHelpers(adminPage).login('admin', 'admin')
  })

  test.afterAll(async () => {
    if (projectId && adminPage) {
      const cleanup = await api<unknown>(
        adminPage,
        'DELETE',
        `/api/test/cleanup/${projectId}`,
      ).catch((err: unknown) => ({ status: 0, body: String(err) }))
      console.log(`[cleanup] project ${projectId}: ${cleanup.status}`)
    }
    await adminContext?.close()
    await orgHost?.close()
  })

  test('LLM lane: a wizard-built Klausur is graded against its Bewertungsbogen, and a misaimed judge fails loudly', async ({
    browser,
  }) => {
    test.setTimeout(600000)
    const page = adminPage
    let rubricConfig: EvalConfig | null = null

    await test.step('create the Klausur through the wizard inside TUM', async () => {
      tumOrgId = await page.evaluate(async () => {
        const response = await fetch('/api/organizations', {
          credentials: 'include',
        })
        const orgs = (await response.json()) as Array<{
          id: string
          slug?: string
        }>
        return orgs.find((o) => o.slug === 'tum')?.id ?? ''
      })
      expect(tumOrgId, 'the test seed has no TUM organization').toBeTruthy()

      await page.goto('/projects/create')
      const nameInput = page.locator(
        '[data-testid="project-create-name-input"]',
      )
      await expect(nameInput).toBeVisible({ timeout: 60000 })

      // The admin works inside TUM, so the wizard starts attached to it and
      // says why.
      const orgRadio = page.locator(
        '[data-testid="wizard-visibility-organization-radio"]',
      )
      await expect(orgRadio).toBeChecked({ timeout: 30000 })
      await expect(
        page.locator(
          `[data-testid="wizard-organization-${tumOrgId}-checkbox"]`,
        ),
      ).toBeChecked()
      await expect(
        page.locator('[data-testid="wizard-org-preselected-hint"]'),
      ).toContainText('TUM')

      // Retried: a click that lands before hydration does nothing.
      const examKind = page.locator('[data-testid="project-kind-exam"]')
      await expect(async () => {
        await examKind.click()
        await expect(examKind).toHaveAttribute('aria-checked', 'true', {
          timeout: 2000,
        })
      }).toPass({ timeout: 30000 })
      await nameInput.fill(PROJECT_NAME)
      await expect(nameInput).toHaveValue(PROJECT_NAME)
      // Choosing the project type must not undo the organization.
      await expect(orgRadio).toBeChecked()

      const pasteTab = page.locator('[data-testid="project-create-paste-tab"]')
      await advanceWizardUntil(page, pasteTab)
      await pasteTab.click()
      await page
        .locator('[data-testid="project-create-paste-data-textarea"]')
        .fill(JSON.stringify([TASK]))
      // The detected columns are what the reference field options come from.
      await expect(
        page.getByText('musterloesung', { exact: true }),
      ).toBeVisible()

      await advanceWizardUntil(
        page,
        page.locator('[data-testid="wizard-metric-llm_judge_rubric"]'),
      )
      await chooseMetricExpectingAnswerFields(page, 'llm_judge_rubric')
      await chooseMetricExpectingAnswerFields(page, 'korrektur_custom')
      await page.locator('[data-testid="wizard-grade-scale-enable"]').click()
      await expect(
        page.locator('[data-testid="wizard-grade-scale-clear"]'),
      ).toBeVisible()

      await clickSubmitFromAnyStep(page)
      await page.waitForURL(/\/projects\/[0-9a-f-]{36}$/, { timeout: 180000 })
      projectId = new URL(page.url()).pathname.split('/').pop() ?? ''
      expect(projectId).toBeTruthy()
    })

    await test.step('the saved project belongs to TUM and grades the submitted answer', async () => {
      const project = await loadProject(page)
      expect(project.kind).toBe('exam')
      expect(project.is_private).toBe(false)
      expect((project.organizations ?? []).map((o) => o.id)).toContain(tumOrgId)
      expect(project.korrektur_enabled).toBe(true)

      for (const metric of ['llm_judge_rubric', 'korrektur_custom']) {
        const config = configFor(project, metric)
        // The answer and nothing else. A bulk selector next to it would also
        // grade the outline and the notes as if each were the answer.
        expect(config.prediction_fields, metric).toEqual(['human:loesung'])
        expect(config.reference_fields, metric).toEqual(['musterloesung'])
      }
      rubricConfig = configFor(project, 'llm_judge_rubric')

      gradeScale = project.evaluation_config?.grade_scale ?? null
      expect(gradeScale?.thresholds).toHaveLength(18)
    })

    await test.step('import the Korrekturbogen and activate it as the Bewertungsbogen', async () => {
      const tasks = await api<{
        items?: Array<{ id: string; data: Record<string, unknown> }>
      }>(page, 'GET', `/api/projects/${projectId}/tasks`)
      expect(tasks.status).toBe(200)
      const items = tasks.body.items ?? []
      expect(items).toHaveLength(1)
      taskId = items[0].id
      expect(items[0].data.musterloesung).toBe(TASK.musterloesung)

      const parsed = await page.evaluate(
        async ({ markdown, orgId }) => {
          const form = new FormData()
          form.append(
            'file',
            new Blob([markdown], { type: 'text/markdown' }),
            'korrekturbogen.md',
          )
          const response = await fetch('/api/task-rubrics/parse', {
            method: 'POST',
            body: form,
            credentials: 'include',
            headers: { 'X-Organization-Context': orgId },
          })
          return { status: response.status, body: await response.json() }
        },
        { markdown: KORREKTURBOGEN_MD, orgId: tumOrgId },
      )
      expect(parsed.status, JSON.stringify(parsed.body)).toBe(200)
      const parsedSteps = (parsed.body.structure.nodes as RubricNode[]).filter(
        (n) => n.kind === 'step',
      )
      expect(parsedSteps.map((n) => n.max_score)).toEqual(SHEET_STEP_MAXIMA)
      expect(parsed.body.total_points).toBe(SHEET_TOTAL)

      const created = await api<StoredRubric>(
        page,
        'POST',
        `/api/projects/${projectId}/task-rubrics`,
        {
          task_id: taskId,
          title: parsed.body.title,
          structure: parsed.body.structure,
          grade_scale: parsed.body.grade_scale,
          activate: true,
        },
      )
      expect(created.status, JSON.stringify(created.body)).toBe(201)
      expect(created.body.status).toBe('active')
      expect(created.body.total_points).toBe(SHEET_TOTAL)
      rubric = created.body
    })

    await test.step('a participant submits an answer', async () => {
      const context = await browser.newContext({ baseURL: BASE_URL })
      try {
        const participant = await context.newPage()
        await new TestHelpers(participant).login('annotator', 'admin')
        const submitted = await api<{ id?: string }>(
          participant,
          'POST',
          `/api/projects/tasks/${taskId}/annotations`,
          {
            result: [
              {
                from_name: 'gliederung',
                to_name: 'sachverhalt',
                type: 'gliederung',
                value: { text: [ANSWER_GLIEDERUNG] },
              },
              {
                from_name: 'loesung',
                to_name: 'sachverhalt',
                type: 'loesung',
                value: { text: [ANSWER_LOESUNG] },
              },
            ],
          },
        )
        expect(submitted.status, JSON.stringify(submitted.body)).toBe(200)
        annotationId = submitted.body.id ?? ''
        expect(annotationId).toBeTruthy()
      } finally {
        await context.close()
      }
    })

    await test.step('a batch evaluation grades the answer against the sheet', async () => {
      const config = rubricConfig as EvalConfig
      const evaluationId = await dispatchRun(page, config)
      expect(await waitForRunEnd(page, evaluationId)).toBe('completed')

      const samples = await api<{
        items?: Array<{
          task_id: string
          field_name: string
          prediction: string
          passed: boolean
          metrics: Record<string, any>
        }>
      }>(page, 'GET', `/api/evaluations/${evaluationId}/samples?page_size=100`)
      expect(samples.status).toBe(200)
      const rows = (samples.body.items ?? []).filter(
        (row) => row.metrics?.llm_judge_rubric,
      )
      // One grading of the one answer. Any other row would be a different
      // field of the same submission graded against the Bewertungsbogen.
      expect(rows.map((row) => row.field_name)).toEqual([
        `${config.id}|human:loesung|musterloesung`,
      ])
      const row = rows[0]
      expect(row.task_id).toBe(taskId)
      expect(row.prediction).toBe(ANSWER_LOESUNG)

      const blob = row.metrics.llm_judge_rubric
      expect(blob.error).toBeNull()
      const sheet = blob.details as FilledSheet
      expectFilledSheet(sheet, rubric as StoredRubric, gradeScale as GradeScale)
      // The exam's Notenschluessel, not the default table, produced the grade.
      expect(sheet.grade_scale_source).toBe('project')
      expect(row.metrics.llm_judge_rubric_grade_points).toBe(sheet.grade_points)
      expect(row.passed).toBe(sheet.passed)
      expect(blob.value).toBeCloseTo(sheet.total_score / sheet.total_max, 6)
    })

    await test.step('a judge aimed at model generations fails loudly, and an empty one is rejected', async () => {
      const config = rubricConfig as EvalConfig
      const project = await loadProject(page)
      const configs = project.evaluation_config?.evaluation_configs ?? []
      const withFields = (fields: string[]) =>
        configs.map((c) =>
          c.id === config.id ? { ...c, prediction_fields: fields } : c,
        )
      const configUrl = `/api/evaluations/projects/${projectId}/evaluation-config`

      const empty = await api<unknown>(page, 'PUT', configUrl, {
        evaluation_configs: withFields([]),
      })
      expect(empty.status).toBe(422)
      expect(JSON.stringify(empty.body)).toContain('prediction_fields is empty')

      const aimed = await api<unknown>(page, 'PUT', configUrl, {
        evaluation_configs: withFields(['__all_model__']),
      })
      expect(aimed.status, JSON.stringify(aimed.body)).toBe(200)
      const saved = configFor(await loadProject(page), 'llm_judge_rubric')
      expect(saved.prediction_fields).toEqual(['__all_model__'])

      const evaluationId = await dispatchRun(page, saved)
      expect(await waitForRunEnd(page, evaluationId)).toBe('failed')

      const run = await api<{
        error_message?: string | null
        eval_metadata?: {
          match_by_config?: Record<string, { reason: string | null }>
        }
      }>(page, 'GET', `/api/evaluations/run/results/${evaluationId}`)
      expect(run.status).toBe(200)
      expect(run.body.error_message).toContain(
        'no cells matched the evaluation configuration',
      )
      expect(run.body.error_message).toContain(config.display_name as string)
      expect(run.body.eval_metadata?.match_by_config?.[config.id]?.reason).toBe(
        'no_generations',
      )

      await page.goto(`/evaluations/${evaluationId}`)
      const banner = page.locator('[data-testid="evaluation-run-failed"]')
      await expect(banner).toBeVisible({ timeout: 60000 })
      await expect(banner).toContainText(
        'no cells matched the evaluation configuration',
      )
      const unmatched = banner.locator(
        '[data-testid="evaluation-unmatched-configs"]',
      )
      await expect(unmatched).toContainText(config.display_name as string)
      await expect(unmatched).toContainText('no_generations')

      // Point the judge back at the answer, as the wizard left it.
      const restored = await api<unknown>(page, 'PUT', configUrl, {
        evaluation_configs: configs,
      })
      expect(restored.status, JSON.stringify(restored.body)).toBe(200)
    })
  })

  test('Human lane: a grader fills the same Bewertungsbogen in the Korrektur UI', async () => {
    test.setTimeout(300000)
    test.skip(
      !projectId || !rubric || !annotationId || !gradeScale,
      'the LLM lane did not set up the exam',
    )
    const page = adminPage
    const sheetRow = rubric as StoredRubric
    const steps = sheetRow.structure.nodes.filter((n) => n.kind === 'step')
    expect(steps.map((s) => s.max_score)).toEqual(SHEET_STEP_MAXIMA)
    const entered = new Map(
      steps.map((step, i) => [step.key as string, HUMAN_POINTS[i]]),
    )
    const enteredTotal = HUMAN_POINTS.reduce((a, b) => a + b, 0)
    const expected = expectedGrade(
      enteredTotal,
      SHEET_TOTAL,
      gradeScale as GradeScale,
    )

    await test.step('grade the answer through the Korrektur modal', async () => {
      await page.goto(`/projects/${projectId}/korrektur`)
      const rubricTab = page.getByRole('button', {
        name: 'Bewertung (Bewertungsbogen)',
      })
      // Retried: the queue renders before hydration, and a click on
      // "Korrektur starten" before that opens nothing.
      await expect(async () => {
        if (!(await rubricTab.isVisible())) {
          await page
            .getByRole('button', { name: /Korrektur starten/ })
            .first()
            .click({ timeout: 3000 })
        }
        await expect(rubricTab).toBeVisible({ timeout: 5000 })
      }).toPass({ timeout: 120000 })
      await rubricTab.click()

      const form = page.locator('[data-testid="rubric-grading-form"]')
      await expect(form).toBeVisible()
      for (const [key, points] of entered) {
        await form.locator(`#korrektur-rubric-${key}`).fill(String(points))
      }
      const summary = form.locator('[data-testid="rubric-grading-summary"]')
      await expect(summary).toContainText(`${expected.grade} / 18`)
      await form.locator('[data-testid="rubric-grading-submit"]').click()
    })

    await test.step('the stored human grade carries the entered sheet', async () => {
      let sheet: FilledSheet | null = null
      await expect(async () => {
        const detail = await api<{
          evaluations?: Array<{
            annotation_id?: string | null
            metrics?: Record<string, any>
          }>
        }>(page, 'GET', `/api/projects/${projectId}/korrektur/tasks/${taskId}`)
        expect(detail.status).toBe(200)
        const row = (detail.body.evaluations ?? []).find(
          (e) =>
            e.metrics?.korrektur_custom && e.annotation_id === annotationId,
        )
        expect(row, 'no korrektur_custom grade stored yet').toBeTruthy()
        sheet = row?.metrics?.korrektur_custom?.details as FilledSheet
      }).toPass({ timeout: 30000 })

      const stored = sheet as unknown as FilledSheet
      for (const [key, points] of entered) {
        expect(stored.scores[key].score).toBe(points)
      }
      expectFilledSheet(stored, sheetRow, gradeScale as GradeScale)
      expect(stored.total_score).toBe(enteredTotal)
      expect(stored.grade_points).toBe(expected.grade)
      expect(stored.passed).toBe(false)
    })
  })
})
