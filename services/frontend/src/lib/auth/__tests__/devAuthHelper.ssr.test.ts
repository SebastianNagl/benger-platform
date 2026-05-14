/**
 * @jest-environment node
 *
 * SSR (no-document) behavior of devAuthHelper. Lives in a separate file
 * because JSDOM 21+ makes `document` non-configurable; running under the
 * node test environment gives us `typeof document === 'undefined'`.
 */

import { devAuthHelper } from '@/lib/auth/devAuthHelper'

jest.mock('@/lib/utils/subdomain', () => ({
  getCookieDomain: jest.fn(() => ''),
}))

describe('DevAuthHelper (SSR)', () => {
  it('markManualLogout does not throw when document is undefined', () => {
    expect(() => devAuthHelper.markManualLogout()).not.toThrow()
  })

  it('clearManualLogout does not throw when document is undefined', () => {
    expect(() => devAuthHelper.clearManualLogout()).not.toThrow()
  })
})
