/**
 * @jest-environment jsdom
 *
 * BaseApiClient and Safe Exam Browser (see lib/seb.ts):
 * - it forwards the JS-API proof on every request, so SEB exams verify on
 *   macOS / iOS too, and reads the keys only once SEB has computed them;
 * - it reports a refusal at the SEB gate to the page.
 *
 * Runs against the real lib/seb with a fake `window.SafeExamBrowser`.
 */
jest.unmock('@/lib/api/base')

jest.mock('@/lib/utils/logger', () => ({
  __esModule: true,
  default: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}))

type BaseModule = typeof import('../base')
type SebModule = typeof import('@/lib/seb')

const EXAM_PATH = '/student/exams/p1'

/** Load base + seb fresh, so seb's module state sees the current window. */
function load() {
  let base: BaseModule | undefined
  let seb: SebModule | undefined
  jest.isolateModules(() => {
    seb = require('@/lib/seb')
    base = require('../base')
  })
  class TestApiClient extends base!.BaseApiClient {
    call(endpoint: string, options: RequestInit = {}) {
      return (this as any).request(endpoint, options)
    }
    authCheck(endpoint: string) {
      return (this as any).authCheckRequest(endpoint)
    }
  }
  return { client: new TestApiClient(), seb: seb! }
}

function response(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Forbidden',
    headers: new Headers({ 'content-type': 'application/json' }),
    text: async () => JSON.stringify(body),
    json: async () => body,
    body: null,
  }
}

function sentHeaders(call = 0): Record<string, string> {
  return (global.fetch as jest.Mock).mock.calls[call][1].headers
}

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue(response(200, {}))
  window.history.replaceState(null, '', EXAM_PATH)
})

afterEach(() => {
  delete (window as any).SafeExamBrowser
  window.history.replaceState(null, '', '/')
})

describe('SEB proof headers', () => {
  beforeEach(() => {
    ;(window as any).SafeExamBrowser = {
      version: '3.7.1',
      security: { configKey: 'ck-hash', browserExamKey: 'bek-hash' },
    }
  })

  it('adds them to request()', async () => {
    await load().client.call('/projects/p1/tasks/t1/draft', {
      method: 'PUT',
      body: '{}',
    })
    const headers = sentHeaders()
    expect(headers['X-Benger-SEB-CK']).toBe('ck-hash')
    expect(headers['X-Benger-SEB-BEK']).toBe('bek-hash')
    expect(headers['X-Benger-SEB-URL']).toBe(`http://localhost${EXAM_PATH}`)
    expect(headers['X-Benger-SEB-Load-URL']).toBe(
      `http://localhost${EXAM_PATH}`,
    )
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('adds them to requestRaw()', async () => {
    await load().client.requestRaw('/seb/projects/p1/status')
    expect(sentHeaders()['X-Benger-SEB-CK']).toBe('ck-hash')
  })

  it('adds them to the auth check request', async () => {
    await load().client.authCheck('/auth/me')
    expect(sentHeaders()['X-Benger-SEB-CK']).toBe('ck-hash')
  })

  it('sends nothing outside SEB', async () => {
    delete (window as any).SafeExamBrowser
    await load().client.call('/projects/p1/tasks/t1/draft', { method: 'GET' })
    const headers = sentHeaders()
    expect(
      Object.keys(headers).filter((h) => h.startsWith('X-Benger-SEB')),
    ).toEqual([])
  })
})

describe('waiting for the SEB keys', () => {
  it('reads the keys only after SEB 3.0 has filled them', async () => {
    const callbacks: Array<() => void> = []
    const security: any = {
      updateKeys: (done: () => void) => callbacks.push(done),
    }
    ;(window as any).SafeExamBrowser = { version: '3.0', security }
    const { client } = load()

    const pending = client.call('/projects/p1/next', { method: 'GET' })
    // Give the request every chance to go out early.
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(global.fetch).not.toHaveBeenCalled()

    security.configKey = 'filled-later'
    callbacks.forEach((done) => done())
    await pending
    expect(sentHeaders()['X-Benger-SEB-CK']).toBe('filled-later')
  })

  it('asks SEB again after client-side navigation', async () => {
    const hashes: Record<string, string> = {
      [`http://localhost${EXAM_PATH}`]: 'hash-of-exam-page',
      'http://localhost/projects/p1/label': 'hash-of-label-page',
    }
    const security: any = {
      updateKeys: (done: () => void) => {
        security.configKey = hashes[window.location.href]
        done()
      },
    }
    ;(window as any).SafeExamBrowser = { version: '3.0', security }
    const { client } = load()

    await client.call('/projects/p1/next', { method: 'GET' })
    expect(sentHeaders(0)['X-Benger-SEB-CK']).toBe('hash-of-exam-page')

    window.history.pushState(null, '', '/projects/p1/label')
    await client.requestRaw('/projects/p1/tasks/t1')
    expect(sentHeaders(1)['X-Benger-SEB-CK']).toBe('hash-of-label-page')
    expect(sentHeaders(1)['X-Benger-SEB-URL']).toBe(
      'http://localhost/projects/p1/label',
    )
  })
})

describe('refusal at the SEB gate', () => {
  function listen(seb: SebModule) {
    const codes: string[] = []
    const handler = (event: Event) =>
      codes.push((event as CustomEvent).detail.code)
    window.addEventListener(seb.SEB_REFUSED_EVENT, handler)
    return {
      codes,
      stop: () => window.removeEventListener(seb.SEB_REFUSED_EVENT, handler),
    }
  }

  it.each(['seb_required', 'seb_version_not_allowed'])(
    'tells the page about a 403 %s from request()',
    async (code) => {
      ;(global.fetch as jest.Mock).mockResolvedValue(
        response(403, { detail: { code, message: 'Open in SEB.' } }),
      )
      const { client, seb } = load()
      const heard = listen(seb)
      await expect(
        client.call('/projects/p1/tasks/t1/draft', {
          method: 'PUT',
          body: '{}',
        }),
      ).rejects.toThrow('Open in SEB.')
      heard.stop()
      expect(heard.codes).toEqual([code])
    },
  )

  it('tells the page about a refusal from requestRaw()', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue(
      response(403, { detail: { code: 'seb_required', message: 'x' } }),
    )
    const { client, seb } = load()
    const heard = listen(seb)
    await expect(client.requestRaw('/projects/p1/tasks/t1')).rejects.toThrow()
    heard.stop()
    expect(heard.codes).toEqual(['seb_required'])
  })

  it.each([
    [403, { detail: 'Access denied' }],
    [403, { detail: { code: 'project_window_closed', message: 'x' } }],
    [409, { detail: { code: 'seb_required', message: 'x' } }],
    [404, { detail: 'Not found' }],
  ])('stays quiet on %s %j', async (status, body) => {
    ;(global.fetch as jest.Mock).mockResolvedValue(response(status, body))
    const { client, seb } = load()
    const heard = listen(seb)
    await expect(
      client.call('/projects/p1/next', { method: 'GET' }),
    ).rejects.toThrow()
    heard.stop()
    expect(heard.codes).toEqual([])
  })
})
