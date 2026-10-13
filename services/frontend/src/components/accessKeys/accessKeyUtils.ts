/**
 * Pure helpers of the access-key UI: expiry presets, scope filtering by who
 * may grant what, copy-paste snippets and the reading of a failed
 * connection test. Kept free of React so they are easy to test.
 */

import type {
  AccessKey,
  AccessKeyCreate,
  AccessKeyTestResult,
  ScopeCatalog,
  ScopeDefinition,
} from '@/lib/api/types'

export const DAY_MS = 24 * 60 * 60 * 1000

/** Keys expiring within this many days get a warning in the list. */
export const EXPIRY_WARNING_DAYS = 14

export type ExpiryChoice = '30' | '90' | '365' | 'never'
export const EXPIRY_CHOICES: ExpiryChoice[] = ['30', '90', '365', 'never']
export const DEFAULT_EXPIRY: ExpiryChoice = '365'

/** The three presets the UI names in plain language, in display order. */
export const KNOWN_PRESETS = [
  'benchmark_read',
  'benchmark_submit',
  'org_full',
] as const

export type AccessKeyMode = 'org' | 'personal'

export function expiryToIso(
  choice: ExpiryChoice,
  now: number = Date.now(),
): string | null {
  if (choice === 'never') return null
  return new Date(now + Number(choice) * DAY_MS).toISOString()
}

/** Whole days until `iso` (negative once passed), null without a date. */
export function daysUntil(
  iso: string | null | undefined,
  now: number = Date.now(),
): number | null {
  if (!iso) return null
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return null
  return Math.ceil((ts - now) / DAY_MS)
}

export function expiresSoon(key: AccessKey, now: number = Date.now()) {
  if (key.status !== 'active') return false
  const days = daysUntil(key.expires_at, now)
  return days !== null && days <= EXPIRY_WARNING_DAYS
}

export function formatDate(
  iso: string | null | undefined,
  locale: string,
): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(locale === 'en' ? 'en-GB' : 'de-DE')
}

export interface GrantContext {
  mode: AccessKeyMode
  /** Org-wide admin (or superadmin); group admins are not. */
  isOrgAdmin: boolean
  role: 'ANNOTATOR' | 'CONTRIBUTOR'
}

/** Whether the scope can be offered at all in this context. */
export function isScopeOffered(
  scope: ScopeDefinition,
  ctx: Pick<GrantContext, 'mode' | 'isOrgAdmin'>,
): boolean {
  switch (scope.grantable) {
    case 'personal_only':
      return ctx.mode === 'personal'
    case 'org_admin':
      return ctx.mode === 'org' && ctx.isOrgAdmin
    default:
      return true
  }
}

/** Offered but blocked by the chosen role (org keys with ANNOTATOR). */
export function needsContributor(
  scope: ScopeDefinition,
  ctx: Pick<GrantContext, 'mode'>,
): boolean {
  return ctx.mode === 'org' && scope.grantable === 'full_data_role'
}

export function isScopeGrantable(
  scope: ScopeDefinition,
  ctx: GrantContext,
): boolean {
  if (!isScopeOffered(scope, ctx)) return false
  if (needsContributor(scope, ctx)) return ctx.role === 'CONTRIBUTOR'
  return true
}

export function offeredScopes(
  catalog: ScopeCatalog | null,
  ctx: Pick<GrantContext, 'mode' | 'isOrgAdmin'>,
): ScopeDefinition[] {
  return (catalog?.scopes ?? []).filter((s) => isScopeOffered(s, ctx))
}

/** Preset ids in display order: the known ones first, overlay ones after. */
export function presetIds(catalog: ScopeCatalog | null): string[] {
  const ids = Object.keys(catalog?.presets ?? {})
  const known = KNOWN_PRESETS.filter((p) => ids.includes(p)) as string[]
  return [...known, ...ids.filter((id) => !known.includes(id))]
}

/**
 * Scopes of a preset that the context may grant at all, plus whether the
 * preset needs the CONTRIBUTOR role for an org key.
 */
