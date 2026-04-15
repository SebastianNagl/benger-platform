/**
 * Security Configuration for Cookies
 *
 * Implements 2025 best practices for cookie security:
 * - SameSite attribute to prevent CSRF attacks
 * - Secure flag for HTTPS-only transmission
 * - HttpOnly flag to prevent XSS attacks (handled server-side)
 * - Proper expiration and path settings
 */

export interface CookieOptions {
  sameSite?: 'strict' | 'lax' | 'none'
  secure?: boolean
  httpOnly?: boolean
  maxAge?: number
  path?: string
  domain?: string
}

/**
 * Get secure cookie configuration based on environment
 */
export function getSecureCookieConfig(): CookieOptions {
  const isProduction = process.env.NODE_ENV === 'production'
  const isDevelopment = process.env.NODE_ENV === 'development'

  // Production configuration
  if (isProduction) {
    return {
      sameSite: 'strict', // Strictest CSRF protection
      secure: true, // HTTPS only
      httpOnly: true, // Not accessible via JavaScript
      maxAge: 60 * 60 * 24 * 7, // 7 days
      path: '/',
    }
  }

  // Development configuration
  if (isDevelopment) {
    return {
      sameSite: 'lax', // Allow some cross-site requests for dev
      secure: false, // Allow HTTP in development
      httpOnly: true, // Still protect from XSS
      maxAge: 60 * 60 * 24 * 30, // 30 days for dev convenience
      path: '/',
    }
  }

  // Default (safest) configuration
  return {
    sameSite: 'strict',
    secure: true,
    httpOnly: true,
    maxAge: 60 * 60 * 24, // 1 day
    path: '/',
  }
}

/**
 * Get CSRF token cookie configuration
 */
export function getCSRFCookieConfig(): CookieOptions {
  const base = getSecureCookieConfig()

  return {
    ...base,
    sameSite: 'strict', // Always strict for CSRF tokens
    httpOnly: false, // Must be readable by JavaScript for CSRF protection
  }
}

/**
 * Get refresh token cookie configuration
 */
export function getRefreshTokenCookieConfig(): CookieOptions {
  const base = getSecureCookieConfig()

  return {
    ...base,
    sameSite: 'strict',
    httpOnly: true,
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: '/api/auth/refresh', // Only sent to refresh endpoint
  }
}

/**
 * Get access token cookie configuration
 */
export function getAccessTokenCookieConfig(): CookieOptions {
  const base = getSecureCookieConfig()

  return {
    ...base,
    sameSite: process.env.NODE_ENV === 'production' ? 'strict' : 'lax',
    httpOnly: true,
    maxAge: 60 * 30, // 30 minutes
    path: '/',
  }
}

/**
 * Cookie name constants with security prefixes
 */
export const COOKIE_NAMES = {
  ACCESS_TOKEN: '__Host-access-token', // __Host- prefix requires Secure, Path=/, no Domain
  REFRESH_TOKEN: '__Secure-refresh-token', // __Secure- prefix requires Secure
  CSRF_TOKEN: '__Host-csrf-token',
  SESSION_ID: '__Host-session-id',
} as const

/**
 * Validate cookie configuration for security
 */
export function validateCookieSecurity(options: CookieOptions): boolean {
  // SameSite=None requires Secure (check this first for specific error message)
  if (options.sameSite === 'none' && !options.secure) {
    console.error('SameSite=None requires Secure flag')
    return false
  }

  // In production, cookies must be secure
  if (process.env.NODE_ENV === 'production') {
    if (!options.secure) {
      console.error('Cookie must have Secure flag in production')
      return false
    }
  }

  return true
}

/**
 * Security headers for API requests
 */
export function getSecurityHeaders(): HeadersInit {
  return {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
  }
}

/**
 * Content Security Policy configuration
 */
export function getCSPHeader(): string {
  const isProduction = process.env.NODE_ENV === 'production'

  const directives = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'", // Note: Remove unsafe-eval in production
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    "connect-src 'self' https://api.benger.de wss://api.benger.de",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ]

  // Stricter CSP in production
  if (isProduction) {
    directives[1] = "script-src 'self'" // Remove unsafe-inline and unsafe-eval
    directives[2] = "style-src 'self'" // Remove unsafe-inline from styles
  }

  return directives.join('; ')
}
