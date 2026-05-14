/**
 * @jest-environment node
 *
 * SSR (no-document) behavior of subdomain.ts helpers. Lives in a separate
 * file because JSDOM 21+ makes `document` non-configurable; running under
 * the node test environment gives us `typeof document === 'undefined'`.
 */

import {
  clearLastOrgSlug,
  getLastOrgSlug,
  setLastOrgSlug,
} from '../subdomain'

describe('subdomain helpers (SSR)', () => {
  it('getLastOrgSlug returns null when document is undefined', () => {
    expect(getLastOrgSlug()).toBeNull()
  })

  it('setLastOrgSlug does not throw when document is undefined', () => {
    expect(() => setLastOrgSlug('test')).not.toThrow()
  })

  it('clearLastOrgSlug does not throw when document is undefined', () => {
    expect(() => clearLastOrgSlug()).not.toThrow()
  })
})
