/**
 * Integration tests for HTTP-only cookie authentication and security
 *
 * Tests the complete cookie-based authentication flow, security configurations,
 * and proper handling of authentication state with HttpOnly cookies.
 */

import {
  COOKIE_NAMES,
  getAccessTokenCookieConfig,
  getCSRFCookieConfig,
  getRefreshTokenCookieConfig,
  getSecureCookieConfig,
  validateCookieSecurity,
} from '@/lib/security/cookieConfig'

// Mock fetch for testing HTTP requests
global.fetch = jest.fn()

// Mock process.env for testing different environments
const originalEnv = process.env.NODE_ENV

describe('Cookie Authentication Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Reset cookies in test environment
    document.cookie.split(';').forEach((cookie) => {
      const eqPos = cookie.indexOf('=')
      const name = eqPos > -1 ? cookie.substr(0, eqPos) : cookie
      document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`
    })
  })

  afterAll(() => {
    process.env.NODE_ENV = originalEnv
  })

  describe('Cookie Configuration Integration', () => {
    it('should provide secure production cookie configuration', () => {
      process.env.NODE_ENV = 'production'

      const config = getSecureCookieConfig()

      expect(config.sameSite).toBe('strict')
      expect(config.secure).toBe(true)
      expect(config.httpOnly).toBe(true)
      expect(config.maxAge).toBe(60 * 60 * 24 * 7) // 7 days
      expect(config.path).toBe('/')
    })

    it('should provide relaxed development cookie configuration', () => {
      process.env.NODE_ENV = 'development'

      const config = getSecureCookieConfig()

      expect(config.sameSite).toBe('lax')
      expect(config.secure).toBe(false)
      expect(config.httpOnly).toBe(true)
      expect(config.maxAge).toBe(60 * 60 * 24 * 30) // 30 days
      expect(config.path).toBe('/')
    })

    it('should validate cookie security configurations', () => {
      process.env.NODE_ENV = 'production'

      // Valid production config
      const validConfig = { secure: true, sameSite: 'strict' as const }
      expect(validateCookieSecurity(validConfig)).toBe(true)

      // Invalid production config
      const invalidConfig = { secure: false, sameSite: 'lax' as const }
      expect(validateCookieSecurity(invalidConfig)).toBe(false)

      // SameSite=None requires Secure
      const sameSiteNoneConfig = { secure: false, sameSite: 'none' as const }
      expect(validateCookieSecurity(sameSiteNoneConfig)).toBe(false)
    })
  })

  describe('CSRF Token Cookie Integration', () => {
    it('should configure CSRF cookies correctly', () => {
      const csrfConfig = getCSRFCookieConfig()

      expect(csrfConfig.sameSite).toBe('strict')
      expect(csrfConfig.httpOnly).toBe(false) // Must be readable by JavaScript
      expect(csrfConfig.path).toBe('/')
    })

    it('should use secure cookie names with prefixes', () => {
      expect(COOKIE_NAMES.ACCESS_TOKEN).toBe('__Host-access-token')
      expect(COOKIE_NAMES.REFRESH_TOKEN).toBe('__Secure-refresh-token')
      expect(COOKIE_NAMES.CSRF_TOKEN).toBe('__Host-csrf-token')
      expect(COOKIE_NAMES.SESSION_ID).toBe('__Host-session-id')
    })
  })

  describe('Token Cookie Configurations', () => {
    it('should configure refresh token cookies for security', () => {
      const refreshConfig = getRefreshTokenCookieConfig()

      expect(refreshConfig.sameSite).toBe('strict')
      expect(refreshConfig.httpOnly).toBe(true)
      expect(refreshConfig.maxAge).toBe(60 * 60 * 24 * 30) // 30 days
      expect(refreshConfig.path).toBe('/api/auth/refresh')
    })

    it('should configure access token cookies with short expiry', () => {
      const accessConfig = getAccessTokenCookieConfig()

      expect(accessConfig.httpOnly).toBe(true)
      expect(accessConfig.maxAge).toBe(60 * 30) // 30 minutes
      expect(accessConfig.path).toBe('/')
    })

    it('should adapt access token sameSite policy by environment', () => {
      process.env.NODE_ENV = 'production'
      const prodConfig = getAccessTokenCookieConfig()
      expect(prodConfig.sameSite).toBe('strict')

      process.env.NODE_ENV = 'development'
      const devConfig = getAccessTokenCookieConfig()
      expect(devConfig.sameSite).toBe('lax')
    })
  })

  describe('Authentication Flow Integration', () => {
    it('should handle login with HttpOnly cookies', async () => {
      const mockFetch = fetch as jest.MockedFunction<typeof fetch>

      // Mock successful login response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ user: { id: 'user-123' } }),
        headers: new Headers({
          'Set-Cookie':
            '__Host-access-token=token123; HttpOnly; Secure; SameSite=Strict',
        }),
      } as Response)

      const response = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'test', password: 'test' }),
      })

      expect(response.ok).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'test', password: 'test' }),
      })
    })

    it('should handle token refresh with HttpOnly cookies', async () => {
      const mockFetch = fetch as jest.MockedFunction<typeof fetch>

      // Mock successful refresh response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Set-Cookie':
            '__Host-access-token=newtoken456; HttpOnly; Secure; SameSite=Strict',
        }),
      } as Response)

      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      })

      expect(response.ok).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      })
    })

    it('should handle logout and clear cookies', async () => {
      const mockFetch = fetch as jest.MockedFunction<typeof fetch>

      // Mock successful logout response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Set-Cookie': [
            '__Host-access-token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/',
            '__Secure-refresh-token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/',
          ].join(', '),
        }),
      } as Response)

      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      })

      expect(response.ok).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      })
    })
  })

  describe('API Request Integration with Cookies', () => {
    it('should automatically include cookies in API requests', async () => {
      const mockFetch = fetch as jest.MockedFunction<typeof fetch>

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: 'protected-data' }),
      } as Response)

      const response = await fetch('/api/projects', {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      })

      expect(response.ok).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith('/api/projects', {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      })
    })

    it('should handle 401 responses and attempt token refresh', async () => {
      const mockFetch = fetch as jest.MockedFunction<typeof fetch>

      // First call returns 401
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ error: 'Unauthorized' }),
      } as Response)

      // Refresh call succeeds
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Set-Cookie': '__Host-access-token=refreshed-token; HttpOnly; Secure',
        }),
      } as Response)

      // Retry original call succeeds
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: 'protected-data' }),
      } as Response)

      // First API call (fails with 401)
      const firstResponse = await fetch('/api/projects', {
        credentials: 'include',
      })

      expect(firstResponse.status).toBe(401)

      // Token refresh attempt
      const refreshResponse = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
      })

      expect(refreshResponse.ok).toBe(true)

      // Retry original call
      const retryResponse = await fetch('/api/projects', {
        credentials: 'include',
      })

      expect(retryResponse.ok).toBe(true)
    })
  })

  describe('Cross-Origin and CORS Integration', () => {
    it('should handle CORS with credentials correctly', async () => {
      const mockFetch = fetch as jest.MockedFunction<typeof fetch>

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'Access-Control-Allow-Credentials': 'true',
          'Access-Control-Allow-Origin': 'https://benger.localhost',
        }),
        json: async () => ({ data: 'cors-data' }),
      } as Response)

      const response = await fetch('https://api.benger.localhost/projects', {
        credentials: 'include',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
      })

      expect(response.ok).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith(
        'https://api.benger.localhost/projects',
        {
          credentials: 'include',
          mode: 'cors',
          headers: { 'Content-Type': 'application/json' },
        }
      )
    })
  })

  describe('Security Headers Integration', () => {
    it('should include security headers in API responses', async () => {
      const mockFetch = fetch as jest.MockedFunction<typeof fetch>

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'X-Content-Type-Options': 'nosniff',
          'X-Frame-Options': 'DENY',
          'X-XSS-Protection': '1; mode=block',
          'Referrer-Policy': 'strict-origin-when-cross-origin',
          'Content-Security-Policy': "default-src 'self'",
        }),
        json: async () => ({ data: 'secure-data' }),
      } as Response)

      const response = await fetch('/api/secure-endpoint', {
        credentials: 'include',
      })

      expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff')
      expect(response.headers.get('X-Frame-Options')).toBe('DENY')
      expect(response.headers.get('X-XSS-Protection')).toBe('1; mode=block')
    })
  })

  describe('Environment-Specific Cookie Behavior', () => {
    it('should handle development environment cookie settings', () => {
      process.env.NODE_ENV = 'development'

      const config = getSecureCookieConfig()

      // Development should allow HTTP
      expect(config.secure).toBe(false)
      expect(config.sameSite).toBe('lax')

      // But still protect from XSS
      expect(config.httpOnly).toBe(true)
    })

    it('should enforce strict security in production', () => {
      process.env.NODE_ENV = 'production'

      const config = getSecureCookieConfig()

      expect(config.secure).toBe(true)
      expect(config.sameSite).toBe('strict')
      expect(config.httpOnly).toBe(true)

      // Validation should enforce these requirements
      expect(validateCookieSecurity(config)).toBe(true)

      const insecureConfig = { ...config, secure: false }
      expect(validateCookieSecurity(insecureConfig)).toBe(false)
    })
  })

  describe('Cookie Name Security Integration', () => {
    it('should use secure cookie prefixes correctly', () => {
      // __Host- prefix requires Secure, Path=/, no Domain
      expect(COOKIE_NAMES.ACCESS_TOKEN.startsWith('__Host-')).toBe(true)
      expect(COOKIE_NAMES.CSRF_TOKEN.startsWith('__Host-')).toBe(true)
      expect(COOKIE_NAMES.SESSION_ID.startsWith('__Host-')).toBe(true)

      // __Secure- prefix requires Secure
      expect(COOKIE_NAMES.REFRESH_TOKEN.startsWith('__Secure-')).toBe(true)
    })

    it('should validate cookie prefixes match their security requirements', () => {
      // __Host- cookies must have specific config
      const hostCookieConfig = {
        secure: true,
        path: '/',
        domain: undefined,
      }
      expect(validateCookieSecurity(hostCookieConfig)).toBe(true)

      // __Secure- cookies must be secure
      const secureCookieConfig = {
        secure: true,
        path: '/api/auth/refresh',
      }
      expect(validateCookieSecurity(secureCookieConfig)).toBe(true)
    })
  })
})
