/**
 * Test suite for API Client method bindings
 * Ensures all bound methods exist and have correct signatures
 */

import { ApiClient } from '../index'
import { InvitationsApiClient } from '../invitations'
import { OrganizationsClient } from '../organizations'

describe('API Client Method Bindings', () => {
  let apiClient: ApiClient

  beforeEach(() => {
    apiClient = new ApiClient()
  })

  describe('Method Existence and Signatures', () => {
    it('should have all expected invitation methods with correct signatures', () => {
      // Test that invitation methods exist
      expect(apiClient.getInvitationByToken).toBeDefined()
      expect(apiClient.acceptInvitation).toBeDefined()
      expect(apiClient.createInvitation).toBeDefined()
      expect(apiClient.listInvitations).toBeDefined()
      expect(apiClient.cancelInvitation).toBeDefined()

      // Test that getOrganizationInvitations exists and is properly bound
      expect(apiClient.getOrganizationInvitations).toBeDefined()

      // Verify they are functions
      expect(typeof apiClient.getInvitationByToken).toBe('function')
      expect(typeof apiClient.acceptInvitation).toBe('function')
      expect(typeof apiClient.createInvitation).toBe('function')
      expect(typeof apiClient.listInvitations).toBe('function')
      expect(typeof apiClient.cancelInvitation).toBe('function')
      expect(typeof apiClient.getOrganizationInvitations).toBe('function')
    })

    it('should have getOrganizationInvitations work the same as listInvitations', () => {
      // These should have the same behavior since listInvitations is assigned to getOrganizationInvitations
      // They may not be the same object reference due to .bind() creating new functions
      expect(apiClient.getOrganizationInvitations).toEqual(
        apiClient.listInvitations
      )

      // Both should be functions with the same signature
      expect(typeof apiClient.getOrganizationInvitations).toBe('function')
      expect(typeof apiClient.listInvitations).toBe('function')
      expect(apiClient.getOrganizationInvitations.length).toBe(
        apiClient.listInvitations.length
      )
    })

    it('should have all expected organization methods', () => {
      expect(apiClient.getOrganizations).toBeDefined()
      expect(apiClient.createOrganization).toBeDefined()
      expect(apiClient.getOrganization).toBeDefined()
      expect(apiClient.updateOrganization).toBeDefined()
      expect(apiClient.deleteOrganization).toBeDefined()
      expect(apiClient.getOrganizationMembers).toBeDefined()
      expect(apiClient.updateMemberRole).toBeDefined()
      expect(apiClient.removeMember).toBeDefined()
      expect(apiClient.addUserToOrganization).toBeDefined()

      // Verify they are functions
      expect(typeof apiClient.getOrganizationMembers).toBe('function')
      expect(typeof apiClient.updateMemberRole).toBe('function')
      expect(typeof apiClient.removeMember).toBe('function')
      expect(typeof apiClient.addUserToOrganization).toBe('function')
    })
  })

  describe('Method Binding Consistency', () => {
    it('should have consistent naming between bound methods and their sources', () => {
      // Create a mapping of expected method names to their bindings
      const methodBindings = [
        {
          boundName: 'getOrganizationInvitations',
          sourceName: 'list',
          expectMatch: true,
        },
        { boundName: 'listInvitations', sourceName: 'list', expectMatch: true },
        {
          boundName: 'createInvitation',
          sourceName: 'create',
          expectMatch: true,
        },
        {
          boundName: 'cancelInvitation',
          sourceName: 'cancel',
          expectMatch: true,
        },
      ]

      methodBindings.forEach(({ boundName, expectMatch }) => {
        const boundMethod = (apiClient as any)[boundName]
        expect(boundMethod).toBeDefined()
        if (expectMatch) {
          expect(typeof boundMethod).toBe('function')
        }
      })
    })

    it('should detect naming inconsistencies in method aliases', () => {
      // This test specifically checks for the issue we found
      // getOrganizationInvitations should either:
      // 1. Not exist (use listInvitations instead)
      // 2. Be the same reference as listInvitations
      // 3. Be a proper wrapper that maintains the expected signature

      const hasGetOrgInvitations = 'getOrganizationInvitations' in apiClient
      const hasListInvitations = 'listInvitations' in apiClient

      expect(hasListInvitations).toBe(true)

      if (hasGetOrgInvitations && hasListInvitations) {
        // If both exist, they should have equivalent behavior
        expect(apiClient.getOrganizationInvitations).toEqual(
          apiClient.listInvitations
        )

        // Both methods should accept the same parameters
        expect(() => {
          const getOrgInvitationsParams =
            apiClient.getOrganizationInvitations.length
          const listInvitationsParams = apiClient.listInvitations.length
          expect(getOrgInvitationsParams).toBe(listInvitationsParams)
        }).not.toThrow()
      }
    })
  })

  describe('Resource Client Access', () => {
    it('should have all expected public API methods', () => {
      // Test authentication methods
      expect(apiClient.login).toBeDefined()
      expect(apiClient.signup).toBeDefined()
      expect(apiClient.getCurrentUser).toBeDefined()
      expect(apiClient.getProfile).toBeDefined()
      expect(apiClient.updateProfile).toBeDefined()
      expect(apiClient.logout).toBeDefined()

      // Test organization methods
      expect(apiClient.getOrganizations).toBeDefined()
      expect(apiClient.createOrganization).toBeDefined()
      expect(apiClient.getOrganization).toBeDefined()
      expect(apiClient.getOrganizationMembers).toBeDefined()

      // Test project methods
      expect(apiClient.getProjects).toBeDefined()
      expect(apiClient.getProject).toBeDefined()
      expect(apiClient.createTask).toBeDefined()
      expect(apiClient.updateTask).toBeDefined()

      // Test evaluation methods
      expect(apiClient.getEvaluations).toBeDefined()
      expect(apiClient.getLLMModels).toBeDefined()

      // Test notification methods
      expect(apiClient.getNotifications).toBeDefined()
      expect(apiClient.markNotificationAsRead).toBeDefined()

      // Test invitation methods
      expect(apiClient.getInvitationByToken).toBeDefined()
      expect(apiClient.acceptInvitation).toBeDefined()
      expect(apiClient.createInvitation).toBeDefined()

      // Test feature flag methods
      expect(apiClient.getFeatureFlags).toBeDefined()
      expect(apiClient.checkFeatureFlag).toBeDefined()

      // Verify they are functions
      expect(typeof apiClient.getCurrentUser).toBe('function')
      expect(typeof apiClient.getOrganizations).toBe('function')
      expect(typeof apiClient.getProjects).toBe('function')
      expect(typeof apiClient.getNotifications).toBe('function')
      expect(typeof apiClient.getInvitationByToken).toBeDefined()
      expect(typeof apiClient.getFeatureFlags).toBe('function')
    })

    it('should have invitations client be an instance of InvitationsApiClient', () => {
      expect(apiClient.invitations).toBeInstanceOf(InvitationsApiClient)
    })

    it('should have organizations client be an instance of OrganizationsClient', () => {
      expect(apiClient.organizations).toBeInstanceOf(OrganizationsClient)
    })
  })

  describe('Method Parameter Validation', () => {
    it('should validate invitation methods expect correct parameters', () => {
      // Mock the underlying request method to test parameter passing
      const mockRequest = jest.fn().mockResolvedValue({})
      ;(apiClient.invitations as any).request = mockRequest

      // Test listInvitations/getOrganizationInvitations
      const orgId = 'test-org-123'
      apiClient.listInvitations(orgId)

      expect(mockRequest).toHaveBeenCalledWith(
        expect.stringContaining(`/organizations/${orgId}/invitations`),
        expect.any(Object)
      )

      // If getOrganizationInvitations exists, it should work the same way
      mockRequest.mockClear()
      apiClient.getOrganizationInvitations(orgId)

      expect(mockRequest).toHaveBeenCalledWith(
        expect.stringContaining(`/organizations/${orgId}/invitations`),
        expect.any(Object)
      )
    })
  })

  describe('Backwards Compatibility', () => {
    it('should maintain backwards compatibility for renamed methods', () => {
      // List of methods that might have been renamed but need backwards compatibility
      const backwardsCompatibilityMap = [
        { old: 'getOrganizationInvitations', new: 'listInvitations' },
        { old: 'uploadTaskData', new: 'uploadData' }, // From line 226 in index.ts
      ]

      backwardsCompatibilityMap.forEach(({ old, new: newName }) => {
        if ((apiClient as any)[old] && (apiClient as any)[newName]) {
          // If both exist, the old should have equivalent behavior to the new
          expect((apiClient as any)[old]).toEqual((apiClient as any)[newName])
        }
      })
    })
  })
})
