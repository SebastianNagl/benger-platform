/**
 * Organizations API client
 */

import { BaseApiClient } from './base'
import type {
  BulkInvitationCreate,
  BulkInvitationResponse,
  Invitation,
  InvitationCreate,
  Organization,
  OrganizationCreate,
  OrganizationMember,
  OrganizationRole,
  OrganizationUpdate,
  User,
} from './types'

export class OrganizationsClient extends BaseApiClient {
  /**
   * Get all organizations accessible to the current user
   */
  async getOrganizations(): Promise<Organization[]> {
    return this.get('/organizations')
  }

  /**
   * Create a new organization (superadmin only)
   */
  async createOrganization(data: OrganizationCreate): Promise<Organization> {
    return this.post('/organizations', data)
  }

  /**
   * Get organization by ID
   */
  async getOrganization(organizationId: string): Promise<Organization> {
    return this.get(`/organizations/${organizationId}`)
  }

  /**
   * Update organization
   */
  async updateOrganization(
    organizationId: string,
    data: OrganizationUpdate
  ): Promise<Organization> {
    return this.put(`/organizations/${organizationId}`, data)
  }

  /**
   * Delete organization
   */
  async deleteOrganization(
    organizationId: string
  ): Promise<{ message: string }> {
    return this.delete(`/organizations/${organizationId}`)
  }

  /**
   * Get organization members
   */
  async getOrganizationMembers(
    organizationId: string
  ): Promise<OrganizationMember[]> {
    return this.get(`/organizations/${organizationId}/members`)
  }

  /**
   * Update member role
   */
  async updateMemberRole(
    organizationId: string,
    userId: string,
    role: OrganizationRole
  ): Promise<{ message: string }> {
    return this.put(`/organizations/${organizationId}/members/${userId}/role`, {
      role,
    })
  }

  /**
   * Remove member from organization
   */
  async removeMember(
    organizationId: string,
    userId: string
  ): Promise<{ message: string }> {
    return this.delete(`/organizations/${organizationId}/members/${userId}`)
  }

  /**
   * Send invitation (alias for createInvitation for compatibility)
   */
  async sendInvitation(
    organizationId: string,
    data: InvitationCreate
  ): Promise<Invitation> {
    return this.createInvitation(organizationId, data)
  }

  /**
   * Create invitation
   */
  async createInvitation(
    organizationId: string,
    data: InvitationCreate
  ): Promise<Invitation> {
    return this.post(
      `/invitations/organizations/${organizationId}/invitations`,
      data
    )
  }

  /**
   * Send multiple invitations in one request. Each email is validated and
   * deduplicated server-side; the response reports a per-email status.
   */
  async bulkInvite(
    organizationId: string,
    data: BulkInvitationCreate
  ): Promise<BulkInvitationResponse> {
    return this.post(
      `/invitations/organizations/${organizationId}/invitations/bulk`,
      data
    )
  }

  /**
   * Get organization invitations
   */
  async getOrganizationInvitations(
    organizationId: string,
    includeExpired = false
  ): Promise<Invitation[]> {
    const params = new URLSearchParams()
    if (includeExpired) {
      params.append('include_expired', 'true')
    }

    const url = `/invitations/organizations/${organizationId}/invitations${params.toString() ? '?' + params.toString() : ''}`
    return this.get(url)
  }

  /**
   * Get invitation by token
   */
  async getInvitationByToken(token: string): Promise<Invitation> {
    return this.get(`/invitations/token/${token}`)
  }

  /**
   * Accept invitation
   */
  async acceptInvitation(
    token: string
  ): Promise<{ message: string; organization_id: string; role: string }> {
    return this.post(`/invitations/accept/${token}`)
  }

  /**
   * Cancel invitation
   */
  async cancelInvitation(invitationId: string): Promise<{ message: string }> {
    return this.delete(`/invitations/${invitationId}`)
  }

  /**
   * List all users (superadmin only). Pass `search` to push the filter to
   * the server so the admin tab doesn't have to load every user just to
   * filter in JS; the response is bounded by `limit` either way.
   */
  async getAllUsers(options?: { search?: string; limit?: number }): Promise<User[]> {
    const params = new URLSearchParams()
    if (options?.search) params.append('search', options.search)
    if (options?.limit) params.append('limit', String(options.limit))
    const qs = params.toString()
    return this.get(`/organizations/manage/users${qs ? '?' + qs : ''}`)
  }

