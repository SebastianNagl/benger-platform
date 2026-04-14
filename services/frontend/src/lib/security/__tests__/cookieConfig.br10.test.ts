/**
 * @jest-environment jsdom
 *
 * Branch coverage for cookieConfig.ts - 16 uncovered branches.
 */

import {
  getSecureCookieConfig,
  getCSRFCookieConfig,
  getRefreshTokenCookieConfig,
  getAccessTokenCookieConfig,
  validateCookieSecurity,
  getSecurityHeaders,
  getCSPHeader,
  COOKIE_NAMES,
} from '../cookieConfig'

describe('getSecureCookieConfig', () => {
  it('returns config with correct properties', () => {
    const config = getSecureCookieConfig()
    expect(config.path).toBe('/')
    expect(config.httpOnly).toBe(true)
    expect(config.sameSite).toBeDefined()
    expect(config.maxAge).toBeGreaterThan(0)
  })
})

describe('getCSRFCookieConfig', () => {
  it('returns config with httpOnly false', () => {
    const config = getCSRFCookieConfig()
    expect(config.httpOnly).toBe(false)
    expect(config.sameSite).toBe('strict')
  })
})

describe('getRefreshTokenCookieConfig', () => {
  it('returns config with long maxAge', () => {
    const config = getRefreshTokenCookieConfig()
    expect(config.httpOnly).toBe(true)
    expect(config.maxAge).toBe(60 * 60 * 24 * 30) // 30 days
    expect(config.path).toBe('/api/auth/refresh')
  })
})

describe('getAccessTokenCookieConfig', () => {
  it('returns config with short maxAge', () => {
    const config = getAccessTokenCookieConfig()
    expect(config.httpOnly).toBe(true)
    expect(config.maxAge).toBe(60 * 30) // 30 minutes
    expect(config.path).toBe('/')
  })
})

describe('validateCookieSecurity', () => {
  it('returns true for valid config', () => {
    expect(validateCookieSecurity({ sameSite: 'strict', secure: true })).toBe(true)
  })

  it('returns false for SameSite=None without Secure', () => {
    const spy = jest.spyOn(console, 'error').mockImplementation()
    expect(validateCookieSecurity({ sameSite: 'none', secure: false })).toBe(false)
    spy.mockRestore()
  })

  it('returns true for SameSite=None with Secure', () => {
    expect(validateCookieSecurity({ sameSite: 'none', secure: true })).toBe(true)
  })

  it('returns true for lax sameSite', () => {
    expect(validateCookieSecurity({ sameSite: 'lax' })).toBe(true)
  })
})

describe('getSecurityHeaders', () => {
  it('returns security headers', () => {
    const headers = getSecurityHeaders()
    expect(headers).toHaveProperty('X-Content-Type-Options', 'nosniff')
    expect(headers).toHaveProperty('X-Frame-Options', 'DENY')
    expect(headers).toHaveProperty('X-XSS-Protection')
  })
})

describe('getCSPHeader', () => {
  it('returns a CSP string', () => {
    const csp = getCSPHeader()
    expect(csp).toContain("default-src 'self'")
    expect(csp).toContain("frame-ancestors 'none'")
  })
})

describe('COOKIE_NAMES', () => {
  it('has expected cookie name constants', () => {
    expect(COOKIE_NAMES.ACCESS_TOKEN).toBe('__Host-access-token')
    expect(COOKIE_NAMES.REFRESH_TOKEN).toBe('__Secure-refresh-token')
    expect(COOKIE_NAMES.CSRF_TOKEN).toBe('__Host-csrf-token')
    expect(COOKIE_NAMES.SESSION_ID).toBe('__Host-session-id')
  })
})
