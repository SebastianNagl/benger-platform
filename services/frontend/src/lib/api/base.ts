/**
 * Base API client for BenGER
 * Provides common functionality for all resource-specific API clients
 *
 * Issue #171:  with connection pooling and request management
 */

import logger from '@/lib/utils/logger'

// Server-side vs client-side API URL handling
function getApiBaseUrl(): string {
  // Server-side (SSR) - use direct API container URL
  if (typeof window === 'undefined') {
    // Use environment variable if available (for E2E tests), otherwise default
    const apiBaseUrl = process.env.INTERNAL_API_URL || process.env.API_BASE_URL || 'http://api:8000'
    return `${apiBaseUrl}/api`
  }

  // Client-side - ALWAYS use Next.js proxy, never direct API access
  return '/api'
}

// Maximum concurrent requests to prevent resource exhaustion
// Increased from 3 to 10 to improve page load performance
const MAX_CONCURRENT_REQUESTS = 10
const REQUEST_TIMEOUT = 30000 // 30 seconds

// Enhanced cache for GET requests with user validation
interface CacheEntry {
  data: any
  timestamp: number
  userId: string | null // Track which user this cache entry belongs to
}

const CACHE_TTL = 30000 // 30 seconds cache for GET requests

export class BaseApiClient {
  private onAuthFailure?: () => void
  private refreshPromise: Promise<boolean> | null = null
  private organizationContextProvider?: () => string | null
  private activeRequests = new Set<string>()
  private requestQueue: Array<() => void> = []
  private responseCache = new Map<string, CacheEntry>()
  private lastKnownUserId: string | null = null

  /**
   * Clear the response cache (useful after mutations)
   */
  clearCache() {
    this.responseCache.clear()
    // Also reset the last known user ID to force re-validation
    this.lastKnownUserId = null
    logger.debug('Response cache cleared and user ID reset')
  }

  /**
   * Clear cache entries for a specific user
   */
  clearUserCache(userId: string) {
    const keysToDelete: string[] = []
    this.responseCache.forEach((value, key) => {
      // Clear entries that match the user ID in the key or in the entry metadata
      if (key.startsWith(`${userId}-`) || value.userId === userId) {
        keysToDelete.push(key)
      }
    })
    keysToDelete.forEach((key) => this.responseCache.delete(key))
    logger.debug(
      `Cleared cache for user ${userId}: ${keysToDelete.length} entries removed`
    )
  }

  /**
   * Clear cache entries matching an endpoint pattern
   * @param pattern - Endpoint pattern to match (e.g., '/organizations/123' or '/organizations/123/members')
   */
  invalidateCache(pattern: string | RegExp) {
    const keysToDelete: string[] = []
    this.responseCache.forEach((value, key) => {
      // Extract the endpoint from the cache key (format: "userId-METHOD-endpoint")
      const parts = key.split('-')
      if (parts.length >= 3) {
        const endpoint = parts.slice(2).join('-') // Rejoin in case endpoint contains dashes

        if (typeof pattern === 'string') {
          // For string patterns, check if the endpoint includes the pattern
          // Note: This is intentionally broad - invalidating '/organizations' will also
          // invalidate '/organizations/123', '/organizations/456', etc.
          // This ensures related caches are cleared but may invalidate more than strictly necessary
          if (endpoint.includes(pattern)) {
            keysToDelete.push(key)
          }
        } else {
          // For regex patterns, test against the endpoint
          if (pattern.test(endpoint)) {
            keysToDelete.push(key)
          }
        }
      }
    })

    keysToDelete.forEach((key) => this.responseCache.delete(key))
    logger.debug(
      `Invalidated cache for pattern ${pattern}: ${keysToDelete.length} entries removed`
    )
  }

