/**
 * E2E: Moodle LTI 1.3 launch flows against the LIVE local dev stack
 * (issue #61). Requires the lti-dev harness (local Moodle 4.5 on
 * http://moodle:8081 with the seeded `lti-dev-moodle` registration), so the
 * whole file is gated behind LTI_E2E=1 and skips silently everywhere else.
 *
 * Run:
 *   LTI_E2E=1 PLAYWRIGHT_BASE_URL=http://vertretbar.localhost \
 *     npx playwright test e2e/lti --reporter=line
 *
 * The five steps ride one fresh Moodle activity + one fresh Moodle student
 * per run (unique run-id suffix), so re-runs never collide with earlier
 * state:
 *   a. instructor launch → consent (when this teacher has no current
 *      consent on the connection) → LtiLinkPicker → link a fresh exam → exam
 *   b. student first launch → public consent page (no session yet; both
 *      the processing and the research consent are required) → exam
 *   c. returning student launch → straight into the exam (no consent)
 *   d. two-tabs guard: ?lti_u mismatch hard-blocks the exam page
 *   e. /lti/error?code=not_linked renders the German explanation
 *
 * The UI surfaces under test ship in the extended edition (slot
 * implementations), hence the @extended tag per suite convention.
 */
import { Browser, BrowserContext, expect, Page, test } from '@playwright/test'

import {
  APP_BASE,
  createLtiActivity,
  createMoodleStudent,
  currentUserId,
  gotoWithRetry,
  launchActivity,
  MOODLE_TEACHER,
  moodleLogin,
  warmAppRoutes,
} from './moodle-helpers'

// Steps build on each other (activity → link → consent → relaunch), so run
// them serially and let a failed step skip the dependent rest.
test.describe.configure({ mode: 'serial' })

