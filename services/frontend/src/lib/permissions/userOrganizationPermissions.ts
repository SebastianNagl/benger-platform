/**
 * User Organization Permissions Service
 *
 * Centralized permission logic for admin and organization management features.
 * This service determines what actions users can perform based on their roles
 * and organizational membership.
 */

import { User } from '@/lib/api/types'

export interface UserWithOrganizations extends User {
  organizations?: Array<{
    id: string
    role: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR'
  }>
}

export class UserOrganizationPermissions {
  /**
   * Check if user can manage global users (superadmin only)
   */
  static canManageGlobalUsers(user: UserWithOrganizations | null): boolean {
    if (!user) return false
    return user.is_superadmin === true
  }

  /**
   * Check if user can manage a specific organization
   * Superadmins can manage all organizations
   * Org admins can manage their own organizations
   */
  static canManageOrganization(
    user: UserWithOrganizations | null,
    orgId: string
  ): boolean {
    if (!user) return false

    // Superadmins can manage all organizations
    if (user.is_superadmin === true) return true

    // Check if user is an org admin for this organization
    const userOrg = user.organizations?.find((org) => org.id === orgId)
    return userOrg?.role === 'ORG_ADMIN'
  }

  /**
   * Check if user can invite members to an organization
   * Superadmins and org admins can invite
   */
  static canInviteToOrganization(
    user: UserWithOrganizations | null,
    orgId: string
  ): boolean {
    return this.canManageOrganization(user, orgId)
  }

  /**
   * Check if user can change another user's role in an organization
   * Superadmins can change any role
   * Org admins can change roles except for other org admins
   */
  static canChangeUserRole(
    user: UserWithOrganizations | null,
    targetUserId: string,
    orgId: string,
    targetUserRole?: string
  ): boolean {
    if (!user) return false

    // Users cannot change their own role
    if (user.id === targetUserId) return false

    // Superadmins can change any role
    if (user.is_superadmin === true) return true

    // Check if user is an org admin for this organization
    const userOrg = user.organizations?.find((org) => org.id === orgId)
    if (userOrg?.role !== 'ORG_ADMIN') return false

    // Org admins cannot change other org admin roles
    if (targetUserRole === 'ORG_ADMIN') return false

    return true
  }

  /**
   * Check if user can remove a member from an organization
   * Superadmins can remove anyone
   * Org admins can remove non-admins
   */
  static canRemoveMember(
    user: UserWithOrganizations | null,
    targetUserId: string,
    orgId: string,
    targetUserRole?: string
  ): boolean {
    if (!user) return false

    // Users cannot remove themselves
    if (user.id === targetUserId) return false

    // Superadmins can remove anyone
    if (user.is_superadmin === true) return true

    // Check if user is an org admin for this organization
    const userOrg = user.organizations?.find((org) => org.id === orgId)
    if (userOrg?.role !== 'ORG_ADMIN') return false

    // Org admins cannot remove other org admins
    if (targetUserRole === 'ORG_ADMIN') return false

    return true
  }

  /**
   * Check if user can delete an organization
   * Only superadmins can delete organizations
   */
  static canDeleteOrganization(user: UserWithOrganizations | null): boolean {
    if (!user) return false
    return user.is_superadmin === true
  }

  /**
   * Check if user can create an organization
   * Only superadmins can create organizations
   */
  static canCreateOrganization(user: UserWithOrganizations | null): boolean {
    if (!user) return false
    return user.is_superadmin === true
  }

  /**
   * Check if user can edit organization details
   * Superadmins and org admins can edit
   */
  static canEditOrganization(
    user: UserWithOrganizations | null,
    orgId: string
  ): boolean {
    return this.canManageOrganization(user, orgId)
  }

  /**
   * Check if user can view organization members
   * All members of an organization can view other members
   * Superadmins can view all organization members
   */
  static canViewOrganizationMembers(
    user: UserWithOrganizations | null,
    orgId: string
  ): boolean {
    if (!user) return false

    // Superadmins can view all
    if (user.is_superadmin === true) return true

    // Check if user is a member of this organization
    return user.organizations?.some((org) => org.id === orgId) ?? false
  }

  /**
   * Check if user can access the Users & Organizations page.
   * All authenticated users can access it (with role-based view restrictions).
   */
  static canAccessAdminInterface(user: UserWithOrganizations | null): boolean {
    return user !== null
  }

  /**
   * Get list of organizations user can manage
   * Superadmins can manage all (returns null for "all")
   * Others return specific org IDs
   */
  static getManageableOrganizations(
    user: UserWithOrganizations | null
  ): string[] | null {
    if (!user) return []

    // Superadmins can manage all organizations
    if (user.is_superadmin === true) return null

    // Return organizations where user is an org admin
    return (
      user.organizations
        ?.filter((org) => org.role === 'ORG_ADMIN')
        .map((org) => org.id) ?? []
    )
  }

  /**
   * Check if user can perform bulk operations on users
   * Only superadmins can perform bulk operations
   */
  static canPerformBulkOperations(user: UserWithOrganizations | null): boolean {
    if (!user) return false
    return user.is_superadmin === true
  }

  /**
   * Check if user can verify email addresses
   * Only superadmins can manually verify emails
   */
  static canVerifyEmails(user: UserWithOrganizations | null): boolean {
    if (!user) return false
    return user.is_superadmin === true
  }

  /**
   * Check if user can delete users globally
   * Only superadmins can delete users
   */
  static canDeleteUsers(user: UserWithOrganizations | null): boolean {
    if (!user) return false
    return user.is_superadmin === true
  }
}
