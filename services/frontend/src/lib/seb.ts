/**
 * Safe Exam Browser (SEB) helpers.
 *
 * Exams that require SEB are verified server-side (see /shared/seb.py). SEB
 * for Windows sends its proof as HTTP headers on every request. The modern
 * WebView of SEB for macOS / iOS cannot, and exposes the same hashes through
 * its JavaScript API instead (`SafeExamBrowser.security`). Those hashes are
 * computed over the page URL, so we forward them together with the current
 * page URL and the URL the document was loaded with (SEB may hash either
 * after client-side navigation).
 */

interface SafeExamBrowserApi {
  version?: string
  security?: {
    configKey?: string
    browserExamKey?: string
    updateKeys?: (callback: () => void) => void
  }
}

declare global {
  interface Window {
    SafeExamBrowser?: SafeExamBrowserApi
  }
}

// Captured when this module is first evaluated in the browser, i.e. on the
// document load that SEB computed its initial hashes for.
const LOAD_URL: string | null =
  typeof window !== 'undefined' ? window.location.href : null

function sebApi(): SafeExamBrowserApi | undefined {
  if (typeof window === 'undefined') return undefined
  return window.SafeExamBrowser
}

// SEB 3.0 for macOS / iOS only fills the key variables after updateKeys().
// Later versions set them on load and may not define the function.
if (typeof window !== 'undefined') {
  try {
    sebApi()?.security?.updateKeys?.(() => {})
  } catch {
    // Not in SEB, or an SEB build without the function.
  }
}

/** Whether the page runs inside Safe Exam Browser. */
export function isSafeExamBrowser(): boolean {
  if (sebApi()) return true
  if (typeof navigator === 'undefined') return false
  return /\bSEB\/\d/.test(navigator.userAgent)
}

/** The SEB version the JavaScript API reports, if any. */
export function sebVersion(): string | null {
  return sebApi()?.version ?? null
}

/** Platforms SEB ships a client for. Linux, ChromeOS and Android have none. */
export type SebPlatform = 'windows' | 'macos' | 'ios' | 'unsupported'

export function sebPlatform(userAgent?: string): SebPlatform {
  const ua =
    userAgent ?? (typeof navigator !== 'undefined' ? navigator.userAgent : '')
  if (/iPad|iPhone|iPod/.test(ua)) return 'ios'
  // iPadOS reports a desktop Mac user agent; touch support tells them apart.
  if (/Macintosh|Mac OS X/.test(ua)) {
    if (typeof navigator !== 'undefined' && navigator.maxTouchPoints > 1) {
      return 'ios'
    }
    return 'macos'
  }
  if (/Windows/.test(ua)) return 'windows'
  return 'unsupported'
}

/**
 * Headers carrying the SEB JavaScript API proof. Empty outside SEB or when
 * SEB exposes no keys (then its native headers, if any, carry the proof).
 */
export function sebRequestHeaders(): Record<string, string> {
  const security = sebApi()?.security
  if (!security) return {}
  const headers: Record<string, string> = {}
  if (security.configKey) headers['X-Benger-SEB-CK'] = security.configKey
  if (security.browserExamKey) {
    headers['X-Benger-SEB-BEK'] = security.browserExamKey
  }
  if (Object.keys(headers).length === 0) return {}
  headers['X-Benger-SEB-URL'] = window.location.href
  if (LOAD_URL) headers['X-Benger-SEB-Load-URL'] = LOAD_URL
  return headers
}
