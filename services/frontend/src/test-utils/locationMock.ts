/**
 * Opt-in window.location mock for Jest 30 / JSDOM 26.
 *
 * Import this module at the top of any test file that needs to mock
 * `window.location` (read its fields, assign to `href`, assert on
 * `.assign/.replace/.reload`):
 *
 *     import '@/test-utils/locationMock'
 *
 * That single import:
 *   - Loads `jest-location-mock`, which installs `beforeAll` / `beforeEach`
 *     hooks that swap `window.location` with a freely-mockable instance.
 *   - Patches the mock's `href` setter to relativize against its origin,
 *     so production code that does `window.location.href = '/login'`
 *     works the same as in a real browser.
 *
 * NOT loaded from `jest.setup.js` globally because jest-location-mock
 * replaces `window._globalProxy` with a Proxy, which breaks JSDOM's
 * WebSocket bookkeeping (`openSockets.get(window)` keys mismatch
 * between registration and close-time lookup). Scoping per-file
 * keeps the breakage out of unrelated suites.
 */

import 'jest-location-mock'

// Patch LocationMockRelative.prototype.href setter so it accepts relative
// URLs (the parent URL setter throws "Invalid URL: /login" otherwise).
 
const { LocationMockRelative } = require('jest-location-mock/lib/utils')
let proto = Object.getPrototypeOf(LocationMockRelative.prototype)
let hrefDesc: PropertyDescriptor | null = null
while (proto && !hrefDesc) {
  hrefDesc = Object.getOwnPropertyDescriptor(proto, 'href') ?? null
  if (!hrefDesc) proto = Object.getPrototypeOf(proto)
}
if (hrefDesc && hrefDesc.set) {
  const originalSetter = hrefDesc.set
  const originalGetter = hrefDesc.get!
  Object.defineProperty(LocationMockRelative.prototype, 'href', {
    configurable: true,
    get(this: URL) {
      return originalGetter.call(this)
    },
    set(this: URL, value: string) {
      try {
        originalSetter.call(this, value)
      } catch {
        // Relative URL — resolve against the mock's origin.
        originalSetter.call(this, new URL(value, this.origin).href)
      }
    },
  })
}
