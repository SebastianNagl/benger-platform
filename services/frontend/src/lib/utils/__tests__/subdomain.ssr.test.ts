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
  getSisterHostUrl,
  setLastOrgSlug,
} from '../subdomain'

describe('subdomain helpers (SSR)', () => {
  it('getSisterHostUrl returns null without window and no host', () => {
    expect(getSisterHostUrl()).toBeNull()
  })

  it('getSisterHostUrl infers the protocol from an explicit host', () => {
    expect(getSisterHostUrl('what-a-benger.net')).toBe('https://vertretbar.net')
    expect(getSisterHostUrl('vertretbar.localhost:3000')).toBe(
      'http://benger.localhost:3000'
    )
  })

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
