/**
 * Comprehensive tests for permission utility functions
 * Tests the permission logic for different user roles and scenarios
 */

import { Organization, User } from '@/lib/api'
import {
  canAccessProjectData,
  canCreateProjects,
  canDeleteProjects,
  canStartGeneration,
  getUserPermissions,
  hasOrganization,
  isAnnotatorOnly,
} from '../permissions'

// Mock users for testing
const createMockUser = (overrides: Partial<User> = {}): User => ({
  id: 'test-user-id',
  username: 'testuser',
  email: 'test@example.com',
  name: 'Test User',
  is_superadmin: false,
  is_active: true,
  created_at: '2023-01-01T00:00:00Z',
  role: undefined,
  ...overrides,
})

describe('Permission Utilities', () => {
  describe('canAccessProjectData', () => {
    it('should allow superadmins to access project data regardless of role', () => {
      const superadmin = createMockUser({
        is_superadmin: true,
        role: undefined, // No organization role
      })

      expect(canAccessProjectData(superadmin)).toBe(true)
    })

    it('should allow superadmins with organization roles to access project data', () => {
      const superadminWithRole = createMockUser({
        is_superadmin: true,
        role: 'ANNOTATOR', // Even with lower role, superadmin should have access
      })

      expect(canAccessProjectData(superadminWithRole)).toBe(true)
    })

    it('should allow ORG_ADMIN users to access project data', () => {
      const orgAdmin = createMockUser({ role: 'ORG_ADMIN' })

      expect(canAccessProjectData(orgAdmin)).toBe(true)
    })

    it('should allow CONTRIBUTOR users to access project data', () => {
      const contributor = createMockUser({ role: 'CONTRIBUTOR' })

      expect(canAccessProjectData(contributor)).toBe(true)
    })

    it('should deny ANNOTATOR users access to project data', () => {
      const annotator = createMockUser({ role: 'ANNOTATOR' })

      expect(canAccessProjectData(annotator)).toBe(false)
    })

    it('should deny users with no role access to project data', () => {
      const userWithoutRole = createMockUser({ role: undefined })

      expect(canAccessProjectData(userWithoutRole)).toBe(false)
    })

    it('should deny null users access to project data', () => {
      expect(canAccessProjectData(null)).toBe(false)
    })

    it('should deny users with invalid roles access to project data', () => {
      const userWithInvalidRole = createMockUser({
        role: 'INVALID_ROLE' as any,
      })

      expect(canAccessProjectData(userWithInvalidRole)).toBe(false)
    })
  })

  describe('canCreateProjects', () => {
    it('should allow superadmins to create projects', () => {
      const superadmin = createMockUser({ is_superadmin: true })

      expect(canCreateProjects(superadmin)).toBe(true)
    })

    it('should allow ORG_ADMIN users to create projects', () => {
      const orgAdmin = createMockUser({ role: 'ORG_ADMIN' })

      expect(canCreateProjects(orgAdmin)).toBe(true)
    })

    it('should allow CONTRIBUTOR users to create projects', () => {
      const contributor = createMockUser({ role: 'CONTRIBUTOR' })

      expect(canCreateProjects(contributor)).toBe(true)
    })

    it('should deny ANNOTATOR users ability to create projects', () => {
      const annotator = createMockUser({ role: 'ANNOTATOR' })

      expect(canCreateProjects(annotator)).toBe(false)
    })

    it('should deny null users ability to create projects', () => {
      expect(canCreateProjects(null)).toBe(false)
    })
  })

  describe('canDeleteProjects', () => {
    it('should allow only superadmins to delete projects', () => {
      const superadmin = createMockUser({ is_superadmin: true })

      expect(canDeleteProjects(superadmin)).toBe(true)
    })

    it('should deny ORG_ADMIN users ability to delete projects', () => {
      const orgAdmin = createMockUser({ role: 'ORG_ADMIN' })

      expect(canDeleteProjects(orgAdmin)).toBe(false)
    })

    it('should deny CONTRIBUTOR users ability to delete projects', () => {
      const contributor = createMockUser({ role: 'CONTRIBUTOR' })

      expect(canDeleteProjects(contributor)).toBe(false)
    })

    it('should deny ANNOTATOR users ability to delete projects', () => {
      const annotator = createMockUser({ role: 'ANNOTATOR' })

      expect(canDeleteProjects(annotator)).toBe(false)
    })

    it('should deny null users ability to delete projects', () => {
      expect(canDeleteProjects(null)).toBe(false)
    })
  })

  describe('isAnnotatorOnly', () => {
    it('should identify ANNOTATOR users as annotator-only', () => {
      const annotator = createMockUser({ role: 'ANNOTATOR' })

      expect(isAnnotatorOnly(annotator)).toBe(true)
    })

    it('should not identify superadmins as annotator-only, even with ANNOTATOR role', () => {
      const superadminAnnotator = createMockUser({
        is_superadmin: true,
        role: 'ANNOTATOR',
      })

      expect(isAnnotatorOnly(superadminAnnotator)).toBe(false)
    })

    it('should not identify ORG_ADMIN users as annotator-only', () => {
      const orgAdmin = createMockUser({ role: 'ORG_ADMIN' })

      expect(isAnnotatorOnly(orgAdmin)).toBe(false)
    })

    it('should not identify CONTRIBUTOR users as annotator-only', () => {
      const contributor = createMockUser({ role: 'CONTRIBUTOR' })

      expect(isAnnotatorOnly(contributor)).toBe(false)
    })

    it('should not identify users without roles as annotator-only', () => {
      const userWithoutRole = createMockUser({ role: undefined })

      expect(isAnnotatorOnly(userWithoutRole)).toBe(false)
    })

    it('should handle null users', () => {
      expect(isAnnotatorOnly(null)).toBe(false)
    })
  })

  describe('getUserPermissions', () => {
    it('should return correct permissions for superadmin', () => {
      const superadmin = createMockUser({
        is_superadmin: true,
        role: 'ORG_ADMIN',
      })

      const permissions = getUserPermissions(superadmin)

      expect(permissions).toEqual({
        canCreate: true,
        canAccessData: true,
        canDelete: true,
        canStartGeneration: true,
        canAccessReports: true,
        isAnnotatorOnly: false,
        role: 'superadmin',
        isAuthenticated: true,
      })
    })

    it('should return correct permissions for ORG_ADMIN', () => {
      const orgAdmin = createMockUser({ role: 'ORG_ADMIN' })

      const permissions = getUserPermissions(orgAdmin)

      expect(permissions).toEqual({
        canCreate: true,
        canAccessData: true,
        canDelete: false,
        canStartGeneration: true,
        canAccessReports: true,
        isAnnotatorOnly: false,
        role: 'ORG_ADMIN',
        isAuthenticated: true,
      })
    })

    it('should return correct permissions for CONTRIBUTOR', () => {
      const contributor = createMockUser({ role: 'CONTRIBUTOR' })

      const permissions = getUserPermissions(contributor)

      expect(permissions).toEqual({
        canCreate: true,
        canAccessData: true,
        canDelete: false,
        canStartGeneration: true,
        canAccessReports: false,
        isAnnotatorOnly: false,
        role: 'CONTRIBUTOR',
        isAuthenticated: true,
      })
    })

    it('should return correct permissions for ANNOTATOR', () => {
      const annotator = createMockUser({ role: 'ANNOTATOR' })

      const permissions = getUserPermissions(annotator)

      expect(permissions).toEqual({
        canCreate: false,
        canAccessData: false,
        canDelete: false,
        canStartGeneration: false,
        canAccessReports: false,
        isAnnotatorOnly: true,
        role: 'ANNOTATOR',
        isAuthenticated: true,
      })
    })

    it('should return correct permissions for user without role', () => {
      const userWithoutRole = createMockUser({ role: undefined })

      const permissions = getUserPermissions(userWithoutRole)

      expect(permissions).toEqual({
        canCreate: false,
        canAccessData: false,
        canDelete: false,
        canStartGeneration: false,
        canAccessReports: false,
        isAnnotatorOnly: false,
        role: 'unknown',
        isAuthenticated: true,
      })
    })

    it('should return correct permissions for null user', () => {
      const permissions = getUserPermissions(null)

      expect(permissions).toEqual({
        canCreate: false,
        canAccessData: false,
        canDelete: false,
        canStartGeneration: false,
        canAccessReports: false,
        isAnnotatorOnly: false,
        role: 'none',
        isAuthenticated: false,
      })
    })
  })

  describe('canStartGeneration', () => {
    it('should allow superadmins to start generation', () => {
      const superadmin = createMockUser({ is_superadmin: true })
      expect(canStartGeneration(superadmin)).toBe(true)
    })

    it('should allow ORG_ADMIN to start generation', () => {
      const orgAdmin = createMockUser({ role: 'ORG_ADMIN' })
      expect(canStartGeneration(orgAdmin)).toBe(true)
    })

    it('should allow CONTRIBUTOR to start generation', () => {
      const contributor = createMockUser({ role: 'CONTRIBUTOR' })
      expect(canStartGeneration(contributor)).toBe(true)
    })

    it('should deny ANNOTATOR from starting generation', () => {
      const annotator = createMockUser({ role: 'ANNOTATOR' })
      expect(canStartGeneration(annotator)).toBe(false)
    })

    it('should deny null users from starting generation', () => {
      expect(canStartGeneration(null)).toBe(false)
    })

    it('should deny users with no role from starting generation', () => {
      const userWithoutRole = createMockUser({ role: undefined })
      expect(canStartGeneration(userWithoutRole)).toBe(false)
    })
  })

  describe('hasOrganization', () => {
    const createMockOrganization = (
      overrides: Partial<Organization> = {}
    ): Organization => ({
      id: 'test-org-id',
      name: 'Test Organization',
      created_at: '2023-01-01T00:00:00Z',
      ...overrides,
    })

    it('should return true when organizations array has one item', () => {
      const organizations = [createMockOrganization()]
      expect(hasOrganization(organizations)).toBe(true)
    })

    it('should return true when organizations array has multiple items', () => {
      const organizations = [
        createMockOrganization({ id: 'org-1', name: 'Org 1' }),
        createMockOrganization({ id: 'org-2', name: 'Org 2' }),
        createMockOrganization({ id: 'org-3', name: 'Org 3' }),
      ]
      expect(hasOrganization(organizations)).toBe(true)
    })

    it('should return false when organizations array is empty', () => {
      expect(hasOrganization([])).toBe(false)
    })
  })

  describe('Edge Cases', () => {
    it('should handle users with mixed case roles', () => {
      const userWithMixedCase = createMockUser({ role: 'org_admin' as any })

      // Our system should be case-sensitive and only accept exact matches
      expect(canAccessProjectData(userWithMixedCase)).toBe(false)
      expect(canCreateProjects(userWithMixedCase)).toBe(false)
    })

    it('should handle inactive users correctly', () => {
      const inactiveUser = createMockUser({
        is_active: false,
        role: 'ORG_ADMIN',
      })

      // Permissions should still work based on role, even if user is inactive
      // The active check is handled at the authentication level
      expect(canAccessProjectData(inactiveUser)).toBe(true)
      expect(canCreateProjects(inactiveUser)).toBe(true)
    })

    it('should prioritize superadmin flag over role restrictions', () => {
      const superadminWithLowerRole = createMockUser({
        is_superadmin: true,
        role: 'ANNOTATOR',
      })

      expect(canAccessProjectData(superadminWithLowerRole)).toBe(true)
      expect(canCreateProjects(superadminWithLowerRole)).toBe(true)
      expect(canDeleteProjects(superadminWithLowerRole)).toBe(true)
      expect(isAnnotatorOnly(superadminWithLowerRole)).toBe(false)
    })
  })
})
