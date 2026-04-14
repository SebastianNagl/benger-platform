/**
 * Tests for OrganizationsClient
 */

import { OrganizationsClient, organizationsAPI } from '../organizations'
import type {
  InvitationCreate,
  OrganizationCreate,
  OrganizationUpdate,
} from '../types'

// Mock BaseApiClient
jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    protected async get(endpoint: string): Promise<any> {
      return this.mockRequest('GET', endpoint)
    }

    protected async post(endpoint: string, data?: any): Promise<any> {
      return this.mockRequest('POST', endpoint, data)
    }

    protected async put(endpoint: string, data?: any): Promise<any> {
      return this.mockRequest('PUT', endpoint, data)
    }

    protected async delete(endpoint: string): Promise<any> {
      return this.mockRequest('DELETE', endpoint)
    }

    private mockRequest(method: string, endpoint: string, data?: any): any {
      // Get all organizations
      if (endpoint === '/organizations' && method === 'GET') {
        return [
          {
            id: 'org-1',
            name: 'TUM',
            display_name: 'Technical University of Munich',
            slug: 'tum',
            is_active: true,
            created_at: '2024-01-01T00:00:00Z',
          },
        ]
      }

      // Create organization
      if (endpoint === '/organizations' && method === 'POST') {
        return {
          id: 'org-new',
          ...data,
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
        }
      }

      // Get specific organization
      if (endpoint.match(/^\/organizations\/org-\w+$/) && method === 'GET') {
        return {
          id: endpoint.split('/').pop(),
          name: 'Test Org',
          display_name: 'Test Organization',
          slug: 'test-org',
          is_active: true,
          created_at: '2024-01-01T00:00:00Z',
        }
      }

      // Update organization
      if (endpoint.match(/^\/organizations\/org-\w+$/) && method === 'PUT') {
        return {
          id: endpoint.split('/').pop(),
          ...data,
          updated_at: '2024-01-02T00:00:00Z',
        }
      }

      // Delete organization
      if (endpoint.match(/^\/organizations\/org-\w+$/) && method === 'DELETE') {
        return { message: 'Organization deleted successfully' }
      }

      // Get organization members
      if (
        endpoint.match(/^\/organizations\/org-\w+\/members$/) &&
        method === 'GET'
      ) {
        return [
          {
            id: 'member-1',
            user_id: 'user-1',
            organization_id: endpoint.split('/')[2],
            role: 'ORG_ADMIN',
            is_active: true,
            joined_at: '2024-01-01T00:00:00Z',
          },
        ]
      }

      // Update member role
      if (
        endpoint.match(/^\/organizations\/org-\w+\/members\/user-\w+\/role$/) &&
        method === 'PUT'
      ) {
        return { message: 'Role updated successfully' }
      }

      // Remove member
      if (
        endpoint.match(/^\/organizations\/org-\w+\/members\/user-\w+$/) &&
        method === 'DELETE'
      ) {
        return { message: 'Member removed successfully' }
      }

      // Create invitation
      if (
        endpoint.match(
          /^\/invitations\/organizations\/org-\w+\/invitations$/
        ) &&
        method === 'POST'
      ) {
        return {
          id: 'inv-new',
          organization_id: endpoint.split('/')[3],
          email: data.email,
          role: data.role,
          token: 'test-token',
          status: 'pending',
          created_at: '2024-01-01T00:00:00Z',
        }
      }

      // Get organization invitations
      if (
        endpoint.match(/^\/invitations\/organizations\/org-\w+\/invitations/) &&
        method === 'GET'
      ) {
        const includeExpired = endpoint.includes('include_expired=true')
        const invitations = [
          {
            id: 'inv-1',
            organization_id: endpoint.split('/')[3],
            email: 'user@example.com',
            role: 'ANNOTATOR',
            token: 'token-1',
            status: 'pending',
            created_at: '2024-01-01T00:00:00Z',
          },
        ]
        if (includeExpired) {
          invitations.push({
            id: 'inv-2',
            organization_id: endpoint.split('/')[3],
            email: 'expired@example.com',
            role: 'ANNOTATOR',
            token: 'token-2',
            status: 'expired',
            created_at: '2023-12-01T00:00:00Z',
          } as any)
        }
        return invitations
      }

      // Get invitation by token
      if (
        endpoint.match(/^\/invitations\/token\/[\w-]+$/) &&
        method === 'GET'
      ) {
        return {
          id: 'inv-1',
          organization_id: 'org-1',
          email: 'user@example.com',
          role: 'ANNOTATOR',
          token: endpoint.split('/').pop(),
          status: 'pending',
          created_at: '2024-01-01T00:00:00Z',
        }
      }

      // Accept invitation
      if (
        endpoint.match(/^\/invitations\/accept\/[\w-]+$/) &&
        method === 'POST'
      ) {
        return {
          message: 'Invitation accepted successfully',
          organization_id: 'org-1',
          role: 'ANNOTATOR',
        }
      }

      // Cancel invitation
      if (endpoint.match(/^\/invitations\/inv-\w+$/) && method === 'DELETE') {
        return { message: 'Invitation cancelled successfully' }
      }

      // Get all users
      if (endpoint === '/organizations/manage/users' && method === 'GET') {
        return [
          {
            id: 'user-1',
            username: 'user1',
            email: 'user1@example.com',
            name: 'User One',
            is_superadmin: false,
            is_active: true,
            created_at: '2024-01-01T00:00:00Z',
          },
        ]
      }

      // Update user global role
      if (
        endpoint.match(
          /^\/organizations\/manage\/users\/user-\w+\/superadmin$/
        ) &&
        method === 'PUT'
      ) {
        return { message: 'User role updated successfully' }
      }

      // Add user to organization
      if (
        endpoint.match(/^\/organizations\/org-\w+\/members$/) &&
        method === 'POST'
      ) {
        return { message: 'User added to organization successfully' }
      }

      // Verify member email
      if (
        endpoint.match(
          /^\/organizations\/org-\w+\/members\/user-\w+\/verify-email$/
        ) &&
        method === 'POST'
      ) {
        return {
          message: 'Email verified successfully',
          email: 'user@example.com',
          verified_by: 'admin-1',
          verification_method: 'admin',
        }
      }

      // Bulk verify emails
      if (
        endpoint.match(/^\/organizations\/org-\w+\/members\/verify-emails$/) &&
        method === 'POST'
      ) {
        return {
          summary: {
            total: data.user_ids.length,
            success: data.user_ids.length - 1,
            skipped: 1,
            errors: 0,
          },
          results: data.user_ids.map((userId: string, index: number) => ({
            user_id: userId,
            email: index === 0 ? undefined : `user${index}@example.com`,
            status: index === 0 ? 'skipped' : 'success',
            message: index === 0 ? 'Already verified' : 'Email verified',
          })),
        }
      }

      throw new Error(`Unmocked request: ${method} ${endpoint}`)
    }

    clearCache() {}
  },
}))

