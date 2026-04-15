/**
 * Cookie Security Configuration Test Suite
 * Tests security settings and validation
 */

import {
  COOKIE_NAMES,
  getAccessTokenCookieConfig,
  getCSPHeader,
  getCSRFCookieConfig,
  getRefreshTokenCookieConfig,
  getSecureCookieConfig,
  getSecurityHeaders,
  validateCookieSecurity,
} from '@/lib/security/cookieConfig'

describe('Cookie Security Configuration', () => {
  const originalEnv = process.env

  beforeEach(() => {
    jest.resetModules()
    process.env = { ...originalEnv }
  })

  afterAll(() => {
    process.env = originalEnv
  })

  describe('getSecureCookieConfig', () => {
    it('should return strict production configuration', () => {
      process.env.NODE_ENV = 'production'

      const config = getSecureCookieConfig()

      expect(config).toEqual({
        sameSite: 'strict',
        secure: true,
        httpOnly: true,
        maxAge: 60 * 60 * 24 * 7, // 7 days
        path: '/',
      })
    })

    it('should return relaxed development configuration', () => {
      process.env.NODE_ENV = 'development'

      const config = getSecureCookieConfig()

      expect(config).toEqual({
        sameSite: 'lax',
        secure: false,
        httpOnly: true,
        maxAge: 60 * 60 * 24 * 30, // 30 days
        path: '/',
      })
    })

    it('should return strict default configuration', () => {
      process.env.NODE_ENV = 'unknown'

      const config = getSecureCookieConfig()

      expect(config).toEqual({
        sameSite: 'strict',
        secure: true,
        httpOnly: true,
        maxAge: 60 * 60 * 24, // 1 day
        path: '/',
      })
    })
  })

  describe('getCSRFCookieConfig', () => {
    it('should have httpOnly false for CSRF token', () => {
      const config = getCSRFCookieConfig()

      expect(config.httpOnly).toBe(false)
      expect(config.sameSite).toBe('strict')
    })
  })

  describe('getRefreshTokenCookieConfig', () => {
    it('should have restricted path for refresh token', () => {
      const config = getRefreshTokenCookieConfig()

      expect(config.path).toBe('/api/auth/refresh')
      expect(config.maxAge).toBe(60 * 60 * 24 * 30) // 30 days
      expect(config.httpOnly).toBe(true)
      expect(config.sameSite).toBe('strict')
    })
  })

  describe('getAccessTokenCookieConfig', () => {
    it('should have shorter maxAge for access token', () => {
      const config = getAccessTokenCookieConfig()

      expect(config.maxAge).toBe(60 * 30) // 30 minutes
      expect(config.path).toBe('/')
      expect(config.httpOnly).toBe(true)
    })

    it('should use strict sameSite in production', () => {
      process.env.NODE_ENV = 'production'

      const config = getAccessTokenCookieConfig()

      expect(config.sameSite).toBe('strict')
    })

    it('should use lax sameSite in development', () => {
      process.env.NODE_ENV = 'development'

      const config = getAccessTokenCookieConfig()

      expect(config.sameSite).toBe('lax')
    })
  })

  describe('COOKIE_NAMES', () => {
    it('should use security prefixes', () => {
      expect(COOKIE_NAMES.ACCESS_TOKEN).toMatch(/^__Host-/)
      expect(COOKIE_NAMES.REFRESH_TOKEN).toMatch(/^__Secure-/)
      expect(COOKIE_NAMES.CSRF_TOKEN).toMatch(/^__Host-/)
      expect(COOKIE_NAMES.SESSION_ID).toMatch(/^__Host-/)
    })
  })

  describe('validateCookieSecurity', () => {
    const originalConsoleError = console.error

    beforeEach(() => {
      console.error = jest.fn()
    })

    afterEach(() => {
      console.error = originalConsoleError
    })

    it('should pass valid production configuration', () => {
      process.env.NODE_ENV = 'production'

      const config = {
        secure: true,
        sameSite: 'strict' as const,
        httpOnly: true,
      }

      expect(validateCookieSecurity(config)).toBe(true)
      expect(console.error).not.toHaveBeenCalled()
    })

    it('should fail insecure production configuration', () => {
      process.env.NODE_ENV = 'production'

      const config = {
        secure: false,
        sameSite: 'strict' as const,
      }

      expect(validateCookieSecurity(config)).toBe(false)
      expect(console.error).toHaveBeenCalledWith(
        'Cookie must have Secure flag in production'
      )
    })

    it('should fail SameSite=None without Secure', () => {
      process.env.NODE_ENV = 'production'

      const config = {
        secure: false,
        sameSite: 'none' as const,
      }

      expect(validateCookieSecurity(config)).toBe(false)
      expect(console.error).toHaveBeenCalledWith(
        'SameSite=None requires Secure flag'
      )
    })

    it('should allow insecure in development', () => {
      process.env.NODE_ENV = 'development'

      const config = {
        secure: false,
        sameSite: 'lax' as const,
      }

      expect(validateCookieSecurity(config)).toBe(true)
    })
  })

  describe('getSecurityHeaders', () => {
    it('should return all security headers', () => {
      const headers = getSecurityHeaders()

      expect(headers).toHaveProperty('X-Content-Type-Options', 'nosniff')
      expect(headers).toHaveProperty('X-Frame-Options', 'DENY')
      expect(headers).toHaveProperty('X-XSS-Protection', '1; mode=block')
      expect(headers).toHaveProperty(
        'Referrer-Policy',
        'strict-origin-when-cross-origin'
      )
      expect(headers).toHaveProperty('Permissions-Policy')
    })
  })

  describe('getCSPHeader', () => {
    it('should return strict CSP in production', () => {
      process.env.NODE_ENV = 'production'

      const csp = getCSPHeader()

      expect(csp).toContain("default-src 'self'")
      expect(csp).toContain("script-src 'self'")
      expect(csp).not.toContain('unsafe-inline')
      expect(csp).not.toContain('unsafe-eval')
      expect(csp).toContain("frame-ancestors 'none'")
    })

    it('should allow unsafe scripts in development', () => {
      process.env.NODE_ENV = 'development'

      const csp = getCSPHeader()

      expect(csp).toContain("script-src 'self' 'unsafe-inline' 'unsafe-eval'")
    })

    it('should include proper directives', () => {
      const csp = getCSPHeader()

      expect(csp).toContain("default-src 'self'")
      expect(csp).toContain("style-src 'self' 'unsafe-inline'")
      expect(csp).toContain("img-src 'self' data: https:")
      expect(csp).toContain("font-src 'self' data:")
      expect(csp).toContain(
        "connect-src 'self' https://api.benger.de wss://api.benger.de"
      )
      expect(csp).toContain("frame-ancestors 'none'")
      expect(csp).toContain("base-uri 'self'")
      expect(csp).toContain("form-action 'self'")
    })
  })
})
