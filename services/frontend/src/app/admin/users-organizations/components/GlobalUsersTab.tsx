'use client'

import { EmailVerificationModal } from '@/components/admin/EmailVerificationModal'
import { FilterToolbar } from '@/components/shared/FilterToolbar'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useDeleteConfirm, useErrorAlert } from '@/hooks/useDialogs'
import { api, User } from '@/lib/api'
import { UserOrganizationPermissions } from '@/lib/permissions/userOrganizationPermissions'
import {
  CheckCircleIcon,
  CheckIcon,
  TrashIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useState } from 'react'

type VerificationFilter = 'all' | 'verified' | 'unverified'
type SuperadminFilter = 'all' | 'superadmin' | 'regular'
type UserSortBy = 'name' | 'email' | 'created_at'
type SortOrder = 'asc' | 'desc'

export function GlobalUsersTab() {
  const { user: currentUser, organizations } = useAuth()
  const { t } = useI18n()
  const showError = useErrorAlert()
  const confirmDelete = useDeleteConfirm()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [updatingUser, setUpdatingUser] = useState<string | null>(null)
  const [deletingUser, setDeletingUser] = useState<string | null>(null)
  const [selectedUsers, setSelectedUsers] = useState<string[]>([])
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(
    null
  )

  // Filter/sort state
  const [searchQuery, setSearchQuery] = useState('')
  const [verificationFilter, setVerificationFilter] =
    useState<VerificationFilter>('all')
  const [superadminFilter, setSuperadminFilter] =
    useState<SuperadminFilter>('all')
  const [sortBy, setSortBy] = useState<UserSortBy>('name')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')

  const filteredUsers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    const matchesSearch = (u: User) => {
      if (!query) return true
      return (
        u.name?.toLowerCase().includes(query) ||
        u.username?.toLowerCase().includes(query) ||
        u.email?.toLowerCase().includes(query)
      )
    }
    const matchesVerification = (u: User) => {
      if (verificationFilter === 'all') return true
      return verificationFilter === 'verified'
        ? !!u.email_verified
        : !u.email_verified
    }
    const matchesSuperadmin = (u: User) => {
      if (superadminFilter === 'all') return true
      return superadminFilter === 'superadmin'
        ? !!u.is_superadmin
        : !u.is_superadmin
    }
    const direction = sortOrder === 'asc' ? 1 : -1
    return [...users]
      .filter(
        (u) => matchesSearch(u) && matchesVerification(u) && matchesSuperadmin(u)
      )
      .sort((a, b) => {
        const aVal = (a[sortBy] ?? '').toString().toLowerCase()
        const bVal = (b[sortBy] ?? '').toString().toLowerCase()
        if (aVal < bVal) return -1 * direction
        if (aVal > bVal) return 1 * direction
        return 0
      })
  }, [users, searchQuery, verificationFilter, superadminFilter, sortBy, sortOrder])

  const hasActiveFilters =
    verificationFilter !== 'all' ||
    superadminFilter !== 'all' ||
    sortBy !== 'name' ||
    sortOrder !== 'asc' ||
    searchQuery.trim() !== ''

  const clearAllFilters = () => {
    setVerificationFilter('all')
    setSuperadminFilter('all')
    setSortBy('name')
    setSortOrder('asc')
    setSearchQuery('')
  }

  // Combine user with organizations for permissions system
  const userWithOrganizations = currentUser
    ? {
        ...currentUser,
        organizations: organizations.map((org) => ({
          id: org.id,
          role: org.role!,
        })),
      }
    : null

  // Email verification modal state
  const [emailVerificationModal, setEmailVerificationModal] = useState<{
    isOpen: boolean
    user: User | null
    action: 'verify'
  }>({
    isOpen: false,
    user: null,
    action: 'verify',
  })

  const canManageUsers = UserOrganizationPermissions.canManageGlobalUsers(
    userWithOrganizations
  )

  const fetchUsers = useCallback(async () => {
    try {
      const data = await api.getAllUsers()
      setUsers(data)
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('admin.users.updateFailed')
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    if (canManageUsers) {
      fetchUsers()
    }
  }, [canManageUsers, fetchUsers])

  const handleVerifyEmail = async (user: User, reason?: string) => {
    try {
      await api.verifyUserEmail(user.id)
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
      showError(t('admin.users.emailVerifiedSuccess'), t('admin.users.successTitle'))
    } catch (error) {
      showError(t('admin.users.emailVerifyFailed'), t('admin.users.errorTitle'))
    }
  }

  const handleBulkVerifyEmails = async () => {
    const unverifiedUsers = users.filter(
      (u) => selectedUsers.includes(u.id) && !u.email_verified
    )

    if (unverifiedUsers.length === 0) {
      showError(t('admin.users.noUnverifiedSelected'), t('admin.users.infoTitle'))
      return
    }

    try {
      await Promise.all(
        unverifiedUsers.map((user) => api.verifyUserEmail(user.id))
      )

      setUsers(
        users.map((u) =>
          selectedUsers.includes(u.id)
            ? {
                ...u,
                email_verified: true,
                email_verification_method: 'admin' as const,
              }
            : u
        )
      )

      setSelectedUsers([])
      showError(
        unverifiedUsers.length > 1
          ? t('admin.users.bulkVerifySuccessPlural', { count: unverifiedUsers.length })
          : t('admin.users.bulkVerifySuccess', { count: unverifiedUsers.length }),
        t('admin.users.successTitle')
      )
    } catch (error) {
      showError(t('admin.users.bulkVerifyFailed'), t('admin.users.errorTitle'))
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

      if (updatedUser && updatedUser.id) {
        setUsers((prevUsers) =>
          prevUsers.map((u) => (u.id === userId ? { ...u, ...updatedUser } : u))
        )
      } else {
        // Refresh the user list if the response is invalid
        fetchUsers()
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('admin.users.updateFailed')
      showError(errorMessage, 'Error')
    } finally {
      setUpdatingUser(null)
    }
  }

  const handleDeleteUser = async (userId: string) => {
    const user = users.find((u) => u.id === userId)
    if (!user) return

    const confirmed = await confirmDelete(`user "${user.name}"`)

    if (!confirmed) {
      setShowDeleteConfirm(null)
      return
    }

    setDeletingUser(userId)
    try {
      await api.deleteUser(userId)
      setUsers(users.filter((u) => u.id !== userId))
      showError(t('admin.users.deleteSuccess'), t('admin.users.successTitle'))
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : t('admin.users.deleteFailed')
      showError(errorMessage, 'Error')
    } finally {
      setDeletingUser(null)
      setShowDeleteConfirm(null)
    }
  }

  useEffect(() => {
    if (showDeleteConfirm) {
      handleDeleteUser(showDeleteConfirm)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- handleDeleteUser is stable within this effect's purpose
  }, [showDeleteConfirm])

  if (!canManageUsers) {
    return (
      <div className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
        <p className="text-center text-zinc-500 dark:text-zinc-400">
          {t('admin.users.noPermission')}
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
        <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
      </div>
    )
  }

  return (
    <>
      <FilterToolbar
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t('admin.users.filters.searchPlaceholder')}
        searchLabel={t('common.filters.search')}
        filtersLabel={t('common.filters.filters')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearAllFilters}
        clearLabel={t('common.filters.clearAll', 'Clear filters')}
        rightExtras={
          <span className="text-sm text-zinc-600 dark:text-zinc-400">
            {t('admin.users.filters.totalUsers', { count: filteredUsers.length })}
          </span>
        }
      >
        <FilterToolbar.Field label={t('admin.users.filters.verification')}>
          <Select
            value={verificationFilter}
            onValueChange={(v) => setVerificationFilter(v as VerificationFilter)}
            displayValue={
              verificationFilter === 'all'
                ? t('common.filters.all')
                : verificationFilter === 'verified'
                  ? t('admin.users.filters.verified')
                  : t('admin.users.filters.unverified')
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('common.filters.all')}</SelectItem>
              <SelectItem value="verified">{t('admin.users.filters.verified')}</SelectItem>
              <SelectItem value="unverified">{t('admin.users.filters.unverified')}</SelectItem>
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('admin.users.filters.role')}>
          <Select
            value={superadminFilter}
            onValueChange={(v) => setSuperadminFilter(v as SuperadminFilter)}
            displayValue={
              superadminFilter === 'all'
                ? t('common.filters.all')
                : superadminFilter === 'superadmin'
                  ? t('admin.users.filters.superadmin')
                  : t('admin.users.filters.regularUser')
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('common.filters.all')}</SelectItem>
              <SelectItem value="superadmin">{t('admin.users.filters.superadmin')}</SelectItem>
              <SelectItem value="regular">{t('admin.users.filters.regularUser')}</SelectItem>
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('common.filters.sortBy')}>
          <div className="flex gap-2">
            <Select
              value={sortBy}
              onValueChange={(v) => setSortBy(v as UserSortBy)}
              displayValue={
                sortBy === 'name'
                  ? t('admin.users.filters.sortName')
                  : sortBy === 'email'
                    ? t('admin.users.filters.sortEmail')
                    : t('admin.users.filters.sortCreated')
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="name">{t('admin.users.filters.sortName')}</SelectItem>
                <SelectItem value="email">{t('admin.users.filters.sortEmail')}</SelectItem>
                <SelectItem value="created_at">{t('admin.users.filters.sortCreated')}</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={sortOrder}
              onValueChange={(v) => setSortOrder(v as SortOrder)}
              displayValue={
                sortOrder === 'asc' ? t('common.filters.asc') : t('common.filters.desc')
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="asc">{t('common.filters.asc')}</SelectItem>
                <SelectItem value="desc">{t('common.filters.desc')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </FilterToolbar.Field>
      </FilterToolbar>

      <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
        {/* Bulk actions bar */}
        {selectedUsers.length > 0 && (
          <div className="flex items-center justify-between bg-indigo-50 px-6 py-3 dark:bg-indigo-900/20">
            <span className="text-sm text-indigo-700 dark:text-indigo-300">
              {selectedUsers.length > 1
                ? t('admin.users.usersSelected', { count: selectedUsers.length })
                : t('admin.users.userSelected', { count: selectedUsers.length })}
            </span>
            <div className="flex gap-2">
              <button
                onClick={handleBulkVerifyEmails}
                className="rounded-md bg-green-600 px-3 py-1 text-sm font-medium text-white hover:bg-green-700"
              >
                {t('admin.users.bulkVerifyEmails')}
              </button>
              <button
                onClick={() => setSelectedUsers([])}
                className="rounded-md border border-zinc-300 bg-white px-3 py-1 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"
              >
                {t('admin.users.clearSelection')}
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="p-6 text-center text-zinc-500 dark:text-zinc-400">
            {t('admin.users.loading')}
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
                        filteredUsers.length > 0 &&
                        filteredUsers.every((u) =>
                          selectedUsers.includes(u.id)
                        )
                      }
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedUsers(filteredUsers.map((u) => u.id))
                        } else {
                          setSelectedUsers([])
                        }
                      }}
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    {t('admin.users.columnUser')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    {t('admin.users.columnEmail')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    {t('admin.users.columnEmailVerification')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    {t('admin.users.columnSuperadminStatus')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                    {t('admin.users.columnActions')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
                {filteredUsers.length === 0 && users.length > 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-6 py-8 text-center text-sm text-zinc-500 dark:text-zinc-400"
                    >
                      {t('admin.users.filters.noMatches')}
                    </td>
                  </tr>
                )}
                {filteredUsers.map((user) => (
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
                                {t('admin.users.verified')}
                                {user.email_verification_method === 'admin' && (
                                  <span className="ml-1 text-xs text-zinc-500 dark:text-zinc-400">
                                    ({t('admin.users.adminMethod')})
                                  </span>
                                )}
                              </span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1">
                              <XCircleIcon className="h-5 w-5 text-red-500" />
                              <span className="text-sm text-red-600 dark:text-red-400">
                                {t('admin.users.unverified')}
                              </span>
                            </div>
                          )}

                          {/* Verification actions */}
                          {!user.email_verified && (
                            <button
                              onClick={() => {
                                setEmailVerificationModal({
                                  isOpen: true,
                                  user: user,
                                  action: 'verify',
                                })
                              }}
                              className="text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300"
                              title={t('admin.users.verifyEmail')}
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
                              ? t('admin.users.updating')
                              : user.is_superadmin
                                ? t('admin.users.superadmin')
                                : t('admin.users.regularUser')}
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
                            displayValue={user.is_superadmin ? t('admin.users.superadmin') : t('admin.users.regularUser')}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder={t('admin.users.regularUser')} />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="user">
                                {t('admin.users.regularUser')}
                              </SelectItem>
                              <SelectItem value="superadmin">{t('admin.users.superadmin')}</SelectItem>
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
                                t('admin.users.deleting')
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

      {/* Email Verification Modal */}
      {emailVerificationModal.isOpen && emailVerificationModal.user && (
        <EmailVerificationModal
          isOpen={emailVerificationModal.isOpen}
          onClose={() => {
            setEmailVerificationModal({
              isOpen: false,
              user: null,
              action: 'verify',
            })
          }}
          user={emailVerificationModal.user}
          action={emailVerificationModal.action}
          onConfirm={async (reason) => {
            if (emailVerificationModal.user) {
              await handleVerifyEmail(emailVerificationModal.user, reason)
            }
            setEmailVerificationModal({
              isOpen: false,
              user: null,
              action: 'verify',
            })
          }}
        />
      )}
    </>
  )
}