describe('OrganizationsClient', () => {
  let client: OrganizationsClient

  beforeEach(() => {
    client = new OrganizationsClient()
  })

  describe('getOrganizations', () => {
    it('should get all organizations', async () => {
      const result = await client.getOrganizations()

      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({
        id: 'org-1',
        name: 'TUM',
        display_name: 'Technical University of Munich',
        slug: 'tum',
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })

    it('should call correct endpoint', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getOrganizations()

      expect(getSpy).toHaveBeenCalledWith('/organizations')
    })
  })

  describe('createOrganization', () => {
    it('should create a new organization', async () => {
      const orgData: OrganizationCreate = {
        name: 'New Org',
        display_name: 'New Organization',
        slug: 'new-org',
      }

      const result = await client.createOrganization(orgData)

      expect(result).toEqual({
        id: 'org-new',
        name: 'New Org',
        display_name: 'New Organization',
        slug: 'new-org',
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })

    it('should create organization with description', async () => {
      const orgData: OrganizationCreate = {
        name: 'Test',
        display_name: 'Test Org',
        slug: 'test',
        description: 'Test description',
      }

      const result = await client.createOrganization(orgData)

      expect(result.description).toBe('Test description')
    })
  })

  describe('getOrganization', () => {
    it('should get a specific organization', async () => {
      const result = await client.getOrganization('org-1')

      expect(result.id).toBe('org-1')
      expect(result.name).toBe('Test Org')
    })
  })

  describe('updateOrganization', () => {
    it('should update organization name', async () => {
      const updates: OrganizationUpdate = {
        name: 'Updated Name',
      }

      const result = await client.updateOrganization('org-1', updates)

      expect(result.name).toBe('Updated Name')
      expect(result.updated_at).toBeDefined()
    })

    it('should update organization is_active status', async () => {
      const updates: OrganizationUpdate = {
        is_active: false,
      }

      const result = await client.updateOrganization('org-1', updates)

      expect(result.is_active).toBe(false)
    })
  })

  describe('deleteOrganization', () => {
    it('should delete an organization', async () => {
      const result = await client.deleteOrganization('org-1')

      expect(result).toEqual({ message: 'Organization deleted successfully' })
    })
  })

  describe('getOrganizationMembers', () => {
    it('should get organization members', async () => {
      const result = await client.getOrganizationMembers('org-1')

      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({
        id: 'member-1',
        user_id: 'user-1',
        organization_id: 'org-1',
        role: 'ORG_ADMIN',
        is_active: true,
        joined_at: '2024-01-01T00:00:00Z',
      })
    })
  })

  describe('updateMemberRole', () => {
    it('should update member role', async () => {
      const result = await client.updateMemberRole(
        'org-1',
        'user-1',
        'CONTRIBUTOR'
      )

      expect(result).toEqual({ message: 'Role updated successfully' })
    })

    it('should call correct endpoint', async () => {
      const putSpy = jest.spyOn(client as any, 'put')
      await client.updateMemberRole('org-1', 'user-1', 'ANNOTATOR')

      expect(putSpy).toHaveBeenCalledWith(
        '/organizations/org-1/members/user-1/role',
        { role: 'ANNOTATOR' }
      )
    })
  })

  describe('removeMember', () => {
    it('should remove member from organization', async () => {
      const result = await client.removeMember('org-1', 'user-1')

      expect(result).toEqual({ message: 'Member removed successfully' })
    })
  })

  describe('sendInvitation', () => {
    it('should send invitation (alias for createInvitation)', async () => {
      const invitationData: InvitationCreate = {
        email: 'newuser@example.com',
        role: 'ANNOTATOR',
      }

      const result = await client.sendInvitation('org-1', invitationData)

      expect(result.email).toBe('newuser@example.com')
      expect(result.role).toBe('ANNOTATOR')
    })
  })

  describe('createInvitation', () => {
    it('should create a new invitation', async () => {
      const invitationData: InvitationCreate = {
        email: 'newuser@example.com',
        role: 'CONTRIBUTOR',
      }

      const result = await client.createInvitation('org-1', invitationData)

      expect(result).toEqual({
        id: 'inv-new',
        organization_id: 'org-1',
        email: 'newuser@example.com',
        role: 'CONTRIBUTOR',
        token: 'test-token',
        status: 'pending',
        created_at: '2024-01-01T00:00:00Z',
      })
    })

    it('should call correct endpoint', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      const invitationData: InvitationCreate = {
        email: 'test@example.com',
        role: 'ANNOTATOR',
      }

      await client.createInvitation('org-1', invitationData)

      expect(postSpy).toHaveBeenCalledWith(
        '/invitations/organizations/org-1/invitations',
        invitationData
      )
    })
  })

  describe('getOrganizationInvitations', () => {
    it('should get organization invitations without expired', async () => {
      const result = await client.getOrganizationInvitations('org-1')

      expect(result).toHaveLength(1)
      expect(result[0].status).toBe('pending')
    })

    it('should get organization invitations including expired', async () => {
      const result = await client.getOrganizationInvitations('org-1', true)

      expect(result.length).toBeGreaterThan(1)
    })

    it('should call correct endpoint with includeExpired=false', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getOrganizationInvitations('org-1', false)

      expect(getSpy).toHaveBeenCalledWith(
        '/invitations/organizations/org-1/invitations'
      )
    })

    it('should call correct endpoint with includeExpired=true', async () => {
      const getSpy = jest.spyOn(client as any, 'get')
      await client.getOrganizationInvitations('org-1', true)

      expect(getSpy).toHaveBeenCalledWith(
        '/invitations/organizations/org-1/invitations?include_expired=true'
      )
    })
  })

  describe('getInvitationByToken', () => {
    it('should get invitation by token', async () => {
      const result = await client.getInvitationByToken('test-token')

      expect(result).toEqual({
        id: 'inv-1',
        organization_id: 'org-1',
        email: 'user@example.com',
        role: 'ANNOTATOR',
        token: 'test-token',
        status: 'pending',
        created_at: '2024-01-01T00:00:00Z',
      })
    })
  })

  describe('acceptInvitation', () => {
    it('should accept invitation', async () => {
      const result = await client.acceptInvitation('test-token')

      expect(result).toEqual({
        message: 'Invitation accepted successfully',
        organization_id: 'org-1',
        role: 'ANNOTATOR',
      })
    })
  })

  describe('cancelInvitation', () => {
    it('should cancel invitation', async () => {
      const result = await client.cancelInvitation('inv-1')

      expect(result).toEqual({ message: 'Invitation cancelled successfully' })
    })
  })

  describe('getAllUsers', () => {
    it('should get all users', async () => {
      const result = await client.getAllUsers()

      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({
        id: 'user-1',
        username: 'user1',
        email: 'user1@example.com',
        name: 'User One',
        is_superadmin: false,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
      })
    })
  })

  describe('updateUserGlobalRole', () => {
    it('should update user to superadmin', async () => {
      const result = await client.updateUserGlobalRole('user-1', 'superadmin')

      expect(result).toEqual({ message: 'User role updated successfully' })
    })

    it('should update user to regular user', async () => {
      const result = await client.updateUserGlobalRole('user-1', 'user')

      expect(result).toEqual({ message: 'User role updated successfully' })
    })

    it('should call correct endpoint with correct data', async () => {
      const putSpy = jest.spyOn(client as any, 'put')
      await client.updateUserGlobalRole('user-1', 'superadmin')

      expect(putSpy).toHaveBeenCalledWith(
        '/organizations/manage/users/user-1/superadmin',
        { is_superadmin: true }
      )
    })

    it('should send is_superadmin=false for regular user', async () => {
      const putSpy = jest.spyOn(client as any, 'put')
      await client.updateUserGlobalRole('user-1', 'user')

      expect(putSpy).toHaveBeenCalledWith(
        '/organizations/manage/users/user-1/superadmin',
        { is_superadmin: false }
      )
    })
  })

  describe('addUserToOrganization', () => {
    it('should add user to organization with default role', async () => {
      const result = await client.addUserToOrganization('org-1', 'user-1')

      expect(result).toEqual({
        message: 'User added to organization successfully',
      })
    })

    it('should add user with specific role', async () => {
      const result = await client.addUserToOrganization(
        'org-1',
        'user-1',
        'CONTRIBUTOR'
      )

      expect(result).toEqual({
        message: 'User added to organization successfully',
      })
    })

    it('should call correct endpoint', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      await client.addUserToOrganization('org-1', 'user-1', 'ORG_ADMIN')

      expect(postSpy).toHaveBeenCalledWith('/organizations/org-1/members', {
        user_id: 'user-1',
        role: 'ORG_ADMIN',
      })
    })
  })

  describe('verifyMemberEmail', () => {
    it('should verify member email without reason', async () => {
      const result = await client.verifyMemberEmail('org-1', 'user-1')

      expect(result).toEqual({
        message: 'Email verified successfully',
        email: 'user@example.com',
        verified_by: 'admin-1',
        verification_method: 'admin',
      })
    })

    it('should verify member email with reason', async () => {
      const result = await client.verifyMemberEmail(
        'org-1',
        'user-1',
        'Manual verification'
      )

      expect(result.message).toBe('Email verified successfully')
    })

    it('should call correct endpoint', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      await client.verifyMemberEmail('org-1', 'user-1', 'Test reason')

      expect(postSpy).toHaveBeenCalledWith(
        '/organizations/org-1/members/user-1/verify-email',
        { reason: 'Test reason' }
      )
    })
  })

  describe('bulkVerifyMemberEmails', () => {
    it('should verify multiple member emails', async () => {
      const userIds = ['user-1', 'user-2', 'user-3']
      const result = await client.bulkVerifyMemberEmails('org-1', userIds)

      expect(result.summary.total).toBe(3)
      expect(result.summary.success).toBe(2)
      expect(result.summary.skipped).toBe(1)
      expect(result.results).toHaveLength(3)
    })

    it('should verify emails with reason', async () => {
      const userIds = ['user-1', 'user-2']
      const result = await client.bulkVerifyMemberEmails(
        'org-1',
        userIds,
        'Bulk verification'
      )

      expect(result.summary.total).toBe(2)
    })

    it('should call correct endpoint', async () => {
      const postSpy = jest.spyOn(client as any, 'post')
      const userIds = ['user-1', 'user-2']

      await client.bulkVerifyMemberEmails('org-1', userIds, 'Test')

      expect(postSpy).toHaveBeenCalledWith(
        '/organizations/org-1/members/verify-emails',
        {
          user_ids: userIds,
          reason: 'Test',
        }
      )
    })

    it('should handle mixed verification results', async () => {
      const userIds = ['user-1', 'user-2', 'user-3']
      const result = await client.bulkVerifyMemberEmails('org-1', userIds)

      expect(result.results[0].status).toBe('skipped')
      expect(result.results[1].status).toBe('success')
      expect(result.results[2].status).toBe('success')
    })
  })

  describe('error handling', () => {
    it('should handle network errors', async () => {
      const getSpy = jest
        .spyOn(client as any, 'get')
        .mockRejectedValueOnce(new Error('Network error'))

      await expect(client.getOrganizations()).rejects.toThrow('Network error')
    })

    it('should handle unauthorized errors', async () => {
      const postSpy = jest
        .spyOn(client as any, 'post')
        .mockRejectedValueOnce(new Error('Unauthorized'))

      await expect(
        client.createOrganization({
          name: 'Test',
          display_name: 'Test',
          slug: 'test',
        })
      ).rejects.toThrow('Unauthorized')
    })

    it('should handle 404 errors', async () => {
      const getSpy = jest
        .spyOn(client as any, 'get')
        .mockRejectedValueOnce(new Error('Not found'))

      await expect(client.getOrganization('invalid-id')).rejects.toThrow(
        'Not found'
      )
    })
  })

  describe('organizationsAPI singleton', () => {
    it('should export a default instance', () => {
      expect(organizationsAPI).toBeDefined()
      expect(organizationsAPI).toBeInstanceOf(OrganizationsClient)
    })

    it('should have all methods available on singleton', () => {
      expect(typeof organizationsAPI.getOrganizations).toBe('function')
      expect(typeof organizationsAPI.createOrganization).toBe('function')
      expect(typeof organizationsAPI.getOrganization).toBe('function')
      expect(typeof organizationsAPI.updateOrganization).toBe('function')
      expect(typeof organizationsAPI.deleteOrganization).toBe('function')
    })
  })
})
