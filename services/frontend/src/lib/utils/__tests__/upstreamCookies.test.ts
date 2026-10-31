/**
 * Upstream Set-Cookie scoping: auth cookies are relayed host-only, and only
 * expiring legacy-domain clears keep their Domain (for hosts inside it).
 */

import {
  isExpiringSetCookie,
  scopeUpstreamSetCookie,
  scopeUpstreamSetCookies,
  stripCookieDomain,
} from '../upstreamCookies'

const LEGACY_CLEAR =
  'access_token=""; Domain=.what-a-benger.net; expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; Max-Age=0; Path=/; SameSite=lax; Secure'

describe('stripCookieDomain', () => {
  it('removes a Domain attribute anywhere in the cookie', () => {
    expect(stripCookieDomain('a=1; Domain=.x.net; Path=/')).toBe('a=1; Path=/')
    expect(stripCookieDomain('a=1; Path=/; domain=x.net')).toBe('a=1; Path=/')
    expect(stripCookieDomain('a=1; Domain=x; Path=/; Domain=y')).toBe(
      'a=1; Path=/',
    )
  })

  it('leaves the cookie value alone', () => {
    expect(stripCookieDomain('Domain=keep; Path=/')).toBe('Domain=keep; Path=/')
  })
})

describe('isExpiringSetCookie', () => {
  it('detects Max-Age=0 and negative Max-Age', () => {
    expect(isExpiringSetCookie('a=; Max-Age=0')).toBe(true)
    expect(isExpiringSetCookie('a=; max-age=-1')).toBe(true)
    expect(isExpiringSetCookie('a=1; Max-Age=1800')).toBe(false)
  })

  it('lets Max-Age win over Expires', () => {
    expect(
      isExpiringSetCookie(
        'a=1; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=60',
      ),
    ).toBe(false)
  })

  it('falls back to Expires', () => {
    expect(
      isExpiringSetCookie('a=; expires=Thu, 01 Jan 1970 00:00:00 GMT'),
    ).toBe(true)
    expect(
      isExpiringSetCookie('a=1; expires=Fri, 01 Jan 2100 00:00:00 GMT'),
    ).toBe(false)
    expect(isExpiringSetCookie('a=1; expires=not a date')).toBe(false)
  })

  it('treats a session cookie as live', () => {
    expect(isExpiringSetCookie('a=1; Path=/')).toBe(false)
  })
})

describe('scopeUpstreamSetCookie', () => {
  it('passes a cookie without Domain through unchanged', () => {
    const cookie =
      'access_token=t; HttpOnly; Max-Age=1800; Path=/; SameSite=lax'
    expect(scopeUpstreamSetCookie(cookie, 'what-a-benger.net')).toBe(cookie)
  })

  it('strips the Domain of a live cookie and never adds one', () => {
    expect(
      scopeUpstreamSetCookie(
        'access_token=t; Domain=.what-a-benger.net; Path=/; Secure',
        'what-a-benger.net',
      ),
    ).toBe('access_token=t; Path=/; Secure')
  })

  it('keeps the Domain of an expiring cookie for a host inside it', () => {
    expect(scopeUpstreamSetCookie(LEGACY_CLEAR, 'what-a-benger.net')).toBe(
      LEGACY_CLEAR,
    )
    expect(
      scopeUpstreamSetCookie(LEGACY_CLEAR, 'staging.what-a-benger.net:443'),
    ).toBe(LEGACY_CLEAR)
  })

  it('drops an expiring cookie for a domain the host is not part of', () => {
    expect(scopeUpstreamSetCookie(LEGACY_CLEAR, 'vertretbar.net')).toBeNull()
    expect(scopeUpstreamSetCookie(LEGACY_CLEAR, 'localhost:3000')).toBeNull()
    // Suffix match on labels only, not on raw strings.
    expect(
      scopeUpstreamSetCookie(LEGACY_CLEAR, 'evilwhat-a-benger.net'),
    ).toBeNull()
  })
})

describe('scopeUpstreamSetCookies', () => {
  it('keeps order and filters out rejected cookies', () => {
    const vertretbarClear = LEGACY_CLEAR.replace(
      '.what-a-benger.net',
      '.vertretbar.net',
    )
    const session = 'access_token=new; HttpOnly; Max-Age=1800; Path=/'
    expect(
      scopeUpstreamSetCookies(
        [LEGACY_CLEAR, vertretbarClear, session],
        'vertretbar.net',
      ),
    ).toEqual([vertretbarClear, session])
  })
})
