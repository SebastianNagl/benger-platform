/**
 * The technical context a problem report attaches, built in the browser when
 * the dialog opens (the dialog shows exactly this before sending). The server
 * reduces it again to the keys and sizes it allows
 * (services/shared/bug_reports.py `clean_context`).
 *
 * Ids only: the page path and its route parameters (project and task ids),
 * never titles, names or e-mail addresses. Query strings travel as their
 * keys, never their values.
 */

import { getRecordedContext, redactPath } from './recorder'
import type { BugReportSource } from './store'

export interface BugReportContextInput {
  source: BugReportSource
  locale?: string
  /** Route parameters of the current page (`useParams()`). */
  routeParams?: Record<string, string | string[] | undefined>
  /** Flags on for the viewer (names only). */
  featureFlags?: Record<string, boolean>
  extensions?: readonly string[]
  uiMode?: string
  /** Roles of the viewer's organization memberships (no names). */
  orgRoles?: (string | undefined | null)[]
}

export interface BugReportContext {
  [key: string]: unknown
}

function size(width: number | undefined, height: number | undefined) {
  if (!width || !height) return undefined
  return { width: Math.round(width), height: Math.round(height) }
}

function sameOriginPath(url: string): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    if (parsed.origin !== window.location.origin) return undefined
    return redactPath(parsed.pathname)
  } catch {
    return undefined
  }
}

function params(
  input: BugReportContextInput['routeParams'],
): Record<string, string> | undefined {
  if (!input) return undefined
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(input)) {
    if (typeof value === 'string') out[key] = value
    else if (Array.isArray(value)) out[key] = value.join('/')
  }
  return Object.keys(out).length ? out : undefined
}

function timezone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch {
    return undefined
  }
}

export function buildBugReportContext(
  input: BugReportContextInput,
): BugReportContext {
  if (typeof window === 'undefined') return { source: input.source }
  const nav = window.navigator
  const uaData = (nav as Navigator & { userAgentData?: { platform?: string } })
    .userAgentData
  const queryKeys = Array.from(
    new Set(new URLSearchParams(window.location.search).keys()),
  )
  const recorded = getRecordedContext()
  const flags = Object.entries(input.featureFlags ?? {})
    .filter(([, on]) => on)
    .map(([name]) => name)
    .sort()
  const roles = Array.from(
    new Set((input.orgRoles ?? []).filter((r): r is string => !!r)),
  ).sort()
  const ctx: BugReportContext = {
    source: input.source,
    page: redactPath(window.location.pathname),
    query_keys: queryKeys.length ? queryKeys : undefined,
    route_params: params(input.routeParams),
    referrer: sameOriginPath(document.referrer),
    time: new Date().toISOString(),
    timezone: timezone(),
    locale: input.locale,
    languages: nav.languages
      ? Array.from(nav.languages).slice(0, 5)
      : undefined,
    user_agent: nav.userAgent,
    platform: uaData?.platform || nav.platform || undefined,
    viewport: size(window.innerWidth, window.innerHeight),
    screen: size(window.screen?.width, window.screen?.height),
    device_pixel_ratio: window.devicePixelRatio,
    color_scheme: document.documentElement.classList.contains('dark')
      ? 'dark'
      : 'light',
    online: nav.onLine,
    edition: process.env.NEXT_PUBLIC_BENGER_EDITION || 'community',
    extensions: input.extensions?.length ? [...input.extensions] : undefined,
    feature_flags: flags.length ? flags : undefined,
    ui_mode: input.uiMode,
    org_roles: roles.length ? roles : undefined,
    errors: recorded.errors.length ? recorded.errors : undefined,
    failed_requests: recorded.failed_requests.length
      ? recorded.failed_requests
      : undefined,
    navigation: recorded.navigation.length ? recorded.navigation : undefined,
  }
  for (const key of Object.keys(ctx)) {
    if (ctx[key] === undefined) delete ctx[key]
  }
  return ctx
}
