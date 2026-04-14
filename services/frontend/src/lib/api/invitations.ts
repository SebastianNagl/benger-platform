/**
 * API client for organization invitations
 */

import { BaseApiClient } from './base'
import { OrganizationRole } from './types'

export interface InvitationDetails {
  id: string
  organization_id: string
  email: string
  role: OrganizationRole
  token: string
  invited_by: string
  expires_at: string
  accepted_at: string | null
  is_accepted: boolean
  created_at: string
  organization_name?: string
  inviter_name?: string
}

export interface CreateInvitationRequest {
  email: string
  role: OrganizationRole
}

export class InvitationsApiClient extends BaseApiClient {
  /**
   * Get invitation details by token (public endpoint)
   */
  async getByToken(token: string): Promise<InvitationDetails> {
    const response = await this.request(`/invitations/token/${token}`, {
      method: 'GET',
    })
    return response
  }

  /**
   * Accept an invitation
   */
  async accept(
    token: string
  ): Promise<{ message: string; organization_id: string; role: string }> {
    const response = await this.request(`/invitations/accept/${token}`, {
      method: 'POST',
    })
    return response
  }

  /**
   * Create an organization invitation (org admin only)
   */
  async create(
    organizationId: string,
    invitation: CreateInvitationRequest
  ): Promise<InvitationDetails> {
    const response = await this.request(
      `/invitations/organizations/${organizationId}/invitations`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(invitation),
      }
    )
    return response
  }

  /**
   * List organization invitations (org admin only)
   */
  async list(
    organizationId: string,
    includeExpired: boolean = false
  ): Promise<InvitationDetails[]> {
    const params = new URLSearchParams()
    if (includeExpired) {
      params.append('include_expired', 'true')
    }

    const url = `/invitations/organizations/${organizationId}/invitations${params.toString() ? `?${params.toString()}` : ''}`
    const response = await this.request(url, {
      method: 'GET',
    })
    return response
  }

  /**
   * Cancel an invitation (org admin only)
   */
  async cancel(invitationId: string): Promise<{ message: string }> {
    const response = await this.request(`/invitations/${invitationId}`, {
      method: 'DELETE',
    })
    return response
  }
}
