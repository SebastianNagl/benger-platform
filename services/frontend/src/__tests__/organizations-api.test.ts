/**
 * @jest-environment jsdom
 */

import { OrganizationsClient } from '@/lib/api/organizations'
import { OrganizationCreate } from '@/lib/api/types'

// Mock the BaseApiClient
jest.mock('@/lib/api/base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async request<T>(url: string, options?: RequestInit): Promise<T> {
      // Mock implementation that returns appropriate test data based on URL
      if (url === '/organizations') {
        if (options?.method === 'POST') {
          const body = JSON.parse(options.body as string) as OrganizationCreate
          return {
            id: 'org-123',
            name: body.name,
            slug: body.slug,
            description: body.description,
            settings: body.settings || {},
            is_active: true,
            created_at: '2023-01-01T00:00:00Z',
            member_count: 1,
          } as T
        }

        return [
          {
            id: 'org-123',
            name: 'Test Organization',
            slug: 'test-org',
            description: 'A test organization',
            settings: {},
            is_active: true,
            created_at: '2023-01-01T00:00:00Z',
            member_count: 2,
          },
        ] as T
      }

      if (url === '/organizations/org-123') {
        return {
          id: 'org-123',
          name: 'Test Organization',
          slug: 'test-org',
          description: 'A test organization',
          settings: {},
          is_active: true,
          created_at: '2023-01-01T00:00:00Z',
          member_count: 2,
        } as T
      }

      if (url === '/organizations/org-123/members') {
        return [
          {
            id: 'member-123',
            user_id: 'user-123',
            organization_id: 'org-123',
            role: 'org_admin',
            is_active: true,
            joined_at: '2023-01-01T00:00:00Z',
            user_name: 'Test User',
            user_email: 'test@example.com',
          },
        ] as T
      }

      if (url.includes('/invitations/organizations/org-123/invitations')) {
        if (options?.method === 'POST') {
          const body = JSON.parse(options.body as string)
          return {
            id: 'inv-123',
            organization_id: 'org-123',
            email: body.email,
            role: body.role,
            token: 'invitation-token-123',
            invited_by: 'user-123',
            expires_at: '2023-12-31T23:59:59Z',
            is_accepted: false,
            created_at: '2023-01-01T00:00:00Z',
            organization_name: 'Test Organization',
            inviter_name: 'Test User',
          } as T
        }

        return [] as T
      }

      if (url === '/invitations/token/invitation-token-123') {
        return {
          id: 'inv-123',
          organization_id: 'org-123',
          email: 'invited@example.com',
          role: 'org_user',
          token: 'invitation-token-123',
          invited_by: 'user-123',
          expires_at: '2023-12-31T23:59:59Z',
          is_accepted: false,
          created_at: '2023-01-01T00:00:00Z',
          organization_name: 'Test Organization',
          inviter_name: 'Test User',
        } as T
      }

      if (url === '/invitations/accept/invitation-token-123') {
        return {
          message: 'Invitation accepted successfully',
          organization_id: 'org-123',
          role: 'org_user',
        } as T
      }

      // Default return for other URLs
      return { message: 'Success' } as T
    }

    // Add HTTP convenience methods that call request
    async get<T>(url: string, options?: RequestInit): Promise<T> {
      return this.request<T>(url, { ...options, method: 'GET' })
    }

    async post<T>(url: string, data?: any, options?: RequestInit): Promise<T> {
      return this.request<T>(url, {
        ...options,
        method: 'POST',
        body: data ? JSON.stringify(data) : undefined,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      })
    }

    async put<T>(url: string, data?: any, options?: RequestInit): Promise<T> {
      return this.request<T>(url, {
        ...options,
        method: 'PUT',
        body: data ? JSON.stringify(data) : undefined,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      })
    }

    async patch<T>(url: string, data?: any, options?: RequestInit): Promise<T> {
      return this.request<T>(url, {
        ...options,
        method: 'PATCH',
        body: data ? JSON.stringify(data) : undefined,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      })
    }

    async delete<T>(url: string, options?: RequestInit): Promise<T> {
      return this.request<T>(url, { ...options, method: 'DELETE' })
    }
  },
}))

