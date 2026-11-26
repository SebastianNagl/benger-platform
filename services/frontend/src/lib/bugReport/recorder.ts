/**
 * What a problem report attaches beyond the form: the last frontend errors,
 * the last failed API requests and the last page changes of this tab.
 *
 * Small ring buffers in module state, filled while the `bug_reports` flag is
 * on (BugReportHost installs the listeners then and removes them when it
 * goes off). Nothing here leaves the browser by itself; the report dialog
 * shows the collected context before it is sent.
 *
 * Kept on purpose: methods, paths, statuses, request ids, error messages and
 * stacks. Never kept: query strings, fragments, request or response bodies,
 * headers other than the request id, cookies or tokens. Path segments that
 * look like secrets are replaced (`redactPath`), and the server applies the
 * same rule again.
 */

export interface RecordedError {
  message: string
  name?: string
  stack?: string
  source: string
  digest?: string
  path?: string
  time: string
}

export interface RecordedRequest {
  method: string
  path: string
  /** HTTP status; 0 when the request never got an answer. */
  status: number
  request_id?: string
  error?: string
  duration_ms?: number
  time: string
}

export interface RecordedNavigation {
  path: string
  time: string
}

export const MAX_ERRORS = 5
export const MAX_REQUESTS = 10
export const MAX_NAVIGATION = 15
const MAX_MESSAGE = 1000
const MAX_STACK = 4000

let errors: RecordedError[] = []
let requests: RecordedRequest[] = []
let navigation: RecordedNavigation[] = []
let installed: (() => void) | null = null

const UUID =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/
const TOKENISH = /^[A-Za-z0-9_\-.~%]{24,}$/
/** Pages whose next path segment is a secret (mail links). */
const TOKEN_ROUTES = new Set([
  'accept-invitation',
  'activate',
  'confirm-email-change',
  'reset-password',
  'verify-email',
])
const REDACTED = '[redacted]'

function now(): string {
  return new Date().toISOString()
}

function push<T>(list: T[], item: T, max: number): T[] {
  const next = [...list, item]
  return next.length > max ? next.slice(next.length - max) : next
}

/** The path of a URL or path, without query or fragment, with secret-looking
 * segments replaced. */
export function redactPath(value: string): string {
  let path = value
  try {
    if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) path = new URL(value).pathname
  } catch {
    path = value
  }
  path = path.split('#')[0].split('?')[0]
  if (!path.startsWith('/')) path = `/${path}`
  let afterTokenRoute = false
  return path
    .split('/')
    .map((segment) => {
      if (afterTokenRoute && segment) {
        afterTokenRoute = false
        return REDACTED
      }
      if (TOKEN_ROUTES.has(segment)) {
        afterTokenRoute = true
        return segment
      }
      if (TOKENISH.test(segment) && !UUID.test(segment)) return REDACTED
      return segment
    })
    .join('/')
    .slice(0, 500)
}

function currentPath(): string | undefined {
  if (typeof window === 'undefined') return undefined
  return redactPath(window.location.pathname)
}

/** Record a frontend error (error boundaries call this; window errors and
 * unhandled rejections are recorded by the installed listeners). */
export function recordError(error: unknown, source: string): void {
  let message: string
  let name: string | undefined
  let stack: string | undefined
  let digest: string | undefined
  if (error instanceof Error) {
    message = error.message || String(error)
    name = error.name
    stack = error.stack
    digest = (error as Error & { digest?: string }).digest
  } else if (typeof error === 'string') {
    message = error
  } else {
    try {
      message = JSON.stringify(error) ?? String(error)
    } catch {
      message = String(error)
    }
  }
  const entry: RecordedError = {
    message: message.slice(0, MAX_MESSAGE),
    source,
    time: now(),
  }
  if (name) entry.name = name
  if (stack) entry.stack = stack.slice(0, MAX_STACK)
  if (digest) entry.digest = String(digest).slice(0, 100)
  const path = currentPath()
  if (path) entry.path = path
  const last = errors[errors.length - 1]
  // React reports one crash several times (boundary + window error).
  if (last && last.message === entry.message && last.stack === entry.stack)
    return
  errors = push(errors, entry, MAX_ERRORS)
}

export function recordFailedRequest(entry: Omit<RecordedRequest, 'time'>) {
  requests = push(
    requests,
    { ...entry, path: redactPath(entry.path), time: now() },
    MAX_REQUESTS,
  )
}

export function recordNavigation(path: string): void {
  const clean = redactPath(path)
  const last = navigation[navigation.length - 1]
  if (last && last.path === clean) return
  navigation = push(navigation, { path: clean, time: now() }, MAX_NAVIGATION)
}

export interface RecordedContext {
  errors: RecordedError[]
  failed_requests: RecordedRequest[]
  navigation: RecordedNavigation[]
}

export function getRecordedContext(): RecordedContext {
  return {
    errors: [...errors],
    failed_requests: [...requests],
    navigation: [...navigation],
  }
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase()
  if (typeof Request !== 'undefined' && input instanceof Request)
    return input.method.toUpperCase()
  return 'GET'
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return (input as Request).url
}

/** Only requests to this app's API are recorded (not third parties). */
function isApiRequest(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin)
    return (
      parsed.origin === window.location.origin &&
      parsed.pathname.startsWith('/api/')
    )
  } catch {
    return false
  }
}

/**
 * Start recording (idempotent): window errors, unhandled rejections and
 * failed same-origin `/api/` requests. Returns the function that stops it.
 * The fetch wrapper passes every call through unchanged and only looks at
 * the answer's status and `X-Request-ID` header.
 */
export function installBugReportRecorder(): () => void {
  if (typeof window === 'undefined') return () => {}
  if (installed) return installed

  const onError = (event: ErrorEvent) => {
    recordError(event.error ?? event.message, 'window.error')
  }
  const onRejection = (event: PromiseRejectionEvent) => {
    recordError(event.reason, 'unhandledrejection')
  }
  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)

  const originalFetch = window.fetch
  const wrapped: typeof window.fetch = async (input, init) => {
    const url = requestUrl(input)
    if (!isApiRequest(url)) return originalFetch(input, init)
    const method = requestMethod(input, init)
    const started = Date.now()
    try {
      const response = await originalFetch(input, init)
      if (!response.ok) {
        const requestId = response.headers?.get?.('x-request-id') ?? undefined
        recordFailedRequest({
          method,
          path: new URL(url, window.location.origin).pathname,
          status: response.status,
          ...(requestId ? { request_id: requestId.slice(0, 100) } : {}),
          duration_ms: Date.now() - started,
        })
      }
      return response
    } catch (error) {
      const aborted =
        error instanceof DOMException && error.name === 'AbortError'
      if (!aborted) {
        recordFailedRequest({
          method,
          path: new URL(url, window.location.origin).pathname,
          status: 0,
          error: error instanceof Error ? error.name : 'NetworkError',
          duration_ms: Date.now() - started,
        })
      }
      throw error
    }
  }
  window.fetch = wrapped

  const uninstall = () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
    // Leave a later wrapper (another library) in place.
    if (window.fetch === wrapped) window.fetch = originalFetch
    installed = null
  }
  installed = uninstall
  return uninstall
}

export function resetBugReportRecorderForTests(): void {
  installed?.()
  installed = null
  errors = []
  requests = []
  navigation = []
}
