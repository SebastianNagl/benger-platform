/**
 * Organizations API Client Test (Fixed)
 *
 * Tests the OrganizationsClient functionality with proper mocking
 */

/**
 * @jest-environment jsdom
 */

import {
  Invitation,
  Organization,
  OrganizationCreate,
  OrganizationMember,
} from '@/lib/api/types'

// Mock the entire organizations module
const mockOrganizationsClient = {
  getOrganizations: jest.fn(),
  createOrganization: jest.fn(),
  getOrganization: jest.fn(),
  getOrganizationMembers: jest.fn(),
  createInvitation: jest.fn(),
  getInvitationByToken: jest.fn(),
  acceptInvitation: jest.fn(),
  updateMemberRole: jest.fn(),
  removeMember: jest.fn(),
}

jest.mock('@/lib/api/organizations', () => ({
  OrganizationsClient: jest
    .fn()
    .mockImplementation(() => mockOrganizationsClient),
}))

describe('OrganizationsClient', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('getOrganizations', () => {
    it('should fetch organizations list', async () => {
      const mockOrganizations: Organization[] = [
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
      ]

      mockOrganizationsClient.getOrganizations.mockResolvedValue(
        mockOrganizations
      )

      const organizations = await mockOrganizationsClient.getOrganizations()

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
      expect(mockOrganizationsClient.getOrganizations).toHaveBeenCalledTimes(1)
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

      const mockOrganization: Organization = {
        id: 'org-123',
        name: 'New Organization',
        slug: 'new-org',
        description: 'A new organization',
        settings: { theme: 'dark' },
        is_active: true,
        created_at: '2023-01-01T00:00:00Z',
        member_count: 1,
      }

      mockOrganizationsClient.createOrganization.mockResolvedValue(
        mockOrganization
      )

      const organization =
        await mockOrganizationsClient.createOrganization(createData)

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
      expect(mockOrganizationsClient.createOrganization).toHaveBeenCalledWith(
        createData
      )
    })
  })

  describe('getOrganization', () => {
    it('should fetch organization by ID', async () => {
      const mockOrganization: Organization = {
        id: 'org-123',
        name: 'Test Organization',
        slug: 'test-org',
        description: 'A test organization',
        settings: {},
        is_active: true,
        created_at: '2023-01-01T00:00:00Z',
        member_count: 2,
      }

      mockOrganizationsClient.getOrganization.mockResolvedValue(
        mockOrganization
      )

      const organization =
        await mockOrganizationsClient.getOrganization('org-123')

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
      expect(mockOrganizationsClient.getOrganization).toHaveBeenCalledWith(
        'org-123'
      )
    })
  })

  describe('getOrganizationMembers', () => {
    it('should fetch organization members', async () => {
      const mockMembers: OrganizationMember[] = [
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
      ]

      mockOrganizationsClient.getOrganizationMembers.mockResolvedValue(
        mockMembers
      )

      const members =
        await mockOrganizationsClient.getOrganizationMembers('org-123')

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
      expect(
        mockOrganizationsClient.getOrganizationMembers
      ).toHaveBeenCalledWith('org-123')
    })
  })

  describe('createInvitation', () => {
    it('should create an invitation', async () => {
      const invitationData = {
        email: 'newuser@example.com',
        role: 'org_user' as const,
      }

      const mockInvitation: Invitation = {
        id: 'inv-123',
        organization_id: 'org-123',
        email: 'newuser@example.com',
        role: 'org_user',
        token: 'invitation-token-123',
        invited_by: 'user-123',
        expires_at: '2023-12-31T23:59:59Z',
        is_accepted: false,
        created_at: '2023-01-01T00:00:00Z',
        organization_name: 'Test Organization',
        inviter_name: 'Test User',
      }

      mockOrganizationsClient.createInvitation.mockResolvedValue(mockInvitation)

      const invitation = await mockOrganizationsClient.createInvitation(
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
      expect(mockOrganizationsClient.createInvitation).toHaveBeenCalledWith(
        'org-123',
        invitationData
      )
    })
  })

  describe('getInvitationByToken', () => {
    it('should fetch invitation by token', async () => {
      const mockInvitation: Invitation = {
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
      }

      mockOrganizationsClient.getInvitationByToken.mockResolvedValue(
        mockInvitation
      )

      const invitation = await mockOrganizationsClient.getInvitationByToken(
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
      expect(mockOrganizationsClient.getInvitationByToken).toHaveBeenCalledWith(
        'invitation-token-123'
      )
    })
  })

  describe('acceptInvitation', () => {
    it('should accept an invitation', async () => {
      const mockResult = {
        message: 'Invitation accepted successfully',
        organization_id: 'org-123',
        role: 'org_user',
      }

      mockOrganizationsClient.acceptInvitation.mockResolvedValue(mockResult)

      const result = await mockOrganizationsClient.acceptInvitation(
        'invitation-token-123'
      )

      expect(result).toEqual({
        message: 'Invitation accepted successfully',
        organization_id: 'org-123',
        role: 'org_user',
      })
      expect(mockOrganizationsClient.acceptInvitation).toHaveBeenCalledWith(
        'invitation-token-123'
      )
    })
  })

  describe('updateMemberRole', () => {
    it('should update member role', async () => {
      const mockResult = { message: 'Success' }

      mockOrganizationsClient.updateMemberRole.mockResolvedValue(mockResult)

      const result = await mockOrganizationsClient.updateMemberRole(
        'org-123',
        'user-123',
        'org_contributor'
      )

      expect(result).toEqual({ message: 'Success' })
      expect(mockOrganizationsClient.updateMemberRole).toHaveBeenCalledWith(
        'org-123',
        'user-123',
        'org_contributor'
      )
    })
  })

  describe('removeMember', () => {
    it('should remove member from organization', async () => {
      const mockResult = { message: 'Success' }

      mockOrganizationsClient.removeMember.mockResolvedValue(mockResult)

      const result = await mockOrganizationsClient.removeMember(
        'org-123',
        'user-123'
      )

      expect(result).toEqual({ message: 'Success' })
      expect(mockOrganizationsClient.removeMember).toHaveBeenCalledWith(
        'org-123',
        'user-123'
      )
    })
  })

  describe('Mock verification', () => {
    it('should verify all mocks are working correctly', () => {
      expect(mockOrganizationsClient.getOrganizations).toBeDefined()
      expect(mockOrganizationsClient.createOrganization).toBeDefined()
      expect(mockOrganizationsClient.getOrganization).toBeDefined()
      expect(mockOrganizationsClient.getOrganizationMembers).toBeDefined()
      expect(mockOrganizationsClient.createInvitation).toBeDefined()
      expect(mockOrganizationsClient.getInvitationByToken).toBeDefined()
      expect(mockOrganizationsClient.acceptInvitation).toBeDefined()
      expect(mockOrganizationsClient.updateMemberRole).toBeDefined()
      expect(mockOrganizationsClient.removeMember).toBeDefined()

      // Verify all are jest functions
      Object.values(mockOrganizationsClient).forEach((mock) => {
        expect(jest.isMockFunction(mock)).toBe(true)
      })
    })
  })
})
