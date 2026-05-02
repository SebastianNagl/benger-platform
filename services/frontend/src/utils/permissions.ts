/**
 * Permission utility functions for role-based access control
 * Centralizes all permission logic for consistent application across the frontend
 */

import { Organization, User } from '@/lib/api'
import { Project } from '@/types/labelStudio'

/**
 * Resolve the effective role a user holds for a project. Mirrors the backend
 * helper of the same intent (services/api/routers/projects/helpers.py:
 * get_effective_project_role).
 *
 * Order:
 *   1. Superadmin or project creator → ORG_ADMIN
 *   2. The user's org-membership role for an org assigned to the project
 *   3. Public projects → fall back to project.public_role
 *   4. Otherwise null
 */
export const getEffectiveProjectRole = (
  user: User | null,
  project: Pick<Project, 'created_by' | 'is_public' | 'public_role'> | null,
  orgRole?: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR' | null
): 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR' | null => {
  if (!user || !project) return null
  if (user.is_superadmin) return 'ORG_ADMIN'
  if (String(user.id) === String(project.created_by)) return 'ORG_ADMIN'
  if (orgRole) return orgRole
  if (project.is_public && project.public_role) return project.public_role
  return null
}

/**
 * Whether the user can flip a project to public visibility.
 * Per design: project creator + superadmins.
 */
export const canMakeProjectPublic = (
  user: User | null,
  project: Pick<Project, 'created_by'> | null
): boolean => {
  if (!user || !project) return false
  if (user.is_superadmin) return true
  return String(user.id) === String(project.created_by)
}

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
 *
 * When a `project` is supplied, public-tier visitors fall back to the
 * project's `public_role` (treated as CONTRIBUTOR-equivalent for data access).
 */
export const canAccessProjectData = (
  user: User | null,
  options?: {
    isPrivateMode?: boolean
    project?: Pick<Project, 'created_by' | 'is_public' | 'public_role'> | null
  }
): boolean => {
  if (!user) return false
  if (user.is_superadmin) return true
  if (options?.isPrivateMode) return true
  if (user.role === 'ORG_ADMIN' || user.role === 'CONTRIBUTOR') return true
  if (options?.project) {
    const eff = getEffectiveProjectRole(user, options.project)
    return eff === 'ORG_ADMIN' || eff === 'CONTRIBUTOR'
  }
  return false
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
 *
 * When a `project` is supplied, public-tier visitors fall back to the
 * project's `public_role` — public CONTRIBUTORs are allowed.
 */
export const canStartGeneration = (
  user: User | null,
  project?: Pick<Project, 'created_by' | 'is_public' | 'public_role'> | null
): boolean => {
  if (!user) return false
  if (user.is_superadmin) return true
  if (user.role === 'ORG_ADMIN' || user.role === 'CONTRIBUTOR') return true
  if (project) {
    const eff = getEffectiveProjectRole(user, project)
    return eff === 'ORG_ADMIN' || eff === 'CONTRIBUTOR'
  }
  return false
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
