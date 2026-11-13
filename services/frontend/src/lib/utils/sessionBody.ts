/**
 * Response bodies of the auth routes, as relayed to the browser.
 *
 * Session tokens live in HttpOnly cookies only, so script on the page can
 * never read them. The API no longer puts them in the login or refresh
 * body; the proxy routes drop them anyway, so no API version or future
 * change can hand one to the page.
 */

const SESSION_TOKEN_FIELDS = ['access_token', 'refresh_token'] as const

/** ``body`` without its session token fields (other values pass unchanged). */
export function withoutSessionTokens<T>(body: T): T {
  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    return body
  }
  const copy: Record<string, unknown> = { ...(body as Record<string, unknown>) }
  for (const field of SESSION_TOKEN_FIELDS) delete copy[field]
  return copy as T
}