describe('OrganizationsClient', () => {
  let client: OrganizationsClient

  beforeEach(() => {
    client = new OrganizationsClient()
  })

  describe('getOrganizations', () => {
    it('should fetch organizations list', async () => {
      const organizations = await client.getOrganizations()

      expect(organizations).toHaveLength(1)
      expect(organizations[0]).toEqual({
        id: 'org-123',
        name: 'Test Organization',
        slug: 'test-org',
        description: 'A test organization',
        settings: {},
        is_active: true,
        created_at: '2023-01-01T00:00:00Z',
        member_count: 2,
      })
    })
  })

  describe('createOrganization', () => {
    it('should create a new organization', async () => {
      const createData: OrganizationCreate = {
        name: 'New Organization',
        slug: 'new-org',
        description: 'A new organization',
        settings: { theme: 'dark' },
      }

      const organization = await client.createOrganization(createData)

      expect(organization).toEqual({
        id: 'org-123',
        name: 'New Organization',
        slug: 'new-org',
        description: 'A new organization',
        settings: { theme: 'dark' },
        is_active: true,
        created_at: '2023-01-01T00:00:00Z',
        member_count: 1,
      })
    })
  })

  describe('getOrganization', () => {
    it('should fetch organization by ID', async () => {
      const organization = await client.getOrganization('org-123')

      expect(organization).toEqual({
        id: 'org-123',
        name: 'Test Organization',
        slug: 'test-org',
        description: 'A test organization',
        settings: {},
        is_active: true,
        created_at: '2023-01-01T00:00:00Z',
        member_count: 2,
      })
    })
  })

  describe('getOrganizationMembers', () => {
    it('should fetch organization members', async () => {
      const members = await client.getOrganizationMembers('org-123')

      expect(members).toHaveLength(1)
      expect(members[0]).toEqual({
        id: 'member-123',
        user_id: 'user-123',
        organization_id: 'org-123',
        role: 'org_admin',
        is_active: true,
        joined_at: '2023-01-01T00:00:00Z',
        user_name: 'Test User',
        user_email: 'test@example.com',
      })
    })
  })

  describe('createInvitation', () => {
    it('should create an invitation', async () => {
      const invitationData = {
        email: 'newuser@example.com',
        role: 'org_user' as const,
      }

      const invitation = await client.createInvitation(
        'org-123',
        invitationData
      )

      expect(invitation).toMatchObject({
        id: 'inv-123',
        organization_id: 'org-123',
        email: 'newuser@example.com',
        role: 'org_user',
        token: 'invitation-token-123',
        is_accepted: false,
        organization_name: 'Test Organization',
        inviter_name: 'Test User',
      })
    })
  })

  describe('getInvitationByToken', () => {
    it('should fetch invitation by token', async () => {
      const invitation = await client.getInvitationByToken(
        'invitation-token-123'
      )

      expect(invitation).toMatchObject({
        id: 'inv-123',
        organization_id: 'org-123',
        email: 'invited@example.com',
        role: 'org_user',
        token: 'invitation-token-123',
        is_accepted: false,
        organization_name: 'Test Organization',
        inviter_name: 'Test User',
      })
    })
  })

  describe('acceptInvitation', () => {
    it('should accept an invitation', async () => {
      const result = await client.acceptInvitation('invitation-token-123')

      expect(result).toEqual({
        message: 'Invitation accepted successfully',
        organization_id: 'org-123',
        role: 'org_user',
      })
    })
  })

  describe('updateMemberRole', () => {
    it('should update member role', async () => {
      const result = await client.updateMemberRole(
        'org-123',
        'user-123',
        'org_contributor'
      )

      expect(result).toEqual({ message: 'Success' })
    })
  })

  describe('removeMember', () => {
    it('should remove member from organization', async () => {
      const result = await client.removeMember('org-123', 'user-123')

      expect(result).toEqual({ message: 'Success' })
    })
  })
})