test.describe('LTI Moodle launch flows @extended', () => {
  test.skip(
    !process.env.LTI_E2E,
    'needs the lti-dev Moodle harness (LTI_E2E=1)',
  )

  // Unique per run: the Moodle activity, the exam, and the student are
  // created fresh every time, so the spec is re-runnable without cleanup.
  const runId = Date.now().toString(36)
  const activityName = `E2E Aktivitaet ${runId}`
  const examTitle = `E2E LTI Klausur ${runId}`
  const studentUsername = `e2estu${runId}`
  const studentPassword = 'E2e-Student-1'

  let cmid: number
  let examId: string
  let teacherContext: BrowserContext | undefined
  let studentContext: BrowserContext | undefined
  let teacherPage: Page
  let studentPage: Page

  /**
   * Consent first (owner decision D7): a launch without current consent on
   * the connection lands on the public consent page. Give both consents and
   * wait until the page moves on. An existing account with the same email
   * leads to the account choice; the suite then continues with a separate
   * account (the dev harness has no mailbox for the proof mail).
   */
  async function passConsentIfAsked(page: Page): Promise<void> {
    if (!new URL(page.url()).pathname.startsWith('/lti/consent')) return
    const continueButton = page.getByTestId('lti-consent-continue')
    await expect(continueButton).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('lti-gdpr-consent').check()
    await page.getByTestId('research-consent-checkbox').check()
    await continueButton.click()
    await page.waitForURL((url) => !url.pathname.startsWith('/lti/consent'), {
      timeout: 30_000,
    })
    if (new URL(page.url()).pathname.startsWith('/lti/link-account')) {
      const separate = page.getByTestId('lti-identity-separate')
      await expect(separate).toBeVisible({ timeout: 20_000 })
      await separate.click()
      await page.waitForURL(
        (url) => !url.pathname.startsWith('/lti/link-account'),
        { timeout: 30_000 },
      )
    }
  }

  /**
   * App-side browser context: pin the suite's `e2e_test_mode` flag before
   * any app script runs — the dev stack's auto-login (layout.tsx) would
   * otherwise log the context in as `admin` and yank it to /dashboard,
   * clobbering the LTI-provisioned session under test.
   */
  async function newAppContext(browser: Browser): Promise<BrowserContext> {
    const context = await browser.newContext({ baseURL: APP_BASE })
    await context.addInitScript(() => {
      try {
        sessionStorage.setItem('e2e_test_mode', 'true')
      } catch {
        /* opaque origins (about:blank) — ignore */
      }
    })
    return context
  }

  test.beforeAll(async ({ browser }) => {
    cmid = createLtiActivity(activityName)

    // Pre-compile the Next dev routes the launch chain will redirect
    // through, so traefik doesn't 502 mid-chain on first compilation.
    const warmContext = await browser.newContext()
    const warmPage = await warmContext.newPage()
    await warmAppRoutes(warmPage, APP_BASE, [
      '/login',
      '/lti/link',
      '/lti/consent',
      '/lti/link-account',
      '/lti/error',
      '/student/exams',
      '/student/exams/warm-up',
    ])
    await warmContext.close()
  })

  test.afterAll(async () => {
    await teacherContext?.close()
    await studentContext?.close()
  })

  test('a. instructor first launch shows the picker and links a fresh exam', async ({
    browser,
  }) => {
    teacherContext = await newAppContext(browser)
    teacherPage = await teacherContext.newPage()

    await moodleLogin(
      teacherPage,
      MOODLE_TEACHER.username,
      MOODLE_TEACHER.password,
    )
    await launchActivity(teacherPage, cmid)
    await passConsentIfAsked(teacherPage)

    // Unlinked activity + Instructor role → the link picker host route.
    await expect(teacherPage).toHaveURL(/\/lti\/link\?rl=[0-9a-f-]+/)

    // German picker UI, titled after the Moodle activity; the submit stays
    // disabled while nothing is selected.
    await expect(
      teacherPage.getByRole('heading', { name: activityName }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(teacherPage.getByText('Wähle die Klausur')).toBeVisible()
    await expect(teacherPage.getByTestId('lti-link-submit')).toBeDisabled()

    // The instructor needs an exam they own: create it through the
    // cookie-authenticated API of the LTI-provisioned browser session.
    const created = await teacherPage.request.post(
      `${APP_BASE}/api/student/exams`,
      {
        data: {
          title: examTitle,
          angabe: 'E2E-Sachverhalt: A verkauft B ein Fahrrad.',
          musterloesung: 'E2E-Musterlösung: Anspruch aus § 433 II BGB besteht.',
        },
      },
    )
    expect(created.status(), await created.text()).toBe(201)
    examId = (await created.json()).project_id
    expect(examId).toBeTruthy()

    // Fresh candidates after reload; the new exam is selectable (its
    // default grading config is falloesung-family, i.e. syncable).
    await teacherPage.reload({ waitUntil: 'domcontentloaded' })
    const option = teacherPage.getByTestId(`lti-exam-option-${examId}`)
    await expect(option).toBeVisible({ timeout: 20_000 })
    await expect(option).toBeEnabled()
    await option.check()

    const submit = teacherPage.getByTestId('lti-link-submit')
    await expect(submit).toBeEnabled()
    await submit.click()

    // Linking navigates into the exam the activity now points at.
    await teacherPage.waitForURL(new RegExp(`/student/exams/${examId}`), {
      timeout: 30_000,
    })
    await expect(
      teacherPage.getByRole('heading', { name: examTitle }),
    ).toBeVisible({ timeout: 20_000 })
  })

  test('b. student first launch requires both consents before opening the exam', async ({
    browser,
  }) => {
    createMoodleStudent(studentUsername, studentPassword)
    studentContext = await newAppContext(browser)
    studentPage = await studentContext.newPage()

    await moodleLogin(studentPage, studentUsername, studentPassword)
    await launchActivity(studentPage, cmid)

    // Linked activity + first-time student → the launch is parked and the
    // public consent page opens with the parked launch's handle.
    await expect(studentPage).toHaveURL(
      /\/lti\/consent\?rl=[0-9a-f-]+&p=[\w-]+/,
    )
    // Nothing is provisioned before consent: no session exists yet.
    const before = await studentPage.request.get(`${APP_BASE}/api/auth/me`)
    expect(before.ok(), `/api/auth/me answered ${before.status()}`).toBe(false)

    // Standalone page titled after the LMS activity.
    await expect(
      studentPage.getByRole('heading', { name: activityName }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(studentPage.getByTestId('lti-consent-identity')).toBeVisible()

    const processing = studentPage.getByTestId('lti-gdpr-consent')
    const research = studentPage.getByTestId('research-consent-checkbox')
    const continueButton = studentPage.getByTestId('lti-consent-continue')

    await expect(processing).toBeVisible()
    await expect(processing).not.toBeChecked()
    await expect(research).toBeVisible()
    await expect(research).not.toBeChecked()
    await expect(continueButton).toBeDisabled()

    // Both consents are required: neither box alone unlocks the button.
    await research.check()
    await expect(continueButton).toBeDisabled()
    await research.uncheck()
    await processing.check()
    await expect(continueButton).toBeDisabled()

    await research.check()
    await expect(continueButton).toBeEnabled()
    await continueButton.click()

    await studentPage.waitForURL(
      new RegExp(`/student/exams/${examId}\\?.*lti_u=`),
      { timeout: 30_000 },
    )
    // The landing carries the two-tabs guard binding of the new account.
    const landing = new URL(studentPage.url())
    expect(landing.searchParams.get('lti_u')).toBe(
      await currentUserId(studentPage),
    )
    await expect(
      studentPage.getByRole('heading', { name: examTitle }),
    ).toBeVisible({ timeout: 20_000 })
  })

  test('c. returning student launch goes straight into the exam', async () => {
    await launchActivity(studentPage, cmid)

    // No consent gate on the way in — direct exam landing, carrying the
    // two-tabs guard's expected-user parameter.
    await studentPage.waitForURL(
      new RegExp(`/student/exams/${examId}\\?.*lti_u=`),
      { timeout: 30_000 },
    )
    const landing = new URL(studentPage.url())
    expect(landing.pathname).toBe(`/student/exams/${examId}`)
    expect(landing.searchParams.get('lti_u')).toBe(
      await currentUserId(studentPage),
    )

    await expect(
      studentPage.getByRole('heading', { name: examTitle }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(studentPage.getByTestId('lti-session-mismatch')).toHaveCount(0)
  })

  test('d. two-tabs guard blocks the exam when lti_u mismatches the session', async () => {
    const userId = await currentUserId(studentPage)

    // Wrong expected user (someone else's launch URL) → hard-block overlay.
    await gotoWithRetry(
      studentPage,
      `${APP_BASE}/student/exams/${examId}?lti_u=e2e-someone-else`,
    )
    const overlay = studentPage.getByTestId('lti-session-mismatch')
    await expect(overlay).toBeVisible({ timeout: 20_000 })
    await expect(overlay).toHaveAttribute('role', 'alertdialog')
    await expect(overlay).toContainText('Andere Moodle-Sitzung aktiv')

    // Matching expected user → no overlay, exam usable.
    await gotoWithRetry(
      studentPage,
      `${APP_BASE}/student/exams/${examId}?lti_u=${userId}`,
    )
    await expect(
      studentPage.getByRole('heading', { name: examTitle }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(studentPage.getByTestId('lti-session-mismatch')).toHaveCount(0)
  })

  test('e. launch error page explains the not_linked case in German', async () => {
    // Failed launches 303 here with ?code=<reason>. The page is public and
    // standalone, so it renders with or without a session.
    await gotoWithRetry(studentPage, `${APP_BASE}/lti/error?code=not_linked`)

    await expect(
      studentPage.getByRole('heading', {
        name: 'Start aus der Lernplattform fehlgeschlagen',
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      studentPage.getByText(
        'Diese Aktivität ist noch keiner Klausur zugeordnet.',
      ),
    ).toBeVisible()
    await expect(studentPage.getByText('Fehlercode')).toBeVisible()
    await expect(
      studentPage.getByText('not_linked', { exact: true }),
    ).toBeVisible()
  })
})
