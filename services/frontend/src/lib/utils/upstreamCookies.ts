/**
 * Set-Cookie handling for responses relayed from the API.
 *
 * Auth cookies are host-only: a browser returns them to the exact host that
 * received them and never to sister hosts under the same apex (storage.,
 * staging., demo.). The relay therefore strips any Domain attribute from a
 * cookie the API sets and never adds one.
 *
 * One exception: an expiring cookie (Max-Age <= 0, or an Expires date in the
 * past) keeps its Domain when the browser's host lies inside that domain.
 * That is how the API drops the domain-wide cookies older releases set
 * (LEGACY_COOKIE_DOMAIN, services/api/auth_module/auth_cookies.py). Stripping
 * the Domain there would turn the clear into a host-only one that removes
 * the fresh session cookie instead. An expiring cookie for a domain the host
 * is not part of is dropped, since the browser would reject it anyway.
 */

const DOMAIN_ATTR = /;\s*Domain=([^;]*)/gi

function attribute(cookie: string, name: string): string | null {
  const match = cookie.match(new RegExp(`;\\s*${name}=([^;]*)`, 'i'))
  return match ? match[1].trim() : null
}

/** Does this Set-Cookie value delete the cookie? */
export function isExpiringSetCookie(
  cookie: string,
  now: number = Date.now(),
): boolean {
  // Max-Age wins over Expires (RFC 6265, 5.3).
  const maxAge = attribute(cookie, 'Max-Age')
  if (maxAge !== null && /^-?\d+$/.test(maxAge)) {
    return Number(maxAge) <= 0
  }
  const expires = attribute(cookie, 'Expires')
  if (expires !== null) {
    const at = Date.parse(expires)
    return !Number.isNaN(at) && at <= now
  }
  return false
}

/** Remove every Domain attribute, keeping the rest of the cookie intact. */
export function stripCookieDomain(cookie: string): string {
  return cookie.replace(DOMAIN_ATTR, '')
}

function hostInDomain(host: string, domain: string): boolean {
  const bareHost = host.split(':')[0].toLowerCase()
  const bareDomain = domain.trim().replace(/^\./, '').toLowerCase()
  if (!bareHost || !bareDomain) return false
  return bareHost === bareDomain || bareHost.endsWith(`.${bareDomain}`)
}

/**
 * Re-scope one upstream Set-Cookie value for the browser on ``host``.
 * Returns null when the cookie must not be relayed.
 */
export function scopeUpstreamSetCookie(
  cookie: string,
  host: string,
): string | null {
  const domains = [...cookie.matchAll(DOMAIN_ATTR)].map((m) => m[1])
  if (domains.length === 0) return cookie
  if (isExpiringSetCookie(cookie)) {
    // The last Domain attribute is the one a browser applies.
    return hostInDomain(host, domains[domains.length - 1]) ? cookie : null
  }
  return stripCookieDomain(cookie)
}

/** scopeUpstreamSetCookie over a list, dropping the cookies it rejects. */
export function scopeUpstreamSetCookies(
  cookies: string[],
  host: string,
): string[] {
  return cookies
    .map((cookie) => scopeUpstreamSetCookie(cookie, host))
    .filter((cookie): cookie is string => cookie !== null)
}
