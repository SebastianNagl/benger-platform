/**
 * Subdomain utilities for multi-organization context switching.
 *
 * URL scheme:
 * - Private mode: what-a-benger.net / benger.localhost
 * - Org mode: {slug}.what-a-benger.net / {slug}.benger.localhost
 */

export const BASE_DOMAINS = [
  'staging.what-a-benger.net',
  'what-a-benger.net',
  'benger.localhost',
]

/**
 * Get the base domain from a hostname string.
 */
export function getBaseDomainFromHost(hostname: string): string {
  for (const baseDomain of BASE_DOMAINS) {
    if (hostname === baseDomain || hostname.endsWith(`.${baseDomain}`)) {
      return baseDomain
    }
  }
  return hostname
}

/**
 * Get the base domain from the current hostname.
 * Returns 'benger.localhost' or 'what-a-benger.net'.
 */
export function getBaseDomain(): string {
  if (typeof window === 'undefined') return 'benger.localhost'
  return getBaseDomainFromHost(window.location.hostname)
}

/**
 * Parse a hostname to extract org slug and mode.
 */
export function parseSubdomainFromHost(hostname: string): {
  orgSlug: string | null
  isPrivateMode: boolean
} {
  for (const baseDomain of BASE_DOMAINS) {
    if (hostname === baseDomain) {
      return { orgSlug: null, isPrivateMode: true }
    }
    if (hostname.endsWith(`.${baseDomain}`)) {
      const slug = hostname.replace(`.${baseDomain}`, '')
      if (slug && !slug.includes('.')) {
        return { orgSlug: slug, isPrivateMode: false }
      }
    }
  }
  return { orgSlug: null, isPrivateMode: true }
}

/**
 * Parse the current URL to extract org slug and mode.
 */
export function parseSubdomain(): {
  orgSlug: string | null
  isPrivateMode: boolean
} {
  if (typeof window === 'undefined') {
    return { orgSlug: null, isPrivateMode: true }
  }
  return parseSubdomainFromHost(window.location.hostname)
}

/**
 * Build a full URL for an organization subdomain, preserving the current path.
 */
export function getOrgUrl(slug: string, path?: string): string {
  const baseDomain = getBaseDomain()
  const protocol = typeof window !== 'undefined' ? window.location.protocol : 'http:'
  const port =
    typeof window !== 'undefined' && window.location.port ? `:${window.location.port}` : ''
  const targetPath = path || (typeof window !== 'undefined' ? window.location.pathname : '/')
  return `${protocol}//${slug}.${baseDomain}${port}${targetPath}`
}

/**
 * Build a full URL for private mode (no subdomain), preserving the current path.
 */
export function getPrivateUrl(path?: string): string {
  const baseDomain = getBaseDomain()
  const protocol = typeof window !== 'undefined' ? window.location.protocol : 'http:'
  const port =
    typeof window !== 'undefined' && window.location.port ? `:${window.location.port}` : ''
  const targetPath = path || (typeof window !== 'undefined' ? window.location.pathname : '/')
  return `${protocol}//${baseDomain}${port}${targetPath}`
}

/**
 * Get the cookie domain for cross-subdomain auth.
 * Returns '.benger.localhost' or '.what-a-benger.net'.
 */
export function getCookieDomain(): string {
  return `.${getBaseDomain()}`
}

/**
 * Get the cookie domain from a request hostname (for server-side use).
 */
export function getCookieDomainFromHost(host: string): string {
  for (const baseDomain of BASE_DOMAINS) {
    if (host === baseDomain || host.endsWith(`.${baseDomain}`)) {
      return `.${baseDomain}`
    }
  }
  // For plain localhost, don't set a domain
  return ''
}

/**
 * Cross-subdomain cookie helpers for persisting the last org slug.
 * Uses a cookie (not localStorage) so it's accessible across subdomains.
 */
const LAST_ORG_COOKIE = 'last_org_slug'

export function getLastOrgSlug(): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${LAST_ORG_COOKIE}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export function setLastOrgSlug(slug: string): void {
  if (typeof document === 'undefined') return
  const domain = getCookieDomain()
  document.cookie = `${LAST_ORG_COOKIE}=${encodeURIComponent(slug)}; domain=${domain}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`
}

export function clearLastOrgSlug(): void {
  if (typeof document === 'undefined') return
  const domain = getCookieDomain()
  document.cookie = `${LAST_ORG_COOKIE}=; domain=${domain}; path=/; max-age=0; SameSite=Lax`
}
