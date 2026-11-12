/**
 * @jest-environment node
 */

/**
 * next.config.js security headers.
 *
 * Every page sends X-Frame-Options: DENY except the three LTI pages an LMS
 * frames: the Dynamic Registration page (Moodle's "Add LTI Advantage" loads
 * /api/lti/register/init inside an iframe), the launch that answers an
 * embedded launch with an "open in a new window" page (and passes a
 * deep-linking request on to the picker), and the deep-linking content
 * picker. The API answer limits framing with a CSP frame-ancestors
 * instead.
 *
 * The routes run through Next's own loader (which validates the source
 * syntax) and its own runtime matcher, so the negative lookahead is tested
 * the way the production server applies it.
 */

import loadCustomRoutes from 'next/dist/lib/load-custom-routes'
import { buildCustomRoute } from 'next/dist/server/lib/router-utils/filesystem'

type HeaderRoute = {
  source: string
  headers: { key: string; value: string }[]
}
type BuiltRoute = HeaderRoute & {
  match: (pathname: string) => false | Record<string, unknown>
}
type NextConfigModule = {
  headers: () => Promise<HeaderRoute[]>
}

const REGISTER_PATH = '/api/lti/register/init'
const FRAMEABLE = [REGISTER_PATH, '/api/lti/launch', '/api/lti/deep-link']

function loadConfig(nodeEnv: string): NextConfigModule {
  const previous = process.env.NODE_ENV
  const env = process.env as Record<string, string | undefined>
  env.NODE_ENV = nodeEnv
  const log = jest.spyOn(console, 'log').mockImplementation(() => undefined)
  try {
    let config: NextConfigModule | undefined
    jest.isolateModules(() => {
      config = require('../../next.config.js')
    })
    return config as NextConfigModule
  } finally {
    env.NODE_ENV = previous
    log.mockRestore()
  }
}

async function builtRoutes(nodeEnv = 'production'): Promise<BuiltRoute[]> {
  const config = loadConfig(nodeEnv)
  const routes = await loadCustomRoutes(config as never)
  return routes.headers.map(
    (route: HeaderRoute) =>
      buildCustomRoute('header', route as never, '', false) as BuiltRoute,
  )
}

async function headersFor(pathname: string): Promise<Record<string, string>> {
  const result: Record<string, string> = {}
  for (const route of await builtRoutes()) {
    if (!route.match(pathname)) continue
    for (const { key, value } of route.headers) result[key] = value
  }
  return result
}

describe('next.config.js headers', () => {
  it.each([
    '/',
    '/projects',
    '/lti/error',
    '/api/lti/login',
    '/api/lti/launchx',
    '/api/lti/launch/x',
    '/api/lti/deep-link/x',
    '/api/lti/deep-linking',
    '/api/lti/register',
    '/api/lti/register/initx',
    '/x/api/lti/register/init',
    '/x/api/lti/launch',
    '/api/projects/abc',
    '/_next/static/chunk.js',
  ])('denies framing of %s', async (pathname) => {
    const headers = await headersFor(pathname)
    expect(headers['X-Frame-Options']).toBe('DENY')
    expect(headers['X-Content-Type-Options']).toBe('nosniff')
  })

  it.each(FRAMEABLE)('lets an LMS frame %s', async (pathname) => {
    const headers = await headersFor(pathname)
    expect(headers).not.toHaveProperty('X-Frame-Options')
    // The other protections stay.
    expect(headers['X-Content-Type-Options']).toBe('nosniff')
    expect(headers['X-XSS-Protection']).toBe('1; mode=block')
  })

  it('matches the register path with a query string stripped', async () => {
    // Next matches the pathname only; Moodle appends ?token=…&
    // openid_configuration=…&registration_token=… to the same path.
    const routes = await builtRoutes()
    const denying = routes.filter((r) =>
      r.headers.some((h) => h.key === 'X-Frame-Options'),
    )
    expect(denying).toHaveLength(1)
    for (const pathname of FRAMEABLE) {
      expect(denying[0].match(pathname)).toBe(false)
    }
  })

  it('sends no custom headers outside production', async () => {
    expect(await builtRoutes('test')).toEqual([])
  })
})