  /**
   * Invalidate related cache entries after a mutation
   * @param mutationEndpoint - The endpoint that was mutated
   */
  private invalidateRelatedCache(mutationEndpoint: string) {
    // Extract the resource path from the mutation endpoint
    // For example: /organizations/123/members/456 -> /organizations/123
    const segments = mutationEndpoint.split('/')

    // Build progressive patterns to invalidate
    const patterns: string[] = []

    // Always invalidate the exact endpoint
    patterns.push(mutationEndpoint)

    // For organization member operations, invalidate the organization and members list
    if (
      mutationEndpoint.includes('/organizations/') &&
      mutationEndpoint.includes('/members')
    ) {
      const orgMatch = mutationEndpoint.match(/\/organizations\/([^\/]+)/)
      if (orgMatch) {
        patterns.push(`/organizations/${orgMatch[1]}`)
        patterns.push(`/organizations/${orgMatch[1]}/members`)
      }
    }

    // For invitation operations, invalidate related organization data
    if (mutationEndpoint.includes('/invitations/')) {
      const orgMatch = mutationEndpoint.match(/\/organizations\/([^\/]+)/)
      if (orgMatch) {
        patterns.push(`/organizations/${orgMatch[1]}`)
        patterns.push(`/organizations/${orgMatch[1]}/members`)
        patterns.push(`/organizations/${orgMatch[1]}/invitations`)
      }
      // Also invalidate invitation lists
      patterns.push('/invitations')
    }

    // For organization updates, invalidate the organization list
    if (mutationEndpoint.match(/^\/organizations\/[^\/]+$/)) {
      patterns.push('/organizations')
    }

    // For user API key operations, invalidate the status endpoint
    if (mutationEndpoint.includes('/users/api-keys/')) {
      patterns.push('/users/api-keys/status')
    }

    // For organization API key operations, invalidate the status and settings endpoints
    if (
      mutationEndpoint.includes('/organizations/') &&
      mutationEndpoint.includes('/api-keys/')
    ) {
      const orgMatch = mutationEndpoint.match(/\/organizations\/([^\/]+)/)
      if (orgMatch) {
        patterns.push(`/organizations/${orgMatch[1]}/api-keys`)
      }
    }

    // Invalidate each pattern
    patterns.forEach((pattern) => {
      this.invalidateCache(pattern)
    })
  }

  /**
   * Validate if a cache entry belongs to the current user
   */
  private validateCacheEntry(
    entry: CacheEntry,
    currentUserId: string | null
  ): boolean {
    // If entry has no user ID (old cache), invalidate it for safety
    if (entry.userId === undefined) {
      logger.debug('Cache entry has no user ID, invalidating for safety')
      return false
    }

    // Check if the cache entry belongs to the current user
    if (entry.userId !== currentUserId) {
      logger.warn(
        `Cache entry user mismatch: expected ${currentUserId}, got ${entry.userId} - clearing entire cache`
      )
      // Clear entire cache on user mismatch to prevent any pollution
      this.clearCache()
      return false
    }

    // Check if the cache entry is still within TTL
    if (Date.now() - entry.timestamp >= CACHE_TTL) {
      logger.debug('Cache entry expired')
      return false
    }

    return true
  }

  /**
   * Set callback for authentication failures
   */
  setAuthFailureHandler(handler: () => void) {
    this.onAuthFailure = handler
  }

  /**
   * Set function to provide current organization context
   */
  setOrganizationContextProvider(provider: () => string | null) {
    this.organizationContextProvider = provider
  }

