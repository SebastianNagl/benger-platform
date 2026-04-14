/**
 * API Client Export
 * Re-exports the main API client for backward compatibility and cleaner imports
 */

export { ApiClient, api, default as apiClient, default } from './index'

/**
 * Get the API URL for client-side requests
 * Used primarily for WebSocket connections which need the full URL
 */
export function getApiUrl(): string {
  // In browser, determine API URL based on current host
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol
    const host = window.location.host

    // For development on localhost:3000, API is on localhost:8000
    if (host === 'localhost:3000') {
      return 'http://localhost:8000'
    }

    // For production or Docker environments, use same host with /api path
    // This works for both benger.localhost and production domains
    return `${protocol}//${host}`
  }

  // Server-side fallback (shouldn't be used for WebSocket URLs)
  return 'http://api:8000'
}
