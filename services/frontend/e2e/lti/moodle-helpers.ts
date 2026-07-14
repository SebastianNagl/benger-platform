/**
 * Helpers for the LTI Moodle-launch E2E specs (issue #61).
 *
 * These specs run exclusively against the LIVE local dev stack brought up
 * with the lti-dev harness (`benger-extended/infra/lti-dev/`): a throwaway
 * Moodle 4.5 at http://moodle:8081 wired to the dev tool registration
 * `lti-dev-moodle` (client `bengerspike001`, course id 2). They are gated
 * behind the LTI_E2E env var, so a normal CI run without the harness skips
 * them entirely.
 *
 * Moodle-side seeding happens through `docker exec` into the Moodle
 * container: moosh for object creation plus direct PHP for the fixes moosh
 * gets wrong (see `benger-extended/infra/lti-dev/README.md`, gotcha #4:
 * `moosh activity-add` pollutes new LTI instances with legacy consumer-key
 * defaults and ignores `typeid`; `moosh course-enrol` explodes in this
 * image's bootstrap, so enrolment goes through `enrol_try_internal_enrol`).
 */
import { execFileSync } from 'node:child_process'

import { expect, Page } from '@playwright/test'

export const APP_BASE =
  process.env.PLAYWRIGHT_BASE_URL || 'http://vertretbar.localhost'
export const MOODLE_BASE = process.env.LTI_E2E_MOODLE_URL || 'http://moodle:8081'
export const MOODLE_HOST = new URL(MOODLE_BASE).host

const MOODLE_CONTAINER =
  process.env.LTI_E2E_MOODLE_CONTAINER || 'benger-moodle-1'
const DB_CONTAINER = process.env.LTI_E2E_DB_CONTAINER || 'benger-db-1'
const MOODLE_COURSE_ID = 2
/** Moodle tool type id of the seeded BenGER external tool (lti-dev harness). */
const MOODLE_TOOL_TYPE_ID = 1

export const MOODLE_TEACHER = { username: 'teacher1', password: 'Spike-Teacher-1' }

function dockerExec(args: string[], input?: string): string {
  return execFileSync('docker', ['exec', ...args], {
    ...(input === undefined ? {} : { input }),
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'pipe'], // silence moosh/Moodle debug chatter on stderr
  })
}

/** Run a PHP snippet inside the Moodle container with Moodle bootstrapped. */
function moodlePhp(script: string): string {
  return dockerExec(
    ['-i', MOODLE_CONTAINER, 'php'],
    `<?php\ndefine('CLI_SCRIPT', true);\nrequire '/var/www/html/config.php';\n${script}`
  )
}

/** moosh with `-n` (no interaction). Long-form flags only — moosh's global
 *  short flags shadow command flags (lti-dev README). */
function moosh(args: string[]): string {
  return dockerExec([
    '--workdir',
    '/var/www/html',
    MOODLE_CONTAINER,
    'moosh',
    '-n',
    ...args,
  ])
}

/** Run a SQL statement against the dev benger database. */
export function bengerDbSql(sql: string): string {
  return dockerExec([
    DB_CONTAINER,
    'psql',
    '-U',
    'postgres',
    '-d',
    'benger',
    '-c',
    sql,
  ])
}

/**
 * Create a fresh LTI activity in course 2 bound to the BenGER tool and
 * return its course-module id (cmid).
 *
 * moosh's `activity-add` prints the new lti instance id but leaves the row
 * pointing at the legacy consumer-key flow (`resourcekey=12345`,
 * `password=secret`, `typeid=0`) which would override the tool client_id as
 * the id_token `aud` — clear both and pin the tool type, then rebuild the
 * course cache so the activity actually launches.
 */
export function createLtiActivity(name: string): number {
  const out = moosh([
    'activity-add',
    `--name=${name}`,
    'lti',
    String(MOODLE_COURSE_ID),
  ])
  const instanceId = Number((out.match(/\d+/) || [])[0])
  if (!Number.isInteger(instanceId) || instanceId <= 0) {
    throw new Error(`moosh activity-add did not return an instance id: ${out}`)
  }
  const fixed = moodlePhp(`
    $DB->set_field('lti', 'typeid', ${MOODLE_TOOL_TYPE_ID}, ['id' => ${instanceId}]);
    $DB->set_field('lti', 'resourcekey', '', ['id' => ${instanceId}]);
    $DB->set_field('lti', 'password', '', ['id' => ${instanceId}]);
    rebuild_course_cache(${MOODLE_COURSE_ID}, true);
    $moduleid = $DB->get_field('modules', 'id', ['name' => 'lti']);
    $cmid = $DB->get_field('course_modules', 'id', ['course' => ${MOODLE_COURSE_ID}, 'module' => $moduleid, 'instance' => ${instanceId}]);
    echo "CMID=$cmid";
  `)
  const cmid = Number((fixed.match(/CMID=(\d+)/) || [])[1])
  if (!Number.isInteger(cmid) || cmid <= 0) {
    throw new Error(`could not resolve cmid for lti instance ${instanceId}: ${fixed}`)
  }
  return cmid
}