  /**
   * Check if a JWT token is expired or will expire soon
   */
  private isTokenExpired(token: string): boolean {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      const now = Date.now() / 1000
      // Consider token expired if it expires within the next 30 seconds
      return payload.exp * 1000 < Date.now() + 30000
    } catch {
      // Treat malformed tokens as expired
      return true
    }
  }

  /**
   * Attempt to refresh the access token using the refresh token
   */
  private async refreshAccessToken(): Promise<boolean> {
    try {
      const response = await fetch(`${getApiBaseUrl()}/auth/refresh`, {
        method: 'POST',
        credentials: 'include', // Include refresh token cookie
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        // New tokens are set as cookies by the server
        return true
      } else {
        return false
      }
    } catch (error) {
      // Token refresh failed
      return false
    }
  }

  /**
   * Special request method for authentication checks that doesn't log 401 errors
   * as they are expected for unauthenticated users
   */
  protected async authCheckRequest(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<any> {
    const url = `${getApiBaseUrl()}${endpoint}`
    const isFormData = options.body instanceof FormData
    const method = options.method || 'GET'

    const headers: Record<string, string> = {}

    // Only set Content-Type for JSON requests, not for FormData
    if (!isFormData) {
      headers['Content-Type'] = 'application/json'
    }

    // SECURITY FIX: Removed localStorage token fallback
    // Authentication now relies entirely on HttpOnly cookies for XSS protection
    // The browser automatically includes cookies with 'credentials: include'

    // Add organization context header if available
    if (this.organizationContextProvider) {
      const orgContext = this.organizationContextProvider()
      if (orgContext) {
        headers['X-Organization-Context'] = orgContext
      }
    }

    try {
      const response = await fetch(url, {
        ...options,
        credentials: 'include', // Include cookies for HttpOnly JWT
        headers: {
          ...headers,
          ...options.headers,
        },
      })

      if (!response.ok) {
        // For auth checks, 401 is an expected response for unauthenticated users
        if (response.status === 401) {
          throw new Error('Unauthenticated')
        }

        let errorMessage = `HTTP error! status: ${response.status}`
        try {
          const errorText = await response.text()
          if (errorText) {
            errorMessage += ` - ${errorText}`
          }
        } catch (e) {
          logger.debug('Could not read error text from response')
        }
        throw new Error(errorMessage)
      }

      // Handle 204 No Content responses
      if (response.status === 204) {
        // Invalidate related cache after successful mutations (204 is common for DELETE)
        if (['POST', 'PUT', 'DELETE'].includes(method)) {
          this.invalidateRelatedCache(endpoint)
          logger.debug(
            `Cache invalidated after ${method} to ${endpoint} (204 response)`
          )
        }
        return undefined
      }

      const contentType = response.headers.get('content-type')
      if (contentType && contentType.includes('application/json')) {
        const text = await response.text()
        if (!text) {
          return null
        }
        try {
          return JSON.parse(text)
        } catch (jsonError) {
          logger.error('Failed to parse JSON response:', jsonError)
          throw new Error(`Invalid JSON response: ${jsonError}`)
        }
      }
      return response.text()
    } catch (error) {
      // Handle network errors and other fetch failures
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error(`Network error: Unable to connect to API at ${url}`)
      }
      // Re-throw other errors as-is
      throw error
    }
  }

  /**
   * Process request queue when a request completes
   */
  private processRequestQueue() {
    if (
      this.requestQueue.length > 0 &&
      this.activeRequests.size < MAX_CONCURRENT_REQUESTS
    ) {
      const nextRequest = this.requestQueue.shift()
      if (nextRequest) {
        nextRequest()
      }
    }
  }

  /**
   * Wait for available request slot
   */
  private async waitForRequestSlot(requestId: string): Promise<void> {
    if (this.activeRequests.size >= MAX_CONCURRENT_REQUESTS) {
      // Request queue full, queueing request

      return new Promise((resolve) => {
        this.requestQueue.push(() => {
          this.activeRequests.add(requestId)
          resolve()
        })
      })
    } else {
      this.activeRequests.add(requestId)
    }
  }

  protected async request(
    endpoint: string,
    options: RequestInit = {},
    isRetry: boolean = false,
    retryCount: number = 0
  ): Promise<any> {
    const apiBaseUrl = getApiBaseUrl()
    const url = `${apiBaseUrl}${endpoint}`

    // Debug logging for request construction - removed for production
    const isFormData = options.body instanceof FormData
    const requestId = `${options.method || 'GET'}-${endpoint}-${Date.now()}`

    // Check cache for GET requests - include user identity in cache key
    const method = options.method || 'GET'
    // Get the current user ID from localStorage
    const userId =
      typeof window !== 'undefined'
        ? localStorage.getItem('benger_last_session_user')
        : null

    // Detect user change and clear cache if needed
    if (this.lastKnownUserId !== null && this.lastKnownUserId !== userId) {
      logger.warn(
        `User changed from ${this.lastKnownUserId} to ${userId} - clearing cache`
      )
      this.clearCache()
    }
    this.lastKnownUserId = userId

    // Always include userId in cache key, use 'anonymous' for no user
    const cacheKey = `${userId || 'anonymous'}-${method}-${endpoint}`

    if (method === 'GET' && !isRetry) {
      const cached = this.responseCache.get(cacheKey)
      if (cached) {
        // Validate that the cache entry belongs to the current user
        if (this.validateCacheEntry(cached, userId)) {
          logger.debug(`Cache hit for ${cacheKey} (user: ${userId})`)
          return Promise.resolve(cached.data)
        } else {
          // Cache entry is invalid or belongs to different user, remove it
          logger.debug(
            `Cache invalidated for ${cacheKey}, removing stale entry`
          )
          this.responseCache.delete(cacheKey)
        }
      }
    }

    // Wait for available request slot
    await this.waitForRequestSlot(requestId)

    try {
      // API Request in progress
      const headers: Record<string, string> = {}

      // Only set Content-Type for JSON requests, not for FormData
      if (!isFormData) {
        headers['Content-Type'] = 'application/json'
      }

      // Add Authorization header if we have a valid token in localStorage as fallback
      if (typeof window !== 'undefined') {
        const token = localStorage.getItem('access_token')
        if (token && !this.isTokenExpired(token)) {
          headers['Authorization'] = `Bearer ${token}`
        } else if (token && this.isTokenExpired(token)) {
          logger.debug('Token is expired, will trigger refresh on 401 response')
        }
      }

      // Add organization context header if available
      if (this.organizationContextProvider) {
        const orgContext = this.organizationContextProvider()
        if (orgContext) {
          headers['X-Organization-Context'] = orgContext
        }
      }

      // Create AbortController for timeout if not provided
      const controller = new AbortController()
      const signal = options.signal || controller.signal
      const timeoutId = !options.signal
        ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT)
        : undefined

      const response = await fetch(url, {
        ...options,
        signal,
        credentials: 'include', // Include cookies for HttpOnly JWT
        headers: {
          ...headers,
          ...options.headers,
        },
      })

      // Clear timeout if request completes
      if (timeoutId) {
        clearTimeout(timeoutId)
      }

      if (!response.ok) {
        // Special handling for logout endpoint - 401 is expected
        if (endpoint === '/auth/logout' && response.status === 401) {
          return undefined // Return undefined for successful logout
        }

        // Parse error response to extract structured error data
        let errorData: any = null
        let errorMessage = `HTTP error! status: ${response.status}`

        try {
          const errorText = await response.text()
          if (errorText) {
            try {
              // Try to parse as JSON first
              errorData = JSON.parse(errorText)
              errorMessage =
                errorData.detail || errorData.message || errorMessage
            } catch {
              // If not JSON, use the text as-is
              errorMessage += ` - ${errorText}`
            }
          }
        } catch (e) {
          logger.debug('Could not read error text from response')
        }

        // API Error occurred

        // Handle 502/503 errors during service restarts - retry with backoff
        if ([502, 503].includes(response.status) && retryCount < 2) {
          const delay = (retryCount + 1) * 1000 // 1s, 2s delays
          // Service temporarily unavailable, retrying...
          await new Promise((resolve) => setTimeout(resolve, delay))
          return this.request(endpoint, options, isRetry, retryCount + 1)
        }

        // Handle 429 rate limiting - retry with exponential backoff
        if (response.status === 429 && retryCount < 3) {
          const retryAfter = response.headers.get('retry-after')
          const delay = retryAfter
            ? parseInt(retryAfter) * 1000
            : Math.pow(2, retryCount + 2) * 1000
          // Rate limited, retrying...
          await new Promise((resolve) => setTimeout(resolve, delay))
          return this.request(endpoint, options, isRetry, retryCount + 1)
        }

        // Handle 401 errors - attempt token refresh before triggering logout
        // Skip refresh attempt for certain endpoints where 401 is expected
        const skipAuthFailureEndpoints = [
          '/auth/refresh',
          '/auth/logout',
          '/feature-flags', // Feature flags should not trigger auth failure
        ]

        const shouldSkipAuthFailure = skipAuthFailureEndpoints.some((path) =>
          endpoint.includes(path)
        )

        if (response.status === 401 && !isRetry && !shouldSkipAuthFailure) {
          // Authentication failed, attempting token refresh...

          // Ensure only one refresh happens at a time
          if (!this.refreshPromise) {
            this.refreshPromise = this.refreshAccessToken()
          }

          const refreshSuccess = await this.refreshPromise
          this.refreshPromise = null

          if (refreshSuccess) {
            // Token refresh successful, retrying original request
            // Retry the original request with the new token
            return this.request(endpoint, options, true, retryCount)
          } else {
            // Token refresh failed, triggering logout
            // Refresh failed, trigger logout
            if (this.onAuthFailure) {
              this.onAuthFailure()
            }
          }
        }

        // Create axios-like error structure for better frontend compatibility
        const error = new Error(errorMessage) as any
        error.response = {
          status: response.status,
          statusText: response.statusText,
          data: errorData,
        }
        throw error
      }

      // Handle 204 No Content responses
      if (response.status === 204) {
        // Invalidate related cache after successful mutations (204 is common for DELETE)
        if (['POST', 'PUT', 'DELETE'].includes(method)) {
          this.invalidateRelatedCache(endpoint)
          logger.debug(
            `Cache invalidated after ${method} to ${endpoint} (204 response)`
          )
        }
        return undefined
      }

      const contentType = response.headers.get('content-type')
      const contentDisposition = response.headers.get('content-disposition')

      // Handle blob responses (binary files like ZIP, PDF, etc.)
      // Also handle CSV/TSV exports and any response with Content-Disposition: attachment
      // which indicates a file download
      if (
        (contentType &&
          (contentType.includes('application/zip') ||
            contentType.includes('application/octet-stream') ||
            contentType.includes('application/pdf') ||
            contentType.includes('text/csv') ||
            contentType.includes('text/tab-separated-values') ||
            contentType.startsWith('image/') ||
            contentType.startsWith('video/') ||
            contentType.startsWith('audio/'))) ||
        (contentDisposition && contentDisposition.includes('attachment'))
      ) {
        const blob = await response.blob()
        logger.debug(
          `Returning blob response with content-type: ${contentType}, content-disposition: ${contentDisposition}`
        )
        return blob
      }

      // Handle JSON responses
      if (contentType && contentType.includes('application/json')) {
        const text = await response.text()
        if (!text) {
          return null
        }
        try {
          const jsonResult = JSON.parse(text)

          // Cache successful GET responses with user validation
          if (method === 'GET' && response.ok) {
            // Get the current user ID at cache time to ensure consistency
            const currentUserId =
              typeof window !== 'undefined'
                ? localStorage.getItem('benger_last_session_user')
                : null
            this.responseCache.set(cacheKey, {
              data: jsonResult,
              timestamp: Date.now(),
              userId: currentUserId,
            })
            logger.debug(
              `Cached JSON response for ${cacheKey} (user: ${currentUserId})`
            )
          }

          // Invalidate related cache after successful mutations
          if (['POST', 'PUT', 'DELETE'].includes(method) && response.ok) {
            this.invalidateRelatedCache(endpoint)
            logger.debug(`Cache invalidated after ${method} to ${endpoint}`)
          }

          return jsonResult
        } catch (jsonError) {
          logger.error('Failed to parse JSON response:', jsonError)
          throw new Error(`Invalid JSON response: ${jsonError}`)
        }
      }

      // Handle text responses
      const textResult = await response.text()

      // Cache successful GET responses with user validation
      if (method === 'GET' && response.ok) {
        // Get the current user ID at cache time to ensure consistency
        const currentUserId =
          typeof window !== 'undefined'
            ? localStorage.getItem('benger_last_session_user')
            : null
        this.responseCache.set(cacheKey, {
          data: textResult,
          timestamp: Date.now(),
          userId: currentUserId,
        })
        logger.debug(`Cached response for ${cacheKey} (user: ${currentUserId})`)
      }

      // Invalidate related cache after successful mutations
      if (['POST', 'PUT', 'DELETE'].includes(method) && response.ok) {
        this.invalidateRelatedCache(endpoint)
        logger.debug(`Cache invalidated after ${method} to ${endpoint}`)
      }

      return textResult
    } catch (error) {
      // Handle network errors and other fetch failures with retry logic
      if (
        error instanceof TypeError &&
        error.message.includes('fetch') &&
        retryCount < 2
      ) {
        const delay = (retryCount + 1) * 1000 // 1s, 2s delays
        // Network error, retrying...
        await new Promise((resolve) => setTimeout(resolve, delay))
        return this.request(endpoint, options, isRetry, retryCount + 1)
      }

      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error(`Network error: Unable to connect to API at ${url}`)
      }
      // Re-throw other errors as-is
      throw error
    } finally {
      // Always clean up request tracking
      this.activeRequests.delete(requestId)
      this.processRequestQueue()
    }
  }

  /**
   * HTTP convenience methods for testing and backward compatibility
   */
  async get(endpoint: string, options: RequestInit = {}): Promise<any> {
    return this.request(endpoint, {
      ...options,
      method: 'GET',
    })
  }

  async post(
    endpoint: string,
    data?: any,
    options: RequestInit = {}
  ): Promise<any> {
    // Handle FormData specially - don't JSON.stringify it
    let body: any
    if (data instanceof FormData) {
      body = data
    } else if (data !== undefined) {
      body = JSON.stringify(data)
    } else {
      body = options.body
    }

    return this.request(endpoint, {
      ...options,
      method: 'POST',
      body,
    })
  }

  async put(
    endpoint: string,
    data?: any,
    options: RequestInit = {}
  ): Promise<any> {
    return this.request(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : options.body,
    })
  }

  async patch(
    endpoint: string,
    data?: any,
    options: RequestInit = {}
  ): Promise<any> {
    return this.request(endpoint, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : options.body,
    })
  }

  async delete(endpoint: string, options: RequestInit = {}): Promise<any> {
    return this.request(endpoint, {
      ...options,
      method: 'DELETE',
    })
  }
}
