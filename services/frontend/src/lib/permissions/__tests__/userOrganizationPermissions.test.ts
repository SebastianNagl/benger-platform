import {
  UserOrganizationPermissions,
  UserWithOrganizations,
} from '../userOrganizationPermissions'

describe('UserOrganizationPermissions', () => {
  const mockSuperadmin: UserWithOrganizations = {
    id: 'superadmin-1',
    email: 'superadmin@example.com',
    username: 'superadmin',
    is_superadmin: true,
    is_active: true,
    organizations: [],
  }

  const mockOrgAdmin: UserWithOrganizations = {
    id: 'user-1',
    email: 'admin@example.com',
    username: 'admin',
    is_superadmin: false,
    is_active: true,
    organizations: [
      { id: 'org-1', role: 'ORG_ADMIN' },
      { id: 'org-2', role: 'CONTRIBUTOR' },
    ],
  }

  const mockContributor: UserWithOrganizations = {
    id: 'user-2',
    email: 'contributor@example.com',
    username: 'contributor',
    is_superadmin: false,
    is_active: true,
    organizations: [{ id: 'org-1', role: 'CONTRIBUTOR' }],
  }

  const mockAnnotator: UserWithOrganizations = {
    id: 'user-3',
    email: 'annotator@example.com',
    username: 'annotator',
    is_superadmin: false,
    is_active: true,
    organizations: [{ id: 'org-1', role: 'ANNOTATOR' }],
  }

  const mockUserNoOrgs: UserWithOrganizations = {
    id: 'user-4',
    email: 'noorg@example.com',
    username: 'noorg',
    is_superadmin: false,
    is_active: true,
    organizations: [],
  }

  describe('canManageGlobalUsers', () => {
    it('returns true for superadmin', () => {
      expect(
        UserOrganizationPermissions.canManageGlobalUsers(mockSuperadmin)
      ).toBe(true)
    })

    it('returns false for org admin', () => {
      expect(
        UserOrganizationPermissions.canManageGlobalUsers(mockOrgAdmin)
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canManageGlobalUsers(mockContributor)
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(UserOrganizationPermissions.canManageGlobalUsers(null)).toBe(false)
    })
  })

  describe('canManageOrganization', () => {
    it('returns true for superadmin on any organization', () => {
      expect(
        UserOrganizationPermissions.canManageOrganization(
          mockSuperadmin,
          'org-1'
        )
      ).toBe(true)
      expect(
        UserOrganizationPermissions.canManageOrganization(
          mockSuperadmin,
          'org-999'
        )
      ).toBe(true)
    })

    it('returns true for org admin on their organization', () => {
      expect(
        UserOrganizationPermissions.canManageOrganization(mockOrgAdmin, 'org-1')
      ).toBe(true)
    })

    it('returns false for org admin on different organization', () => {
      expect(
        UserOrganizationPermissions.canManageOrganization(mockOrgAdmin, 'org-3')
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canManageOrganization(
          mockContributor,
          'org-1'
        )
      ).toBe(false)
    })

    it('returns false for annotator', () => {
      expect(
        UserOrganizationPermissions.canManageOrganization(
          mockAnnotator,
          'org-1'
        )
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(
        UserOrganizationPermissions.canManageOrganization(null, 'org-1')
      ).toBe(false)
    })

    it('returns false for user not in organization', () => {
      expect(
        UserOrganizationPermissions.canManageOrganization(
          mockOrgAdmin,
          'org-not-member'
        )
      ).toBe(false)
    })
  })

  describe('canInviteToOrganization', () => {
    it('returns true for superadmin', () => {
      expect(
        UserOrganizationPermissions.canInviteToOrganization(
          mockSuperadmin,
          'org-1'
        )
      ).toBe(true)
    })

    it('returns true for org admin', () => {
      expect(
        UserOrganizationPermissions.canInviteToOrganization(
          mockOrgAdmin,
          'org-1'
        )
      ).toBe(true)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canInviteToOrganization(
          mockContributor,
          'org-1'
        )
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(
        UserOrganizationPermissions.canInviteToOrganization(null, 'org-1')
      ).toBe(false)
    })
  })

  describe('canChangeUserRole', () => {
    it('returns true for superadmin changing any role', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockSuperadmin,
          'user-2',
          'org-1',
          'ORG_ADMIN'
        )
      ).toBe(true)
    })

    it('returns false for user changing their own role', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockOrgAdmin,
          'user-1',
          'org-1',
          'CONTRIBUTOR'
        )
      ).toBe(false)
    })

    it('returns true for org admin changing contributor role', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockOrgAdmin,
          'user-2',
          'org-1',
          'CONTRIBUTOR'
        )
      ).toBe(true)
    })

    it('returns true for org admin changing annotator role', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockOrgAdmin,
          'user-3',
          'org-1',
          'ANNOTATOR'
        )
      ).toBe(true)
    })

    it('returns false for org admin changing another org admin role', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockOrgAdmin,
          'user-5',
          'org-1',
          'ORG_ADMIN'
        )
      ).toBe(false)
    })

    it('returns false for org admin on organization they do not admin', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockOrgAdmin,
          'user-2',
          'org-2',
          'CONTRIBUTOR'
        )
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockContributor,
          'user-2',
          'org-1',
          'ANNOTATOR'
        )
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          null,
          'user-2',
          'org-1',
          'CONTRIBUTOR'
        )
      ).toBe(false)
    })

    it('returns true for org admin when target role is undefined', () => {
      expect(
        UserOrganizationPermissions.canChangeUserRole(
          mockOrgAdmin,
          'user-2',
          'org-1'
        )
      ).toBe(true)
    })
  })

  describe('canRemoveMember', () => {
    it('returns true for superadmin removing anyone', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockSuperadmin,
          'user-2',
          'org-1',
          'ORG_ADMIN'
        )
      ).toBe(true)
    })

    it('returns false for user removing themselves', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockOrgAdmin,
          'user-1',
          'org-1',
          'ORG_ADMIN'
        )
      ).toBe(false)
    })

    it('returns true for org admin removing contributor', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockOrgAdmin,
          'user-2',
          'org-1',
          'CONTRIBUTOR'
        )
      ).toBe(true)
    })

    it('returns true for org admin removing annotator', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockOrgAdmin,
          'user-3',
          'org-1',
          'ANNOTATOR'
        )
      ).toBe(true)
    })

    it('returns false for org admin removing another org admin', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockOrgAdmin,
          'user-5',
          'org-1',
          'ORG_ADMIN'
        )
      ).toBe(false)
    })

    it('returns false for org admin on organization they do not admin', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockOrgAdmin,
          'user-2',
          'org-2',
          'CONTRIBUTOR'
        )
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockContributor,
          'user-2',
          'org-1',
          'ANNOTATOR'
        )
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          null,
          'user-2',
          'org-1',
          'CONTRIBUTOR'
        )
      ).toBe(false)
    })

    it('returns true for org admin when target role is undefined', () => {
      expect(
        UserOrganizationPermissions.canRemoveMember(
          mockOrgAdmin,
          'user-2',
          'org-1'
        )
      ).toBe(true)
    })
  })

  describe('canDeleteOrganization', () => {
    it('returns true for superadmin', () => {
      expect(
        UserOrganizationPermissions.canDeleteOrganization(mockSuperadmin)
      ).toBe(true)
    })

    it('returns false for org admin', () => {
      expect(
        UserOrganizationPermissions.canDeleteOrganization(mockOrgAdmin)
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canDeleteOrganization(mockContributor)
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(UserOrganizationPermissions.canDeleteOrganization(null)).toBe(
        false
      )
    })
  })

  describe('canCreateOrganization', () => {
    it('returns true for superadmin', () => {
      expect(
        UserOrganizationPermissions.canCreateOrganization(mockSuperadmin)
      ).toBe(true)
    })

    it('returns false for org admin', () => {
      expect(
        UserOrganizationPermissions.canCreateOrganization(mockOrgAdmin)
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canCreateOrganization(mockContributor)
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(UserOrganizationPermissions.canCreateOrganization(null)).toBe(
        false
      )
    })
  })

  describe('canEditOrganization', () => {
    it('returns true for superadmin', () => {
      expect(
        UserOrganizationPermissions.canEditOrganization(mockSuperadmin, 'org-1')
      ).toBe(true)
    })

    it('returns true for org admin on their organization', () => {
      expect(
        UserOrganizationPermissions.canEditOrganization(mockOrgAdmin, 'org-1')
      ).toBe(true)
    })

    it('returns false for org admin on different organization', () => {
      expect(
        UserOrganizationPermissions.canEditOrganization(mockOrgAdmin, 'org-3')
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canEditOrganization(
          mockContributor,
          'org-1'
        )
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(
        UserOrganizationPermissions.canEditOrganization(null, 'org-1')
      ).toBe(false)
    })
  })

  describe('canViewOrganizationMembers', () => {
    it('returns true for superadmin on any organization', () => {
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          mockSuperadmin,
          'org-1'
        )
      ).toBe(true)
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          mockSuperadmin,
          'org-999'
        )
      ).toBe(true)
    })

    it('returns true for org admin on their organization', () => {
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          mockOrgAdmin,
          'org-1'
        )
      ).toBe(true)
    })

    it('returns true for contributor on their organization', () => {
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          mockContributor,
          'org-1'
        )
      ).toBe(true)
    })

    it('returns true for annotator on their organization', () => {
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          mockAnnotator,
          'org-1'
        )
      ).toBe(true)
    })

    it('returns false for user not in organization', () => {
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          mockOrgAdmin,
          'org-3'
        )
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(null, 'org-1')
      ).toBe(false)
    })

    it('returns false for user with no organizations', () => {
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          mockUserNoOrgs,
          'org-1'
        )
      ).toBe(false)
    })

    it('returns false for user with undefined organizations', () => {
      const userUndefinedOrgs = { ...mockUserNoOrgs, organizations: undefined }
      expect(
        UserOrganizationPermissions.canViewOrganizationMembers(
          userUndefinedOrgs,
          'org-1'
        )
      ).toBe(false)
    })
  })

  describe('canAccessAdminInterface', () => {
    it('returns true for superadmin', () => {
      expect(
        UserOrganizationPermissions.canAccessAdminInterface(mockSuperadmin)
      ).toBe(true)
    })

    it('returns true for org admin', () => {
      expect(
        UserOrganizationPermissions.canAccessAdminInterface(mockOrgAdmin)
      ).toBe(true)
    })

    it('returns true for contributor', () => {
      expect(
        UserOrganizationPermissions.canAccessAdminInterface(mockContributor)
      ).toBe(true)
    })

    it('returns true for annotator', () => {
      expect(
        UserOrganizationPermissions.canAccessAdminInterface(mockAnnotator)
      ).toBe(true)
    })

    it('returns true for user with no organizations', () => {
      expect(
        UserOrganizationPermissions.canAccessAdminInterface(mockUserNoOrgs)
      ).toBe(true)
    })

    it('returns false for null user', () => {
      expect(UserOrganizationPermissions.canAccessAdminInterface(null)).toBe(
        false
      )
    })

    it('returns true for user with undefined organizations', () => {
      const userUndefinedOrgs = { ...mockUserNoOrgs, organizations: undefined }
      expect(
        UserOrganizationPermissions.canAccessAdminInterface(userUndefinedOrgs)
      ).toBe(true)
    })
  })

  describe('getManageableOrganizations', () => {
    it('returns null for superadmin (can manage all)', () => {
      expect(
        UserOrganizationPermissions.getManageableOrganizations(mockSuperadmin)
      ).toBeNull()
    })

    it('returns org IDs where user is org admin', () => {
      const result =
        UserOrganizationPermissions.getManageableOrganizations(mockOrgAdmin)
      expect(result).toEqual(['org-1'])
    })

    it('returns empty array for contributor', () => {
      expect(
        UserOrganizationPermissions.getManageableOrganizations(mockContributor)
      ).toEqual([])
    })

    it('returns empty array for annotator', () => {
      expect(
        UserOrganizationPermissions.getManageableOrganizations(mockAnnotator)
      ).toEqual([])
    })

    it('returns empty array for user with no organizations', () => {
      expect(
        UserOrganizationPermissions.getManageableOrganizations(mockUserNoOrgs)
      ).toEqual([])
    })

    it('returns empty array for null user', () => {
      expect(
        UserOrganizationPermissions.getManageableOrganizations(null)
      ).toEqual([])
    })

    it('returns empty array for user with undefined organizations', () => {
      const userUndefinedOrgs = { ...mockUserNoOrgs, organizations: undefined }
      expect(
        UserOrganizationPermissions.getManageableOrganizations(
          userUndefinedOrgs
        )
      ).toEqual([])
    })

    it('returns multiple org IDs for user who is admin of multiple orgs', () => {
      const multiAdminUser: UserWithOrganizations = {
        ...mockOrgAdmin,
        organizations: [
          { id: 'org-1', role: 'ORG_ADMIN' },
          { id: 'org-2', role: 'ORG_ADMIN' },
          { id: 'org-3', role: 'CONTRIBUTOR' },
        ],
      }
      const result =
        UserOrganizationPermissions.getManageableOrganizations(multiAdminUser)
      expect(result).toEqual(['org-1', 'org-2'])
    })
  })

  describe('canPerformBulkOperations', () => {
    it('returns true for superadmin', () => {
      expect(
        UserOrganizationPermissions.canPerformBulkOperations(mockSuperadmin)
      ).toBe(true)
    })

    it('returns false for org admin', () => {
      expect(
        UserOrganizationPermissions.canPerformBulkOperations(mockOrgAdmin)
      ).toBe(false)
    })

    it('returns false for contributor', () => {
      expect(
        UserOrganizationPermissions.canPerformBulkOperations(mockContributor)
      ).toBe(false)
    })

    it('returns false for null user', () => {
      expect(UserOrganizationPermissions.canPerformBulkOperations(null)).toBe(
        false
      )
    })
  })

  describe('canVerifyEmails', () => {
    it('returns true for superadmin', () => {
      expect(UserOrganizationPermissions.canVerifyEmails(mockSuperadmin)).toBe(
        true
      )
    })

    it('returns false for org admin', () => {
      expect(UserOrganizationPermissions.canVerifyEmails(mockOrgAdmin)).toBe(
        false
      )
    })

    it('returns false for contributor', () => {
      expect(UserOrganizationPermissions.canVerifyEmails(mockContributor)).toBe(
        false
      )
    })

    it('returns false for null user', () => {
      expect(UserOrganizationPermissions.canVerifyEmails(null)).toBe(false)
    })
  })

  describe('canDeleteUsers', () => {
    it('returns true for superadmin', () => {
      expect(UserOrganizationPermissions.canDeleteUsers(mockSuperadmin)).toBe(
        true
      )
    })

    it('returns false for org admin', () => {
      expect(UserOrganizationPermissions.canDeleteUsers(mockOrgAdmin)).toBe(
        false
      )
    })

    it('returns false for contributor', () => {
      expect(UserOrganizationPermissions.canDeleteUsers(mockContributor)).toBe(
        false
      )
    })

    it('returns false for null user', () => {
      expect(UserOrganizationPermissions.canDeleteUsers(null)).toBe(false)
    })
  })
})
