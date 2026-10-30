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
