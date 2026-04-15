'use client'

import { EmailVerificationModal } from '@/components/admin/EmailVerificationModal'
import { logger } from '@/lib/utils/logger'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useDeleteConfirm, useErrorAlert } from '@/hooks/useDialogs'
import {
  api,
  Organization,
  OrganizationMember,
  OrganizationRole,
  User,
} from '@/lib/api'
import { InvitationDetails } from '@/lib/api/invitations'
import { organizationsAPI } from '@/lib/api/organizations'
import {
  BuildingOfficeIcon,
  CheckCircleIcon,
  CheckIcon,
  ChevronDownIcon,
  EnvelopeIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  UserGroupIcon,
  XCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

export default function AdminUsersPage() {
  const router = useRouter()
  const {
    user: currentUser,
    organizations,
    refreshOrganizations,
    apiClient,
  } = useAuth()
  const { t } = useI18n()
  const showError = useErrorAlert()
  const confirmDelete = useDeleteConfirm()
  const [users, setUsers] = useState<User[]>([])
  const [selectedOrganization, setSelectedOrganization] =
    useState<Organization | null>(null)
  const [members, setMembers] = useState<OrganizationMember[]>([])
  const [invitations, setInvitations] = useState<InvitationDetails[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Active tab state
  const [activeTab, setActiveTab] = useState<'users' | 'organizations'>('users')

  // Modal states
  const [showCreateOrgModal, setShowCreateOrgModal] = useState(false)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [showAddUserModal, setShowAddUserModal] = useState(false)
  const [showOrgSwitcher, setShowOrgSwitcher] = useState(false)
  const [isEditingOrg, setIsEditingOrg] = useState(false)

  // Form states
  const [newOrgName, setNewOrgName] = useState('')
  const [newOrgSlug, setNewOrgSlug] = useState('')
  const [newOrgDescription, setNewOrgDescription] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<OrganizationRole>('ANNOTATOR')
  const [selectedUserId, setSelectedUserId] = useState('')
  const [selectedUserRole, setSelectedUserRole] =
    useState<OrganizationRole>('ANNOTATOR')
  const [editOrgName, setEditOrgName] = useState('')
  const [editOrgDescription, setEditOrgDescription] = useState('')

  // Loading states
  const [updatingUser, setUpdatingUser] = useState<string | null>(null)
  const [deletingUser, setDeletingUser] = useState<string | null>(null)
  const [orgUpdateLoading, setOrgUpdateLoading] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(
    null
  )

  // Email verification states
  const [emailVerificationModal, setEmailVerificationModal] = useState<{
    isOpen: boolean
    user: User | null
    action: 'verify'
  }>({
    isOpen: false,
    user: null,
    action: 'verify',
  })
  const [selectedUsers, setSelectedUsers] = useState<string[]>([])

  const isSuperAdmin = currentUser?.is_superadmin === true

  // Show create organization button to superadmins and users with organizations
  // (backend will validate actual permissions)
  const canCreateOrganization =
    isSuperAdmin || (organizations && organizations.length > 0)

  // Always redirect to unified interface
  useEffect(() => {
    router.push('/admin/users-organizations')
  }, [router])

  useEffect(() => {
    if (isSuperAdmin) {
      fetchUsers()
      if (organizations && organizations.length > 0 && !selectedOrganization) {
        setSelectedOrganization(organizations[0])
      }
    }
  }, [isSuperAdmin, organizations, selectedOrganization])

  const fetchUsers = async () => {
    try {
      const data = await api.getAllUsers()
      setUsers(data)
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('admin.usersPage.failedToLoadUsers')
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const loadOrganizationData = useCallback(async () => {
    if (!selectedOrganization) return

    try {
      const [membersData, invitationsData] = await Promise.all([
        apiClient.getOrganizationMembers(selectedOrganization.id),
        apiClient.listInvitations(selectedOrganization.id),
      ])
      setMembers(membersData)
      setInvitations(invitationsData)
    } catch (error) {
      console.error('Failed to load organization data:', error)
    }
  }, [selectedOrganization, apiClient])

  useEffect(() => {
    if (selectedOrganization && activeTab === 'organizations') {
      loadOrganizationData()
    }
  }, [selectedOrganization, activeTab, loadOrganizationData])

  const handleVerifyEmail = async (user: User, reason?: string) => {
    try {
      // Use the new users API endpoint for direct email verification
      await api.verifyUserEmail(user.id)

      // Update local state based on which tab we're in
      if (activeTab === 'users') {
        setUsers(
          users.map((u) =>
            u.id === user.id
              ? {
                  ...u,
                  email_verified: true,
                  email_verification_method: 'admin' as const,
                }
              : u
          )
        )
      } else {
        // Refresh organization members
        await loadOrganizationData()
      }

      showError(t('admin.usersPage.emailVerifiedSuccess'), t('admin.usersPage.successTitle'))
    } catch (error) {
      showError(t('admin.usersPage.emailVerifyFailed'), t('admin.usersPage.errorTitle'))
    }
  }

  const handleSuperadminChange = async (
    userId: string,
    isSuperadmin: boolean
  ) => {
    setUpdatingUser(userId)
    try {
      const updatedUser = await api.updateUserSuperadminStatus(
        userId,
        isSuperadmin
      )
      logger.debug('Updated user response:', updatedUser)

      // Ensure the updated user has all required fields
      if (updatedUser && updatedUser.id) {
        setUsers((prevUsers) =>
          prevUsers.map((u) => (u.id === userId ? { ...u, ...updatedUser } : u))
        )
      } else {
        console.error('Invalid user response:', updatedUser)
        // Refresh the user list if the response is invalid
        fetchUsers()
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : t('admin.usersPage.updateSuperadminFailed')
      setError(errorMessage)
      console.error('Error updating superadmin status:', error)
      // Refresh the user list on error
      fetchUsers()
    } finally {
      setUpdatingUser(null)
    }
  }

  const handleDeleteUser = async (userId: string) => {
    setDeletingUser(userId)
    try {
      await api.deleteUser(userId)
      setUsers(users.filter((u) => u.id !== userId))
      setShowDeleteConfirm(null)
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('admin.usersPage.failedToDeleteUser')
      setError(errorMessage)
    } finally {
      setDeletingUser(null)
    }
  }

  const handleBulkVerifyEmails = async () => {
    if (selectedUsers.length === 0) {
      showError(t('admin.usersPage.pleaseSelectUsers'), t('admin.usersPage.selectionRequired'))
      return
    }

    // For superadmins in the global users tab, use the first organization or TUM as default
    let orgId = selectedOrganization?.id

    if (!orgId && isSuperAdmin && activeTab === 'users') {
      // Try to use TUM organization as default for superadmin actions
      const tumOrg = organizations?.find(
        (org) => org.slug === 'tum' || org.name.toLowerCase().includes('tum')
      )
      orgId = tumOrg?.id || organizations?.[0]?.id

      if (!orgId) {
        showError(t('admin.usersPage.noOrgsAvailable'), t('admin.usersPage.orgRequired'))
        return
      }
    } else if (!orgId) {
      showError(
        t('admin.usersPage.pleaseSelectOrg'),
        t('admin.usersPage.noOrgSelected')
      )
      return
    }

    try {
      const result = await organizationsAPI.bulkVerifyMemberEmails(
        orgId,
        selectedUsers,
        t('admin.usersPage.bulkVerifyReason')
      )

      // Update local state for successfully verified users
      const successfulIds = result.results
        .filter((r) => r.status === 'success')
        .map((r) => r.user_id)

      setUsers(
        users.map((u) =>
          successfulIds.includes(u.id)
            ? {
                ...u,
                email_verified: true,
                email_verification_method: 'admin' as const,
              }
            : u
        )
      )

      setSelectedUsers([])

      // Show summary
      showError(
        t('admin.usersPage.bulkVerifyResult', {
          success: result.summary.success,
          skipped: result.summary.skipped,
          errors: result.summary.errors,
        }),
        t('admin.usersPage.bulkVerifyComplete')
      )
    } catch (error) {
      showError(t('admin.usersPage.bulkVerifyFailed'), t('admin.usersPage.bulkVerifyError'))
    }
  }

  // Organization management functions
  const handleCreateOrganization = async (e: React.FormEvent) => {
    e.preventDefault()

    try {
      await apiClient.createOrganization({
        name: newOrgName,
        display_name: newOrgName, // Use same value as name for display_name
        slug: newOrgSlug,
        description: newOrgDescription,
      })

      setNewOrgName('')
      setNewOrgSlug('')
      setNewOrgDescription('')
      setShowCreateOrgModal(false)

      await refreshOrganizations()
    } catch (error) {
      console.error('Failed to create organization:', error)
      showError(
        t('admin.users.createOrg.failed'),
        t('admin.usersPage.orgCreationFailed')
      )
    }
  }

  const handleInviteUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedOrganization) return

    try {
      await apiClient.createInvitation(selectedOrganization.id, {
        email: inviteEmail,
        role: inviteRole,
      })

      setInviteEmail('')
      setInviteRole('ANNOTATOR')
      setShowInviteModal(false)

      await loadOrganizationData()
    } catch (error) {
      console.error('Failed to send invitation:', error)
      showError(t('admin.users.invite.failed'), t('admin.usersPage.invitationFailed'))
    }
  }

  const handleOrgRoleChange = async (
    userId: string,
    newRole: OrganizationRole
  ) => {
    if (!selectedOrganization) return

    try {
      await apiClient.updateMemberRole(selectedOrganization.id, userId, newRole)
      await loadOrganizationData()
    } catch (error) {
      console.error('Failed to update member role:', error)
      showError(t('admin.users.members.updateFailed'), t('admin.usersPage.updateFailed'))
    }
  }

  const handleRemoveMember = async (userId: string) => {
    if (!selectedOrganization) return

    const confirmed = await confirmDelete('this member')
    if (!confirmed) return

    try {
      await apiClient.removeMember(selectedOrganization.id, userId)
      await loadOrganizationData()
    } catch (error) {
      console.error('Failed to remove member:', error)
      showError(t('admin.users.members.removeFailed'), t('admin.usersPage.removeMemberFailed'))
    }
  }

  const handleAddUserToOrganization = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedOrganization) return

    try {
      // Debug: Check if user exists in the users list
      const selectedUser = users.find((u) => u.id === selectedUserId)

      await apiClient.addUserToOrganization(
        selectedOrganization.id,
        selectedUserId,
        selectedUserRole
      )

      setSelectedUserId('')
      setSelectedUserRole('ANNOTATOR')
      setShowAddUserModal(false)

      await loadOrganizationData()
    } catch (error: any) {
      console.error('Failed to add user to organization:', error)
      console.error('Error response:', error?.response)
      console.error('Error response data:', error?.response?.data)
      console.error('Error response status:', error?.response?.status)

      // Provide more specific error messages
      let errorMessage = t('admin.users.addUser.failed')

      if (error?.response?.status === 400) {
        // Check if it's the "already a member" error
        if (error?.response?.data?.detail?.includes('already a member')) {
          errorMessage = t('admin.users.addUser.alreadyMember')
        } else {
          errorMessage = `${t('admin.users.addUser.invalidRequest')}: ${error?.response?.data?.detail || ''}`
        }
      } else if (error?.response?.status === 403) {
        errorMessage = t('admin.users.addUser.noPermission')
      } else if (error?.response?.status === 404) {
        errorMessage = t('admin.users.addUser.notFound')
      }

      showError(errorMessage, t('admin.usersPage.addUserFailed'))
    }
  }

  const handleCancelInvitation = async (invitationId: string) => {
    try {
      await apiClient.cancelInvitation(invitationId)
      await loadOrganizationData()
    } catch (error) {
      console.error('Failed to cancel invitation:', error)
      showError(
        t('admin.users.invitations.cancelFailed'),
        t('admin.usersPage.cancelInvitationFailed')
      )
    }
  }

  const handleEditOrgStart = () => {
    if (selectedOrganization) {
      setEditOrgName(selectedOrganization.name)
      setEditOrgDescription(selectedOrganization.description || '')
      setIsEditingOrg(true)
    }
  }

  const handleEditOrgSave = async () => {
    if (!selectedOrganization) return

    try {
      setOrgUpdateLoading(true)
      const updatedOrg = await apiClient.updateOrganization(
        selectedOrganization.id,
        {
          name: editOrgName,
          description: editOrgDescription,
        }
      )

      setSelectedOrganization(updatedOrg)
      await refreshOrganizations()
      setIsEditingOrg(false)
    } catch (error) {
      console.error('Failed to update organization:', error)
      showError(
        t('admin.users.orgDetails.updateFailed'),
        t('admin.usersPage.orgUpdateFailed')
      )
    } finally {
      setOrgUpdateLoading(false)
    }
  }

  const getRoleDisplayName = (role: string) => {
    switch (role) {
      case 'ORG_ADMIN':
        return t('admin.users.roles.orgAdmin')
      case 'CONTRIBUTOR':
        return t('admin.users.roles.contributor')
      case 'ANNOTATOR':
        return t('admin.users.roles.annotator')
      default:
        return role
    }
  }

  if (!isSuperAdmin) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        {/* Breadcrumb */}
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('admin.usersPage.breadcrumb.dashboard'), href: '/dashboard' },
              { label: t('admin.usersPage.breadcrumb.userManagement'), href: '/admin/users' },
            ]}
          />
        </div>

        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-600">
            {t('admin.accessDenied')}
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t('admin.accessDeniedDesc')}
          </p>
        </div>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('admin.usersPage.breadcrumb.dashboard'), href: '/dashboard' },
            { label: t('admin.usersPage.breadcrumb.userManagement'), href: '/admin/users' },
          ]}
        />
      </div>

      <div className="mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('admin.usersPage.title')}
          </h1>
          <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
            {t('admin.usersPage.subtitle')}
          </p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="mb-8">
        <div className="border-b border-zinc-200 dark:border-zinc-700">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('users')}
              className={`border-b-2 px-1 py-2 text-sm font-medium ${
                activeTab === 'users'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
              }`}
              data-testid="admin-users-tab"
            >
              <UserGroupIcon className="mr-2 inline h-5 w-5" />
              {t('admin.usersPage.tabs.globalUserRoles')}
            </button>
            <button
              onClick={() => setActiveTab('organizations')}
              className={`border-b-2 px-1 py-2 text-sm font-medium ${
                activeTab === 'organizations'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
              }`}
              data-testid="admin-organizations-tab"
            >
              <BuildingOfficeIcon className="mr-2 inline h-5 w-5" />
              {t('admin.usersPage.tabs.organizationRoles')}
            </button>
          </nav>
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Users Tab */}
      {activeTab === 'users' && (
        <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          {/* Bulk actions bar */}
          {selectedUsers.length > 0 && (
            <div className="flex items-center justify-between bg-indigo-50 px-6 py-3 dark:bg-indigo-900/20">
              <span className="text-sm text-indigo-700 dark:text-indigo-300">
                {selectedUsers.length > 1
                  ? t('admin.usersPage.usersSelected', { count: selectedUsers.length })
                  : t('admin.usersPage.userSelected', { count: selectedUsers.length })}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={handleBulkVerifyEmails}
                  className="rounded-md bg-green-600 px-3 py-1 text-sm font-medium text-white hover:bg-green-700"
                >
                  {t('admin.usersPage.bulkVerifyEmails')}
                </button>
                <button
                  onClick={() => setSelectedUsers([])}
                  className="rounded-md border border-zinc-300 bg-white px-3 py-1 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"
                >
                  {t('admin.usersPage.clearSelection')}
                </button>
              </div>
            </div>
          )}

          {loading ? (
            <div className="p-6 text-center text-zinc-500 dark:text-zinc-400">
              {t('admin.usersPage.loadingUsers')}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700">
                <thead className="bg-zinc-50 dark:bg-zinc-800">
                  <tr>
                    <th className="px-6 py-3 text-left">
                      <input
                        type="checkbox"
                        checked={
                          selectedUsers.length === users.length &&
                          users.length > 0
                        }
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedUsers(users.map((u) => u.id))
                          } else {
                            setSelectedUsers([])
                          }
                        }}
                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('admin.usersPage.columnUser')}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('admin.usersPage.columnEmail')}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('admin.usersPage.columnEmailVerification')}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('admin.usersPage.columnSuperadminStatus')}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                      {t('admin.usersPage.columnActions')}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
                  {Array.isArray(users) &&
                    users.map((user) => (
                      <tr key={`user-row-${user.id}`}>
                        <td className="px-6 py-4">
                          <input
                            type="checkbox"
                            checked={selectedUsers.includes(user.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedUsers([...selectedUsers, user.id])
                              } else {
                                setSelectedUsers(
                                  selectedUsers.filter((id) => id !== user.id)
                                )
                              }
                            }}
                            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                          />
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          <div className="flex items-center">
                            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-300 dark:bg-zinc-600">
                              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
                                {user.name?.charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div className="ml-3">
                              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                                {user.name}
                              </div>
                              <div className="text-sm text-zinc-500 dark:text-zinc-400">
                                {user.username}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-zinc-900 dark:text-zinc-100">
                          {user.email}
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          <div className="flex items-center gap-2">
                            {user.email_verified ? (
                              <div className="flex items-center gap-1">
                                <CheckCircleIcon className="h-5 w-5 text-green-500" />
                                <span className="text-sm text-green-600 dark:text-green-400">
                                  {t('admin.usersPage.verified')}
                                  {user.email_verification_method ===
                                    'admin' && (
                                    <span className="ml-1 text-xs text-zinc-500 dark:text-zinc-400">
                                      ({t('admin.usersPage.adminMethod')})
                                    </span>
                                  )}
                                </span>
                              </div>
                            ) : (
                              <div className="flex items-center gap-1">
                                <XCircleIcon className="h-5 w-5 text-red-500" />
                                <span className="text-sm text-red-600 dark:text-red-400">
                                  {t('admin.usersPage.unverified')}
                                </span>
                              </div>
                            )}

                            {/* Verification actions */}
                            {isSuperAdmin && !user.email_verified && (
                              <button
                                onClick={() => {
                                  setEmailVerificationModal({
                                    isOpen: true,
                                    user: user,
                                    action: 'verify',
                                  })
                                }}
                                className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300"
                                title={t('admin.usersPage.verifyEmail')}
                              >
                                <CheckIcon className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          {user.id === currentUser?.id ||
                          updatingUser === user.id ? (
                            <span className="text-sm text-zinc-600 dark:text-zinc-400">
                              {updatingUser === user.id
                                ? t('admin.usersPage.updating')
                                : user.is_superadmin
                                  ? t('admin.usersPage.superadmin')
                                  : t('admin.usersPage.regularUser')}
                            </span>
                          ) : (
                            <Select
                              value={user.is_superadmin ? 'superadmin' : 'user'}
                              onValueChange={(v) =>
                                handleSuperadminChange(
                                  user.id,
                                  v === 'superadmin'
                                )
                              }
                              disabled={updatingUser === user.id}
                              displayValue={user.is_superadmin ? t('admin.usersPage.superadmin') : t('admin.usersPage.regularUser')}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={t('admin.usersPage.regularUser')} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="user">{t('admin.usersPage.regularUser')}</SelectItem>
                                <SelectItem value="superadmin">{t('admin.usersPage.superadmin')}</SelectItem>
                              </SelectContent>
                            </Select>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm font-medium">
                          {user.id !== currentUser?.id && (
                            <div className="flex space-x-2">
                              <button
                                onClick={() => setShowDeleteConfirm(user.id)}
                                disabled={deletingUser === user.id}
                                className="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300"
                              >
                                {deletingUser === user.id ? (
                                  t('admin.usersPage.deleting')
                                ) : (
                                  <TrashIcon className="h-4 w-4" />
                                )}
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Organizations Tab */}
      {activeTab === 'organizations' && (
        <div>
          {/* Organization Selector and Actions */}
          <div className="mb-6 flex items-center justify-between">
            <div className="relative">
              <button
                onClick={() => setShowOrgSwitcher(!showOrgSwitcher)}
                className="inline-flex items-center rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
              >
                <BuildingOfficeIcon className="mr-2 h-4 w-4" />
                {selectedOrganization
                  ? selectedOrganization.name
                  : t('admin.usersPage.selectOrganization')}
                <ChevronDownIcon className="ml-2 h-4 w-4" />
              </button>

              {showOrgSwitcher && (
                <div className="absolute z-10 mt-1 w-64 rounded-md border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
                  {organizations &&
                    Array.isArray(organizations) &&
                    organizations.map((org) => (
                      <button
                        key={`org-switcher-${org.id}`}
                        onClick={() => {
                          setSelectedOrganization(org)
                          setShowOrgSwitcher(false)
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
                    ))}
                </div>
              )}
            </div>

            {canCreateOrganization && (
              <button
                onClick={() => setShowCreateOrgModal(true)}
                className="inline-flex items-center rounded-md border border-transparent bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
              >
                <PlusIcon className="mr-2 h-4 w-4" />
                {t('admin.usersPage.createOrganization')}
              </button>
            )}
          </div>

          {selectedOrganization ? (
            <div className="space-y-6">
              {/* Organization Info */}
              <div className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
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
                            <button
                              onClick={handleEditOrgSave}
                              disabled={orgUpdateLoading}
                              className="inline-flex items-center rounded-md bg-green-600 px-3 py-1 text-sm font-medium text-white hover:bg-green-700"
                            >
                              <CheckIcon className="mr-1 h-4 w-4" />
                              {t('admin.usersPage.save')}
                            </button>
                            <button
                              onClick={() => setIsEditingOrg(false)}
                              disabled={orgUpdateLoading}
                              className="inline-flex items-center rounded-md border border-zinc-300 bg-white px-3 py-1 text-sm font-medium text-zinc-700 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300"
                            >
                              <XMarkIcon className="mr-1 h-4 w-4" />
                              {t('admin.usersPage.cancel')}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                            {selectedOrganization.name}
                          </h2>
                          {selectedOrganization.description && (
                            <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                              {selectedOrganization.description}
                            </p>
                          )}
                          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
                            {members.length} {t('admin.usersPage.members')} • {t('admin.usersPage.created')}{' '}
                            {new Date(
                              selectedOrganization.created_at
                            ).toLocaleDateString()}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                  {!isEditingOrg && (
                    <button
                      onClick={handleEditOrgStart}
                      className="inline-flex items-center rounded-md border border-zinc-300 bg-white px-3 py-1 text-sm font-medium text-zinc-700 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300"
                    >
                      <PencilIcon className="mr-1 h-4 w-4" />
                      {t('admin.usersPage.edit')}
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* Members */}
                <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
                  <div className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                        {t('admin.usersPage.members')}
                      </h3>
                      <div className="flex space-x-2">
                        <button
                          onClick={() => setShowInviteModal(true)}
                          className="inline-flex items-center rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white hover:bg-indigo-700"
                        >
                          <EnvelopeIcon className="mr-1 h-4 w-4" />
                          {t('admin.usersPage.invite')}
                        </button>
                        <button
                          onClick={() => setShowAddUserModal(true)}
                          className="inline-flex items-center rounded-md bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700"
                        >
                          <PlusIcon className="mr-1 h-4 w-4" />
                          {t('admin.usersPage.addUser')}
                        </button>
                      </div>
                    </div>
                  </div>
                  <div className="max-h-96 overflow-y-auto">
                    {members.map((member) => (
                      <div
                        key={`member-${member.user_id}-${member.organization_id}`}
                        className="border-b border-zinc-200 px-6 py-4 last:border-b-0 dark:border-zinc-700"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center">
                            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-300 dark:bg-zinc-600">
                              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-200">
                                {member.user_name?.charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div className="ml-3">
                              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                                {member.user_name}
                              </p>
                              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                                {member.user_email}
                              </p>
                              {/* Email verification status */}
                              <div className="mt-1 flex items-center gap-1">
                                {member.email_verified ? (
                                  <>
                                    <CheckCircleIcon className="h-4 w-4 text-green-500" />
                                    <span className="text-xs text-green-600 dark:text-green-400">
                                      {t('admin.usersPage.verified')}
                                      {member.email_verification_method ===
                                        'admin' && (
                                        <span className="ml-1 text-xs text-zinc-500 dark:text-zinc-400">
                                          ({t('admin.usersPage.adminMethod')})
                                        </span>
                                      )}
                                    </span>
                                  </>
                                ) : (
                                  <>
                                    <XCircleIcon className="h-4 w-4 text-red-500" />
                                    <span className="text-xs text-red-600 dark:text-red-400">
                                      {t('admin.usersPage.unverified')}
                                    </span>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            {/* Email verification actions */}
                            {!member.email_verified && (
                              <button
                                onClick={() => {
                                  // Create a temporary User object from member data for the modal
                                  const tempUser: User = {
                                    id: member.user_id,
                                    username: member.user_name || '',
                                    email: member.user_email || '',
                                    email_verified: member.email_verified,
                                    email_verification_method:
                                      member.email_verification_method,
                                    name: member.user_name || '',
                                    is_superadmin: false,
                                    is_active: member.is_active,
                                    created_at: member.joined_at,
                                  }
                                  setEmailVerificationModal({
                                    isOpen: true,
                                    user: tempUser,
                                    action: 'verify',
                                  })
                                }}
                                className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300"
                                title={t('admin.usersPage.verifyEmail')}
                              >
                                <CheckIcon className="h-4 w-4" />
                              </button>
                            )}

                            <Select
                              value={member.role}
                              onValueChange={(v) =>
                                handleOrgRoleChange(
                                  member.user_id,
                                  v as any
                                )
                              }
                              displayValue={
                                member.role === 'ANNOTATOR' ? t('admin.usersPage.roles.annotator') :
                                member.role === 'CONTRIBUTOR' ? t('admin.usersPage.roles.contributor') :
                                t('admin.usersPage.roles.admin')
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={t('admin.usersPage.roles.annotator')} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="ANNOTATOR">{t('admin.usersPage.roles.annotator')}</SelectItem>
                                <SelectItem value="CONTRIBUTOR">{t('admin.usersPage.roles.contributor')}</SelectItem>
                                <SelectItem value="ORG_ADMIN">{t('admin.usersPage.roles.admin')}</SelectItem>
                              </SelectContent>
                            </Select>
                            <button
                              onClick={() => handleRemoveMember(member.user_id)}
                              className="text-red-600 hover:text-red-800 dark:text-red-400"
                            >
                              <TrashIcon className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Invitations */}
                <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
                  <div className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
                    <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                      {t('admin.usersPage.pendingInvitations')}
                    </h3>
                  </div>
                  <div className="max-h-96 overflow-y-auto">
                    {invitations.length === 0 ? (
                      <div className="p-6 text-center text-zinc-500 dark:text-zinc-400">
                        {t('admin.usersPage.noPendingInvitations')}
                      </div>
                    ) : (
                      invitations.map((invitation) => (
                        <div
                          key={`invitation-${invitation.id}`}
                          className="border-b border-zinc-200 px-6 py-4 last:border-b-0 dark:border-zinc-700"
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                                {invitation.email}
                              </p>
                              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                                {getRoleDisplayName(invitation.role)} • {t('admin.usersPage.expires')}{' '}
                                {new Date(
                                  invitation.expires_at
                                ).toLocaleDateString()}
                              </p>
                            </div>
                            <button
                              onClick={() =>
                                handleCancelInvitation(invitation.id)
                              }
                              className="text-red-600 hover:text-red-800 dark:text-red-400"
                            >
                              {t('admin.usersPage.cancel')}
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-lg bg-white p-8 text-center shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
              <BuildingOfficeIcon className="mx-auto h-12 w-12 text-zinc-400" />
              <h3 className="mt-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.usersPage.noOrgSelected')}
              </h3>
              <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
                {t('admin.usersPage.noOrgSelectedDesc')}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 h-full w-full overflow-y-auto bg-zinc-600 bg-opacity-50 dark:bg-zinc-900 dark:bg-opacity-75">
          <div className="relative top-20 mx-auto w-96 rounded-md border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mt-3 text-center">
              <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.usersPage.deleteUser')}
              </h3>
              <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
                {t('admin.usersPage.deleteUserConfirm')}
              </p>
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowDeleteConfirm(null)}
                  className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"
                >
                  {t('admin.usersPage.cancel')}
                </button>
                <button
                  onClick={() => handleDeleteUser(showDeleteConfirm)}
                  className="rounded-md border border-transparent bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
                >
                  {t('admin.usersPage.delete')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Create Organization Modal */}
      {showCreateOrgModal && (
        <div className="fixed inset-0 z-50 h-full w-full overflow-y-auto bg-zinc-600 bg-opacity-50 dark:bg-zinc-900 dark:bg-opacity-75">
          <div className="relative top-20 mx-auto w-96 rounded-md border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mt-3">
              <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.usersPage.createNewOrganization')}
              </h3>
              <form onSubmit={handleCreateOrganization}>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.usersPage.organizationName')}
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
                    {t('admin.usersPage.urlSlug')}
                  </label>
                  <input
                    type="text"
                    value={newOrgSlug}
                    onChange={(e) =>
                      setNewOrgSlug(
                        e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-')
                      )
                    }
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                    required
                  />
                </div>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.usersPage.descriptionOptional')}
                  </label>
                  <textarea
                    value={newOrgDescription}
                    onChange={(e) => setNewOrgDescription(e.target.value)}
                    rows={3}
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
                  />
                </div>
                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => setShowCreateOrgModal(false)}
                    className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300"
                  >
                    {t('admin.usersPage.cancel')}
                  </button>
                  <button
                    type="submit"
                    className="rounded-md border border-transparent bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
                  >
                    {t('admin.usersPage.create')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Invite User Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 z-50 h-full w-full overflow-y-auto bg-zinc-600 bg-opacity-50 dark:bg-zinc-900 dark:bg-opacity-75">
          <div className="relative top-20 mx-auto w-96 rounded-md border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mt-3">
              <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.usersPage.inviteNewMember')}
              </h3>
              <form onSubmit={handleInviteUser}>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.usersPage.emailAddress')}
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
                    {t('admin.usersPage.role')}
                  </label>
                  <Select
                    value={inviteRole}
                    onValueChange={(v) => setInviteRole(v as any)}
                    displayValue={
                      inviteRole === 'ANNOTATOR' ? t('admin.usersPage.roles.annotator') :
                      inviteRole === 'CONTRIBUTOR' ? t('admin.usersPage.roles.contributor') :
                      t('admin.usersPage.roles.admin')
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t('admin.usersPage.roles.annotator')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ANNOTATOR">{t('admin.usersPage.roles.annotator')}</SelectItem>
                      <SelectItem value="CONTRIBUTOR">{t('admin.usersPage.roles.contributor')}</SelectItem>
                      <SelectItem value="ORG_ADMIN">{t('admin.usersPage.roles.admin')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => setShowInviteModal(false)}
                    className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300"
                  >
                    {t('admin.usersPage.cancel')}
                  </button>
                  <button
                    type="submit"
                    className="rounded-md border border-transparent bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                  >
                    {t('admin.usersPage.sendInvitation')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Add User to Organization Modal */}
      {showAddUserModal && (
        <div className="fixed inset-0 z-50 h-full w-full overflow-y-auto bg-zinc-600 bg-opacity-50 dark:bg-zinc-900 dark:bg-opacity-75">
          <div className="relative top-20 mx-auto w-96 rounded-md border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mt-3">
              <h3 className="mb-4 text-lg font-medium text-zinc-900 dark:text-zinc-100">
                {t('admin.usersPage.addUserToOrganization')}
              </h3>
              <form onSubmit={handleAddUserToOrganization}>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.usersPage.selectUser')}
                  </label>
                  <Select
                    value={selectedUserId}
                    onValueChange={setSelectedUserId}
                    displayValue={
                      selectedUserId
                        ? (() => {
                            const u = users.find((u) => u.id === selectedUserId)
                            return u ? `${u.name} (${u.email})` : ''
                          })()
                        : undefined
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t('admin.usersPage.chooseUser')} />
                    </SelectTrigger>
                    <SelectContent>
                      {users
                        .filter((u) => !members.find((m) => m.user_id === u.id))
                        .map((u) => (
                          <SelectItem key={`user-option-${u.id}`} value={u.id}>
                            {u.name} ({u.email})
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="mb-4">
                  <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                    {t('admin.usersPage.role')}
                  </label>
                  <Select
                    value={selectedUserRole}
                    onValueChange={(v) => setSelectedUserRole(v as any)}
                    displayValue={
                      selectedUserRole === 'ANNOTATOR' ? t('admin.usersPage.roles.annotator') :
                      selectedUserRole === 'CONTRIBUTOR' ? t('admin.usersPage.roles.contributor') :
                      t('admin.usersPage.roles.admin')
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t('admin.usersPage.roles.annotator')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ANNOTATOR">{t('admin.usersPage.roles.annotator')}</SelectItem>
                      <SelectItem value="CONTRIBUTOR">{t('admin.usersPage.roles.contributor')}</SelectItem>
                      <SelectItem value="ORG_ADMIN">{t('admin.usersPage.roles.admin')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => setShowAddUserModal(false)}
                    className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300"
                  >
                    {t('admin.usersPage.cancel')}
                  </button>
                  <button
                    type="submit"
                    className="rounded-md border border-transparent bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                  >
                    {t('admin.usersPage.addUser')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Email Verification Modal */}
      <EmailVerificationModal
        isOpen={emailVerificationModal.isOpen}
        onClose={() =>
          setEmailVerificationModal({
            isOpen: false,
            user: null,
            action: 'verify',
          })
        }
        user={emailVerificationModal.user}
        action={emailVerificationModal.action}
        onConfirm={async (reason) => {
          if (emailVerificationModal.user) {
            await handleVerifyEmail(emailVerificationModal.user, reason)
          }
        }}
      />
    </ResponsiveContainer>
  )
}
