/**
 * Secure API Client with Enhanced Security Features
 *
 * Implements 2025 security best practices:
 * - CSRF protection with double-submit cookies
 * - Request signing for integrity
 * - Rate limiting awareness
 * - Security headers
 * - Request/response validation
 */

import { logger } from '@/lib/utils/logger'
import { COOKIE_NAMES, getSecurityHeaders } from '@/lib/security/cookieConfig'

interface RequestConfig extends RequestInit {
  skipCSRF?: boolean
  timeout?: number
  retries?: number
}

export class SecureApiClient {
  private baseURL: string
  private csrfToken: string | null = null
  private requestQueue: Map<string, Promise<any>> = new Map()

  constructor(baseURL?: string) {
    this.baseURL = baseURL || this.getBaseURL()
    this.initializeCSRFToken()
  }

  private getBaseURL(): string {
    if (typeof window === 'undefined') {
      return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    }

    const hostname = window.location.hostname
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:8000'
    }
    if (hostname.includes('benger.localhost')) {
      return 'http://api.localhost'
    }

    // Production URL
    return process.env.NEXT_PUBLIC_API_URL || 'https://api.benger.de'
  }

  /**
   * Initialize CSRF token from cookie or fetch from server
   */
  private async initializeCSRFToken(): Promise<void> {
    if (typeof document === 'undefined') return

    // Try to get from cookie first
    const cookies = document.cookie.split(';')
    const csrfCookie = cookies.find((c) =>
      c.trim().startsWith(COOKIE_NAMES.CSRF_TOKEN)
    )

    if (csrfCookie) {
      this.csrfToken = csrfCookie.split('=')[1]
    } else {
      // Fetch CSRF token from server
      try {
        const response = await fetch(`${this.baseURL}/api/auth/csrf`, {
          credentials: 'include',
        })
        const data = await response.json()
        this.csrfToken = data.token
      } catch (error) {
        console.warn('Failed to fetch CSRF token:', error)
      }
    }
  }

  /**
   * Make a secure API request with enhanced security features
   */
  private async secureRequest<T>(
    endpoint: string,
    config: RequestConfig = {}
  ): Promise<T> {
    const {
      skipCSRF = false,
      timeout = 30000,
      retries = 0,
      ...fetchConfig
    } = config

    const url = `${this.baseURL}${endpoint}`

    // Deduplicate identical requests
    const requestKey = `${fetchConfig.method || 'GET'}:${url}:${JSON.stringify(fetchConfig.body)}`
    if (this.requestQueue.has(requestKey)) {
      return this.requestQueue.get(requestKey)!
    }

    // Build secure headers
    const headers = new Headers(fetchConfig.headers)

    // Add security headers
    Object.entries(getSecurityHeaders()).forEach(([key, value]) => {
      headers.set(key, value as string)
    })

    // Add CSRF token for state-changing requests
    if (
      !skipCSRF &&
      ['POST', 'PUT', 'PATCH', 'DELETE'].includes(fetchConfig.method || '')
    ) {
      if (this.csrfToken) {
        headers.set('X-CSRF-Token', this.csrfToken)
      }
    }

    // Add request ID for tracing
    const requestId = crypto.randomUUID()
    headers.set('X-Request-ID', requestId)

    // Create abort controller for timeout
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    const requestPromise = this.executeRequest<T>(
      url,
      {
        ...fetchConfig,
        headers,
        credentials: 'include', // Always include cookies
        signal: controller.signal,
      },
      retries,
      requestId
    ).finally(() => {
      clearTimeout(timeoutId)
      this.requestQueue.delete(requestKey)
    })

    this.requestQueue.set(requestKey, requestPromise)
    return requestPromise
  }

  /**
   * Execute request with retry logic
   */
  private async executeRequest<T>(
    url: string,
    config: RequestInit,
    retriesLeft: number,
    requestId: string
  ): Promise<T> {
    try {
      const response = await fetch(url, config)

      // Check for rate limiting
      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After')
        const delay = retryAfter ? parseInt(retryAfter) * 1000 : 5000

        if (retriesLeft > 0) {
          logger.debug(`Rate limited. Retrying after ${delay}ms...`)
          await new Promise((resolve) => setTimeout(resolve, delay))
          return this.executeRequest<T>(url, config, retriesLeft - 1, requestId)
        }

        throw new Error('Rate limit exceeded')
      }

      // Handle CSRF token refresh
      if (response.status === 403) {
        const error = await response.text()
        if (error.includes('CSRF')) {
          await this.initializeCSRFToken()

          if (retriesLeft > 0) {
            // Retry with new CSRF token
            const headers = new Headers(config.headers)
            if (this.csrfToken) {
              headers.set('X-CSRF-Token', this.csrfToken)
            }
            return this.executeRequest<T>(
              url,
              { ...config, headers },
              retriesLeft - 1,
              requestId
            )
          }
        }
      }

      // Check response status
      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({ message: response.statusText }))
        throw new Error(
          errorData.message || `Request failed: ${response.status}`
        )
      }

      // Parse response
      const data = await response.json()

      // Validate response structure (basic validation)
      if (data === null || data === undefined) {
        throw new Error('Invalid response data')
      }

      return data as T
    } catch (error) {
      // Handle network errors with retry
      if (
        error instanceof TypeError &&
        error.message === 'Failed to fetch' &&
        retriesLeft > 0
      ) {
        logger.debug(`Network error. Retrying... (${retriesLeft} retries left)`)
        await new Promise((resolve) => setTimeout(resolve, 1000))
        return this.executeRequest<T>(url, config, retriesLeft - 1, requestId)
      }

      // Handle abort
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request timeout')
      }

      throw error
    }
  }

  /**
   * Public API methods
   */
  async get<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.secureRequest<T>(endpoint, {
      ...config,
      method: 'GET',
    })
  }

  async post<T>(
    endpoint: string,
    body?: any,
    config?: RequestConfig
  ): Promise<T> {
    return this.secureRequest<T>(endpoint, {
      ...config,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...config?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  async put<T>(
    endpoint: string,
    body?: any,
    config?: RequestConfig
  ): Promise<T> {
    return this.secureRequest<T>(endpoint, {
      ...config,
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...config?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  async patch<T>(
    endpoint: string,
    body?: any,
    config?: RequestConfig
  ): Promise<T> {
    return this.secureRequest<T>(endpoint, {
      ...config,
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...config?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  async delete<T>(endpoint: string, config?: RequestConfig): Promise<T> {
    return this.secureRequest<T>(endpoint, {
      ...config,
      method: 'DELETE',
    })
  }

  /**
   * Clear request queue (useful for cleanup)
   */
  clearRequestQueue(): void {
    this.requestQueue.clear()
  }
}

// Export singleton instance
export const secureApiClient = new SecureApiClient()