  /**
   * Update user's superadmin status (superadmin only)
   */
  async updateUserGlobalRole(
    userId: string,
    role: 'superadmin' | 'user'
  ): Promise<{ message: string }> {
    const isSuperadmin = role === 'superadmin'
    return this.put(`/organizations/manage/users/${userId}/superadmin`, {
      is_superadmin: isSuperadmin,
    })
  }

  /**
   * Add user to organization (superadmin/org admin only)
   */
  async addUserToOrganization(
    organizationId: string,
    userId: string,
    role: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR' = 'ANNOTATOR'
  ): Promise<{ message: string }> {
    return this.post(`/organizations/${organizationId}/members`, {
      user_id: userId,
      role,
    })
  }

  /**
   * Verify email for organization member (org admin/superadmin only)
   */
  async verifyMemberEmail(
    organizationId: string,
    userId: string,
    reason?: string
  ): Promise<{
    message: string
    email: string
    verified_by: string
    verification_method: string
  }> {
    return this.post(
      `/organizations/${organizationId}/members/${userId}/verify-email`,
      { reason }
    )
  }

  // ===== Organization groups =====

  /**
   * List an organization's groups. Any active member may call; member_count
   * is null for ANNOTATOR callers.
   */
  async getGroups(organizationId: string): Promise<OrganizationGroup[]> {
    return this.get(`/organizations/${organizationId}/groups`)
  }

  /**
   * Create a group (org admin only; 409 on duplicate name)
   */
  async createGroup(
    organizationId: string,
    data: OrganizationGroupCreate
  ): Promise<OrganizationGroup> {
    return this.post(`/organizations/${organizationId}/groups`, data)
  }

  /**
   * Update a group's name / description / active flag (org admin only)
   */
  async updateGroup(
    organizationId: string,
    groupId: string,
    patch: OrganizationGroupUpdate
  ): Promise<OrganizationGroup> {
    return this.patch(`/organizations/${organizationId}/groups/${groupId}`, patch)
  }

  /**
   * Delete a group (org admin only). Responds 409 with a detail message when
   * project attachments or group-scoped API keys still reference the group.
   */
  async deleteGroup(
    organizationId: string,
    groupId: string
  ): Promise<{ message: string }> {
    return this.delete(`/organizations/${organizationId}/groups/${groupId}`)
  }

  /**
   * List a group's members (org admin or that group's admin)
   */
  async getGroupMembers(
    organizationId: string,
    groupId: string
  ): Promise<OrganizationGroupMember[]> {
    return this.get(`/organizations/${organizationId}/groups/${groupId}/members`)
  }

  /**
   * Add an existing org member to a group (upserts; org admin or group admin)
   */
  async addGroupMember(
    organizationId: string,
    groupId: string,
    data: { user_id: string; is_group_admin: boolean }
  ): Promise<OrganizationGroupMember> {
    return this.post(
      `/organizations/${organizationId}/groups/${groupId}/members`,
      data
    )
  }

  /**
   * Toggle a group member's group-admin flag
   */
  async updateGroupMember(
    organizationId: string,
    groupId: string,
    userId: string,
    data: { is_group_admin: boolean }
  ): Promise<OrganizationGroupMember> {
    return this.patch(
      `/organizations/${organizationId}/groups/${groupId}/members/${userId}`,
      data
    )
  }

  /**
   * Remove a member from a group (org membership is untouched)
   */
  async removeGroupMember(
    organizationId: string,
    groupId: string,
    userId: string
  ): Promise<{ message: string }> {
    return this.delete(
      `/organizations/${organizationId}/groups/${groupId}/members/${userId}`
    )
  }

  /**
   * Bulk verify emails for organization members (org admin/superadmin only)
   */
  async bulkVerifyMemberEmails(
    organizationId: string,
    userIds: string[],
    reason?: string
  ): Promise<{
    summary: {
      total: number
      success: number
      skipped: number
      errors: number
    }
    results: Array<{
      user_id: string
      email?: string
      status: 'success' | 'skipped' | 'error'
      message: string
    }>
  }> {
    return this.post(`/organizations/${organizationId}/members/verify-emails`, {
      user_ids: userIds,
      reason,
    })
  }
  // ===== Organization API Keys (Issue #1180) =====

  /**
   * Scope suffix for the org api-key endpoints: absent groupId = the
   * org-wide key pool, set = that group's keys (group projects fall back to
   * the org-wide pool when no group key exists).
   */
  private groupScopeQuery(groupId?: string): string {
    return groupId ? `?group_id=${encodeURIComponent(groupId)}` : ''
  }

