/**
 * Tests for subdomain utility functions (Issue #1179).
 *
 * Tests the core hostname-based functions that don't depend on window.location.
 * The server-side cookie scoping lives in upstreamCookies.ts.
 */

import {
  getBaseDomain,
  getBaseDomainFromHost,
  getCookieDomain,
  getPrivateUrl,
  getSisterHostUrl,
  isDemoHost,
  isStudentLockedHost,
  parseSubdomain,
  parseSubdomainFromHost,
} from '../subdomain'

describe('getSisterHostUrl (benger <-> vertretbar cross-link)', () => {
  it.each([
    ['what-a-benger.net', 'https://vertretbar.net'],
    ['benchathon.what-a-benger.net', 'https://vertretbar.net'],
    ['staging.what-a-benger.net', 'https://staging.vertretbar.net'],
    ['vertretbar.net', 'https://what-a-benger.net'],
    ['www.vertretbar.net', 'https://what-a-benger.net'],
    ['staging.vertretbar.net', 'https://staging.what-a-benger.net'],
    ['demo.what-a-benger.net', 'https://demo.vertretbar.net'],
    ['demo-uni.demo.what-a-benger.net', 'https://demo.vertretbar.net'],
    ['demo.vertretbar.net', 'https://demo.what-a-benger.net'],
    ['WHAT-A-BENGER.NET', 'https://vertretbar.net'],
    ['benger.localhost', 'http://vertretbar.localhost'],
    ['benger.localhost:3000', 'http://vertretbar.localhost:3000'],
    ['vertretbar.localhost:3000', 'http://benger.localhost:3000'],
  ])('%s -> %s', (host, expected) => {
    expect(getSisterHostUrl(host)).toBe(expected)
  })

  it.each(['localhost', 'example.org', 'benger.example.org', ''])(
    'returns null outside the known host pairs (%s)',
    (host) => {
      expect(getSisterHostUrl(host)).toBeNull()
    },
  )

  it('falls back to window.location (jsdom localhost has no sister)', () => {
    expect(getSisterHostUrl()).toBeNull()
  })
})

describe('isStudentLockedHost (vertretbar)', () => {
  it.each([
    'vertretbar.net',
    'www.vertretbar.net',
    'staging.vertretbar.net',
    'demo.vertretbar.net',
    'vertretbar.localhost',
    'VERTRETBAR.NET',
    'vertretbar.net:3000',
    'app.vertretbar.localhost',
  ])('locks %s to the student view', (host) => {
    expect(isStudentLockedHost(host)).toBe(true)
  })

  it.each([
    '',
    'what-a-benger.net',
    'staging.what-a-benger.net',
    'demo.what-a-benger.net',
    'benger.localhost',
    'notvertretbar.net',
    'vertretbar.net.evil.com',
  ])('does not lock %s', (host) => {
    expect(isStudentLockedHost(host)).toBe(false)
  })

  it('returns false for null/undefined', () => {
    expect(isStudentLockedHost(null)).toBe(false)
    expect(isStudentLockedHost(undefined)).toBe(false)
  })
})

describe('isDemoHost (demo environment)', () => {
  it.each([
    'demo.what-a-benger.net',
    'demo-uni.demo.what-a-benger.net',
    'demo.vertretbar.net',
    'DEMO.WHAT-A-BENGER.NET',
    'demo.what-a-benger.net:443',
  ])('recognises %s', (host) => {
    expect(isDemoHost(host)).toBe(true)
  })

  it.each([
    '',
    'what-a-benger.net',
    'demo.what-a-benger.net.evil.com',
    'staging.what-a-benger.net',
    'vertretbar.net',
    'benger.localhost',
    'notdemo.what-a-benger.net',
  ])('does not treat %s as demo', (host) => {
    expect(isDemoHost(host)).toBe(false)
  })

  it('falls back to window.location (jsdom localhost is not demo)', () => {
    expect(isDemoHost()).toBe(false)
    expect(isDemoHost(null)).toBe(false)
  })
})

describe('getBaseDomainFromHost', () => {
  it('returns benger.localhost for bare domain', () => {
    expect(getBaseDomainFromHost('benger.localhost')).toBe('benger.localhost')
  })

  it('returns benger.localhost for org subdomain', () => {
    expect(getBaseDomainFromHost('tum.benger.localhost')).toBe(
      'benger.localhost',
    )
  })

  it('returns what-a-benger.net for production domain', () => {
    expect(getBaseDomainFromHost('what-a-benger.net')).toBe('what-a-benger.net')
  })

  it('returns what-a-benger.net for production org subdomain', () => {
    expect(getBaseDomainFromHost('tum.what-a-benger.net')).toBe(
      'what-a-benger.net',
    )
  })

  it('falls back to hostname for unknown domains', () => {
    expect(getBaseDomainFromHost('localhost')).toBe('localhost')
  })

  it('falls back to hostname for localhost with port info stripped', () => {
    expect(getBaseDomainFromHost('some-other-domain.com')).toBe(
      'some-other-domain.com',
    )
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
