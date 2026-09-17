/**
 * API client for organization invitations
 */

import { BaseApiClient } from './base'
import { OrganizationRole } from './types'

/**
 * Delivery state of the invitation mail, derived server-side.
 *
 * - sent: the mail provider accepted the message.
 * - failed: the last queue or send attempt ended in an error.
 * - queued: attempted or queued, no confirmation and no error yet.
 * - unknown: nothing recorded. Invitations created before the bookkeeping
 *   existed read as unknown, which is not the same as failed.
 */
export type InvitationEmailStatus = 'sent' | 'failed' | 'queued' | 'unknown'

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
  // Group-scoped invitations (organization groups)
  group_id?: string | null
  invited_as_group_admin?: boolean
  // Mail-delivery bookkeeping. Only the admin list endpoint returns these,
  // so they stay optional for the by-token and create shapes.
  email_status?: InvitationEmailStatus
  email_sent_at?: string | null
  email_last_attempt_at?: string | null
  email_attempts?: number
  email_last_error?: string | null
}

export interface ResendInvitationResult {
  message: string
  invitation_id: string
  email: string
  email_status: InvitationEmailStatus
  email_attempts: number
  email_last_attempt_at: string | null
}

export interface CreateInvitationRequest {
  email: string
  role: OrganizationRole
  group_id?: string | null
  invited_as_group_admin?: boolean
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
    token: string,
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
    invitation: CreateInvitationRequest,
  ): Promise<InvitationDetails> {
    const response = await this.request(
      `/invitations/organizations/${organizationId}/invitations`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(invitation),
      },
    )
    return response
  }

  /**
   * List organization invitations (org admin only)
   */
  async list(
    organizationId: string,
    includeExpired: boolean = false,
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
   * Re-queue the invitation mail for a pending invitation (org admin, or the
   * inviter). Reuses the existing token, so a link already in flight keeps
   * working. The server refuses a resend within a minute of the last attempt.
   */
  async resend(invitationId: string): Promise<ResendInvitationResult> {
    const response = await this.request(`/invitations/${invitationId}/resend`, {
      method: 'POST',
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
