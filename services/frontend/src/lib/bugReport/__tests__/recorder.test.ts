/**
 * @jest-environment jsdom
 *
 * The problem report recorder and context: secrets never travel in paths,
 * only failed same-origin /api/ requests are kept (method, path, status,
 * request id; never bodies or query values), errors are capped and
 * de-duplicated, and uninstalling gives fetch back.
 */
import {
  buildBugReportContext,
  type BugReportContext,
} from '@/lib/bugReport/context'
import {
  getRecordedContext,
  installBugReportRecorder,
  MAX_ERRORS,
  MAX_NAVIGATION,
  MAX_REQUESTS,
  recordError,
  recordNavigation,
  redactPath,
  resetBugReportRecorderForTests,
} from '@/lib/bugReport/recorder'

function response(status: number, headers: Record<string, string> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name: string) => headers[name.toLowerCase()] ?? null },
  } as unknown as Response
}

describe('bug report recorder', () => {
  let original: typeof window.fetch
  beforeEach(() => {
    original = jest.fn(async () => response(200)) as unknown as typeof fetch
    window.fetch = original
    resetBugReportRecorderForTests()
  })
  afterEach(() => resetBugReportRecorderForTests())

  it('keeps paths but drops queries, fragments and secret segments', () => {
    expect(redactPath('https://h.example/projects/1/tasks?x=secret#top')).toBe(
      '/projects/1/tasks',
    )
    expect(redactPath('/reset-password/abc')).toBe('/reset-password/[redacted]')
    expect(redactPath('/verify-email/x/more')).toBe(
      '/verify-email/[redacted]/more',
    )
    expect(redactPath('/shares/' + 'k'.repeat(30))).toBe('/shares/[redacted]')
    const uuid = '0b7e5a51-1d41-4b8e-9d6c-4b0d0a6c1f11'
    expect(redactPath(`/projects/${uuid}`)).toBe(`/projects/${uuid}`)
    expect(redactPath('dashboard')).toBe('/dashboard')
  })

  it('records failed API requests without bodies or query values', async () => {
    const fetchMock = original as unknown as jest.Mock
    installBugReportRecorder()
    fetchMock.mockResolvedValueOnce(response(500, { 'x-request-id': 'req-1' }))
    await window.fetch('/api/projects/1?token=abc', {
      method: 'post',
      body: JSON.stringify({ password: 'secret' }),
    })
    fetchMock.mockResolvedValueOnce(response(200))
    await window.fetch('/api/ok')
    fetchMock.mockResolvedValueOnce(response(404))
    await window.fetch('https://elsewhere.example/api/x')
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(window.fetch('/api/down')).rejects.toThrow('Failed to fetch')

    const { failed_requests } = getRecordedContext()
    expect(failed_requests).toHaveLength(2)
    expect(failed_requests[0]).toMatchObject({
      method: 'POST',
      path: '/api/projects/1',
      status: 500,
      request_id: 'req-1',
    })
    expect(failed_requests[1]).toMatchObject({
      method: 'GET',
      path: '/api/down',
      status: 0,
      error: 'TypeError',
    })
    expect(JSON.stringify(failed_requests)).not.toMatch(/secret|token|abc/)
  })

  it('passes every call through and restores fetch on uninstall', async () => {
    const uninstall = installBugReportRecorder()
    expect(installBugReportRecorder()).toBe(uninstall)
    expect(window.fetch).not.toBe(original)
    const answer = await window.fetch('/api/x')
    expect(answer.status).toBe(200)
    expect(original).toHaveBeenCalledWith('/api/x', undefined)
    uninstall()
    expect(window.fetch).toBe(original)
  })

  it('records window errors and unhandled rejections once installed', () => {
    installBugReportRecorder()
    window.dispatchEvent(
      new ErrorEvent('error', { error: new Error('boom'), message: 'boom' }),
    )
    const rejection = new Event('unhandledrejection') as Event & {
      reason?: unknown
    }
    rejection.reason = 'nope'
    window.dispatchEvent(rejection)
    const { errors } = getRecordedContext()
    expect(errors.map((e) => [e.message, e.source])).toEqual([
      ['boom', 'window.error'],
      ['nope', 'unhandledrejection'],
    ])
    expect(errors[0].stack).toContain('boom')
  })

  it('caps the buffers and skips repeats', () => {
    const crash = new Error('same')
    recordError(crash, 'error-boundary')
    recordError(crash, 'window.error')
    expect(getRecordedContext().errors).toHaveLength(1)
    for (let i = 0; i < MAX_ERRORS + 3; i++)
      recordError(new Error(`e${i}`), 's')
    expect(getRecordedContext().errors).toHaveLength(MAX_ERRORS)
    for (let i = 0; i < MAX_NAVIGATION + 3; i++) recordNavigation(`/p/${i}`)
    recordNavigation(`/p/${MAX_NAVIGATION + 2}`)
    const nav = getRecordedContext().navigation
    expect(nav).toHaveLength(MAX_NAVIGATION)
    expect(nav[nav.length - 1].path).toBe(`/p/${MAX_NAVIGATION + 2}`)
    expect(MAX_REQUESTS).toBe(10)
  })
})

describe('buildBugReportContext', () => {
  afterEach(() => resetBugReportRecorderForTests())

  it('collects ids and environment, never query values or names', () => {
    window.history.pushState({}, '', '/projects/p-1/tasks?status=open&q=Secret')
    recordNavigation('/dashboard')
    const ctx: BugReportContext = buildBugReportContext({
      source: 'menu',
      locale: 'de',
      routeParams: { id: 'p-1', rest: ['a', 'b'] },
      featureFlags: { bug_reports: true, report_paper: false },
      extensions: ['extended'],
      uiMode: 'expert',
      orgRoles: ['ORG_ADMIN', 'ANNOTATOR', 'ORG_ADMIN', undefined],
    })
    expect(ctx).toMatchObject({
      source: 'menu',
      page: '/projects/p-1/tasks',
      query_keys: ['status', 'q'],
      route_params: { id: 'p-1', rest: 'a/b' },
      locale: 'de',
      feature_flags: ['bug_reports'],
      extensions: ['extended'],
      ui_mode: 'expert',
      org_roles: ['ANNOTATOR', 'ORG_ADMIN'],
      navigation: [expect.objectContaining({ path: '/dashboard' })],
    })
    expect(ctx.viewport).toEqual({
      width: window.innerWidth,
      height: window.innerHeight,
    })
    expect(typeof ctx.user_agent).toBe('string')
    expect(JSON.stringify(ctx)).not.toContain('Secret')
    expect(ctx).not.toHaveProperty('errors')
  })
})
