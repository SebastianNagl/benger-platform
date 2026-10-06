/**
 * @jest-environment jsdom
 *
 * Safe Exam Browser helpers: detection, platform support and the JS-API
 * proof headers the API client forwards (macOS / iOS SEB cannot send its own
 * headers).
 */

type SebModule = typeof import('../seb')

function loadSeb(): SebModule {
  let mod: SebModule | undefined
  jest.isolateModules(() => {
    mod = require('../seb')
  })
  return mod!
}

function setUserAgent(ua: string, maxTouchPoints = 0) {
  Object.defineProperty(window.navigator, 'userAgent', {
    value: ua,
    configurable: true,
  })
  Object.defineProperty(window.navigator, 'maxTouchPoints', {
    value: maxTouchPoints,
    configurable: true,
  })
}

afterEach(() => {
  delete (window as any).SafeExamBrowser
  setUserAgent('Mozilla/5.0 (Windows NT 10.0) Chrome/130')
  window.history.replaceState(null, '', '/')
})

describe('isSafeExamBrowser', () => {
  it('is false in a normal browser', () => {
    expect(loadSeb().isSafeExamBrowser()).toBe(false)
  })

  it('detects the JavaScript API', () => {
    ;(window as any).SafeExamBrowser = { version: '3.9.0' }
    const seb = loadSeb()
    expect(seb.isSafeExamBrowser()).toBe(true)
    expect(seb.sebVersion()).toBe('3.9.0')
  })

  it('detects the SEB user agent suffix', () => {
    setUserAgent('Mozilla/5.0 (Windows NT 10.0) Chrome/130 SEB/3.9')
    expect(loadSeb().isSafeExamBrowser()).toBe(true)
  })
})

describe('sebPlatform', () => {
  it.each([
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 0, 'windows'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)', 0, 'macos'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)', 5, 'ios'],
    ['Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X)', 5, 'ios'],
    ['Mozilla/5.0 (X11; Linux x86_64)', 0, 'unsupported'],
    ['Mozilla/5.0 (X11; Ubuntu; Linux x86_64)', 0, 'unsupported'],
    ['Mozilla/5.0 (X11; CrOS x86_64 14541.0.0)', 0, 'unsupported'],
    ['Mozilla/5.0 (Linux; Android 14)', 5, 'unsupported'],
  ])('%s -> %s', (ua, touch, expected) => {
    setUserAgent(ua, touch)
    expect(loadSeb().sebPlatform()).toBe(expected)
  })
})

describe('sebRequestHeaders', () => {
  it('is empty outside SEB and when SEB exposes no keys', () => {
    expect(loadSeb().sebRequestHeaders()).toEqual({})
    ;(window as any).SafeExamBrowser = { version: '3.9', security: {} }
    expect(loadSeb().sebRequestHeaders()).toEqual({})
  })

  it('forwards the keys with the current and the load URL', () => {
    window.history.replaceState(null, '', '/student/exams/p1?lti_u=u1')
    ;(window as any).SafeExamBrowser = {
      security: { configKey: 'ck-hash', browserExamKey: 'bek-hash' },
    }
    const seb = loadSeb()
    window.history.pushState(null, '', '/student/exams/p1/review')
    expect(seb.sebRequestHeaders()).toEqual({
      'X-Benger-SEB-CK': 'ck-hash',
      'X-Benger-SEB-BEK': 'bek-hash',
      'X-Benger-SEB-URL': 'http://localhost/student/exams/p1/review',
      'X-Benger-SEB-Load-URL': 'http://localhost/student/exams/p1?lti_u=u1',
    })
  })

  it('asks SEB 3.0 to fill the keys and waits for the callback', async () => {
    let callback: (() => void) | undefined
    const updateKeys = jest.fn((cb: () => void) => {
      callback = cb
    })
    ;(window as any).SafeExamBrowser = { security: { updateKeys } }
    const seb = loadSeb()
    expect(updateKeys).toHaveBeenCalledTimes(1)
    let ready = false
    void seb.sebKeysReady().then(() => {
      ready = true
    })
    await Promise.resolve()
    expect(ready).toBe(false)
    callback!()
    await seb.sebKeysReady()
    expect(ready).toBe(true)
  })

  it('asks again after client-side navigation, not for the same page', async () => {
    const updateKeys = jest.fn((cb: () => void) => cb())
    ;(window as any).SafeExamBrowser = { security: { updateKeys } }
    window.history.replaceState(null, '', '/login')
    const seb = loadSeb()
    await seb.sebKeysReady()
    expect(updateKeys).toHaveBeenCalledTimes(1)
    window.history.pushState(null, '', '/student/exams/p1')
    await seb.sebKeysReady()
    await seb.sebKeysReady()
    expect(updateKeys).toHaveBeenCalledTimes(2)
  })

  it('does not wait outside SEB or on builds without updateKeys', async () => {
    await expect(loadSeb().sebKeysReady()).resolves.toBeUndefined()
  })

  it('gives up waiting after two seconds', async () => {
    jest.useFakeTimers()
    try {
      ;(window as any).SafeExamBrowser = { security: { updateKeys: jest.fn() } }
      const ready = loadSeb().sebKeysReady()
      jest.advanceTimersByTime(2000)
      await expect(ready).resolves.toBeUndefined()
    } finally {
      jest.useRealTimers()
    }
  })
})

