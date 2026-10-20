/**
 * Shared environment and helpers for the e2e/lti specs.
 *
 * The specs run against either local stack, chosen by PLAYWRIGHT_BASE_URL:
 *
 *   - the dev stack (`make dev` in benger-extended): admin host
 *     http://benger.localhost, database container `benger-db-1`, db `benger`;
 *   - the test stack (`make test-e2e` in benger-platform, the nightly): admin
 *     host http://benger-test.localhost:8090, database container
 *     `benger-test-test-db-1`, db `test_benger`.
 *
 * Every value can be overridden through the environment:
 *
 *   LTI_E2E_ADMIN_URL     host of the admin pages (/admin/lti, organizations)
 *   LTI_E2E_APP_URL       student host the LMS launches into (launch spec)
 *   LTI_E2E_DB_CONTAINER  docker container of the platform database
 *   LTI_E2E_DB_NAME       database name inside it
 *   LTI_E2E_DB_USER       database user (default postgres)
 *
 * The admin specs need nothing beyond the stack and clean up after
 * themselves. The launch spec additionally needs the Moodle harness
 * (benger-extended/infra/lti-dev), see moodle-helpers.ts.
 */
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { APIRequestContext, expect, Page } from '@playwright/test'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

/** True when PLAYWRIGHT_BASE_URL points at the platform test stack. */
const ON_TEST_STACK = (() => {
  try {
    return new URL(BASE_URL).hostname === 'benger-test.localhost'
  } catch {
    return false
  }
})()

/** Student-locked hosts serve the student shell only, never the admin UI. */
function isStudentHost(url: string): boolean {
  try {
    const host = new URL(url).hostname
    return (
      host === 'vertretbar.localhost' || host.endsWith('.vertretbar.localhost')
    )
  } catch {
    return false
  }
}

/** Host of the admin pages: the base URL unless that is a student host. */
export const ADMIN_BASE =
  process.env.LTI_E2E_ADMIN_URL ||
  (BASE_URL && !isStudentHost(BASE_URL) ? BASE_URL : 'http://benger.localhost')

/** Student host the LMS launches into. */
export const APP_BASE =
  process.env.LTI_E2E_APP_URL || BASE_URL || 'http://vertretbar.localhost'

const DB_CONTAINER =
  process.env.LTI_E2E_DB_CONTAINER ||
  (ON_TEST_STACK ? 'benger-test-test-db-1' : 'benger-db-1')
const DB_NAME =
  process.env.LTI_E2E_DB_NAME || (ON_TEST_STACK ? 'test_benger' : 'benger')
const DB_USER = process.env.LTI_E2E_DB_USER || 'postgres'

export function dockerExec(args: string[], input?: string): string {
  return execFileSync('docker', ['exec', ...args], {
    ...(input === undefined ? {} : { input }),
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'pipe'], // keep tool chatter on stderr out of the log
  })
}

/** Run one SQL statement against the platform database of the stack. */
export function bengerDbSql(sql: string): string {
  return dockerExec([
    DB_CONTAINER,
    'psql',
    '-U',
    DB_USER,
    '-d',
    DB_NAME,
    '-v',
    'ON_ERROR_STOP=1',
    '-c',
    sql,
  ])
}

/** Keep the dev auto-login out of a context (suite convention): the specs
 *  log in explicitly or ride an LTI-provisioned session. */
export async function disableAutoLogin(context: {
  addInitScript: (fn: () => void) => Promise<void>
}): Promise<void> {
  await context.addInitScript(() => {
    try {
      sessionStorage.setItem('e2e_test_mode', 'true')
    } catch {
      /* opaque origins (about:blank) */
    }
  })
}

/**
 * Create a throwaway organization through the API as the logged-in
 * superadmin. The specs never borrow seeded organizations, so they run on
 * any database.
 */
export async function createE2eOrganization(
  request: APIRequestContext,
  runId: string,
  purpose: string,
): Promise<string> {
  const response = await request.post(`${ADMIN_BASE}/api/organizations`, {
    data: {
      name: `E2E LTI ${purpose} ${runId}`,
      display_name: `E2E LTI ${purpose} ${runId}`,
      slug: `e2e-lti-${purpose}-${runId}`.toLowerCase(),
      description: 'LTI e2e - safe to delete',
    },
  })
  expect(response.ok(), await response.text()).toBe(true)
  const id = (await response.json()).id
  expect(id, 'created organization id').toBeTruthy()
  return id
}

/**
 * Remove the spec's registrations (ON DELETE CASCADE covers deployments)
 * and its organization. The API deletes organizations softly, so the row is
 * then removed directly; that last step is best effort (a later schema may
 * add references), the API delete already took the org out of every list.
 */
export async function cleanupLtiFixtures(
  request: APIRequestContext | undefined,
  issuer: string,
  organizationId: string | undefined,
): Promise<void> {
  bengerDbSql(
    `DELETE FROM lti_platform_registrations WHERE issuer = '${issuer}'`,
  )
  if (!organizationId) return
  await request
    ?.delete(`${ADMIN_BASE}/api/organizations/${organizationId}`)
    .catch(() => undefined)
  try {
    bengerDbSql(
      `BEGIN; DELETE FROM organization_memberships WHERE organization_id = '${organizationId}'; ` +
        `DELETE FROM organizations WHERE id = '${organizationId}'; COMMIT;`,
    )
  } catch {
    /* best effort, see above */
  }
}

/**
 * Navigation with retries: the traefik + Next-dev combo intermittently
 * answers 404/502/503 while routes compile (same flakiness the suite's
 * TestHelpers.login guards against).
 */
export async function gotoWithRetry(
  page: Page,
  url: string,
  attempts = 5,
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
  throw new Error(
    `navigation to ${url} kept failing (last status ${lastStatus})`,
  )
}

/**
 * Warm the Next dev server's on-demand compilation for the routes a spec is
 * about to exercise, so a redirect chain doesn't hit a mid-compilation 502.
 * Waits until each route answers < 500. A no-op cost on the production
 * build of the test stack.
 */
export async function warmAppRoutes(
  page: Page,
  base: string,
  paths: string[],
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
        { timeout: 60_000, message: `warm-up of ${base}${path}` },
      )
      .toBeLessThan(500)
  }
}

let germanCatalog: Record<string, unknown> | undefined

/**
 * The German UI copy for a dotted i18n key, read from the app's own catalog
 * (src/locales/de/common.json). Specs that check user-facing text compare
 * against the catalog, so a copy edit does not break them while a missing
 * or wrong key still does. The stacks render German by default.
 */
export function germanCopy(key: string): string {
  germanCatalog ??= JSON.parse(
    readFileSync(
      resolve(__dirname, '../../src/locales/de/common.json'),
      'utf8',
    ),
  ) as Record<string, unknown>
  const value = key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object'
          ? (node as Record<string, unknown>)[part]
          : undefined,
      germanCatalog,
    )
  if (typeof value !== 'string') {
    throw new Error(`no German copy for ${key}`)
  }
  return value
}
