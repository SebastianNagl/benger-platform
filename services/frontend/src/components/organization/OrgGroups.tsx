'use client'

import { useI18n } from '@/contexts/I18nContext'
import { Button } from '@/components/shared/Button'
import {
  organizationsAPI,
  type OrganizationGroup,
  type OrganizationGroupMember,
} from '@/lib/api/organizations'
import type { OrganizationMember } from '@/lib/api/types'
import {
  PencilIcon,
  TrashIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { Dialog } from '@headlessui/react'
import { useCallback, useEffect, useState } from 'react'

interface OrgGroupsProps {
  organizationId: string
  /** Org admin (or superadmin): full group CRUD + all member management. */
  isAdmin: boolean
  /** Group admin of at least one group: member management for own groups. */
  canManageGroups?: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface Message {
  type: 'success' | 'error'
  text: string
}

const inputClassName =
  'w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100'

export function OrgGroups({
  organizationId,
  isAdmin,
  canManageGroups = false,
  open,
  onOpenChange,
}: OrgGroupsProps) {
  const { t } = useI18n()

  const [groups, setGroups] = useState<OrganizationGroup[]>([])
  const [groupsLoading, setGroupsLoading] = useState(false)
  const [message, setMessage] = useState<Message | null>(null)

  // Create form (org admins only)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [creating, setCreating] = useState(false)

  // Inline edit (org admins only)
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editIsActive, setEditIsActive] = useState(true)
  const [savingEdit, setSavingEdit] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState<Record<string, boolean>>({})

  // Member sub-view
  const [selectedGroup, setSelectedGroup] = useState<OrganizationGroup | null>(
    null
  )
  const [members, setMembers] = useState<OrganizationGroupMember[]>([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [orgMembers, setOrgMembers] = useState<OrganizationMember[]>([])
  const [addUserId, setAddUserId] = useState('')
  const [addAsGroupAdmin, setAddAsGroupAdmin] = useState(false)
  const [addingMember, setAddingMember] = useState(false)
  const [memberLoading, setMemberLoading] = useState<Record<string, boolean>>({})

  const fetchGroups = useCallback(async () => {
    setGroupsLoading(true)
    try {
      const rows = await organizationsAPI.getGroups(organizationId)
      setGroups(Array.isArray(rows) ? rows : [])
    } catch {
      setGroups([])
    } finally {
      setGroupsLoading(false)
    }
  }, [organizationId])

  useEffect(() => {
    if (open) {
      setMessage(null)
      setSelectedGroup(null)
      setEditingGroupId(null)
      fetchGroups()
    }
  }, [open, fetchGroups])

  const fetchGroupMembers = useCallback(
    async (groupId: string) => {
      setMembersLoading(true)
      try {
        const rows = await organizationsAPI.getGroupMembers(
          organizationId,
          groupId
        )
        setMembers(Array.isArray(rows) ? rows : [])
      } catch (error: any) {
        setMembers([])
        setMessage({
          type: 'error',
          text:
            error.response?.data?.detail ||
            t('admin.organizations.groups.loadMembersFailed'),
        })
      } finally {
        setMembersLoading(false)
      }
    },
    [organizationId, t]
  )

  const fetchOrgMembers = useCallback(async () => {
    try {
      const rows = await organizationsAPI.getOrganizationMembers(organizationId)
      setOrgMembers(Array.isArray(rows) ? rows : [])
    } catch {
      setOrgMembers([])
    }
  }, [organizationId])

  const openMembersView = (group: OrganizationGroup) => {
    setMessage(null)
    setSelectedGroup(group)
    setAddUserId('')
    setAddAsGroupAdmin(false)
    fetchGroupMembers(group.id)
    fetchOrgMembers()
  }

  const closeMembersView = () => {
    setSelectedGroup(null)
    setMembers([])
    setMessage(null)
    // Member counts may have changed while managing members.
    fetchGroups()
  }

  const handleCreateGroup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isAdmin || !newName.trim()) return

    setCreating(true)
    setMessage(null)
    try {
      await organizationsAPI.createGroup(organizationId, {
        name: newName.trim(),
        description: newDescription.trim() || undefined,
      })
      setMessage({
        type: 'success',
        text: t('admin.organizations.groups.created'),
      })
      setNewName('')
      setNewDescription('')
      await fetchGroups()
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('admin.organizations.groups.createFailed'),
      })
    } finally {
      setCreating(false)
    }
  }

  const startEdit = (group: OrganizationGroup) => {
    setEditingGroupId(group.id)
    setEditName(group.name)
    setEditDescription(group.description || '')
    setEditIsActive(group.is_active)
    setMessage(null)
  }

  const handleSaveEdit = async () => {
    if (!isAdmin || !editingGroupId || !editName.trim()) return

    setSavingEdit(true)
    setMessage(null)
    try {
      await organizationsAPI.updateGroup(organizationId, editingGroupId, {
        name: editName.trim(),
        description: editDescription.trim(),
        is_active: editIsActive,
      })
      setMessage({
        type: 'success',
        text: t('admin.organizations.groups.updated'),
      })
      setEditingGroupId(null)
      await fetchGroups()
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('admin.organizations.groups.updateFailed'),
      })
    } finally {
      setSavingEdit(false)
    }
  }

  const handleDeleteGroup = async (group: OrganizationGroup) => {
    if (!isAdmin) return

    setDeleteLoading((prev) => ({ ...prev, [group.id]: true }))
    setMessage(null)
    try {
      await organizationsAPI.deleteGroup(organizationId, group.id)
      setMessage({
        type: 'success',
        text: t('admin.organizations.groups.deleted'),
      })
      await fetchGroups()
    } catch (error: any) {
      // 409 carries a detail explaining which project attachments / group
      // keys still reference the group — surface it verbatim.
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('admin.organizations.groups.deleteFailed'),
      })
    } finally {
      setDeleteLoading((prev) => ({ ...prev, [group.id]: false }))
    }
  }

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedGroup || !addUserId) return

    setAddingMember(true)
    setMessage(null)
    try {
      await organizationsAPI.addGroupMember(organizationId, selectedGroup.id, {
        user_id: addUserId,
        is_group_admin: addAsGroupAdmin,
      })
      setMessage({
        type: 'success',
        text: t('admin.organizations.groups.memberAdded'),
      })
      setAddUserId('')
      setAddAsGroupAdmin(false)
      await fetchGroupMembers(selectedGroup.id)
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('admin.organizations.groups.addMemberFailed'),
      })
    } finally {
      setAddingMember(false)
    }
  }

  const handleToggleGroupAdmin = async (member: OrganizationGroupMember) => {
    if (!selectedGroup) return

    setMemberLoading((prev) => ({ ...prev, [member.user_id]: true }))
    setMessage(null)
    try {
      await organizationsAPI.updateGroupMember(
        organizationId,
        selectedGroup.id,
        member.user_id,
        { is_group_admin: !member.is_group_admin }
      )
      setMessage({
        type: 'success',
        text: t('admin.organizations.groups.memberUpdated'),
      })
      await fetchGroupMembers(selectedGroup.id)
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('admin.organizations.groups.updateMemberFailed'),
      })
    } finally {
      setMemberLoading((prev) => ({ ...prev, [member.user_id]: false }))
    }
  }

  const handleRemoveMember = async (member: OrganizationGroupMember) => {
    if (!selectedGroup) return

    setMemberLoading((prev) => ({ ...prev, [member.user_id]: true }))
    setMessage(null)
    try {
      await organizationsAPI.removeGroupMember(
        organizationId,
        selectedGroup.id,
        member.user_id
      )
      setMessage({
        type: 'success',
        text: t('admin.organizations.groups.memberRemoved'),
      })
      await fetchGroupMembers(selectedGroup.id)
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('admin.organizations.groups.removeMemberFailed'),
      })
    } finally {
      setMemberLoading((prev) => ({ ...prev, [member.user_id]: false }))
    }
  }

  // Group admins without org-admin rights only manage their own groups.
  const canManageMembersOf = (group: OrganizationGroup) =>
    isAdmin || (canManageGroups && group.is_group_admin)

  const memberIds = new Set(members.map((m) => m.user_id))
  const addableMembers = orgMembers.filter((m) => !memberIds.has(m.user_id))

  return (
    <Dialog
      open={open}
      onClose={() => onOpenChange(false)}
      className="relative z-50"
    >
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {selectedGroup
                  ? t('admin.organizations.groups.membersTitle', {
                      name: selectedGroup.name,
                    })
                  : t('admin.organizations.groups.dialogTitle')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('admin.organizations.groups.dialogDescription')}
              </p>
            </div>
            <button
              onClick={() => onOpenChange(false)}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label="Close modal"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="max-h-[70vh] overflow-y-auto px-6 py-4">
            <div className="space-y-6">
              {/* Message banner */}
              {message && (
                <div
                  data-testid="org-groups-message"
                  className={`rounded-md border p-4 text-sm ${
                    message.type === 'success'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                      : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                  }`}
                >
                  {message.text}
                </div>
              )}

              {selectedGroup ? (
                /* ── Member sub-view ─────────────────────────────────── */
                <div className="space-y-4">
                  <button
                    type="button"
                    onClick={closeMembersView}
                    data-testid="group-members-back"
                    className="text-sm font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
                  >
                    ← {t('admin.organizations.groups.back')}
                  </button>

                  {canManageMembersOf(selectedGroup) && (
                    <form
                      onSubmit={handleAddMember}
                      className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50"
                    >
                      <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                        {t('admin.organizations.groups.addMemberLabel')}
                      </label>
                      <select
                        value={addUserId}
                        onChange={(e) => setAddUserId(e.target.value)}
                        data-testid="group-add-member-select"
                        className={inputClassName}
                      >
                        <option value="">
                          {t('admin.organizations.groups.addMemberPlaceholder')}
                        </option>
                        {addableMembers.map((member) => (
                          <option key={member.user_id} value={member.user_id}>
                            {member.user_name} ({member.user_email})
                          </option>
                        ))}
                      </select>
                      {addableMembers.length === 0 && (
                        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                          {t('admin.organizations.groups.noAvailableMembers')}
                        </p>
                      )}
                      <div className="mt-3 flex items-center justify-between">
                        <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                          <input
                            type="checkbox"
                            checked={addAsGroupAdmin}
                            onChange={(e) =>
                              setAddAsGroupAdmin(e.target.checked)
                            }
                            data-testid="group-add-member-admin-checkbox"
                            className="h-4 w-4 rounded border-zinc-300 accent-emerald-600 dark:border-zinc-600"
                          />
                          {t('admin.organizations.groups.addAsGroupAdmin')}
                        </label>
                        <Button
                          type="submit"
                          variant="filled"
                          disabled={addingMember || !addUserId}
                          data-testid="group-add-member-submit"
                        >
                          {addingMember
                            ? t('admin.organizations.groups.adding')
                            : t('admin.organizations.groups.add')}
                        </Button>
                      </div>
                    </form>
                  )}

                  {membersLoading ? (
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t('admin.organizations.groups.loading')}
                    </p>
                  ) : members.length === 0 ? (
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t('admin.organizations.groups.noMembers')}
                    </p>
                  ) : (
                    <div className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-700 dark:border-zinc-700">
                      {members.map((member) => {
                        const isBusy = memberLoading[member.user_id] || false
                        return (
                          <div
                            key={member.user_id}
                            data-testid={`group-member-${member.user_id}`}
                            className="flex items-center justify-between p-3"
                          >
                            <div>
                              <p className="text-sm font-medium text-zinc-900 dark:text-white">
                                {member.user_name}
                                {member.is_group_admin && (
                                  <span className="ml-2 inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                                    {t(
                                      'admin.organizations.groups.groupAdminBadge'
                                    )}
                                  </span>
                                )}
                              </p>
                              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                                {member.user_email} · {member.org_role}
                              </p>
                            </div>
                            {canManageMembersOf(selectedGroup) && (
                              <div className="flex items-center gap-3">
                                <label className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
                                  <input
                                    type="checkbox"
                                    checked={member.is_group_admin}
                                    onChange={() =>
                                      handleToggleGroupAdmin(member)
                                    }
                                    disabled={isBusy}
                                    data-testid={`group-member-admin-toggle-${member.user_id}`}
                                    className="h-4 w-4 rounded border-zinc-300 accent-emerald-600 dark:border-zinc-600"
                                  />
                                  {t(
                                    'admin.organizations.groups.groupAdminToggle'
                                  )}
                                </label>
                                <button
                                  type="button"
                                  onClick={() => handleRemoveMember(member)}
                                  disabled={isBusy}
                                  data-testid={`group-member-remove-${member.user_id}`}
                                  aria-label={t(
                                    'admin.organizations.groups.remove'
                                  )}
                                  className="text-red-600 hover:text-red-800 disabled:opacity-50 dark:text-red-400 dark:hover:text-red-300"
                                >
                                  <TrashIcon className="h-4 w-4" />
                                </button>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              ) : (
                /* ── Group list ──────────────────────────────────────── */
                <>
                  {isAdmin && (
                    <form
                      onSubmit={handleCreateGroup}
                      className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50"
                    >
                      <h3 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-white">
                        {t('admin.organizations.groups.createTitle')}
                      </h3>
                      <div className="space-y-3">
                        <input
                          type="text"
                          value={newName}
                          onChange={(e) => setNewName(e.target.value)}
                          placeholder={t(
                            'admin.organizations.groups.namePlaceholder'
                          )}
                          data-testid="group-create-name"
                          className={inputClassName}
                        />
                        <input
                          type="text"
                          value={newDescription}
                          onChange={(e) => setNewDescription(e.target.value)}
                          placeholder={t(
                            'admin.organizations.groups.descriptionPlaceholder'
                          )}
                          data-testid="group-create-description"
                          className={inputClassName}
                        />
                        <div className="flex justify-end">
                          <Button
                            type="submit"
                            variant="filled"
                            disabled={creating || !newName.trim()}
                            data-testid="group-create-submit"
                          >
                            {creating
                              ? t('admin.organizations.groups.creating')
                              : t('admin.organizations.groups.create')}
                          </Button>
                        </div>
                      </div>
                    </form>
                  )}

                  {groupsLoading ? (
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t('admin.organizations.groups.loading')}
                    </p>
                  ) : groups.length === 0 ? (
                    <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                      <p className="text-sm text-zinc-600 dark:text-zinc-400">
                        {t('admin.organizations.groups.noGroups')}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {groups.map((group) => {
                        const isDeleting = deleteLoading[group.id] || false
                        const isEditing = editingGroupId === group.id

                        return (
                          <div
                            key={group.id}
                            data-testid={`group-row-${group.id}`}
                            className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800"
                          >
                            {isEditing ? (
                              <div className="space-y-3">
                                <input
                                  type="text"
                                  value={editName}
                                  onChange={(e) => setEditName(e.target.value)}
                                  data-testid={`group-edit-name-${group.id}`}
                                  className={inputClassName}
                                />
                                <input
                                  type="text"
                                  value={editDescription}
                                  onChange={(e) =>
                                    setEditDescription(e.target.value)
                                  }
                                  placeholder={t(
                                    'admin.organizations.groups.descriptionPlaceholder'
                                  )}
                                  data-testid={`group-edit-description-${group.id}`}
                                  className={inputClassName}
                                />
                                <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                                  <input
                                    type="checkbox"
                                    checked={editIsActive}
                                    onChange={(e) =>
                                      setEditIsActive(e.target.checked)
                                    }
                                    data-testid={`group-edit-active-${group.id}`}
                                    className="h-4 w-4 rounded border-zinc-300 accent-emerald-600 dark:border-zinc-600"
                                  />
                                  {t('admin.organizations.groups.activeLabel')}
                                </label>
                                <div className="flex justify-end gap-2">
                                  <Button
                                    variant="outline"
                                    onClick={() => setEditingGroupId(null)}
                                  >
                                    {t('admin.organizations.groups.cancel')}
                                  </Button>
                                  <Button
                                    variant="filled"
                                    onClick={handleSaveEdit}
                                    disabled={savingEdit || !editName.trim()}
                                    data-testid={`group-edit-save-${group.id}`}
                                  >
                                    {savingEdit
                                      ? t('admin.organizations.groups.saving')
                                      : t('admin.organizations.groups.save')}
                                  </Button>
                                </div>
                              </div>
                            ) : (
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <h4 className="font-medium text-zinc-900 dark:text-white">
                                      {group.name}
                                    </h4>
                                    {!group.is_active && (
                                      <span className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400">
                                        {t(
                                          'admin.organizations.groups.inactiveBadge'
                                        )}
                                      </span>
                                    )}
                                    {group.is_group_admin && (
                                      <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                                        {t(
                                          'admin.organizations.groups.groupAdminBadge'
                                        )}
                                      </span>
                                    )}
                                  </div>
                                  {group.description && (
                                    <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                                      {group.description}
                                    </p>
                                  )}
                                  {group.member_count !== null && (
                                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                      {t(
                                        'admin.organizations.groups.memberCount',
                                        { count: group.member_count }
                                      )}
                                    </p>
                                  )}
                                </div>
                                <div className="flex shrink-0 items-center gap-2">
                                  {canManageMembersOf(group) && (
                                    <Button
                                      variant="outline"
                                      onClick={() => openMembersView(group)}
                                      data-testid={`group-members-${group.id}`}
                                    >
                                      <UserGroupIcon className="h-4 w-4" />
                                      {t('admin.organizations.groups.members')}
                                    </Button>
                                  )}
                                  {isAdmin && (
                                    <>
                                      <button
                                        type="button"
                                        onClick={() => startEdit(group)}
                                        data-testid={`group-edit-${group.id}`}
                                        aria-label={t(
                                          'admin.organizations.groups.edit'
                                        )}
                                        className="text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                                      >
                                        <PencilIcon className="h-4 w-4" />
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => handleDeleteGroup(group)}
                                        disabled={isDeleting}
                                        data-testid={`group-delete-${group.id}`}
                                        aria-label={t(
                                          'admin.organizations.groups.delete'
                                        )}
                                        className="text-red-600 hover:text-red-800 disabled:opacity-50 dark:text-red-400 dark:hover:text-red-300"
                                      >
                                        <TrashIcon className="h-4 w-4" />
                                      </button>
                                    </>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <button
              onClick={() => onOpenChange(false)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600"
            >
              {t('common.done')}
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}