  /**
   * Get API key status for all providers in an organization
   */
  async getOrgApiKeyStatus(
    orgId: string,
    groupId?: string
  ): Promise<{
    api_key_status: Record<string, boolean>
    available_providers: string[]
  }> {
    return this.get(
      `/organizations/${orgId}/api-keys/status${this.groupScopeQuery(groupId)}`
    )
  }

  /**
   * Set an API key for an organization provider
   */
  async setOrgApiKey(
    orgId: string,
    provider: string,
    apiKey: string,
    groupId?: string
  ): Promise<{ message: string }> {
    return this.post(
      `/organizations/${orgId}/api-keys/${provider}${this.groupScopeQuery(groupId)}`,
      {
        api_key: apiKey,
      }
    )
  }

  /**
   * Remove an API key for an organization provider
   */
  async removeOrgApiKey(
    orgId: string,
    provider: string,
    groupId?: string
  ): Promise<{ message: string }> {
    return this.delete(
      `/organizations/${orgId}/api-keys/${provider}${this.groupScopeQuery(groupId)}`
    )
  }

  /**
   * Test an unsaved API key for an organization provider
   */
  async testOrgApiKey(
    orgId: string,
    provider: string,
    apiKey: string,
    groupId?: string
  ): Promise<{ status: string; message: string; error_type?: string }> {
    return this.post(
      `/organizations/${orgId}/api-keys/${provider}/test${this.groupScopeQuery(groupId)}`,
      {
        api_key: apiKey,
      }
    )
  }

  /**
   * Test a saved API key for an organization provider
   */
  async testSavedOrgApiKey(
    orgId: string,
    provider: string,
    groupId?: string
  ): Promise<{ status: string; message: string; error_type?: string }> {
    return this.post(
      `/organizations/${orgId}/api-keys/${provider}/test-saved${this.groupScopeQuery(groupId)}`,
      {}
    )
  }

  /**
   * Get API key settings for an organization
   */
  async getOrgApiKeySettings(
    orgId: string
  ): Promise<{ require_private_keys: boolean }> {
    return this.get(`/organizations/${orgId}/api-keys/settings`)
  }

  /**
   * Update API key settings for an organization
   */
  async updateOrgApiKeySettings(
    orgId: string,
    requirePrivateKeys: boolean
  ): Promise<{ message: string; require_private_keys: boolean }> {
    return this.put(`/organizations/${orgId}/api-keys/settings`, {
      require_private_keys: requirePrivateKeys,
    })
  }

  // ===== Org-owned (shared) custom-model credentials =====

  /**
   * List custom (BYOM) models shared with the org, annotated with whether a
   * shared key is set. Admin-only. Never returns key material.
   */
  async listOrgCustomModels(
    orgId: string
  ): Promise<OrgSharedCustomModel[]> {
    return this.get(`/organizations/${orgId}/custom-models`)
  }

  /**
   * Whether the org has a shared key for a custom model (never the key).
   */
  async getOrgCustomModelCredential(
    orgId: string,
    modelId: string
  ): Promise<{ has_credential: boolean; updated_at?: string | null }> {
    return this.get(
      `/organizations/${orgId}/custom-models/${modelId}/credential`
    )
  }

  /**
   * Set (or replace) the org's shared key for a custom model.
   */
  async setOrgCustomModelCredential(
    orgId: string,
    modelId: string,
    apiKey: string
  ): Promise<{ has_credential: boolean }> {
    return this.put(
      `/organizations/${orgId}/custom-models/${modelId}/credential`,
      { api_key: apiKey }
    )
  }

  /**
   * Remove the org's shared key for a custom model.
   */
  async removeOrgCustomModelCredential(
    orgId: string,
    modelId: string
  ): Promise<{ has_credential: boolean }> {
    return this.delete(
      `/organizations/${orgId}/custom-models/${modelId}/credential`
    )
  }

  // ===== Org S3 storage connections (cloud imports) =====

  /**
   * List the org's storage connections (metadata only — credentials never
   * leave the server; the access key surfaces as a last-4 hint). Any member.
   */
  async listStorageConnections(
    orgId: string
  ): Promise<OrgStorageConnection[]> {
    return this.get(`/organizations/${orgId}/storage-connections`)
  }

  /**
   * Create a storage connection. Admin only.
   */
  async createStorageConnection(
    orgId: string,
    data: OrgStorageConnectionCreate
  ): Promise<OrgStorageConnection> {
    return this.post(`/organizations/${orgId}/storage-connections`, data)
  }

