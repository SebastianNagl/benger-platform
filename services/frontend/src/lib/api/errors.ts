/**
 * Error-text helpers for API failures, kept apart from the client so
 * components can use them where tests mock the client module.
 */

/**
 * FastAPI returns validation errors as `detail: [{loc, msg, type}, ...]`.
 * Without flattening, `new Error(arr)` calls Array#toString and produces
 * `"[object Object],..."` — opaque to the user. This turns the array into
 * `"email: field required; password: too short"` while leaving plain-string
 * details unchanged.
 */
export function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (!item || typeof item !== 'object') return String(item)
        const e = item as { loc?: unknown[]; msg?: string; message?: string }
        const msg = e.msg || e.message || JSON.stringify(item)
        const loc = Array.isArray(e.loc)
          ? e.loc.filter((p) => p !== 'body').join('.')
          : ''
        return loc ? `${loc}: ${msg}` : msg
      })
      .filter(Boolean)
    return parts.length ? parts.join('; ') : null
  }
  if (detail && typeof detail === 'object') {
    const m =
      (detail as { msg?: string; message?: string }).msg ||
      (detail as { msg?: string; message?: string }).message
    return m || JSON.stringify(detail)
  }
  return null
}

/**
 * Toast text for a failed API call: the server's `detail` (formatted, so a
 * FastAPI validation list reads as text instead of reaching the toast as an
 * array) or the caller's localized fallback when the server sent none.
 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  return formatErrorDetail(detail) || fallback
}

/**
 * Seconds to wait from an auth rate-limit answer: status 429 with
 * `detail: {code: "rate_limited", retry_after}`. Null for anything else.
 */
export function rateLimitRetryAfter(
  status: number | undefined,
  body: unknown,
): number | null {
  if (status !== 429 || !body || typeof body !== 'object') return null
  const detail = (body as { detail?: unknown }).detail
  if (!detail || typeof detail !== 'object') return null
  const { code, retry_after: retryAfter } = detail as {
    code?: unknown
    retry_after?: unknown
  }
  if (code !== 'rate_limited') return null
  const seconds = Number(retryAfter)
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null
}

/**
 * Localized "too many attempts, try again in N minutes" for a thrown API
 * error (BaseApiClient puts `{status, data}` on `error.response`) or for a
 * raw `status` + JSON body. Minutes are rounded up. Null when the error is
 * not a rate limit, so callers fall back to their usual text.
 */
export function rateLimitMessage(
  source: unknown,
  t: (key: string, vars?: Record<string, string | number>) => string,
  body?: unknown,
): string | null {
  let seconds: number | null
  if (typeof source === 'number') {
    seconds = rateLimitRetryAfter(source, body)
  } else {
    const response = (
      source as { response?: { status?: number; data?: unknown } } | null
    )?.response
    seconds = rateLimitRetryAfter(response?.status, response?.data)
  }
  if (seconds === null) return null
  return t('auth.rateLimited', {
    minutes: Math.max(1, Math.ceil(seconds / 60)),
  })
}