describe('hasSebJsApi', () => {
  it('is true only when SEB exposes its security object', () => {
    expect(loadSeb().hasSebJsApi()).toBe(false)
    // Windows SEB: recognisable by its user agent, proof in its own headers.
    setUserAgent('Mozilla/5.0 (Windows NT 10.0) Chrome/130 SEB/3.9')
    expect(loadSeb().hasSebJsApi()).toBe(false)
    ;(window as any).SafeExamBrowser = { version: '3.9.0' }
    expect(loadSeb().hasSebJsApi()).toBe(false)
    ;(window as any).SafeExamBrowser = { security: {} }
    expect(loadSeb().hasSebJsApi()).toBe(true)
  })
})

describe('reportSebRefusal', () => {
  function heard(run: (seb: SebModule) => void): string[] {
    const seb = loadSeb()
    const codes: string[] = []
    const handler = (event: Event) =>
      codes.push((event as CustomEvent).detail.code)
    window.addEventListener(seb.SEB_REFUSED_EVENT, handler)
    run(seb)
    window.removeEventListener(seb.SEB_REFUSED_EVENT, handler)
    return codes
  }

  it('fires for the two SEB codes on a 403', () => {
    expect(
      heard((seb) => {
        seb.reportSebRefusal(403, { detail: { code: 'seb_required' } })
        seb.reportSebRefusal(403, {
          detail: { code: 'seb_version_not_allowed' },
        })
      }),
    ).toEqual(['seb_required', 'seb_version_not_allowed'])
  })

  it('names the refusing project when the API sends it', () => {
    const seb = loadSeb()
    const details: unknown[] = []
    const handler = (event: Event) =>
      details.push((event as CustomEvent).detail)
    window.addEventListener(seb.SEB_REFUSED_EVENT, handler)
    seb.reportSebRefusal(403, {
      detail: { code: 'seb_required', project_id: 'p7' },
    })
    seb.reportSebRefusal(403, { detail: { code: 'seb_required' } })
    seb.reportSebRefusal(403, {
      detail: { code: 'seb_required', project_id: 42 },
    })
    window.removeEventListener(seb.SEB_REFUSED_EVENT, handler)
    expect(details).toEqual([
      { code: 'seb_required', projectId: 'p7' },
      { code: 'seb_required' },
      { code: 'seb_required' },
    ])
  })

  it('ignores other statuses, codes and shapes', () => {
    expect(
      heard((seb) => {
        seb.reportSebRefusal(401, { detail: { code: 'seb_required' } })
        seb.reportSebRefusal(403, { detail: { code: 'window_closed' } })
        seb.reportSebRefusal(403, { detail: 'Access denied' })
        seb.reportSebRefusal(403, { detail: [{ msg: 'x' }] })
        seb.reportSebRefusal(403, null)
        seb.reportSebRefusal(403, 'seb_required')
      }),
    ).toEqual([])
  })
})

describe('sebNavigationTarget', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('never redirects outside SEB', () => {
    const seb = loadSeb()
    expect(seb.sebNavigationTarget('/projects/p1/label')).toBeNull()
    expect(seb.sebNavigationTarget('/dashboard')).toBeNull()
  })

  it('stays open inside SEB until an exam page was opened', () => {
    ;(window as any).SafeExamBrowser = { version: '3.9.0' }
    expect(loadSeb().sebNavigationTarget('/dashboard')).toBeNull()
  })

  it('sends other pages back to the first exam page opened in SEB', () => {
    ;(window as any).SafeExamBrowser = { version: '3.9.0' }
    const seb = loadSeb()
    expect(seb.sebNavigationTarget('/student/exams/e1/')).toBeNull()
    expect(seb.sebNavigationTarget('/projects/p2/label')).toBeNull()
    expect(seb.sebNavigationTarget('/student/decks')).toBe('/student/exams/e1')
    expect(seb.sebNavigationTarget('/projects/p1')).toBe('/student/exams/e1')
  })

  it('keeps sign-in and LMS launch pages reachable', () => {
    ;(window as any).SafeExamBrowser = { version: '3.9.0' }
    const seb = loadSeb()
    seb.sebNavigationTarget('/projects/p1/label')
    expect(seb.sebNavigationTarget('/login')).toBeNull()
    expect(seb.sebNavigationTarget('/lti/consent')).toBeNull()
    expect(seb.sebNavigationTarget('/auth/verify')).toBeNull()
  })

  it('stays off when session storage is blocked', () => {
    ;(window as any).SafeExamBrowser = { version: '3.9.0' }
    const seb = loadSeb()
    const spy = jest
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('blocked')
      })
    try {
      expect(seb.sebNavigationTarget('/dashboard')).toBeNull()
    } finally {
      spy.mockRestore()
    }
  })
})
