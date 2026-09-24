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

  it('asks SEB 3.0 to fill the keys on load', () => {
    const updateKeys = jest.fn()
    ;(window as any).SafeExamBrowser = { security: { updateKeys } }
    loadSeb()
    expect(updateKeys).toHaveBeenCalledTimes(1)
  })
})
