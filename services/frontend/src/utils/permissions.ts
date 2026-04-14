/**
 * Permission utility functions for role-based access control
 * Centralizes all permission logic for consistent application across the frontend
 */

import { Organization, User } from '@/lib/api'

/**
 * Check if user can create projects
 * In org mode: superadmins, ORG_ADMIN, and CONTRIBUTOR can create projects.
 * In private mode: any authenticated user can create private projects.
 */
export const canCreateProjects = (user: User | null, options?: { isPrivateMode?: boolean }): boolean => {
  if (!user) return false
  if (user.is_superadmin) return true
  if (options?.isPrivateMode) return true
  return user.role === 'ORG_ADMIN' || user.role === 'CONTRIBUTOR'
}

/**
 * Check if user can access project data/management features
 * In org mode: superadmins, ORG_ADMIN, and CONTRIBUTOR can access project data.
 * In private mode: any authenticated user can access their own project data.
 */
export const canAccessProjectData = (user: User | null, options?: { isPrivateMode?: boolean }): boolean => {
  if (!user) return false
  if (user.is_superadmin) return true
  if (options?.isPrivateMode) return true
  return user.role === 'ORG_ADMIN' || user.role === 'CONTRIBUTOR'
}

/**
 * Check if user can delete projects
 * Only superadmins can delete projects
 */
export const canDeleteProjects = (user: User | null): boolean => {
  if (!user) return false
  return user.is_superadmin
}

/**
 * Check if user can only annotate (view-only access)
 * Annotators can only view and annotate, not create or manage projects
 */
export const isAnnotatorOnly = (user: User | null): boolean => {
  if (!user) return false

  // Superadmins are never annotator-only
  if (user.is_superadmin) return false

  // Only annotators have view-only access
  return user.role === 'ANNOTATOR'
}

/**
 * Check if user can start generations
 * Superadmins, ORG_ADMIN, and CONTRIBUTOR can start generations.
 * Matches backend GENERATION_CREATE permission.
 */
export const canStartGeneration = (user: User | null): boolean => {
  if (!user) return false
  if (user.is_superadmin) return true
  return user.role === 'ORG_ADMIN' || user.role === 'CONTRIBUTOR'
}

/**
 * Check if user can access reports
 * Only superadmins and org_admins can access reports
 */
export const canAccessReports = (user: User | null): boolean => {
  if (!user) return false

  // Superadmins can always access reports
  if (user.is_superadmin) return true

  // Only ORG_ADMIN can access reports
  return user.role === 'ORG_ADMIN'
}

/**
 * Get user permission summary for debugging/display
 */
export const getUserPermissions = (user: User | null) => {
  if (!user) {
    return {
      canCreate: false,
      canAccessData: false,
      canDelete: false,
      canStartGeneration: false,
      canAccessReports: false,
      isAnnotatorOnly: false,
      role: 'none',
      isAuthenticated: false,
    }
  }

  return {
    canCreate: canCreateProjects(user),
    canAccessData: canAccessProjectData(user),
    canDelete: canDeleteProjects(user),
    canStartGeneration: canStartGeneration(user),
    canAccessReports: canAccessReports(user),
    isAnnotatorOnly: isAnnotatorOnly(user),
    role: user.is_superadmin ? 'superadmin' : user.role || 'unknown',
    isAuthenticated: true,
  }
}

/**
 * Check if user has at least one organization membership
 * Users without organizations have limited access to project features
 */
export const hasOrganization = (organizations: Organization[]): boolean => {
  return organizations.length > 0
}
