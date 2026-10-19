/**
 * Feature flags admin API client (`/api/feature-flags`, superadmin only).
 *
 * The per-viewer read (`/me`) lives in lib/featureFlags, which owns the store.
 */

import apiClient from '@/lib/api'

export type FeatureFlagState = 'off' | 'everyone' | 'allowlist'

export interface FeatureFlagTarget {
  id: string
  kind: 'user' | 'organization'
  user_id?: string | null
  organization_id?: string | null
  /** User: the real name; organization: its display name. */
  name?: string | null
  pseudonym?: string | null
  email?: string | null
  username?: string | null
}

export interface FeatureFlagAdminRow {
  name: string
  description: string
  /** Who registered the flag: `platform` or an extension package id. */
  owner: string
  state: FeatureFlagState
  default_state: FeatureFlagState
  updated_at: string | null
  targets: FeatureFlagTarget[]
  /** False for a stored row no loaded package registers any more. */
  registered: boolean
  /** True for a package master flag (`extension.<id>`). */
  is_master: boolean
}

export type FeatureFlagTargetCreate =
  | { user_id: string; organization_id?: never }
  | { organization_id: string; user_id?: never }

const BASE = '/feature-flags'

const path = (name: string) => `${BASE}/${encodeURIComponent(name)}`

export const featureFlagsAPI = {
  list: (): Promise<FeatureFlagAdminRow[]> => {
    ;(
      apiClient as { invalidateCache?: (pattern: string) => void }
    ).invalidateCache?.(BASE)
    return apiClient.get(BASE)
  },

  setState: (
    name: string,
    state: FeatureFlagState,
  ): Promise<FeatureFlagAdminRow> => apiClient.put(path(name), { state }),

  addTarget: (
    name: string,
    target: FeatureFlagTargetCreate,
  ): Promise<FeatureFlagTarget> =>
    apiClient.post(`${path(name)}/targets`, target),

  removeTarget: (name: string, targetId: string): Promise<void> =>
    apiClient.delete(`${path(name)}/targets/${encodeURIComponent(targetId)}`),

  /** Delete a row no package registers any more (409 for registered ones). */
  remove: (name: string): Promise<void> => apiClient.delete(path(name)),
}