export function resolvePreset(
  catalog: ScopeCatalog | null,
  presetId: string,
  ctx: Pick<GrantContext, 'mode' | 'isOrgAdmin'>,
): { scopes: string[]; needsContributor: boolean } {
  const byName = new Map((catalog?.scopes ?? []).map((s) => [s.name, s]))
  const scopes: string[] = []
  let contributor = false
  for (const name of catalog?.presets?.[presetId] ?? []) {
    const def = byName.get(name)
    if (!def || !isScopeOffered(def, ctx)) continue
    if (needsContributor(def, ctx)) contributor = true
    scopes.push(name)
  }
  return { scopes, needsContributor: contributor }
}

/** The preset whose scopes equal the selection, or 'custom'. */
export function matchPreset(
  catalog: ScopeCatalog | null,
  selected: string[],
  ctx: Pick<GrantContext, 'mode' | 'isOrgAdmin'>,
): string {
  const want = [...selected].sort().join(',')
  for (const id of presetIds(catalog)) {
    const { scopes } = resolvePreset(catalog, id, ctx)
    if (scopes.length && [...scopes].sort().join(',') === want) return id
  }
  return 'custom'
}

export function scopeDescription(
  scope: ScopeDefinition | undefined,
  locale: string,
): string {
  if (!scope) return ''
  return locale === 'en' ? scope.description_en : scope.description_de
}

/** Body that recreates a key with the same settings (renewal). */
export function renewalBody(
  key: AccessKey,
  now: number = Date.now(),
): AccessKeyCreate {
  let expires_at: string | null = null
  if (key.expires_at) {
    const created = key.created_at ? Date.parse(key.created_at) : NaN
    const lifetime = Number.isNaN(created)
      ? 365 * DAY_MS
      : Date.parse(key.expires_at) - created
    const days = Math.max(1, Math.round(lifetime / DAY_MS))
    expires_at = new Date(now + days * DAY_MS).toISOString()
  }
  const body: AccessKeyCreate = {
    name: key.name,
    scopes: [...key.scopes],
    project_ids: key.project_ids ? [...key.project_ids] : null,
    expires_at,
    rate_limit_per_minute: key.rate_limit_per_minute,
    rate_limit_per_day: key.rate_limit_per_day,
  }
  if (key.owner_type === 'org') {
    body.org_role = key.org_role === 'CONTRIBUTOR' ? 'CONTRIBUTOR' : 'ANNOTATOR'
    body.group_id = key.group_id
  }
  return body
}

export function curlSnippet(baseUrl: string, secret: string): string {
  return `curl -H "Authorization: Bearer ${secret}" \\\n  ${baseUrl}/api/v1/me`
}

export function pythonSnippet(baseUrl: string, secret: string): string {
  return [
    'import requests',
    '',
    `API_KEY = "${secret}"`,
    '',
    'response = requests.get(',
    `    "${baseUrl}/api/v1/me",`,
    '    headers={"Authorization": f"Bearer {API_KEY}"},',
    '    timeout=30,',
    ')',
    'response.raise_for_status()',
    'print(response.json())',
  ].join('\n')
}

/** i18n key + variables for a failed connection test. */
export function describeTestFailure(
  result: Extract<AccessKeyTestResult, { ok: false }>,
): { key: string; vars?: Record<string, string | number> } {
  if (result.status === 0) return { key: 'accessKeys.test.network' }
  if (result.status === 401) return { key: 'accessKeys.test.unauthorized' }
  if (result.status === 403) return { key: 'accessKeys.test.forbidden' }
  if (result.status === 404) return { key: 'accessKeys.test.notAvailable' }
  if (result.status === 429) return { key: 'accessKeys.test.rateLimited' }
  return {
    key: 'accessKeys.test.generic',
    vars: { status: result.status, message: result.message },
  }
}

/** The structured error code of a failed API call, if any. */
export function apiErrorCode(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'code' in detail) {
    return String((detail as { code: unknown }).code)
  }
  return null
}

export function apiErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
