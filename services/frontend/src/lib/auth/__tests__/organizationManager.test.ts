/**
 * @jest-environment jsdom
 *
 * OrganizationManager comprehensive branch coverage tests
 * Tests all conditional paths in setOrganizations, fetchOrganizations,
 * getOrganizationContext, and state management.
 */

import { OrganizationManager } from '@/lib/auth/organizationManager'

// Mock dependencies
jest.mock('@/lib/api', () => ({
  ApiClient: jest.fn(),
}))

describe('OrganizationManager', () => {
  let manager: OrganizationManager

  beforeEach(() => {
    manager = new OrganizationManager()
  })

  describe('initial state', () => {
    it('should start with empty organizations', () => {
      expect(manager.getOrganizations()).toEqual([])
    })

    it('should start with null current organization', () => {
      expect(manager.getCurrentOrganization()).toBeNull()
    })
  })

  describe('setOrganizations', () => {
    it('should set organizations list', () => {
      const orgs = [
        { id: 'org1', name: 'Org 1', slug: 'org1' },
        { id: 'org2', name: 'Org 2', slug: 'org2' },
      ] as any[]

      manager.setOrganizations(orgs)

      expect(manager.getOrganizations()).toEqual(orgs)
    })

    it('should auto-select first organization when none is selected', () => {
      const orgs = [
        { id: 'org1', name: 'Org 1', slug: 'org1' },
        { id: 'org2', name: 'Org 2', slug: 'org2' },
      ] as any[]

      manager.setOrganizations(orgs)

      expect(manager.getCurrentOrganization()).toEqual(orgs[0])
    })

    it('should NOT auto-select if an organization is already selected', () => {
      const existingOrg = { id: 'existing', name: 'Existing', slug: 'existing' } as any
      manager.setCurrentOrganization(existingOrg)

      const orgs = [
        { id: 'org1', name: 'Org 1', slug: 'org1' },
        { id: 'org2', name: 'Org 2', slug: 'org2' },
      ] as any[]

      manager.setOrganizations(orgs)

      // Should keep the existing org, not replace with org1
      expect(manager.getCurrentOrganization()).toEqual(existingOrg)
    })

    it('should NOT auto-select when organizations list is empty', () => {
      manager.setOrganizations([])

      expect(manager.getCurrentOrganization()).toBeNull()
    })

    it('should handle single organization', () => {
      const orgs = [{ id: 'only', name: 'Only Org', slug: 'only' }] as any[]
      manager.setOrganizations(orgs)

      expect(manager.getCurrentOrganization()).toEqual(orgs[0])
    })
  })

  describe('setCurrentOrganization', () => {
    it('should set current organization', () => {
      const org = { id: 'org1', name: 'Org 1', slug: 'org1' } as any

      manager.setCurrentOrganization(org)

      expect(manager.getCurrentOrganization()).toEqual(org)
    })

    it('should allow setting current organization to null', () => {
      const org = { id: 'org1', name: 'Org 1', slug: 'org1' } as any
      manager.setCurrentOrganization(org)

      manager.setCurrentOrganization(null)

      expect(manager.getCurrentOrganization()).toBeNull()
    })
  })

  describe('fetchOrganizations', () => {
    it('should fetch and set organizations on success', async () => {
      const mockOrgs = [
        { id: 'org1', name: 'Org 1', slug: 'org1' },
      ] as any[]

      const mockApiClient = {
        getOrganizations: jest.fn().mockResolvedValue(mockOrgs),
      } as any

      const result = await manager.fetchOrganizations(mockApiClient)

      expect(result).toEqual(mockOrgs)
      expect(manager.getOrganizations()).toEqual(mockOrgs)
      expect(manager.getCurrentOrganization()).toEqual(mockOrgs[0])
    })

    it('should clear state on fetch failure', async () => {
      // First set some state
      manager.setOrganizations([{ id: 'old', name: 'Old', slug: 'old' }] as any[])

      const mockApiClient = {
        getOrganizations: jest.fn().mockRejectedValue(new Error('Network error')),
      } as any

      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation()

      const result = await manager.fetchOrganizations(mockApiClient)

      expect(result).toEqual([])
      expect(manager.getOrganizations()).toEqual([])
      expect(manager.getCurrentOrganization()).toBeNull()
      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to fetch organizations:',
        expect.any(Error)
      )

      consoleSpy.mockRestore()
    })

    it('should return empty array on failure', async () => {
      const mockApiClient = {
        getOrganizations: jest.fn().mockRejectedValue(new Error('Timeout')),
      } as any

      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation()

      const result = await manager.fetchOrganizations(mockApiClient)

      expect(result).toEqual([])

      consoleSpy.mockRestore()
    })
  })

  describe('clear', () => {
    it('should clear all organization state', () => {
      const orgs = [{ id: 'org1', name: 'Org 1', slug: 'org1' }] as any[]
      manager.setOrganizations(orgs)

      expect(manager.getOrganizations()).toHaveLength(1)
      expect(manager.getCurrentOrganization()).not.toBeNull()

      manager.clear()

      expect(manager.getOrganizations()).toEqual([])
      expect(manager.getCurrentOrganization()).toBeNull()
    })

    it('should handle clearing when already empty', () => {
      manager.clear()

      expect(manager.getOrganizations()).toEqual([])
      expect(manager.getCurrentOrganization()).toBeNull()
    })
  })

  describe('getOrganizationContext', () => {
    it('should return organization id when org is selected', () => {
      const org = { id: 'org123', name: 'Test Org', slug: 'test-org' } as any
      manager.setCurrentOrganization(org)

      expect(manager.getOrganizationContext()).toBe('org123')
    })

    it('should return "private" when no organization is selected', () => {
      expect(manager.getOrganizationContext()).toBe('private')
    })

    it('should return "private" after clearing organization', () => {
      const org = { id: 'org123', name: 'Test Org', slug: 'test-org' } as any
      manager.setCurrentOrganization(org)
      manager.setCurrentOrganization(null)

      expect(manager.getOrganizationContext()).toBe('private')
    })

    it('should return "private" after clear() is called', () => {
      const org = { id: 'org123', name: 'Test Org', slug: 'test-org' } as any
      manager.setCurrentOrganization(org)
      manager.clear()

      expect(manager.getOrganizationContext()).toBe('private')
    })
  })

  describe('state consistency', () => {
    it('should maintain correct state through set/fetch/clear cycle', async () => {
      const mockOrgs = [
        { id: 'org1', name: 'Org 1', slug: 'org1' },
        { id: 'org2', name: 'Org 2', slug: 'org2' },
      ] as any[]

      const mockApiClient = {
        getOrganizations: jest.fn().mockResolvedValue(mockOrgs),
      } as any

      // Fetch sets orgs and auto-selects first
      await manager.fetchOrganizations(mockApiClient)
      expect(manager.getOrganizations()).toEqual(mockOrgs)
      expect(manager.getCurrentOrganization()?.id).toBe('org1')

      // Switch to second org
      manager.setCurrentOrganization(mockOrgs[1])
      expect(manager.getCurrentOrganization()?.id).toBe('org2')

      // Clear resets everything
      manager.clear()
      expect(manager.getOrganizations()).toEqual([])
      expect(manager.getCurrentOrganization()).toBeNull()
    })
  })
})
