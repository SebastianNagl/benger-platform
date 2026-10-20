/**
 * Moodle helpers for the LTI launch spec (issue #61).
 *
 * The spec drives a throwaway Moodle 4.5 from the harness in
 * `benger-extended/infra/lti-dev/` (dev stack: http://moodle:8081, container
 * `benger-moodle-1`; test stack: http://moodle:8083, container
 * `benger-test-moodle-1`), wired to a BenGER registration for the tool
 * `bengerspike001`. LTI_E2E_MOODLE_URL / _CONTAINER / _COURSE_ID /
 * _TOOL_TYPE_ID select the instance (the harness scripts print them).
 *
 * Moodle-side seeding happens through `docker exec` into the Moodle
 * container: moosh for object creation plus direct PHP for the fixes moosh
 * gets wrong (see `benger-extended/infra/lti-dev/README.md`, gotcha #4:
 * `moosh activity-add` pollutes new LTI instances with legacy consumer-key
 * defaults and ignores `typeid`; `moosh course-enrol` explodes in this
 * image's bootstrap, so enrolment goes through `enrol_try_internal_enrol`).
 */
import { expect, Page } from '@playwright/test'

import { APP_BASE, dockerExec } from './lti-helpers'

export {
  APP_BASE,
  disableAutoLogin,
  germanCopy,
  gotoWithRetry,
  warmAppRoutes,
} from './lti-helpers'

/** Moodle wwwroot; the issuer of the BenGER registration. */
export const MOODLE_BASE =
  process.env.LTI_E2E_MOODLE_URL || 'http://moodle:8081'
export const MOODLE_HOST = new URL(MOODLE_BASE).host

const MOODLE_CONTAINER =
  process.env.LTI_E2E_MOODLE_CONTAINER || 'benger-moodle-1'
const MOODLE_COURSE_ID = Number(process.env.LTI_E2E_MOODLE_COURSE_ID || 2)
/** Moodle tool type id of the BenGER external tool (setup_moodle.sh). */
const MOODLE_TOOL_TYPE_ID = Number(process.env.LTI_E2E_MOODLE_TOOL_TYPE_ID || 1)

export const MOODLE_TEACHER = {
  username: 'teacher1',
  password: 'Spike-Teacher-1',
}

/** Run a PHP snippet inside the Moodle container with Moodle bootstrapped. */
function moodlePhp(script: string): string {
  return dockerExec(
    ['-i', MOODLE_CONTAINER, 'php'],
    `<?php\ndefine('CLI_SCRIPT', true);\nrequire '/var/www/html/config.php';\n${script}`,
  )
}

/** moosh with `-n` (no interaction). Long-form flags only: moosh's global
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

/**
 * Create a fresh LTI activity in course 2 bound to the BenGER tool and
 * return its course-module id (cmid).
 *
 * moosh's `activity-add` leaves the new lti row pointing at the legacy
 * consumer-key flow (`resourcekey=12345`, `password=secret`, `typeid=0`),
 * which would override the tool client_id as
 * the id_token `aud`: clear both and pin the tool type, then rebuild the
 * course cache so the activity actually launches.
 */
export function createLtiActivity(name: string): number {
  // The names are unique per run (run-id suffix), so the instance is looked
  // up by name: moosh's stdout can carry PHP warnings with line numbers on
  // a fresh Moodle, which made "the first number" the wrong id.
  moosh(['activity-add', `--name=${name}`, 'lti', String(MOODLE_COURSE_ID)])
  const fixed = moodlePhp(`
    $instanceid = (int) $DB->get_field_sql(
      'SELECT MAX(id) FROM {lti} WHERE course = ? AND name = ?',
      [${MOODLE_COURSE_ID}, ${JSON.stringify(name)}]);
    if (!$instanceid) { echo "NO_INSTANCE"; exit(1); }
    $DB->set_field('lti', 'typeid', ${MOODLE_TOOL_TYPE_ID}, ['id' => $instanceid]);
    $DB->set_field('lti', 'resourcekey', '', ['id' => $instanceid]);
    $DB->set_field('lti', 'password', '', ['id' => $instanceid]);
    rebuild_course_cache(${MOODLE_COURSE_ID}, true);
    $moduleid = $DB->get_field('modules', 'id', ['name' => 'lti']);
    $cmid = $DB->get_field('course_modules', 'id', ['course' => ${MOODLE_COURSE_ID}, 'module' => $moduleid, 'instance' => $instanceid]);
    echo "CMID=$cmid";
  `)
  const cmid = Number((fixed.match(/CMID=(\d+)/) || [])[1])
  if (!Number.isInteger(cmid) || cmid <= 0) {
    throw new Error(
      `could not resolve the cmid of lti activity ${name}: ${fixed}`,
    )
  }
  return cmid
}

/**
 * Create a fresh Moodle user and enrol them as a student in course 2.
 * `moosh course-enrol` reliably crashes in this image (welcome-message hook
 * under moosh's bootstrap), so the enrolment goes through Moodle's
 * `enrol_try_internal_enrol` API instead: which also assigns the role.
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
    throw new Error(
      `could not enrol ${username} into course ${MOODLE_COURSE_ID}: ${out}`,
    )
  }
}

/**
 * Log into Moodle through its login form.
 *
 * A fresh Moodle occasionally answers the first form post with "Your
 * session has timed out" (the session the login page opened is not found
 * yet) and shows the form again; the next attempt then goes through. So the
 * login is retried a few times before it counts as failed.
 */
export async function moodleLogin(
  page: Page,
  username: string,
  password: string,
  attempts = 3,
): Promise<void> {
  const loggedIn = (url: URL) =>
    url.host === MOODLE_HOST && !url.pathname.startsWith('/login')
  for (let attempt = 1; ; attempt++) {
    await page.goto(`${MOODLE_BASE}/login/index.php`, { waitUntil: 'load' })
    if (loggedIn(new URL(page.url()))) return
    await page.fill('#username', username)
    await page.fill('#password', password)
    await page.click('#loginbtn')
    try {
      await page.waitForURL(loggedIn, { timeout: 20_000 })
      return
    } catch (error) {
      if (attempt >= attempts) throw error
    }
  }
}

/**
 * Open a Moodle LTI activity and ride the full OIDC launch chain
 * (launch.php -> tool /api/lti/login -> Moodle auth.php -> tool
 * /api/lti/launch -> app page). Every hop is an auto-submitted form or a
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
    { timeout: 45_000 },
  )
  await page.waitForLoadState('domcontentloaded')
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
