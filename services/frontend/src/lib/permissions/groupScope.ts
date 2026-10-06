/**
 * Which organization scopes a user may put a project into (project creation
 * wizard, project visibility settings).
 *
 * Every org member has one org role, which covers org-wide projects, and
 * every group membership has its own group role, which covers the group's
 * projects. Creating or attaching a project needs CONTRIBUTOR or ORG_ADMIN
 * in the scope it lands in:
 * - org-wide: the org role,
 * - one group: the group role (org admins count as admin of every group).
 * The API enforces the same rule; this mirror only decides what is offered.
 */

import type { OrganizationRole } from '@/lib/api/types'

/** Roles allowed to create projects in a scope. */
export const PROJECT_CREATOR_ROLES: ReadonlySet<OrganizationRole> = new Set([
  'CONTRIBUTOR',
  'ORG_ADMIN',
])

export const canCreateWithRole = (
  role: OrganizationRole | null | undefined,
): boolean => Boolean(role && PROJECT_CREATOR_ROLES.has(role))

/**
 * May the user scope a project to the whole organization? A missing org
 * role (e.g. a superadmin's org listing) is left to the API to decide.
 */
export function canScopeOrgWide(
  orgRole: OrganizationRole | null | undefined,
  isSuperadmin = false,
): boolean {
  if (isSuperadmin || orgRole == null) return true
  return canCreateWithRole(orgRole)
}

interface ScopeableGroup {
  id: string
  is_active: boolean
  is_member?: boolean
  my_role?: OrganizationRole | null
}

/**
 * The active groups of one org the user may scope a project to: every
 * active group for org admins and superadmins, otherwise the groups where
 * their group role is CONTRIBUTOR or ORG_ADMIN (independent of the org
 * role, so an org Annotator who is group admin still gets their group).
 */
export function scopeableGroups<G extends ScopeableGroup>(
  groups: G[],
  orgRole: OrganizationRole | null | undefined,
  isSuperadmin = false,
): G[] {
  const isOrgAdmin = isSuperadmin || orgRole === 'ORG_ADMIN'
  return groups.filter(
    (group) =>
      group.is_active &&
      (isOrgAdmin ||
        (group.is_member !== false && canCreateWithRole(group.my_role))),
  )
}

/**
 * Can the user create a project in this organization at all (org-wide or
 * in at least one of their groups)? Works on the /auth/me/contexts entries,
 * whose groups carry the caller's group role as `role`.
 */
export function canCreateInOrganization(org: {
  role?: OrganizationRole | null
  groups?: Array<{ role: OrganizationRole; is_active?: boolean }>
}): boolean {
  if (canCreateWithRole(org.role)) return true
  return (org.groups ?? []).some(
    (group) => group.is_active !== false && canCreateWithRole(group.role),
  )
}
