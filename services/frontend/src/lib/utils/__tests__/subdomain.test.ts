/**
 * Tests for subdomain utility functions (Issue #1179).
 *
 * Tests the core hostname-based functions that don't depend on window.location,
 * plus the server-side getCookieDomainFromHost.
 */

import {
  clearLastOrgSlug,
  getBaseDomain,
  getBaseDomainFromHost,
  getCookieDomain,
  getCookieDomainFromHost,
  getLastOrgSlug,
  getOrgUrl,
  getPrivateUrl,
  parseSubdomain,
  parseSubdomainFromHost,
  setLastOrgSlug,
} from '../subdomain'

describe('getBaseDomainFromHost', () => {
  it('returns benger.localhost for bare domain', () => {
    expect(getBaseDomainFromHost('benger.localhost')).toBe('benger.localhost')
  })

  it('returns benger.localhost for org subdomain', () => {
    expect(getBaseDomainFromHost('tum.benger.localhost')).toBe('benger.localhost')
  })

  it('returns what-a-benger.net for production domain', () => {
    expect(getBaseDomainFromHost('what-a-benger.net')).toBe('what-a-benger.net')
  })

  it('returns what-a-benger.net for production org subdomain', () => {
    expect(getBaseDomainFromHost('tum.what-a-benger.net')).toBe('what-a-benger.net')
  })

  it('falls back to hostname for unknown domains', () => {
    expect(getBaseDomainFromHost('localhost')).toBe('localhost')
  })

  it('falls back to hostname for localhost with port info stripped', () => {
    expect(getBaseDomainFromHost('some-other-domain.com')).toBe('some-other-domain.com')
  })
})

describe('parseSubdomainFromHost', () => {
  it('returns private mode for bare benger.localhost', () => {
    expect(parseSubdomainFromHost('benger.localhost')).toEqual({
      orgSlug: null,
      isPrivateMode: true,
    })
  })

  it('returns org slug for tum.benger.localhost', () => {
    expect(parseSubdomainFromHost('tum.benger.localhost')).toEqual({
      orgSlug: 'tum',
      isPrivateMode: false,
    })
  })

  it('returns org slug for lmu.benger.localhost', () => {
    expect(parseSubdomainFromHost('lmu.benger.localhost')).toEqual({
      orgSlug: 'lmu',
      isPrivateMode: false,
    })
  })

  it('handles production domain bare', () => {
    expect(parseSubdomainFromHost('what-a-benger.net')).toEqual({
      orgSlug: null,
      isPrivateMode: true,
    })
  })

  it('handles production org subdomain', () => {
    expect(parseSubdomainFromHost('tum.what-a-benger.net')).toEqual({
      orgSlug: 'tum',
      isPrivateMode: false,
    })
  })

  it('handles slugs with hyphens and numbers', () => {
    expect(parseSubdomainFromHost('my-org-123.benger.localhost')).toEqual({
      orgSlug: 'my-org-123',
      isPrivateMode: false,
    })
  })

  it('rejects nested subdomains (slug with dots)', () => {
    // 'a.b' contains a dot, so it should be treated as private mode
    expect(parseSubdomainFromHost('a.b.benger.localhost')).toEqual({
      orgSlug: null,
      isPrivateMode: true,
    })
  })

  it('returns private mode for unknown domains', () => {
    expect(parseSubdomainFromHost('localhost')).toEqual({
      orgSlug: null,
      isPrivateMode: true,
    })
  })

  it('returns private mode for plain IP addresses', () => {
    expect(parseSubdomainFromHost('127.0.0.1')).toEqual({
      orgSlug: null,
      isPrivateMode: true,
    })
  })
})

