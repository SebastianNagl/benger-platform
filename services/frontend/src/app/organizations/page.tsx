/**
 * Organizations Management Page
 *
 * Allows organization admins to manage their organizations:
 * - View organization details
 * - Invite new members
 * - Manage existing members
 * - Update organization settings
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
import type { Organization } from '@/lib/api/types'
import {
  Dialog,
  DialogBackdrop,
  DialogPanel,
  DialogTitle,
} from '@headlessui/react'
import {
  BuildingOfficeIcon,
  ChevronRightIcon,
  EnvelopeIcon,
  TrashIcon,
  UserGroupIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import React, { useCallback, useEffect, useState } from 'react'

interface OrganizationMember {
  user_id: string
  user_name?: string
  user_email?: string
  role: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR'
  is_active: boolean
  joined_at: string
}

interface OrganizationWithRole extends Organization {
  user_role: 'ORG_ADMIN' | 'CONTRIBUTOR' | 'ANNOTATOR'
}

export default function OrganizationsPage() {
  const router = useRouter()
  const { user, organizations: userOrganizations } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()

  // State
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null)
  const [members, setMembers] = useState<OrganizationMember[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMembers, setLoadingMembers] = useState(false)

  // Always redirect to unified interface
  useEffect(() => {
    router.push('/admin/users-organizations')
  }, [router])

  // Route-level access control
  useEffect(() => {
    if (!user) {
      // User not authenticated, redirect to login
      router.push('/login')
      return
    }

    // Only superadmin can access the organizations management page
    // Regular organization access is handled by the API
    if (!user.is_superadmin) {
      // User doesn't have permission, redirect to dashboard
      addToast(t('admin.accessDeniedDesc'), 'error')
      router.push('/dashboard')
      return
    }
  }, [user, userOrganizations, router, addToast, t])

  // Modal states
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<
    'ANNOTATOR' | 'CONTRIBUTOR' | 'ORG_ADMIN'
  >('ANNOTATOR')
  const [inviting, setInviting] = useState(false)

  // Clear form when modal opens
  useEffect(() => {
    if (showInviteModal) {
      setInviteEmail('')
      setInviteRole('ANNOTATOR')
    }
  }, [showInviteModal])

  // Load user's organizations
  const loadOrganizations = useCallback(async () => {
    try {
      setLoading(true)
      const orgs = await organizationsAPI.getOrganizations()

      // API already filters organizations based on user permissions
      setOrganizations(orgs)

      // Auto-select first organization if only one
      if (orgs.length === 1) {
        setSelectedOrg(orgs[0])
      }
    } catch (error) {
      console.error('Failed to load organizations:', error)
      addToast(t('organizationsPage.failedToLoadOrganizations'), 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    loadOrganizations()
  }, [user, loadOrganizations])

  // Load organization members when org is selected
  const loadMembers = useCallback(async () => {
    if (!selectedOrg) {
      setMembers([])
      return
    }

    try {
      setLoadingMembers(true)
      const orgMembers = await organizationsAPI.getOrganizationMembers(
        selectedOrg.id
      )
      setMembers(orgMembers)
    } catch (error) {
      console.error('Failed to load members:', error)
      addToast(t('organizationsPage.failedToLoadMembers'), 'error')
    } finally {
      setLoadingMembers(false)
    }
  }, [selectedOrg, addToast, t])

  useEffect(() => {
    loadMembers()
  }, [loadMembers])

  const canManageOrg = (org: OrganizationWithRole) => {
    return user?.is_superadmin || org.user_role === 'ORG_ADMIN'
  }

  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedOrg || !inviteEmail) return

    try {
      setInviting(true)

      // Check for existing invitations first
      const existingInvitations =
        await organizationsAPI.getOrganizationInvitations(selectedOrg.id)
      const existingInvite = existingInvitations.find(
        (inv) =>
          inv.email.toLowerCase() === inviteEmail.toLowerCase() &&
          !inv.is_accepted
      )

      if (existingInvite) {
        addToast(
          t('organizationsPage.invitationAlreadyExists', {
            email: inviteEmail,
          }),
          'warning'
        )
        return
      }

      await organizationsAPI.sendInvitation(selectedOrg.id, {
        email: inviteEmail,
        role: inviteRole,
      })

      addToast(t('organizationsPage.invitationSent'), 'success')
      setShowInviteModal(false)
      setInviteEmail('')
      setInviteRole('ANNOTATOR')

      // Reload members list to show updated invitations
      const orgMembers = await organizationsAPI.getOrganizationMembers(
        selectedOrg.id
      )
      setMembers(orgMembers)
    } catch (error: any) {
      console.error('Failed to send invitation:', error)

      // Provide specific error messages based on the error type
      let errorMessage = t('organizationsPage.failedToSendInvitation')

      if (error.response?.data?.detail) {
        const detail = error.response.data.detail

        if (detail.includes('already exists')) {
          errorMessage = t('organizationsPage.invitationAlreadyExists', {
            email: inviteEmail,
          })
        } else if (detail.includes('invalid email')) {
          errorMessage = t('organizationsPage.invalidEmailAddress')
        } else if (detail.includes('rate limit')) {
          errorMessage = t('organizationsPage.rateLimitExceeded')
        } else {
          errorMessage = detail
        }
      } else if (error.message?.includes('Network error')) {
        errorMessage = t('organizationsPage.networkError')
      }

      addToast(errorMessage, 'error')
    } finally {
      setInviting(false)
    }
  }

  const handleRemoveMember = async (userId: string, userName: string) => {
    if (!selectedOrg) return

    if (!confirm(t('organizationsPage.confirmRemoveMember'))) {
      return
    }

    try {
      await organizationsAPI.removeMember(selectedOrg.id, userId)

      // Reload members
      const orgMembers = await organizationsAPI.getOrganizationMembers(
        selectedOrg.id
      )
      setMembers(orgMembers)

      addToast(t('organizationsPage.memberRemoved'), 'success')
    } catch (error) {
      console.error('Failed to remove member:', error)
      addToast(t('organizationsPage.failedToRemoveMember'), 'error')
    }
  }

  const handleChangeRole = async (
    userId: string,
    newRole: 'ANNOTATOR' | 'CONTRIBUTOR' | 'ORG_ADMIN'
  ) => {
    if (!selectedOrg) return

    try {
      await organizationsAPI.updateMemberRole(selectedOrg.id, userId, newRole)

      // Reload members
      const orgMembers = await organizationsAPI.getOrganizationMembers(
        selectedOrg.id
      )
      setMembers(orgMembers)

      addToast(t('organizationsPage.memberRoleUpdated'), 'success')
    } catch (error) {
      console.error('Failed to update role:', error)
      addToast(t('organizationsPage.failedToUpdateRole'), 'error')
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('organizationsPage.loadingOrganizations')}
          </p>
        </div>
      </div>
    )
  }

  if (organizations.length === 0) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="py-12 text-center">
          <BuildingOfficeIcon className="mx-auto mb-4 h-16 w-16 text-zinc-400" />
          <h2 className="mb-2 text-2xl font-bold text-zinc-900 dark:text-white">
            {t('organizationsPage.noOrganizations')}
          </h2>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('organizationsPage.noOrganizationsDesc')}
          </p>
          <Button onClick={() => router.push('/dashboard')} className="mt-6">
            {t('organizationsPage.goToDashboard')}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
          {t('organizationsPage.title')}
        </h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          {t('organizationsPage.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Organization List */}
        <div className="lg:col-span-1">
          <Card>
            <div className="border-b border-zinc-200 p-4 dark:border-zinc-700">
              <h2 className="font-semibold text-zinc-900 dark:text-white">
                {t('organizationsPage.yourOrganizations')}
              </h2>
            </div>
            <div className="p-2">
              {organizations.map((org) => (
                <button
                  key={org.id}
                  onClick={() => setSelectedOrg(org)}
                  className={`w-full rounded-lg px-4 py-3 text-left transition-colors ${
                    selectedOrg?.id === org.id
                      ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20'
                      : 'hover:bg-zinc-50 dark:hover:bg-zinc-800'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-zinc-900 dark:text-white">
                        {org.name}
                      </p>
                      <div className="mt-1 flex items-center gap-2">
                        <Badge variant="secondary">
                          {(org as OrganizationWithRole).user_role}
                        </Badge>
                        {org.member_count && (
                          <span className="text-xs text-zinc-500">
                            {org.member_count} {t('organizationsPage.membersCount')}
                          </span>
                        )}
                      </div>
                    </div>
                    <ChevronRightIcon className="h-5 w-5 flex-shrink-0 text-zinc-400" />
                  </div>
                </button>
              ))}
            </div>
          </Card>
        </div>

        {/* Organization Details */}
        <div className="lg:col-span-2">
          {selectedOrg ? (
            <Card>
              <div className="border-b border-zinc-200 p-6 dark:border-zinc-700">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
                      {selectedOrg.name}
                    </h2>
                    {selectedOrg.description && (
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        {selectedOrg.description}
                      </p>
                    )}
                  </div>
                  {canManageOrg(selectedOrg as OrganizationWithRole) && (
                    <Button
                      onClick={() => setShowInviteModal(true)}
                      variant="primary"
                    >
                      <UserPlusIcon className="mr-2 h-4 w-4" />
                      {t('organizationsPage.inviteMember')}
                    </Button>
                  )}
                </div>
              </div>

              <div className="p-6">
                <h3 className="mb-4 font-medium text-zinc-900 dark:text-white">
                  {t('organizationsPage.members')} ({members.length})
                </h3>

                {loadingMembers ? (
                  <div className="py-8 text-center">
                    <div className="mx-auto h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
                  </div>
                ) : members.length === 0 ? (
                  <div className="py-8 text-center">
                    <UserGroupIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400" />
                    <p className="text-zinc-600 dark:text-zinc-400">
                      {t('organizationsPage.noMembersYet')}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {members.map((member) => (
                      <div
                        key={member.user_id}
                        className="flex items-center justify-between rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-zinc-900 dark:text-white">
                            {member.user_name}
                          </p>
                          <p className="truncate text-sm text-zinc-600 dark:text-zinc-400">
                            {member.user_email}
                          </p>
                          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                            {t('organizationsPage.joined')}
                          </p>
                        </div>

                        <div className="flex items-center gap-3">
                          {canManageOrg(selectedOrg as OrganizationWithRole) ? (
                            <Select
                              value={member.role}
                              onValueChange={(v) =>
                                handleChangeRole(
                                  member.user_id,
                                  v as
                                    | 'ANNOTATOR'
                                    | 'CONTRIBUTOR'
                                    | 'ORG_ADMIN'
                                )
                              }
                              displayValue={
                                member.role === 'ANNOTATOR' ? t('organizationsPage.roles.ANNOTATOR') :
                                member.role === 'CONTRIBUTOR' ? t('organizationsPage.roles.CONTRIBUTOR') :
                                t('organizationsPage.roles.ORG_ADMIN')
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={t('organizationsPage.roles.ANNOTATOR')} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="ANNOTATOR">
                                  {t('organizationsPage.roles.ANNOTATOR')}
                                </SelectItem>
                                <SelectItem value="CONTRIBUTOR">
                                  {t('organizationsPage.roles.CONTRIBUTOR')}
                                </SelectItem>
                                <SelectItem value="ORG_ADMIN">
                                  {t('organizationsPage.roles.ORG_ADMIN')}
                                </SelectItem>
                              </SelectContent>
                            </Select>
                          ) : (
                            <Badge>{member.role.replace('_', ' ')}</Badge>
                          )}

                          {canManageOrg(selectedOrg as OrganizationWithRole) &&
                            member.user_id !== user?.id && (
                              <Button
                                onClick={() =>
                                  handleRemoveMember(
                                    member.user_id,
                                    member.user_name || 'Unknown User'
                                  )
                                }
                                variant="outline"
                                className="text-red-600 hover:text-red-700 dark:text-red-400"
                              >
                                <TrashIcon className="h-4 w-4" />
                              </Button>
                            )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          ) : (
            <Card>
              <div className="p-12 text-center">
                <BuildingOfficeIcon className="mx-auto mb-4 h-16 w-16 text-zinc-400" />
                <p className="text-zinc-600 dark:text-zinc-400">
                  {t('organizationsPage.selectAnOrganization')}
                </p>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* Invite Member Modal */}
      <Dialog
        open={showInviteModal}
        onClose={() => setShowInviteModal(false)}
        className="relative z-50"
      >
        <DialogBackdrop className="fixed inset-0 bg-black/50" />

        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
            <DialogTitle className="mb-4 text-lg font-medium text-zinc-900 dark:text-white">
              {t('organizationsPage.inviteToOrganization')}
            </DialogTitle>

            <form onSubmit={handleInviteMember} className="space-y-4">
              <div>
                <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {t('organizationsPage.emailAddress')}
                </label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-zinc-900 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
                  placeholder={t('organizationsPage.emailPlaceholder')}
                  required
                />
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  {t('organizationsPage.role')}
                </label>
                <Select
                  value={inviteRole}
                  onValueChange={(v) => setInviteRole(v as any)}
                  displayValue={
                    inviteRole === 'ANNOTATOR' ? t('organizationsPage.roleDescriptions.ANNOTATOR') :
                    inviteRole === 'CONTRIBUTOR' ? t('organizationsPage.roleDescriptions.CONTRIBUTOR') :
                    t('organizationsPage.roleDescriptions.ORG_ADMIN')
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t('organizationsPage.roleDescriptions.ANNOTATOR')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ANNOTATOR">
                      {t('organizationsPage.roleDescriptions.ANNOTATOR')}
                    </SelectItem>
                    <SelectItem value="CONTRIBUTOR">
                      {t('organizationsPage.roleDescriptions.CONTRIBUTOR')}
                    </SelectItem>
                    <SelectItem value="ORG_ADMIN">
                      {t('organizationsPage.roleDescriptions.ORG_ADMIN')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowInviteModal(false)}
                >
                  {t('organizationsPage.cancel')}
                </Button>
                <Button type="submit" disabled={inviting || !inviteEmail}>
                  {inviting ? (
                    <>
                      <div className="mr-2 h-4 w-4 animate-spin rounded-full border-b-2 border-white"></div>
                      {t('organizationsPage.sending')}
                    </>
                  ) : (
                    <>
                      <EnvelopeIcon className="mr-2 h-4 w-4" />
                      {t('organizationsPage.sendInvitation')}
                    </>
                  )}
                </Button>
              </div>
            </form>
          </DialogPanel>
        </div>
      </Dialog>
    </div>
  )
}
