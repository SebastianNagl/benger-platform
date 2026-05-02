/**
 * ProjectPermissionsPanel - Single source of truth for project visibility.
 *
 * Three switchable tiers:
 *   - private:      only the creator (and superadmins)
 *   - organization: members of one or more selected organizations (multi-select)
 *   - public:       every authenticated user across all orgs; the publisher
 *                   picks a sub-role (ANNOTATOR / CONTRIBUTOR) that controls
 *                   what visitors are allowed to do beyond just reading.
 *
 * Edit access (settings, label config) stays with creator + superadmins
 * regardless of visibility — the public CONTRIBUTOR role grants task/data
 * interactions only.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Label } from '@/components/shared/Label'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import { useEffect, useState } from 'react'
import { useToast } from '@/components/shared/Toast'

interface Organization {
  id: string
  name: string
  slug?: string
}

export type ProjectVisibility = 'private' | 'organization' | 'public'
export type PublicRole = 'ANNOTATOR' | 'CONTRIBUTOR'

interface ProjectPermissionsPanelProps {
  projectId: string
  projectCreatorId?: string | number
  initialVisibility?: ProjectVisibility
  initialPublicRole?: PublicRole
  initialOrganizations?: Organization[]
  onSave?: (data: {
    visibility: ProjectVisibility
    public_role?: PublicRole
    organization_ids: string[]
  }) => void
  onCancel?: () => void
}

export function ProjectPermissionsPanel({
  projectId,
  projectCreatorId,
  initialVisibility = 'private',
  initialPublicRole = 'ANNOTATOR',
  initialOrganizations = [],
  onSave,
  onCancel,
}: ProjectPermissionsPanelProps) {
  const { user } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()

  const [visibility, setVisibility] =
    useState<ProjectVisibility>(initialVisibility)
  const [publicRole, setPublicRole] = useState<PublicRole>(initialPublicRole)
  const [selectedOrgIds, setSelectedOrgIds] = useState<string[]>(
    initialOrganizations.map((o) => o.id)
  )
  const [availableOrganizations, setAvailableOrganizations] = useState<
    Organization[]
  >([])
  const [loadingOrgs, setLoadingOrgs] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canEditPermissions = () => {
    if (!user) return false
    if (user.is_superadmin) return true
    if (projectCreatorId == null) return false
    return String(user.id) === String(projectCreatorId)
  }

  useEffect(() => {
    let cancelled = false
    const fetchOrgs = async () => {
      try {
        setLoadingOrgs(true)
        const orgs = await organizationsAPI.getOrganizations()
        if (!cancelled) {
          setAvailableOrganizations(orgs)
        }
      } catch (err) {
        if (!cancelled) {
          const msg =
            err instanceof Error
              ? err.message
              : 'Failed to load organizations'
          addToast(msg, 'error')
        }
      } finally {
        if (!cancelled) setLoadingOrgs(false)
      }
    }
    fetchOrgs()
    return () => {
      cancelled = true
    }
  }, [addToast])

  const toggleOrg = (orgId: string) => {
    setSelectedOrgIds((prev) =>
      prev.includes(orgId)
        ? prev.filter((id) => id !== orgId)
        : [...prev, orgId]
    )
  }

  const handleSave = async () => {
    if (!canEditPermissions()) {
      addToast(t('project.permissions.noPermission'), 'error')
      return
    }

    if (visibility === 'organization' && selectedOrgIds.length === 0) {
      setError(t('project.permissions.validation.privateNeedsOrganization'))
      return
    }

    try {
      setSaving(true)
      setError(null)

      const payload =
        visibility === 'private'
          ? ({ is_private: true } as const)
          : visibility === 'public'
            ? ({ is_public: true, public_role: publicRole } as const)
            : ({
                is_private: false,
                organization_ids: selectedOrgIds,
              } as const)

      await projectsAPI.updateVisibility(projectId, payload)
      addToast(t('project.permissions.saveSuccess'), 'success')

      if (onSave) {
        onSave({
          visibility,
          public_role: visibility === 'public' ? publicRole : undefined,
          organization_ids: selectedOrgIds,
        })
      }
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : 'Failed to save permissions'
      setError(errorMessage)
      addToast(errorMessage, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setVisibility(initialVisibility)
    setPublicRole(initialPublicRole)
    setSelectedOrgIds(initialOrganizations.map((o) => o.id))
    setError(null)
    if (onCancel) {
      onCancel()
    }
  }

  if (!canEditPermissions()) {
    return (
      <div className="rounded-lg bg-zinc-50 p-6 dark:bg-zinc-800/50">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('project.permissions.viewOnly')}
        </p>
        <div className="mt-4">
          <Label>{t('project.permissions.visibility')}</Label>
          <div className="mt-2 text-sm text-zinc-900 dark:text-white">
            {visibility === 'public'
              ? `${t('project.permissions.public')} · ${
                  publicRole === 'CONTRIBUTOR'
                    ? t('project.permissions.publicRole.contributor')
                    : t('project.permissions.publicRole.annotator')
                }`
              : visibility === 'private'
                ? t('project.permissions.private')
                : t('project.permissions.organization')}
          </div>
          {visibility === 'organization' && initialOrganizations.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {initialOrganizations.map((org) => (
                <span
                  key={org.id}
                  className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                >
                  {org.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6" data-testid="project-permissions-panel">
      {error && (
        <div
          className="rounded-md bg-red-50 p-4 dark:bg-red-900/20"
          data-testid="project-permissions-error"
        >
          <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      <div>
        <Label htmlFor="visibility-toggle">
          {t('project.permissions.visibility')}
        </Label>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t('project.permissions.visibilityDescription')}
        </p>
        <div className="mt-3 space-y-3">
          <label
            className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
            data-testid="private-option"
          >
            <input
              type="radio"
              name="visibility"
              checked={visibility === 'private'}
              onChange={() => setVisibility('private')}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="private-radio"
            />
            <div className="flex-1">
              <span className="font-medium text-zinc-900 dark:text-white">
                {t('project.permissions.private')}
              </span>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('project.permissions.privateDescription')}
              </p>
            </div>
          </label>

          <label
            className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
            data-testid="organization-option"
          >
            <input
              type="radio"
              name="visibility"
              checked={visibility === 'organization'}
              onChange={() => setVisibility('organization')}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="organization-radio"
            />
            <div className="flex-1">
              <span className="font-medium text-zinc-900 dark:text-white">
                {t('project.permissions.organization')}
              </span>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('project.permissions.organizationDescription')}
              </p>
            </div>
          </label>

          <label
            className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
            data-testid="public-option"
          >
            <input
              type="radio"
              name="visibility"
              checked={visibility === 'public'}
              onChange={() => setVisibility('public')}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="public-radio"
            />
            <div className="flex-1">
              <span className="font-medium text-zinc-900 dark:text-white">
                {t('project.permissions.public')}
              </span>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('project.permissions.publicDescription')}
              </p>
            </div>
          </label>
        </div>
      </div>

      {visibility === 'organization' && (
        <div data-testid="organization-section">
          <Label>
            {t('project.permissions.organizations')}
            <span className="ml-2 text-sm text-red-600 dark:text-red-400">
              *
            </span>
          </Label>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {t('project.permissions.organizationsDescription')}
          </p>
          {loadingOrgs ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              {t('project.permissions.loadingOrganizations')}
            </p>
          ) : availableOrganizations.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              {t('project.permissions.noOrganizationsAvailable')}
            </p>
          ) : (
            <div className="mt-3 space-y-2" data-testid="organization-list">
              {availableOrganizations.map((org) => (
                <label
                  key={org.id}
                  className="flex cursor-pointer items-center space-x-3 rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
                  data-testid={`organization-item-${org.id}`}
                >
                  <input
                    type="checkbox"
                    checked={selectedOrgIds.includes(org.id)}
                    onChange={() => toggleOrg(org.id)}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                    data-testid={`organization-checkbox-${org.id}`}
                  />
                  <div className="flex-1">
                    <span className="text-sm font-medium text-zinc-900 dark:text-white">
                      {org.name}
                    </span>
                    {org.slug && (
                      <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                        ({org.slug})
                      </span>
                    )}
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {visibility === 'public' && (
        <div data-testid="public-role-section">
          <Label>{t('project.permissions.publicRoleLabel')}</Label>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {t('project.permissions.publicRoleDescription')}
          </p>
          <div className="mt-3 space-y-3">
            <label
              className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
              data-testid="public-role-annotator-option"
            >
              <input
                type="radio"
                name="public-role"
                checked={publicRole === 'ANNOTATOR'}
                onChange={() => setPublicRole('ANNOTATOR')}
                className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                data-testid="public-role-annotator-radio"
              />
              <div className="flex-1">
                <span className="font-medium text-zinc-900 dark:text-white">
                  {t('project.permissions.publicRole.annotator')}
                </span>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('project.permissions.publicRole.annotatorDescription')}
                </p>
              </div>
            </label>
            <label
              className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
              data-testid="public-role-contributor-option"
            >
              <input
                type="radio"
                name="public-role"
                checked={publicRole === 'CONTRIBUTOR'}
                onChange={() => setPublicRole('CONTRIBUTOR')}
                className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                data-testid="public-role-contributor-radio"
              />
              <div className="flex-1">
                <span className="font-medium text-zinc-900 dark:text-white">
                  {t('project.permissions.publicRole.contributor')}
                </span>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('project.permissions.publicRole.contributorDescription')}
                </p>
              </div>
            </label>
          </div>
        </div>
      )}

      <div className="flex items-center justify-end space-x-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
        <Button
          onClick={handleCancel}
          variant="outline"
          disabled={saving}
          data-testid="cancel-button"
        >
          {t('project.permissions.cancel')}
        </Button>
        <Button
          onClick={handleSave}
          disabled={saving}
          data-testid="save-button"
        >
          {saving
            ? t('project.permissions.saving')
            : t('project.permissions.save')}
        </Button>
      </div>
    </div>
  )
}