  /**
   * Update a storage connection. Admin only. Omitted credential fields keep
   * the stored values; `endpoint_url: null` resets to the AWS default.
   */
  async updateStorageConnection(
    orgId: string,
    connectionId: string,
    data: OrgStorageConnectionUpdate
  ): Promise<OrgStorageConnection> {
    return this.put(
      `/organizations/${orgId}/storage-connections/${connectionId}`,
      data
    )
  }

  /**
   * Delete a storage connection. Admin only.
   */
  async deleteStorageConnection(
    orgId: string,
    connectionId: string
  ): Promise<{ message: string }> {
    return this.delete(
      `/organizations/${orgId}/storage-connections/${connectionId}`
    )
  }

  /**
   * Test unsaved connection params (pre-save "Test connection"). Admin only.
   */
  async testStorageConnection(
    orgId: string,
    data: OrgStorageConnectionCreate
  ): Promise<{ status: string; message: string }> {
    return this.post(`/organizations/${orgId}/storage-connections/test`, data)
  }

  /**
   * Test a saved connection with its stored credentials. Admin only.
   */
  async testSavedStorageConnection(
    orgId: string,
    connectionId: string
  ): Promise<{ status: string; message: string }> {
    return this.post(
      `/organizations/${orgId}/storage-connections/${connectionId}/test`,
      {}
    )
  }

  /**
   * Browse one listing page of the connected bucket (server-side; the
   * browser never talks to the customer bucket). Any org member.
   */
  async listStorageConnectionObjects(
    orgId: string,
    connectionId: string,
    options?: {
      prefix?: string
      continuationToken?: string
      maxResults?: number
    }
  ): Promise<OrgStorageObjectPage> {
    const params = new URLSearchParams()
    if (options?.prefix !== undefined) params.append('prefix', options.prefix)
    if (options?.continuationToken)
      params.append('continuation_token', options.continuationToken)
    if (options?.maxResults)
      params.append('max_results', String(options.maxResults))
    const qs = params.toString()
    return this.get(
      `/organizations/${orgId}/storage-connections/${connectionId}/objects${qs ? '?' + qs : ''}`
    )
  }
}

/** An org-level S3 storage connection (metadata view; secrets never leave the server). */
export interface OrgStorageConnection {
  id: string
  organization_id: string
  name: string
  endpoint_url: string | null
  bucket: string
  prefix: string
  region: string | null
  use_ssl: boolean
  /** Last 4 chars of the access key id (display only). */
  access_key_hint: string | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

export interface OrgStorageConnectionCreate {
  name: string
  endpoint_url?: string | null
  bucket: string
  prefix?: string
  region?: string | null
  use_ssl?: boolean
  access_key: string
  secret_key: string
}

/** Update body — credential fields optional (omitted keeps stored values). */
export interface OrgStorageConnectionUpdate {
  name?: string
  endpoint_url?: string | null
  bucket?: string
  prefix?: string
  region?: string | null
  use_ssl?: boolean
  access_key?: string
  secret_key?: string
}

/** One listed object in a storage connection's bucket. */
export interface OrgStorageObject {
  key: string
  size: number | null
  last_modified: string | null
}

/** One page of a server-side bucket listing (Delimiter '/'). */
export interface OrgStorageObjectPage {
  objects: OrgStorageObject[]
  prefixes: string[]
  next_token: string | null
}

/**
 * An organization group (e.g. a university chair). `member_count` is null
 * for ANNOTATOR callers; `is_member` / `is_group_admin` are caller-relative.
 */
export interface OrganizationGroup {
  id: string
  organization_id: string
  name: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
  member_count: number | null
  is_member: boolean
  is_group_admin: boolean
}

export interface OrganizationGroupCreate {
  name: string
  description?: string
}

export interface OrganizationGroupUpdate {
  name?: string
  description?: string
  is_active?: boolean
}

/** A member row of one organization group. */
export interface OrganizationGroupMember {
  id: string
  group_id: string
  user_id: string
  is_group_admin: boolean
  created_at: string
  user_name: string
  user_email: string
  org_role: OrganizationRole
}

/** A custom model shared with an org + its shared-credential status. */
export interface OrgSharedCustomModel {
  id: string
  name: string
  description?: string | null
  provider: string
  base_url?: string | null
  endpoint_model_name?: string | null
  requires_api_key: boolean
  has_org_credential: boolean
}

// Create and export a default instance for direct use
const organizationsAPI = new OrganizationsClient()
export { organizationsAPI }