/**
 * Create a fresh Moodle user and enrol them as a student in course 2.
 * `moosh course-enrol` reliably crashes in this image (welcome-message hook
 * under moosh's bootstrap), so the enrolment goes through Moodle's
 * `enrol_try_internal_enrol` API instead — which also assigns the role.
 */
export function createMoodleStudent(username: string, password: string): void {
  moosh([
    'user-create',
    `--password=${password}`,
    `--email=${username}@e2e.example.invalid`,
    '--firstname=E2E',
    '--lastname=Student',
    username,
  ])
  const out = moodlePhp(`
    require_once($CFG->libdir . '/enrollib.php');
    $userid = $DB->get_field('user', 'id', ['username' => '${username}']);
    $roleid = $DB->get_field('role', 'id', ['shortname' => 'student']);
    $ok = enrol_try_internal_enrol(${MOODLE_COURSE_ID}, $userid, $roleid);
    echo $ok ? "ENROLLED=$userid" : "ENROL_FAILED";
  `)
  if (!/ENROLLED=\d+/.test(out)) {
    throw new Error(`could not enrol ${username} into course ${MOODLE_COURSE_ID}: ${out}`)
  }
}

/** Log into Moodle through its login form. */
export async function moodleLogin(
  page: Page,
  username: string,
  password: string
): Promise<void> {
  await page.goto(`${MOODLE_BASE}/login/index.php`, {
    waitUntil: 'domcontentloaded',
  })
  await page.fill('#username', username)
  await page.fill('#password', password)
  await page.click('#loginbtn')
  await page.waitForURL(
    (url) => url.host === MOODLE_HOST && !url.pathname.startsWith('/login'),
    { timeout: 30_000 }
  )
}

/**
 * Open a Moodle LTI activity and ride the full OIDC launch chain
 * (launch.php → tool /api/lti/login → Moodle auth.php → tool
 * /api/lti/launch → app page). Every hop is an auto-submitted form or a
 * redirect, so we just wait until the browser settles on a non-API page of
 * the tool. Returns once the app page has committed.
 */
export async function launchActivity(page: Page, cmid: number): Promise<void> {
  // The auto-submit chain can interrupt goto's own load-state tracking;
  // the waitForURL below is the real synchronization point.
  await page
    .goto(`${MOODLE_BASE}/mod/lti/launch.php?id=${cmid}`, {
      waitUntil: 'commit',
    })
    .catch(() => {})
  await page.waitForURL(
    (url) => url.host !== MOODLE_HOST && !url.pathname.startsWith('/api/'),
    { timeout: 45_000 }
  )
  await page.waitForLoadState('domcontentloaded')
}

/**
 * Navigation with retries: the traefik + Next-dev combo intermittently
 * answers 404/502/503 while routes compile (same flakiness the suite's
 * TestHelpers.login guards against).
 */
export async function gotoWithRetry(
  page: Page,
  url: string,
  attempts = 5
): Promise<void> {
  let lastStatus: number | undefined
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const response = await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: 20_000,
      })
      lastStatus = response?.status()
      if (!response || response.status() < 400) return
    } catch (error) {
      if (attempt === attempts) throw error
    }
    await page.waitForTimeout(500 * attempt)
  }
  throw new Error(`navigation to ${url} kept failing (last status ${lastStatus})`)
}

/**
 * Warm the Next dev server's on-demand compilation for the routes a spec is
 * about to exercise, so the launch redirect chain doesn't hit a
 * mid-compilation 502. Waits until each route answers < 500.
 */
export async function warmAppRoutes(
  page: Page,
  base: string,
  paths: string[]
): Promise<void> {
  for (const path of paths) {
    await expect
      .poll(
        async () => {
          const response = await page.request
            .get(`${base}${path}`, { timeout: 20_000 })
            .catch(() => null)
          return response ? response.status() : 0
        },
        { timeout: 60_000, message: `warm-up of ${base}${path}` }
      )
      .toBeLessThan(500)
  }
}

/** The authenticated user of this page's session, via the cookie-authed API. */
export async function currentUserId(page: Page): Promise<string> {
  const response = await page.request.get(`${APP_BASE}/api/auth/me`)
  expect(response.ok(), `/api/auth/me answered ${response.status()}`).toBe(true)
  const me = await response.json()
  const id = me?.id ?? me?.user?.id
  expect(typeof id, 'user id from /api/auth/me').toBe('string')
  return id
}
