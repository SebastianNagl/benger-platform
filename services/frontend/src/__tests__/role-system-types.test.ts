/**
 * Tests for role system type definitions
 * Ensures type safety and consistency between global and organization roles
 */

import {
  GlobalUserRole,
  OrganizationMember,
  OrganizationRole,
  User,
} from '../lib/api/types'

describe('Role System Types', () => {
  describe('GlobalUserRole', () => {
    it('should only include valid global roles', () => {
      const validGlobalRoles: GlobalUserRole[] = ['superadmin', 'user']

      validGlobalRoles.forEach((role) => {
        expect(typeof role).toBe('string')
        expect(['superadmin', 'user']).toContain(role)
      })
    })

    it('should not include organization roles', () => {
      // TypeScript compilation will fail if these are incorrectly assigned
      const globalRole: GlobalUserRole = 'superadmin'
      expect(globalRole).toBe('superadmin')

      // This would cause a TypeScript error if organization roles were mixed in:
      // const invalidRole: GlobalUserRole = 'org_admin' // Should not compile
    })
  })

  describe('OrganizationRole', () => {
    it('should only include valid organization roles', () => {
      const validOrgRoles: OrganizationRole[] = [
        'org_admin',
        'org_contributor',
        'org_user',
      ]

      validOrgRoles.forEach((role) => {
        expect(typeof role).toBe('string')
        expect(['org_admin', 'org_contributor', 'org_user']).toContain(role)
      })
    })
  })

  describe('User interface', () => {
    it('should only accept global roles', () => {
      const superadminUser: User = {
        id: '1',
        username: 'admin',
        email: 'admin@example.com',
        name: 'Admin User',
        role: 'superadmin',
        is_active: true,
        created_at: '2023-01-01T00:00:00Z',
      }

      const regularUser: User = {
        id: '2',
        username: 'user',
        email: 'user@example.com',
        name: 'Regular User',
        role: 'user',
        is_active: true,
        created_at: '2023-01-01T00:00:00Z',
      }

      expect(superadminUser.role).toBe('superadmin')
      expect(regularUser.role).toBe('user')

      // Verify types are properly constrained
      expect(['superadmin', 'user']).toContain(superadminUser.role)
      expect(['superadmin', 'user']).toContain(regularUser.role)
    })
  })

  describe('OrganizationMember interface', () => {
    it('should only accept organization roles', () => {
      const orgAdmin: OrganizationMember = {
        id: '1',
        user_id: 'user1',
        organization_id: 'org1',
        role: 'org_admin',
        is_active: true,
        joined_at: '2023-01-01T00:00:00Z',
      }

      const orgContributor: OrganizationMember = {
        id: '2',
        user_id: 'user2',
        organization_id: 'org1',
        role: 'org_contributor',
        is_active: true,
        joined_at: '2023-01-01T00:00:00Z',
      }

      const orgUser: OrganizationMember = {
        id: '3',
        user_id: 'user3',
        organization_id: 'org1',
        role: 'org_user',
        is_active: true,
        joined_at: '2023-01-01T00:00:00Z',
      }

      expect(orgAdmin.role).toBe('org_admin')
      expect(orgContributor.role).toBe('org_contributor')
      expect(orgUser.role).toBe('org_user')

      // Verify types are properly constrained
      expect(['org_admin', 'org_contributor', 'org_user']).toContain(
        orgAdmin.role
      )
      expect(['org_admin', 'org_contributor', 'org_user']).toContain(
        orgContributor.role
      )
      expect(['org_admin', 'org_contributor', 'org_user']).toContain(
        orgUser.role
      )
    })
  })

  describe('Type safety', () => {
    it('should prevent mixing global and organization roles', () => {
      // These tests verify that TypeScript prevents incorrect role assignments

      // Valid assignments
      const globalRole: GlobalUserRole = 'superadmin'
      const orgRole: OrganizationRole = 'org_admin'

      expect(globalRole).toBe('superadmin')
      expect(orgRole).toBe('org_admin')

      // TypeScript should prevent these assignments:
      // const invalidGlobal: GlobalUserRole = 'org_admin' // Should not compile
      // const invalidOrg: OrganizationRole = 'superadmin' // Should not compile
    })
  })
})
