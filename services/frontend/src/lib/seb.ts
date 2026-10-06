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

// SEB 3.0 for macOS / iOS only fills the key variables after updateKeys()
// calls back, for the page URL at that moment. Later versions set them on
// load and may not define the function. The API client awaits
// `sebKeysReady()` before every request made with the JavaScript API present,
// which asks again after client-side navigation.
let keysReady: Promise<void> = Promise.resolve()
let keysUrl: string | null = null

function refreshKeys(): Promise<void> {
  const security = sebApi()?.security
  keysUrl = typeof window !== 'undefined' ? window.location.href : null
  if (!security || typeof security.updateKeys !== 'function') {
    return Promise.resolve()
  }
  const updateKeys = security.updateKeys.bind(security)
  return new Promise<void>((resolve) => {
    // Never hang the exam page on a build that doesn't call back.
    const fallback = setTimeout(resolve, 2000)
    try {
      updateKeys(() => {
        clearTimeout(fallback)
        resolve()
      })
    } catch {
      clearTimeout(fallback)
      resolve()
    }
  })
}

if (typeof window !== 'undefined') keysReady = refreshKeys()

/**
 * Resolves once SEB has filled its key variables for the current page
 * (immediately outside SEB).
 */
export function sebKeysReady(): Promise<void> {
  if (typeof window !== 'undefined' && window.location.href !== keysUrl) {
    keysReady = refreshKeys()
  }
  return keysReady
}

/**
 * Whether SEB's JavaScript API is present, i.e. the proof rides our own
 * headers. The API client then waits for `sebKeysReady()` before each
 * request; everywhere else requests go out without that extra await.
 */
export function hasSebJsApi(): boolean {
  return !!sebApi()?.security
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

/** Fired on `window` when the API refuses a request at the SEB gate. */
export const SEB_REFUSED_EVENT = 'benger:seb-refused'

export type SebRefusalCode = 'seb_required' | 'seb_version_not_allowed'

const SEB_REFUSAL_CODES: readonly string[] = [
  'seb_required',
  'seb_version_not_allowed',
]

/** Detail of SEB_REFUSED_EVENT. `projectId` names the refusing exam; older
 * API builds leave it out. */
export interface SebRefusal {
  code: SebRefusalCode
  projectId?: string
}

/**
 * Tells the page that the server refused a request at the SEB gate (a 403
 * whose `detail.code` is one of the SEB codes), so the exam page can switch
 * to its "open in SEB" screen even when the refusal comes mid-exam (settings
 * changed, another SEB version). Anything else is ignored.
 */
export function reportSebRefusal(status: number, errorData: unknown): void {
  if (status !== 403 || typeof window === 'undefined') return
  const detail = (errorData as { detail?: unknown } | null)?.detail as {
    code?: unknown
    project_id?: unknown
  } | null
  const code = detail?.code
  if (typeof code !== 'string' || !SEB_REFUSAL_CODES.includes(code)) return
  const refusal: SebRefusal = { code: code as SebRefusalCode }
  if (typeof detail?.project_id === 'string') {
    refusal.projectId = detail.project_id
  }
  window.dispatchEvent(
    new CustomEvent<SebRefusal>(SEB_REFUSED_EVENT, { detail: refusal }),
  )
}

// Navigation lock inside SEB. SEB's URL filter allows the whole site, so the
// app itself keeps an SEB session on the exam: the first exam page opened in
// SEB becomes the session's home, and any other page leads back to it.
// Sign-in and LMS launch pages stay reachable (they come before the exam).
const EXAM_HOME_KEY = 'benger.seb.examPage'
const EXAM_PAGE = /^\/(projects\/[^/]+\/label|student\/exams\/[^/]+)\/?$/
const FREE_PAGE = /^\/(login|lti|auth)(\/|$)/

function readExamHome(): string | null {
  try {
    return window.sessionStorage.getItem(EXAM_HOME_KEY)
  } catch {
    return null
  }
}

function writeExamHome(path: string): void {
  try {
    window.sessionStorage.setItem(EXAM_HOME_KEY, path)
  } catch {
    // Storage blocked: the lock simply stays off.
  }
}

/**
 * Where an SEB session on `pathname` must go instead, or null to stay.
 * Outside SEB always null. Opening an exam page inside SEB records it as the
 * session's exam.
 */
export function sebNavigationTarget(pathname: string): string | null {
  if (typeof window === 'undefined' || !isSafeExamBrowser()) return null
  if (EXAM_PAGE.test(pathname)) {
    if (!readExamHome()) writeExamHome(pathname.replace(/\/$/, ''))
    return null
  }
  if (FREE_PAGE.test(pathname)) return null
  return readExamHome()
}
