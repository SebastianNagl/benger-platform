/**
 * Project share links + participants — generic CRUD client for the platform
 * share endpoints (`routers/projects/shares.py`). A share link is a
 * password-protected invitation to a project; joiners become participants
 * (consented `ProjectShareMember` rows). Used by the expert project page and
 * the extended student surface alike.
 */

import apiClient from '@/lib/api'

export interface ShareLink {
  id: string
  token: string
  project_id: string
  expires_at: string | null
  max_uses: number | null
  revoked_at: string | null
  is_listed: boolean
  created_at: string
}

export interface ShareCreateRequest {
  password: string
  expires_at?: string | null
  max_uses?: number | null
  /** Opt in to the student discovery directory (student-created kinds only). */
  is_listed?: boolean
}

export interface ShareUpdateRequest {
  password?: string
  expires_at?: string | null
  max_uses?: number | null
  is_listed?: boolean
}

export interface RosterEntry {
  user_id: string
  display_name: string
  attempts: number
  best_score: number | null
  last_score: number | null
  joined_at: string | null
}

const asList = <T,>(res: unknown): T[] =>
  Array.isArray(res) ? (res as T[]) : ((res as { items?: T[] } | null)?.items ?? [])

export interface Participation {
  tier: 'full' | 'participant'
  via: 'share' | 'entitlement' | 'org_exam' | null
  can_leave: boolean
  cannot_leave_reason: 'entitlement_not_leavable' | 'org_membership' | null
  share_tokens: string[]
  entitlement_source: string | null
}

export interface DiscoverShareItem {
  token: string
  project_id: string
  title: string
  kind: string | null
  owner_name: string | null
  already_member: boolean
  origin?: string | null
  is_org_project?: boolean
}

export const sharesAPI = {
  /** Every share link of the project, including revoked ones. */
  listShares: async (projectId: string): Promise<ShareLink[]> =>
    asList<ShareLink>(await apiClient.get(`/projects/${projectId}/shares`)),

  createShare: async (projectId: string, body: ShareCreateRequest): Promise<ShareLink> =>
    apiClient.post(`/projects/${projectId}/shares`, body),

  /** Rotate the password / adjust expiry, cap or listing — the token stays. */
  updateShare: async (
    projectId: string,
    shareId: string,
    body: ShareUpdateRequest,
  ): Promise<ShareLink> => apiClient.put(`/projects/${projectId}/shares/${shareId}`, body),

  /** Revoke: blocks further joins; existing participants keep access. */
  revokeShare: async (projectId: string, shareId: string): Promise<void> => {
    await apiClient.delete(`/projects/${projectId}/shares/${shareId}`)
  },

  getRoster: async (projectId: string): Promise<RosterEntry[]> =>
    asList<RosterEntry>(await apiClient.get(`/projects/${projectId}/shares/roster`)),

  /** Remove a participant (their membership row); attempts are kept. */
  evictMember: async (projectId: string, userId: string): Promise<void> => {
    await apiClient.delete(`/projects/${projectId}/shares/roster/${userId}`)
  },

  /** The caller's own standing on a project (tier, how reached, leavable?). */
  getParticipation: async (projectId: string): Promise<Participation> => {
    apiClient.invalidateCache(`/projects/${projectId}/participation`)
    return apiClient.get(`/projects/${projectId}/participation`)
  },

  /** Leave a project joined via share link / discovery enrollment. */
  leaveProject: async (projectId: string): Promise<void> => {
    await apiClient.delete(`/projects/${projectId}/participation`)
    apiClient.invalidateCache('/projects')
  },

  /** Listed share links. scope 'all' = every kind (benger Entdecken). */
  discover: async (scope: 'student' | 'all' = 'student'): Promise<DiscoverShareItem[]> =>
    asList<DiscoverShareItem>(
      await apiClient.get(scope === 'all' ? '/shares/discover?scope=all' : '/shares/discover'),
    ),
}

export default sharesAPI
