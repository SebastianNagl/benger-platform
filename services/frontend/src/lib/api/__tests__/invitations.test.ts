/**
 * Tests for the InvitationsApiClient
 */

import { InvitationsApiClient } from '../invitations'
import { OrganizationRole } from '../types'

// Mock the BaseApiClient
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async request<T>(url: string, options?: RequestInit): Promise<T> {
      // Mock implementation based on URL and method

      // Get invitation by token
      if (url === '/invitations/token/test-token-123') {
        return {
          id: 'inv-123',
          organization_id: 'org-123',
          email: 'test@example.com',
          role: 'org_user' as OrganizationRole,
          token: 'test-token-123',
          invited_by: 'user-123',
          expires_at: '2024-12-31T23:59:59Z',
          accepted_at: null,
          is_accepted: false,
          created_at: '2024-01-01T00:00:00Z',
          organization_name: 'Test Organization',
          inviter_name: 'John Doe',
        } as T
      }

      // Accept invitation
      if (
        url === '/invitations/accept/test-token-123' &&
        options?.method === 'POST'
      ) {
        return {
          message: 'Invitation accepted successfully',
          organization_id: 'org-123',
          role: 'org_user',
        } as T
      }

      // Create invitation
      if (
        url === '/invitations/organizations/org-123/invitations' &&
        options?.method === 'POST'
      ) {
        const body = JSON.parse(options.body as string)
        return {
          id: 'inv-456',
          organization_id: 'org-123',
          email: body.email,
          role: body.role,
          token: 'new-token-456',
          invited_by: 'user-123',
          expires_at: '2024-12-31T23:59:59Z',
          accepted_at: null,
          is_accepted: false,
          created_at: '2024-01-01T00:00:00Z',
          organization_name: 'Test Organization',
          inviter_name: 'John Doe',
        } as T
      }

      // List invitations
      if (url.startsWith('/invitations/organizations/org-123/invitations')) {
        return [
          {
            id: 'inv-123',
            organization_id: 'org-123',
            email: 'test1@example.com',
            role: 'org_user' as OrganizationRole,
            token: 'token-123',
            invited_by: 'user-123',
            expires_at: '2024-12-31T23:59:59Z',
            accepted_at: null,
            is_accepted: false,
            created_at: '2024-01-01T00:00:00Z',
          },
          {
            id: 'inv-456',
            organization_id: 'org-123',
            email: 'test2@example.com',
            role: 'org_admin' as OrganizationRole,
            token: 'token-456',
            invited_by: 'user-123',
            expires_at: '2024-12-31T23:59:59Z',
            accepted_at: '2024-01-02T00:00:00Z',
            is_accepted: true,
            created_at: '2024-01-01T00:00:00Z',
          },
        ] as T
      }

      // Cancel invitation
      if (url === '/invitations/inv-123' && options?.method === 'DELETE') {
        return { message: 'Invitation cancelled successfully' } as T
      }

      throw new Error(`Unmocked request: ${options?.method || 'GET'} ${url}`)
    }
  },
}))

describe('InvitationsApiClient', () => {
  let client: InvitationsApiClient

  beforeEach(() => {
    client = new InvitationsApiClient()
  })

  describe('getByToken', () => {
    it('should fetch invitation details by token', async () => {
      const invitation = await client.getByToken('test-token-123')

      expect(invitation).toEqual({
        id: 'inv-123',
        organization_id: 'org-123',
        email: 'test@example.com',
        role: 'org_user',
        token: 'test-token-123',
        invited_by: 'user-123',
        expires_at: '2024-12-31T23:59:59Z',
        accepted_at: null,
        is_accepted: false,
        created_at: '2024-01-01T00:00:00Z',
        organization_name: 'Test Organization',
        inviter_name: 'John Doe',
      })
    })
  })

  describe('accept', () => {
    it('should accept an invitation', async () => {
      const result = await client.accept('test-token-123')

      expect(result).toEqual({
        message: 'Invitation accepted successfully',
        organization_id: 'org-123',
        role: 'org_user',
      })
    })
  })

  describe('create', () => {
    it('should create a new invitation', async () => {
      const newInvitation = {
        email: 'newuser@example.com',
        role: 'org_contributor' as OrganizationRole,
      }

      const invitation = await client.create('org-123', newInvitation)

      expect(invitation).toEqual({
        id: 'inv-456',
        organization_id: 'org-123',
        email: 'newuser@example.com',
        role: 'org_contributor',
        token: 'new-token-456',
        invited_by: 'user-123',
        expires_at: '2024-12-31T23:59:59Z',
        accepted_at: null,
        is_accepted: false,
        created_at: '2024-01-01T00:00:00Z',
        organization_name: 'Test Organization',
        inviter_name: 'John Doe',
      })
    })
  })

  describe('list', () => {
    it('should list organization invitations', async () => {
      const invitations = await client.list('org-123')

      expect(invitations).toHaveLength(2)
      expect(invitations[0].email).toBe('test1@example.com')
      expect(invitations[1].email).toBe('test2@example.com')
    })

    it('should support includeExpired parameter', async () => {
      const invitations = await client.list('org-123', true)

      expect(invitations).toHaveLength(2)
    })
  })

  describe('cancel', () => {
    it('should cancel an invitation', async () => {
      const result = await client.cancel('inv-123')

      expect(result).toEqual({
        message: 'Invitation cancelled successfully',
      })
    })
  })
})
