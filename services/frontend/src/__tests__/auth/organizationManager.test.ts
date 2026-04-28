/**
 * Organization Manager Test Suite
 * Tests organization state management and context
 */

import { ApiClient, Organization } from '@/lib/api'
import { OrganizationManager } from '@/lib/auth/organizationManager'

// Mock ApiClient
jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn().mockImplementation(() => ({
    getOrganizations: jest.fn(),
  })),
  Organization: jest.fn(),
}))

describe('OrganizationManager', () => {
  let orgManager: OrganizationManager
  let mockApiClient: any

  const mockOrgs: Organization[] = [
    { id: 'org1', name: 'Organization 1', is_admin: true } as any,
    { id: 'org2', name: 'Organization 2', is_admin: false } as any,
    { id: 'org3', name: 'Organization 3', is_admin: false } as any,
  ]

  beforeEach(() => {
    orgManager = new OrganizationManager()
    mockApiClient = new ApiClient()
    jest.clearAllMocks()
  })

  describe('getOrganizations', () => {
    it('should return empty array initially', () => {
      expect(orgManager.getOrganizations()).toEqual([])
    })

    it('should return organizations after setting them', () => {
      orgManager.setOrganizations(mockOrgs)

      expect(orgManager.getOrganizations()).toEqual(mockOrgs)
    })
  })

  describe('getCurrentOrganization', () => {
    it('should return null initially', () => {
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })

    it('should return current organization after setting it', () => {
      orgManager.setCurrentOrganization(mockOrgs[1])

      expect(orgManager.getCurrentOrganization()).toEqual(mockOrgs[1])
    })
  })

  describe('setOrganizations', () => {
    it('should set organizations list', () => {
      orgManager.setOrganizations(mockOrgs)

      expect(orgManager.getOrganizations()).toEqual(mockOrgs)
    })

    it('does not auto-select after setOrganizations (caller picks)', () => {
      orgManager.setOrganizations(mockOrgs)

      // PR #15: setOrganizations no longer silently picks the first org —
      // AuthContext is the source of truth and decides private vs. picked.
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })

    it('should not change current organization if already selected', () => {
      orgManager.setCurrentOrganization(mockOrgs[2])
      orgManager.setOrganizations(mockOrgs)

      expect(orgManager.getCurrentOrganization()).toEqual(mockOrgs[2])
    })

    it('should handle empty organizations array', () => {
      orgManager.setOrganizations([])

      expect(orgManager.getOrganizations()).toEqual([])
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })
  })

  describe('setCurrentOrganization', () => {
    it('should set current organization', () => {
      orgManager.setCurrentOrganization(mockOrgs[1])

      expect(orgManager.getCurrentOrganization()).toEqual(mockOrgs[1])
    })

    it('should allow setting to null', () => {
      orgManager.setCurrentOrganization(mockOrgs[0])
      orgManager.setCurrentOrganization(null)

      expect(orgManager.getCurrentOrganization()).toBeNull()
    })
  })

  describe('fetchOrganizations', () => {
    it('should fetch and set organizations', async () => {
      mockApiClient.getOrganizations.mockResolvedValue(mockOrgs)

      const result = await orgManager.fetchOrganizations(mockApiClient)

      expect(mockApiClient.getOrganizations).toHaveBeenCalled()
      expect(result).toEqual(mockOrgs)
      expect(orgManager.getOrganizations()).toEqual(mockOrgs)
      // PR #15: fetchOrganizations populates the list but does not auto-pick.
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })

    it('should handle fetch error gracefully', async () => {
      mockApiClient.getOrganizations.mockRejectedValue(
        new Error('Network error')
      )

      const result = await orgManager.fetchOrganizations(mockApiClient)

      expect(result).toEqual([])
      expect(orgManager.getOrganizations()).toEqual([])
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })

    it('should not auto-select if organization already selected', async () => {
      orgManager.setCurrentOrganization(mockOrgs[2])
      mockApiClient.getOrganizations.mockResolvedValue(mockOrgs)

      await orgManager.fetchOrganizations(mockApiClient)

      expect(orgManager.getCurrentOrganization()).toEqual(mockOrgs[2])
    })
  })

  describe('clear', () => {
    it('should clear all organization state', () => {
      orgManager.setOrganizations(mockOrgs)
      orgManager.setCurrentOrganization(mockOrgs[1])

      orgManager.clear()

      expect(orgManager.getOrganizations()).toEqual([])
      expect(orgManager.getCurrentOrganization()).toBeNull()
    })
  })

  describe('getOrganizationContext', () => {
    it('should return organization ID when set', () => {
      orgManager.setCurrentOrganization(mockOrgs[0])

      expect(orgManager.getOrganizationContext()).toBe('org1')
    })

    it('should return "private" when no organization (private mode)', () => {
      expect(orgManager.getOrganizationContext()).toBe('private')
    })
  })
})
