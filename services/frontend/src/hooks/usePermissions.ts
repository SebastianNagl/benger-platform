/**
 * usePermissions - bind the current authenticated user to the permission
 * helpers in `@/utils/permissions`, so components stop re-importing each
 * predicate and threading `user` through by hand.
 *
 * Every method is the matching `@/utils/permissions` function with `user`
 * pre-applied from {@link useAuth}. Predicates that take a per-project argument
 * still accept it.
 *
 * @example
 * const perms = usePermissions()
 * if (perms.canCreateProjects()) { ... }
 * if (perms.canEditTaskData(project)) { ... }
 */

'use client'

import { useAuth } from '@/contexts/AuthContext'
import { OrganizationRole } from '@/lib/api'
import { Project } from '@/types/labelStudio'
import {
  canAccessProjectData,
  canAccessReports,
  canCreateProjects,
  canDeleteProjects,
  canEditTaskData,
  canMakeProjectPublic,
  canStartGeneration,
  getEffectiveProjectRole,
  getUserPermissions,
  isAnnotatorOnly,
} from '@/utils/permissions'
import { useMemo } from 'react'

type ProjectRoleInput = Pick<
  Project,
  'created_by' | 'is_public' | 'public_role' | 'effective_role'
>

export function usePermissions() {
  const { user, organizations } = useAuth()

  return useMemo(
    () => ({
      /** The raw user (or null) these predicates are bound to. */
      user,
      canCreateProjects: (options?: { isPrivateMode?: boolean }) =>
        canCreateProjects(user, options),
      // The user's memberships are bound in so the global (no-project) form
      // resolves the access tier across ALL orgs, not the selected one.
      canAccessProjectData: (options?: {
        isPrivateMode?: boolean
        project?: ProjectRoleInput | null
        organizations?: Array<{ role?: OrganizationRole | null }> | null
      }) => canAccessProjectData(user, { organizations, ...options }),
      canEditTaskData: (project?: ProjectRoleInput | null) =>
        canEditTaskData(user, project),
      canDeleteProjects: () => canDeleteProjects(user),
      canStartGeneration: (project?: ProjectRoleInput | null) =>
        canStartGeneration(user, project),
      canAccessReports: () => canAccessReports(user),
      canMakeProjectPublic: (project: Pick<Project, 'created_by'> | null) =>
        canMakeProjectPublic(user, project),
      getEffectiveProjectRole: (
        project: ProjectRoleInput | null,
        orgRole?: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR' | null,
      ) => getEffectiveProjectRole(user, project, orgRole),
      isAnnotatorOnly: () => isAnnotatorOnly(user),
      /** Memoised summary bundle for display/debug. */
      summary: getUserPermissions(user),
    }),
    [user, organizations],
  )
}

export default usePermissions