describe('getCookieDomainFromHost', () => {
  it('returns .benger.localhost for benger.localhost', () => {
    expect(getCookieDomainFromHost('benger.localhost')).toBe('.benger.localhost')
  })

  it('returns .benger.localhost for org subdomain', () => {
    expect(getCookieDomainFromHost('tum.benger.localhost')).toBe('.benger.localhost')
  })

  it('returns .what-a-benger.net for production domain', () => {
    expect(getCookieDomainFromHost('what-a-benger.net')).toBe('.what-a-benger.net')
  })

  it('returns .what-a-benger.net for production org subdomain', () => {
    expect(getCookieDomainFromHost('tum.what-a-benger.net')).toBe('.what-a-benger.net')
  })

  it('returns empty string for plain localhost', () => {
    expect(getCookieDomainFromHost('localhost')).toBe('')
  })

  it('returns empty string for localhost with port', () => {
    expect(getCookieDomainFromHost('localhost:3000')).toBe('')
  })

  it('returns .benger.localhost for deeply nested subdomain', () => {
    expect(getCookieDomainFromHost('a.b.benger.localhost')).toBe('.benger.localhost')
  })
})

describe('getBaseDomain', () => {
  it('returns a string base domain from window.location.hostname', () => {
    // jsdom default is localhost which falls through to identity return
    const result = getBaseDomain()
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })
})

describe('parseSubdomain', () => {
  it('returns a result with orgSlug and isPrivateMode from current location', () => {
    const result = parseSubdomain()
    expect(result).toHaveProperty('orgSlug')
    expect(result).toHaveProperty('isPrivateMode')
    expect(typeof result.isPrivateMode).toBe('boolean')
  })
})

describe('getOrgUrl', () => {
  it('builds URL with org subdomain and custom path', () => {
    // getOrgUrl reads window.location internally
    const url = getOrgUrl('myorg', '/projects')
    expect(url).toContain('myorg.')
    expect(url).toContain('/projects')
  })

  it('uses current path when no path specified', () => {
    const url = getOrgUrl('tum')
    expect(url).toContain('tum.')
    expect(url).toContain('/')
  })
})

describe('getPrivateUrl', () => {
  it('builds URL without org subdomain', () => {
    const url = getPrivateUrl('/dashboard')
    expect(url).toContain('/dashboard')
    expect(typeof url).toBe('string')
  })

  it('uses current path when no path specified', () => {
    const url = getPrivateUrl()
    expect(typeof url).toBe('string')
    expect(url.length).toBeGreaterThan(0)
  })
})

describe('getCookieDomain', () => {
  it('returns a dot-prefixed domain string', () => {
    const domain = getCookieDomain()
    expect(typeof domain).toBe('string')
    expect(domain.startsWith('.')).toBe(true)
  })
})

describe('cookie helpers', () => {
  beforeEach(() => {
    // Clear all cookies
    document.cookie.split(';').forEach((c) => {
      document.cookie = c
        .replace(/^ +/, '')
        .replace(/=.*/, '=;expires=Thu, 01 Jan 1970 00:00:00 GMT')
    })
  })

  it('getLastOrgSlug returns null when no cookie set', () => {
    expect(getLastOrgSlug()).toBeNull()
  })

  it('setLastOrgSlug sets and getLastOrgSlug reads cookie', () => {
    setLastOrgSlug('myorg')
    expect(getLastOrgSlug()).toBe('myorg')
  })

  it('clearLastOrgSlug removes cookie', () => {
    setLastOrgSlug('myorg')
    expect(getLastOrgSlug()).toBe('myorg')
    clearLastOrgSlug()
    expect(getLastOrgSlug()).toBeNull()
  })

  it('handles encoded slug values', () => {
    setLastOrgSlug('my org')
    expect(getLastOrgSlug()).toBe('my org')
  })

  it('getLastOrgSlug returns null in SSR context', () => {
    const origDocument = global.document
    // @ts-ignore
    delete global.document
    expect(getLastOrgSlug()).toBeNull()
    global.document = origDocument
  })

  it('setLastOrgSlug does nothing in SSR context', () => {
    const origDocument = global.document
    // @ts-ignore
    delete global.document
    // Should not throw
    setLastOrgSlug('test')
    global.document = origDocument
  })

  it('clearLastOrgSlug does nothing in SSR context', () => {
    const origDocument = global.document
    // @ts-ignore
    delete global.document
    clearLastOrgSlug()
    global.document = origDocument
  })
})
