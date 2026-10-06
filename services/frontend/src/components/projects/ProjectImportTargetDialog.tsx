'use client'

import { Button } from '@/components/shared/Button'
import { Dialog } from '@/components/shared/Dialog'
import { useI18n } from '@/contexts/I18nContext'
import {
  organizationsAPI,
  type OrganizationGroup,
} from '@/lib/api/organizations'
import type { OrganizationRole } from '@/lib/api/types'
import { canScopeOrgWide, scopeableGroups } from '@/lib/permissions/groupScope'
import { useEffect, useState } from 'react'

export interface ImportTargetOrganization {
  id: string
  name: string
  /** The caller's org role; decides whether the org-wide scope is offered. */
  role?: OrganizationRole | null
}

/** The radio value for a private import (no organization owns the copy). */
export const PRIVATE_IMPORT_TARGET = 'private'

interface ProjectImportTargetDialogProps {
  isOpen: boolean
  /** Organizations the user may create projects in: org role
   *  ORG_ADMIN/CONTRIBUTOR, or a group role CONTRIBUTOR/ORG_ADMIN there. */
  organizations: ImportTargetOrganization[]
  /** An organization id, PRIVATE_IMPORT_TARGET, or null while nothing is chosen. */
  value: string | null
  onChange: (value: string) => void
  /** Group of the chosen organization the copy is scoped to (null = the
   *  whole organization). Optional: without it no group select is shown. */
  groupId?: string | null
  onGroupChange?: (groupId: string | null) => void
  isSuperadmin?: boolean
  onConfirm: () => void
  onClose: () => void
}

/**
 * Asks where a create-new project import should land before the file picker
 * opens, the way the creation wizard names its target. "Private" is always
 * offered; the caller preselects the only organization a user may create in.
 */
export function ProjectImportTargetDialog({
  isOpen,
  organizations,
  value,
  onChange,
  groupId = null,
  onGroupChange,
  isSuperadmin = false,
  onConfirm,
  onClose,
}: ProjectImportTargetDialogProps) {
  const { t } = useI18n()
  // Group lists per org id, fetched lazily for the chosen org (the wizard's
  // pattern; a failing groups endpoint yields no groups = org-wide only).
  const [groupsByOrg, setGroupsByOrg] = useState<
    Record<string, OrganizationGroup[]>
  >({})
  const selectedOrg =
    value && value !== PRIVATE_IMPORT_TARGET
      ? organizations.find((o) => o.id === value)
      : undefined
  const groupsEnabled = Boolean(onGroupChange)

  useEffect(() => {
    if (!isOpen || !groupsEnabled || !selectedOrg) return
    if (groupsByOrg[selectedOrg.id] !== undefined) return
    let cancelled = false
    const orgId = selectedOrg.id
    let p: Promise<unknown>
    try {
      p = Promise.resolve(organizationsAPI.getGroups(orgId))
    } catch {
      setGroupsByOrg((prev) => ({ ...prev, [orgId]: [] }))
      return
    }
    p.then((rows) => {
      if (cancelled) return
      setGroupsByOrg((prev) => ({
        ...prev,
        [orgId]: Array.isArray(rows) ? (rows as OrganizationGroup[]) : [],
      }))
    }).catch(() => {
      if (!cancelled) setGroupsByOrg((prev) => ({ ...prev, [orgId]: [] }))
    })
    return () => {
      cancelled = true
    }
  }, [isOpen, groupsEnabled, selectedOrg, groupsByOrg])

  const groupsLoaded =
    selectedOrg !== undefined && groupsByOrg[selectedOrg.id] !== undefined
  const groupOptions = selectedOrg
    ? scopeableGroups(
        groupsByOrg[selectedOrg.id] ?? [],
        selectedOrg.role,
        isSuperadmin,
      )
    : []
  // Org-wide needs org role Contributor/Admin; an org annotator who is
  // group contributor/admin must import into one of those groups.
  const orgWideAllowed = selectedOrg
    ? canScopeOrgWide(selectedOrg.role, isSuperadmin)
    : true

  // Keep the group choice valid for the chosen org: pin the first eligible
  // group when org-wide is not allowed, drop a group that is not offered.
  useEffect(() => {
    if (!groupsEnabled || !onGroupChange) return
    if (!selectedOrg) {
      if (groupId !== null) onGroupChange(null)
      return
    }
    if (!groupsLoaded) return
    const valid = groupOptions.some((group) => group.id === groupId)
    if (!orgWideAllowed && !valid && groupOptions.length > 0) {
      onGroupChange(groupOptions[0].id)
    } else if (groupId !== null && !valid) {
      onGroupChange(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupsEnabled, selectedOrg?.id, groupsLoaded, orgWideAllowed, groupId])

  const needsGroup =
    groupsEnabled && selectedOrg !== undefined && !orgWideAllowed
  const confirmDisabled =
    value === null || (needsGroup && (!groupsLoaded || groupId === null))
  const options = [
    ...organizations.map((o) => ({ value: o.id, label: o.name })),
    {
      value: PRIVATE_IMPORT_TARGET,
      label: t('projects.list.importTargetPrivate'),
    },
  ]

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={t('projects.list.importTargetTitle')}
    >
      <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
        {t('projects.list.importTargetDescription')}
      </p>
      <fieldset className="space-y-2" data-testid="project-import-target">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 text-sm text-zinc-900 hover:bg-zinc-50 dark:text-white dark:hover:bg-zinc-800"
          >
            <input
              type="radio"
              name="project-import-target"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              data-testid={`project-import-target-${option.value}`}
            />
            <span className="truncate">{option.label}</span>
          </label>
        ))}
      </fieldset>
      {groupsEnabled && selectedOrg && groupOptions.length > 0 && (
        <div className="mt-4" data-testid="project-import-target-group-section">
          <label
            htmlFor="project-import-target-group"
            className="block text-xs font-medium text-zinc-600 dark:text-zinc-400"
          >
            {t('projects.list.importTargetGroupLabel')}
          </label>
          <select
            id="project-import-target-group"
            value={groupId ?? ''}
            onChange={(e) => onGroupChange?.(e.target.value || null)}
            data-testid="project-import-target-group-select"
            className="mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-100"
          >
            {orgWideAllowed && (
              <option value="">
                {t('projects.list.importTargetGroupOrgWide')}
              </option>
            )}
            {groupOptions.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          {t('projects.list.importTargetCancel')}
        </Button>
        <Button
          variant="primary"
          onClick={onConfirm}
          disabled={confirmDisabled}
          data-testid="project-import-target-confirm"
        >
          {t('projects.list.importTargetChooseFile')}
        </Button>
      </div>
    </Dialog>
  )
}
