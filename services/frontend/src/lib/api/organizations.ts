/**
 * Organizations API client
 */

import { BaseApiClient } from './base'
import type {
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
   * List all users (superadmin only)
   */
  async getAllUsers(): Promise<User[]> {
    return this.get('/organizations/manage/users')
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
   * Get API key status for all providers in an organization
   */
  async getOrgApiKeyStatus(
    orgId: string
  ): Promise<{
    api_key_status: Record<string, boolean>
    available_providers: string[]
  }> {
    return this.get(`/organizations/${orgId}/api-keys/status`)
  }

  /**
   * Set an API key for an organization provider
   */
  async setOrgApiKey(
    orgId: string,
    provider: string,
    apiKey: string
  ): Promise<{ message: string }> {
    return this.post(`/organizations/${orgId}/api-keys/${provider}`, {
      api_key: apiKey,
    })
  }

  /**
   * Remove an API key for an organization provider
   */
  async removeOrgApiKey(
    orgId: string,
    provider: string
  ): Promise<{ message: string }> {
    return this.delete(`/organizations/${orgId}/api-keys/${provider}`)
  }

  /**
   * Test an unsaved API key for an organization provider
   */
  async testOrgApiKey(
    orgId: string,
    provider: string,
    apiKey: string
  ): Promise<{ status: string; message: string; error_type?: string }> {
    return this.post(`/organizations/${orgId}/api-keys/${provider}/test`, {
      api_key: apiKey,
    })
  }

  /**
   * Test a saved API key for an organization provider
   */
  async testSavedOrgApiKey(
    orgId: string,
    provider: string
  ): Promise<{ status: string; message: string; error_type?: string }> {
    return this.post(
      `/organizations/${orgId}/api-keys/${provider}/test-saved`,
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
}

// Create and export a default instance for direct use
const organizationsAPI = new OrganizationsClient()
export { organizationsAPI }
