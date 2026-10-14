/**
 * Fixtures of the access-key UI tests: a scope catalog shaped like
 * GET /api/access-keys/scopes and key rows shaped like AccessKeyOut.
 */

import type { AccessKey, ScopeCatalog } from '@/lib/api/types'

const scope = (name: string, grantable = 'any', implies: string[] = []) => ({
  name,
  description_de: `DE ${name}`,
  description_en: `EN ${name}`,
  implies,
  grantable,
  source: 'platform',
})

export const SCOPE_CATALOG: ScopeCatalog = {
  scopes: [
    scope('org:read'),
    scope('projects:read'),
    scope('tasks:read'),
    scope('tasks:read_reference', 'full_data_role', ['tasks:read']),
    scope('submissions:read'),
    scope('submissions:write', 'any', ['submissions:read']),
    scope('systems:manage'),
    scope('runs:read'),
    scope('runs:write', 'any', ['runs:read']),
    scope('evaluations:read'),
    scope('evaluations:run', 'any', ['evaluations:read']),
    scope('results:read'),
    scope('exports:read'),
    scope('keys:manage', 'personal_only'),
    scope('compliance:admin', 'org_admin'),
  ],
  presets: {
    org_full: [
      'org:read',
      'projects:read',
      'tasks:read_reference',
      'submissions:write',
      'systems:manage',
      'runs:write',
      'evaluations:run',
      'results:read',
      'exports:read',
    ],
    benchmark_read: [
      'org:read',
      'projects:read',
      'tasks:read',
      'runs:read',
      'evaluations:read',
      'results:read',
    ],
    benchmark_submit: [
      'org:read',
      'projects:read',
      'tasks:read',
      'submissions:write',
      'systems:manage',
      'runs:write',
      'evaluations:run',
      'results:read',
    ],
  },
}

const DAY = 24 * 60 * 60 * 1000

export function makeKey(overrides: Partial<AccessKey> = {}): AccessKey {
  const now = Date.now()
  return {
    id: 'key-1',
    name: 'Runner',
    key_prefix: 'bgr_live_abcd1234',
    owner_type: 'org',
    user_id: 'svc-1',
    organization_id: 'org-1',
    group_id: null,
    org_role: 'ANNOTATOR',
    scopes: ['org:read', 'projects:read'],
    project_ids: null,
    environment: 'live',
    expires_at: new Date(now + 200 * DAY).toISOString(),
    revoked_at: null,
    revoked_by: null,
    revoke_reason: null,
    last_used_at: null,
    last_used_ip: null,
    rate_limit_per_minute: null,
    rate_limit_per_day: null,
    created_by: 'user-1',
    created_at: new Date(now - 165 * DAY).toISOString(),
    status: 'active',
    ...overrides,
  }
}

/** i18n mock: the key, plus the variables as JSON when there are any. */
export function mockTranslate(
  key: string,
  a?: string | Record<string, unknown>,
  b?: Record<string, unknown>,
): string {
  const vars = typeof a === 'object' ? a : b
  return vars ? `${key} ${JSON.stringify(vars)}` : key
}
