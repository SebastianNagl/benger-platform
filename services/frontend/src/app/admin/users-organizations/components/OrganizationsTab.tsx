'use client'

import { OrgApiKeys } from '@/components/organization/OrgApiKeys'
import { Badge } from '@/components/shared/Badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { FilterToolbar } from '@/components/shared/FilterToolbar'
import { Input } from '@/components/shared/Input'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useDeleteConfirm, useErrorAlert } from '@/hooks/useDialogs'
import { Organization, OrganizationMember } from '@/lib/api'
import { InvitationDetails } from '@/lib/api/invitations'
import { organizationsAPI } from '@/lib/api/organizations'
import { UserOrganizationPermissions } from '@/lib/permissions/userOrganizationPermissions'
import {
  BuildingOfficeIcon,
  ChevronDownIcon,
  EnvelopeIcon,
  KeyIcon,
  MagnifyingGlassIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  UserGroupIcon,
  UserPlusIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'

interface OrganizationWithRole extends Organization {
  user_role?: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR'
}

export function OrganizationsTab() {
  const {
    user: currentUser,
    organizations,
    refreshOrganizations,
    apiClient,
  } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()
  const showError = useErrorAlert()
  const confirmDelete = useDeleteConfirm()
  const searchParams = useSearchParams()

  // Combine user with organizations for permissions system
  const userWithOrganizations = useMemo(
    () =>
      currentUser
        ? {
            ...currentUser,
            organizations: organizations.map((org) => ({
              id: org.id,
              role: org.role!,
            })),
          }
        : null,
    [currentUser, organizations]
  )

  const [selectedOrganization, setSelectedOrganization] =
    useState<OrganizationWithRole | null>(null)
  const [members, setMembers] = useState<OrganizationMember[]>([])
  const [invitations, setInvitations] = useState<InvitationDetails[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingMembers, setLoadingMembers] = useState(false)

  // Modal states
  const [showCreateOrgModal, setShowCreateOrgModal] = useState(false)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [showAddUserModal, setShowAddUserModal] = useState(false)
  const [showOrgSwitcher, setShowOrgSwitcher] = useState(false)
  const [showApiKeysModal, setShowApiKeysModal] = useState(false)
  const [isEditingOrg, setIsEditingOrg] = useState(false)

  // Form states
  const [newOrgName, setNewOrgName] = useState('')
  const [newOrgSlug, setNewOrgSlug] = useState('')
  const [newOrgDescription, setNewOrgDescription] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<
    'ANNOTATOR' | 'CONTRIBUTOR' | 'ORG_ADMIN'
  >('ANNOTATOR')
  const [editOrgName, setEditOrgName] = useState('')
  const [editOrgDescription, setEditOrgDescription] = useState('')
  const [orgUpdateLoading, setOrgUpdateLoading] = useState(false)
  const [inviting, setInviting] = useState(false)

  // Add existing user states
  const [allUsers, setAllUsers] = useState<any[]>([])
  const [userSearchQuery, setUserSearchQuery] = useState('')
  const [selectedUserId, setSelectedUserId] = useState('')
  const [selectedUserRole, setSelectedUserRole] = useState<
    'ANNOTATOR' | 'CONTRIBUTOR' | 'ORG_ADMIN'
  >('ANNOTATOR')
  const [addingUser, setAddingUser] = useState(false)

  // Filters
  const [orgSwitcherSearch, setOrgSwitcherSearch] = useState('')
  const [memberSearch, setMemberSearch] = useState('')
  const [memberRoleFilter, setMemberRoleFilter] = useState<
    'all' | 'ANNOTATOR' | 'CONTRIBUTOR' | 'ORG_ADMIN'
  >('all')
  const [memberVerificationFilter, setMemberVerificationFilter] = useState<
    'all' | 'verified' | 'unverified'
  >('all')

  const filteredOrganizations = useMemo(() => {
    const list = Array.isArray(organizations) ? organizations : []
    const q = orgSwitcherSearch.trim().toLowerCase()
    if (!q) return list
    return list.filter((org: any) => {
      return (
        org.name?.toLowerCase().includes(q) ||
        org.description?.toLowerCase().includes(q)
      )
    })
  }, [organizations, orgSwitcherSearch])

  const filteredMembers = useMemo(() => {
    const q = memberSearch.trim().toLowerCase()
    return members.filter((m) => {
      if (
        q &&
        !m.user_name?.toLowerCase().includes(q) &&
        !m.user_email?.toLowerCase().includes(q)
      ) {
        return false
      }
      if (memberRoleFilter !== 'all' && m.role !== memberRoleFilter) return false
      if (memberVerificationFilter !== 'all') {
        if (memberVerificationFilter === 'verified' && !m.email_verified) return false
        if (memberVerificationFilter === 'unverified' && m.email_verified) return false
      }
      return true
    })
  }, [members, memberSearch, memberRoleFilter, memberVerificationFilter])

  const memberHasActiveFilters =
    memberRoleFilter !== 'all' ||
    memberVerificationFilter !== 'all' ||
    memberSearch.trim() !== ''

  const clearMemberFilters = () => {
    setMemberRoleFilter('all')
    setMemberVerificationFilter('all')
    setMemberSearch('')
  }

  const canCreateOrganization =
    UserOrganizationPermissions.canCreateOrganization(userWithOrganizations)

  useEffect(() => {
    if (organizations && organizations.length > 0 && !selectedOrganization) {
      // Check if org is specified in URL
      const orgIdFromUrl = searchParams?.get('org')
      const orgFromUrl = orgIdFromUrl
        ? organizations.find((org) => org.id === orgIdFromUrl)
        : null

      if (orgFromUrl) {
        setSelectedOrganization(orgFromUrl)
      } else {
        // If user is org admin, auto-select their first organization
        const adminOrgs = organizations.filter((org: any) =>
          UserOrganizationPermissions.canManageOrganization(
            userWithOrganizations,
            org.id
          )
        )
        if (adminOrgs.length > 0) {
          setSelectedOrganization(adminOrgs[0])
        } else {
          setSelectedOrganization(organizations[0])
        }
      }
    }
  }, [organizations, selectedOrganization, userWithOrganizations, searchParams])

  const loadOrganizationData = useCallback(async () => {
    if (!selectedOrganization) return

    try {
      setLoadingMembers(true)
      const membersData = await apiClient.getOrganizationMembers(selectedOrganization.id)
      setMembers(membersData)

      // Invitations require ORG_ADMIN or superadmin - gracefully skip for others
      try {
        const invitationsData = await organizationsAPI.getOrganizationInvitations(selectedOrganization.id)
        setInvitations(invitationsData)
      } catch (invErr) {
        console.warn('Failed to load invitations:', invErr)
      }
    } catch (error) {
      console.error('Failed to load organization data:', error)
      showError(t('admin.organizations.errors.loadFailed'), t('admin.organizations.errors.errorTitle'))
    } finally {
      setLoadingMembers(false)
    }
  }, [selectedOrganization, apiClient, showError])

  useEffect(() => {
    if (selectedOrganization) {
      loadOrganizationData()
    }
  }, [selectedOrganization, loadOrganizationData])

  const handleCreateOrganization = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canCreateOrganization) {
      showError(t('admin.organizations.errors.noPermissionCreate'), t('admin.organizations.errors.errorTitle'))
      return
    }

    try {
      setLoading(true)
      const newOrg = await apiClient.createOrganization({
        name: newOrgName,
        display_name: newOrgName,
        slug: newOrgSlug,
        description: newOrgDescription,
      })

      await refreshOrganizations()
      setSelectedOrganization(newOrg)
      // Update URL without triggering navigation
      const params = new URLSearchParams(window.location.search)
      params.set('org', newOrg.id)
      window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`)
      setShowCreateOrgModal(false)
      setNewOrgName('')
      setNewOrgSlug('')
      setNewOrgDescription('')
      addToast(t('toasts.admin.orgCreated'), 'success')
    } catch (error) {
      console.error('Failed to create organization:', error)
      showError(t('admin.organizations.errors.createFailed'), t('admin.organizations.errors.errorTitle'))
    } finally {
      setLoading(false)
    }
  }

  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedOrganization || !inviteEmail) return

    if (
      !UserOrganizationPermissions.canInviteToOrganization(
        userWithOrganizations,
        selectedOrganization.id
      )
    ) {
      showError(t('admin.organizations.errors.noPermissionInvite'), t('admin.organizations.errors.errorTitle'))
      return
    }

    try {
      setInviting(true)
      await organizationsAPI.sendInvitation(selectedOrganization.id, {
        email: inviteEmail,
        role: inviteRole,
      })

      await loadOrganizationData()
      addToast(t('toasts.admin.invitationSent'), 'success')
      setShowInviteModal(false)
      setInviteEmail('')
      setInviteRole('ANNOTATOR')
    } catch (error: any) {
      console.error('Failed to send invitation:', error)
      showError(
        error.response?.data?.detail || t('admin.organizations.errors.inviteFailed'),
        t('admin.organizations.errors.errorTitle')
      )
    } finally {
      setInviting(false)
    }
  }

  const handleRemoveMember = async (userId: string, userRole?: string) => {
    if (!selectedOrganization) return

    if (
      !UserOrganizationPermissions.canRemoveMember(
        userWithOrganizations,
        userId,
        selectedOrganization.id,
        userRole
      )
    ) {
      showError(t('admin.organizations.errors.noPermissionRemove'), t('admin.organizations.errors.errorTitle'))
      return
    }

    const member = members.find((m) => m.user_id === userId)
    const confirmed = await confirmDelete(
      `${member?.user_name || 'member'} from organization`
    )

    if (!confirmed) return

    try {
      await organizationsAPI.removeMember(selectedOrganization.id, userId)
      await loadOrganizationData()
      addToast(t('toasts.admin.memberRemoved'), 'success')
    } catch (error) {
      console.error('Failed to remove member:', error)
      showError(t('admin.organizations.errors.removeFailed'), t('admin.organizations.errors.errorTitle'))
    }
  }

  const handleChangeRole = async (
    userId: string,
    newRole: 'ANNOTATOR' | 'CONTRIBUTOR' | 'ORG_ADMIN',
    currentRole?: string
  ) => {
    if (!selectedOrganization) return

    if (
      !UserOrganizationPermissions.canChangeUserRole(
        userWithOrganizations,
        userId,
        selectedOrganization.id,
        currentRole
      )
    ) {
      showError(t('admin.organizations.errors.noPermissionChangeRole'), t('admin.organizations.errors.errorTitle'))
      return
    }

    try {
      await organizationsAPI.updateMemberRole(
        selectedOrganization.id,
        userId,
        newRole
      )
      await loadOrganizationData()
      addToast(t('toasts.admin.memberRoleUpdated'), 'success')
    } catch (error) {
      console.error('Failed to update role:', error)
      showError(t('admin.organizations.errors.updateRoleFailed'), t('admin.organizations.errors.errorTitle'))
    }
  }

  const handleEditOrgSave = async () => {
    if (!selectedOrganization) return

    if (
      !UserOrganizationPermissions.canEditOrganization(
        userWithOrganizations,
        selectedOrganization.id
      )
    ) {
      showError(t('admin.organizations.errors.noPermissionEdit'), t('admin.organizations.errors.errorTitle'))
      return
    }

    try {
      setOrgUpdateLoading(true)
      await apiClient.updateOrganization(selectedOrganization.id, {
        name: editOrgName,
        description: editOrgDescription,
      })

      await refreshOrganizations()
      setIsEditingOrg(false)
      addToast(t('toasts.admin.orgUpdated'), 'success')
    } catch (error) {
      console.error('Failed to update organization:', error)
      showError(t('admin.organizations.errors.updateFailed'), t('admin.organizations.errors.errorTitle'))
    } finally {
      setOrgUpdateLoading(false)
    }
  }

  const handleDeleteOrganization = async () => {
    if (!selectedOrganization) return

    if (
      !UserOrganizationPermissions.canDeleteOrganization(userWithOrganizations)
    ) {
      showError(t('admin.organizations.errors.noPermissionDelete'), t('admin.organizations.errors.errorTitle'))
      return
    }

    const confirmed = await confirmDelete(
      `organization "${selectedOrganization.name}"`
    )

    if (!confirmed) return

    try {
      await apiClient.deleteOrganization(selectedOrganization.id)
      await refreshOrganizations()
      setSelectedOrganization(null)
      addToast(t('toasts.admin.orgDeleted'), 'success')
    } catch (error) {
      console.error('Failed to delete organization:', error)
      showError(t('admin.organizations.errors.deleteFailed'), t('admin.organizations.errors.errorTitle'))
    }
  }

  const handleCancelInvitation = async (invitationId: string) => {
    if (!selectedOrganization) return

    try {
      await apiClient.cancelInvitation(invitationId)
      await loadOrganizationData()
      addToast(t('toasts.admin.invitationCancelled'), 'success')
    } catch (error) {
      console.error('Failed to cancel invitation:', error)
      showError(t('admin.organizations.errors.cancelInvitationFailed'), t('admin.organizations.errors.errorTitle'))
    }
  }

  const loadAllUsers = async () => {
    try {
      const users = await organizationsAPI.getAllUsers()
      // Filter out users who are already members
      const memberIds = members.map((m) => m.user_id)
      const availableUsers = users.filter((u) => !memberIds.includes(u.id))
      setAllUsers(availableUsers)
    } catch (error) {
      console.error('Failed to load users:', error)
      showError(t('admin.organizations.errors.loadUsersFailed'), t('admin.organizations.errors.errorTitle'))
    }
  }

  const handleAddExistingUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedOrganization || !selectedUserId) return

    if (
      !UserOrganizationPermissions.canInviteToOrganization(
        userWithOrganizations,
        selectedOrganization.id
      )
    ) {
      showError(t('admin.organizations.errors.noPermissionAdd'), t('admin.organizations.errors.errorTitle'))
      return
    }

    try {
      setAddingUser(true)
      await organizationsAPI.addUserToOrganization(
        selectedOrganization.id,
        selectedUserId,
        selectedUserRole
      )

      await loadOrganizationData()
      addToast(t('toasts.admin.userAdded'), 'success')
      setShowAddUserModal(false)
      setSelectedUserId('')
      setSelectedUserRole('ANNOTATOR')
      setUserSearchQuery('')
    } catch (error: any) {
      console.error('Failed to add user:', error)
      showError(error.response?.data?.detail || t('admin.organizations.errors.addUserFailed'), t('admin.organizations.errors.errorTitle'))
    } finally {
      setAddingUser(false)
    }
  }

  const openAddUserModal = () => {
    setShowAddUserModal(true)
    loadAllUsers()
  }

  const canManageOrg = selectedOrganization
    ? UserOrganizationPermissions.canManageOrganization(
        userWithOrganizations,
        selectedOrganization.id
      )
    : false

  return (
    <div className="space-y-6">
      {/* Organization Selector and Actions */}
      <div className="flex items-center justify-between">
        <div className="relative">
          <button
            onClick={() => setShowOrgSwitcher(!showOrgSwitcher)}
            className="inline-flex items-center rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
          >
            <BuildingOfficeIcon className="mr-2 h-4 w-4" />
            {selectedOrganization
              ? selectedOrganization.name
              : t('admin.organizations.selectOrganization')}
            <ChevronDownIcon className="ml-2 h-4 w-4" />
          </button>

          {showOrgSwitcher && (
            <div className="absolute z-10 mt-1 w-72 rounded-md border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
              <div className="relative px-2 py-2">
                <MagnifyingGlassIcon className="pointer-events-none absolute left-5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <Input
                  type="text"
                  placeholder={t('admin.organizations.filters.switcherSearchPlaceholder')}
                  value={orgSwitcherSearch}
                  onChange={(e) => setOrgSwitcherSearch(e.target.value)}
                  className="pl-8 text-sm"
                  autoFocus
                />
              </div>
              <div className="max-h-72 overflow-y-auto">
                {filteredOrganizations.length === 0 ? (
                  <div className="px-4 py-3 text-sm text-zinc-500 dark:text-zinc-400">
                    {t('admin.organizations.noOrganizations')}
                  </div>
                ) : (
                  filteredOrganizations.map((org: any) => (
                    <button
                      key={`org-switcher-${org.id}`}
                      onClick={() => {
                        setSelectedOrganization(org)
                        setShowOrgSwitcher(false)
                        setOrgSwitcherSearch('')
                        // Update URL without triggering navigation
                        const params = new URLSearchParams(window.location.search)
                        params.set('org', org.id)
                        window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`)
                      }}
                      className={`w-full px-4 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-700 ${
                        selectedOrganization?.id === org.id
                          ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300'
                          : 'text-zinc-900 dark:text-zinc-100'
                      }`}
                    >
                      <div className="font-medium">{org.name}</div>
                      {org.description && (
                        <div className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                          {org.description}
                        </div>
                      )}
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          {selectedOrganization && canManageOrg && (
            <Button onClick={() => setShowApiKeysModal(true)} variant="outline">
              <KeyIcon className="h-4 w-4" />
              {t('admin.organizations.apiKeys')}
            </Button>
          )}
          {canCreateOrganization && (
            <Button onClick={() => setShowCreateOrgModal(true)} variant="primary">
              <PlusIcon className="h-4 w-4" />
              {t('admin.organizations.createOrganization')}
            </Button>
          )}
        </div>
      </div>

      {selectedOrganization ? (
        <div className="space-y-6">
          {/* Organization Info */}
          <Card>
            <div className="p-6">
              <div className="flex items-start justify-between">
                <div className="flex items-start">
                  <BuildingOfficeIcon className="mr-3 mt-1 h-8 w-8 text-zinc-400 dark:text-zinc-500" />
                  <div className="flex-1">
                    {isEditingOrg ? (
                      <div className="space-y-3">
                        <input
                          type="text"
                          value={editOrgName}
                          onChange={(e) => setEditOrgName(e.target.value)}
                          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                        />
                        <textarea
                          value={editOrgDescription}
                          onChange={(e) =>
                            setEditOrgDescription(e.target.value)
                          }
                          rows={2}
                          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                        />
                        <div className="flex space-x-2">
                          <Button
                            onClick={handleEditOrgSave}
                            disabled={orgUpdateLoading}
                            variant="primary"
                          >
                            {orgUpdateLoading ? t('admin.organizations.saving') : t('admin.organizations.save')}
                          </Button>
                          <Button
                            onClick={() => setIsEditingOrg(false)}
                            variant="outline"
                          >
                            {t('admin.organizations.cancel')}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <h3 className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
                          {selectedOrganization.name}
                        </h3>
                        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                          {selectedOrganization.description || t('admin.organizations.noDescription')}
                        </p>
                        <div className="mt-2 flex items-center gap-4 text-sm">
                          <span className="text-zinc-500 dark:text-zinc-400">
                            <UserGroupIcon className="mr-1 inline h-4 w-4" />
                            {t('admin.organizations.membersCount', { count: members.length })}
                          </span>
                          {selectedOrganization.user_role && (
                            <Badge variant="secondary">
                              {t('admin.organizations.yourRole', { role: selectedOrganization.user_role })}
                            </Badge>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </div>

                {!isEditingOrg && canManageOrg && (
                  <div className="flex space-x-2">
                    <button
                      onClick={() => {
                        setEditOrgName(selectedOrganization.name)
                        setEditOrgDescription(
                          selectedOrganization.description || ''
                        )
                        setIsEditingOrg(true)
                      }}
                      className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                    >
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    {UserOrganizationPermissions.canDeleteOrganization(
                      userWithOrganizations
                    ) && (
                      <button
                        onClick={handleDeleteOrganization}
                        className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </Card>

          {/* Members Section */}
          <Card>
            <div className="border-b border-zinc-200 p-4 dark:border-zinc-700">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-zinc-900 dark:text-white">
                  {t('admin.organizations.members')}
                </h3>
                {canManageOrg && (
                  <div className="flex gap-2">
                    <Button
                      onClick={() => setShowInviteModal(true)}
                      variant="primary"
                    >
                      <UserPlusIcon className="h-4 w-4" />
                      {t('admin.organizations.inviteMember')}
                    </Button>
                    {UserOrganizationPermissions.canManageGlobalUsers(
                      userWithOrganizations
                    ) && (
                      <Button onClick={openAddUserModal} variant="primary">
                        <UserGroupIcon className="h-4 w-4" />
                        {t('admin.organizations.addExistingUser')}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {loadingMembers ? (
              <div className="p-6 text-center text-zinc-500 dark:text-zinc-400">
                {t('admin.organizations.loadingMembers')}
              </div>
            ) : (
              <>
                <div className="px-4 pt-4">
                  <FilterToolbar
                    searchValue={memberSearch}
                    onSearchChange={setMemberSearch}
                    searchPlaceholder={t('admin.organizations.filters.memberSearchPlaceholder')}
                    searchLabel={t('common.filters.search')}
                    filtersLabel={t('common.filters.filters')}
                    hasActiveFilters={memberHasActiveFilters}
                    onClearFilters={clearMemberFilters}
                    clearLabel={t('common.filters.clearAll')}
                  >
                    <FilterToolbar.Field label={t('admin.organizations.filters.role')}>
                      <Select
                        value={memberRoleFilter}
                        onValueChange={(v) => setMemberRoleFilter(v as typeof memberRoleFilter)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">{t('common.filters.all')}</SelectItem>
                          <SelectItem value="ANNOTATOR">{t('admin.organizations.roleAnnotator')}</SelectItem>
                          <SelectItem value="CONTRIBUTOR">{t('admin.organizations.roleContributor')}</SelectItem>
                          <SelectItem value="ORG_ADMIN">{t('admin.organizations.roleAdmin')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </FilterToolbar.Field>

                    <FilterToolbar.Field label={t('admin.organizations.filters.verification')}>
                      <Select
                        value={memberVerificationFilter}
                        onValueChange={(v) => setMemberVerificationFilter(v as typeof memberVerificationFilter)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">{t('common.filters.all')}</SelectItem>
                          <SelectItem value="verified">{t('admin.organizations.filters.verified')}</SelectItem>
                          <SelectItem value="unverified">{t('admin.organizations.filters.unverified')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </FilterToolbar.Field>
                  </FilterToolbar>
                </div>

                <div className="divide-y divide-zinc-200 dark:divide-zinc-700">
                  {filteredMembers.length === 0 && members.length > 0 && (
                    <div className="p-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
                      {t('admin.organizations.filters.noMatches')}
                    </div>
                  )}
                  {filteredMembers.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex items-center justify-between p-4"
                  >
                    <div className="flex items-center">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-300 dark:bg-zinc-600">
                        <span className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
                          {member.user_name?.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div className="ml-3">
                        <p className="font-medium text-zinc-900 dark:text-white">
                          {member.user_name}
                        </p>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {member.user_email}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {canManageOrg && member.user_id !== currentUser?.id ? (
                        <Select
                          value={member.role}
                          onValueChange={(v) =>
                            handleChangeRole(
                              member.user_id,
                              v as any,
                              member.role
                            )
                          }
                          disabled={
                            !UserOrganizationPermissions.canChangeUserRole(
                              userWithOrganizations,
                              member.user_id,
                              selectedOrganization.id,
                              member.role
                            )
                          }
                          displayValue={
                            member.role === 'ANNOTATOR' ? t('admin.organizations.roleAnnotator') :
                            member.role === 'CONTRIBUTOR' ? t('admin.organizations.roleContributor') :
                            t('admin.organizations.roleAdmin')
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder={t('admin.organizations.roleAnnotator')} />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="ANNOTATOR">{t('admin.organizations.roleAnnotator')}</SelectItem>
                            <SelectItem value="CONTRIBUTOR">{t('admin.organizations.roleContributor')}</SelectItem>
                            <SelectItem value="ORG_ADMIN">{t('admin.organizations.roleAdmin')}</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge variant="secondary">{member.role}</Badge>
                      )}

                      {canManageOrg &&
                        member.user_id !== currentUser?.id &&
                        UserOrganizationPermissions.canRemoveMember(
                          userWithOrganizations,
                          member.user_id,
                          selectedOrganization.id,
                          member.role
                        ) && (
                          <button
                            onClick={() =>
                              handleRemoveMember(member.user_id, member.role)
                            }
                            className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                          >
                            <TrashIcon className="h-4 w-4" />
                          </button>
                        )}
                    </div>
                  </div>
                ))}
                </div>
              </>
            )}
          </Card>

          {/* Pending Invitations */}
          {invitations.length > 0 && (
            <Card>
              <div className="border-b border-zinc-200 p-4 dark:border-zinc-700">
                <h3 className="font-semibold text-zinc-900 dark:text-white">
                  {t('admin.organizations.pendingInvitations')}
                </h3>
              </div>
              <div className="divide-y divide-zinc-200 dark:divide-zinc-700">
                {invitations.map((invitation) => (
                  <div
                    key={invitation.id}
                    className="flex items-center justify-between p-4"
                  >
                    <div className="flex items-center">
                      <EnvelopeIcon className="h-5 w-5 text-zinc-400" />
                      <div className="ml-3">
                        <p className="font-medium text-zinc-900 dark:text-white">
                          {invitation.email}
                        </p>
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {t('admin.organizations.invitedAs', { role: invitation.role })}
                        </p>
                      </div>
                    </div>
                    {canManageOrg && (
                      <button
                        onClick={() => handleCancelInvitation(invitation.id)}
                        className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                      >
                        <XMarkIcon className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Organization API Keys Modal (Issue #1180) */}
          {selectedOrganization && (
            <OrgApiKeys
              organizationId={selectedOrganization.id}
              isAdmin={canManageOrg}
              open={showApiKeysModal}
              onOpenChange={setShowApiKeysModal}
            />
          )}
        </div>
      ) : (
        <Card>
          <div className="p-6 text-center text-zinc-500 dark:text-zinc-400">
            {organizations && organizations.length > 0
              ? t('admin.organizations.selectToViewDetails')
              : t('admin.organizations.noOrganizations')}
          </div>
        </Card>
      )}

      {/* Create Organization Modal */}
      {showCreateOrgModal && (
        <div className="fixed inset-0 z-50 h-full w-full overflow-y-auto bg-zinc-600 bg-opacity-50 dark:bg-zinc-900 dark:bg-opacity-75">
          <div className="relative top-20 mx-auto w-96 rounded-md border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mt-3">
              <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.organizations.createNewOrganization')}
              </h3>
              <form onSubmit={handleCreateOrganization}>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.name')}
                  </label>
                  <input
                    type="text"
                    value={newOrgName}
                    onChange={(e) => setNewOrgName(e.target.value)}
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    required
                  />
                </div>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.slug')}
                  </label>
                  <input
                    type="text"
                    value={newOrgSlug}
                    onChange={(e) => setNewOrgSlug(e.target.value)}
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    required
                  />
                </div>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.description')}
                  </label>
                  <textarea
                    value={newOrgDescription}
                    onChange={(e) => setNewOrgDescription(e.target.value)}
                    rows={3}
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                  />
                </div>
                <div className="flex justify-end space-x-3">
                  <Button
                    type="button"
                    onClick={() => setShowCreateOrgModal(false)}
                    variant="outline"
                  >
                    {t('admin.organizations.cancel')}
                  </Button>
                  <Button type="submit" disabled={loading} variant="primary">
                    {loading ? t('admin.organizations.creating') : t('admin.organizations.create')}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Add Existing User Modal */}
      {showAddUserModal && (
        <div className="fixed inset-0 z-50 h-full w-full overflow-y-auto bg-zinc-600 bg-opacity-50 dark:bg-zinc-900 dark:bg-opacity-75">
          <div className="relative top-20 mx-auto w-96 rounded-md border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mt-3">
              <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.organizations.addExistingUserToOrg')}
              </h3>
              <form onSubmit={handleAddExistingUser}>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.searchUsers')}
                  </label>
                  <input
                    type="text"
                    value={userSearchQuery}
                    onChange={(e) => setUserSearchQuery(e.target.value)}
                    placeholder={t('admin.organizations.searchByNameOrEmail')}
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                  />
                </div>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.selectUser')}
                  </label>
                  <Select
                    value={selectedUserId}
                    onValueChange={setSelectedUserId}
                    displayValue={
                      selectedUserId
                        ? (() => {
                            const u = allUsers.find((u) => u.id === selectedUserId)
                            return u ? `${u.name} (${u.email})` : undefined
                          })()
                        : undefined
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t('admin.organizations.selectAUser')} />
                    </SelectTrigger>
                    <SelectContent>
                      {allUsers
                        .filter(
                          (user) =>
                            userSearchQuery === '' ||
                            user.name
                              ?.toLowerCase()
                              .includes(userSearchQuery.toLowerCase()) ||
                            user.email
                              ?.toLowerCase()
                              .includes(userSearchQuery.toLowerCase())
                        )
                        .map((user) => (
                          <SelectItem key={user.id} value={user.id}>
                            {user.name} ({user.email})
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.role')}
                  </label>
                  <Select
                    value={selectedUserRole}
                    onValueChange={(v) => setSelectedUserRole(v as any)}
                    displayValue={
                      selectedUserRole === 'ANNOTATOR' ? t('admin.organizations.roleAnnotator') :
                      selectedUserRole === 'CONTRIBUTOR' ? t('admin.organizations.roleContributor') :
                      t('admin.organizations.roleAdmin')
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t('admin.organizations.roleAnnotator')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ANNOTATOR">{t('admin.organizations.roleAnnotator')}</SelectItem>
                      <SelectItem value="CONTRIBUTOR">{t('admin.organizations.roleContributor')}</SelectItem>
                      <SelectItem value="ORG_ADMIN">{t('admin.organizations.roleAdmin')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex justify-end space-x-3">
                  <Button
                    type="button"
                    onClick={() => {
                      setShowAddUserModal(false)
                      setSelectedUserId('')
                      setUserSearchQuery('')
                      setSelectedUserRole('ANNOTATOR')
                    }}
                    variant="outline"
                  >
                    {t('admin.organizations.cancel')}
                  </Button>
                  <Button
                    type="submit"
                    disabled={addingUser || !selectedUserId}
                    variant="primary"
                  >
                    {addingUser ? t('admin.organizations.adding') : t('admin.organizations.addUser')}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Invite Member Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 z-50 h-full w-full overflow-y-auto bg-zinc-600 bg-opacity-50 dark:bg-zinc-900 dark:bg-opacity-75">
          <div className="relative top-20 mx-auto w-96 rounded-md border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mt-3">
              <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.organizations.inviteMember')}
              </h3>
              <form onSubmit={handleInviteMember}>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.email')}
                  </label>
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    required
                  />
                </div>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.organizations.role')}
                  </label>
                  <Select
                    value={inviteRole}
                    onValueChange={(v) => setInviteRole(v as any)}
                    displayValue={
                      inviteRole === 'ANNOTATOR' ? t('admin.organizations.roleAnnotator') :
                      inviteRole === 'CONTRIBUTOR' ? t('admin.organizations.roleContributor') :
                      t('admin.organizations.roleAdmin')
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t('admin.organizations.roleAnnotator')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ANNOTATOR">{t('admin.organizations.roleAnnotator')}</SelectItem>
                      <SelectItem value="CONTRIBUTOR">{t('admin.organizations.roleContributor')}</SelectItem>
                      <SelectItem value="ORG_ADMIN">{t('admin.organizations.roleAdmin')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex justify-end space-x-3">
                  <Button
                    type="button"
                    onClick={() => setShowInviteModal(false)}
                    variant="outline"
                  >
                    {t('admin.organizations.cancel')}
                  </Button>
                  <Button type="submit" disabled={inviting} variant="primary">
                    {inviting ? t('admin.organizations.sending') : t('admin.organizations.sendInvitation')}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
