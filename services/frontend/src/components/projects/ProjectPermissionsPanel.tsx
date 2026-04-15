/**
 * ProjectPermissionsPanel - Manages project visibility and organization assignments
 *
 * Features:
 * - Public/Private visibility toggle
 * - Organization assignment for access control
 * - User role display within project context
 * - Permission validation and error handling
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Label } from '@/components/shared/Label'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import {
  GlobeAltIcon,
  LockClosedIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'
import { toast } from 'react-hot-toast'

interface Organization {
  id: string
  name: string
  slug: string
}

interface ProjectPermissionsPanelProps {
  projectId: string
  initialIsPublic?: boolean
  initialOrganizations?: Organization[]
  onSave?: (data: { is_public: boolean; organization_ids: string[] }) => void
  onCancel?: () => void
}

export function ProjectPermissionsPanel({
  projectId,
  initialIsPublic = false,
  initialOrganizations = [],
  onSave,
  onCancel,
}: ProjectPermissionsPanelProps) {
  const { user } = useAuth()
  const { t } = useI18n()

  const [isPublic, setIsPublic] = useState(initialIsPublic)
  const [selectedOrganizationIds, setSelectedOrganizationIds] = useState<
    string[]
  >(initialOrganizations.map((org) => org.id))
  const [availableOrganizations, setAvailableOrganizations] = useState<
    Organization[]
  >([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Permission check
  const canEditPermissions = () => {
    if (!user) return false
    return user.is_superadmin
  }

  // Fetch available organizations
  useEffect(() => {
    const fetchOrganizations = async () => {
      try {
        setLoading(true)
        setError(null)
        const orgs = await organizationsAPI.getOrganizations()
        setAvailableOrganizations(orgs)
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : 'Failed to load organizations'
        setError(errorMessage)
        toast.error(errorMessage)
      } finally {
        setLoading(false)
      }
    }

    fetchOrganizations()
  }, [])

  const handleOrganizationToggle = (orgId: string) => {
    setSelectedOrganizationIds((prev) =>
      prev.includes(orgId)
        ? prev.filter((id) => id !== orgId)
        : [...prev, orgId]
    )
  }

  const handleSave = async () => {
    if (!canEditPermissions()) {
      toast.error(t('project.permissions.noPermission'))
      return
    }

    // Validation: Private projects must have at least one organization
    if (!isPublic && selectedOrganizationIds.length === 0) {
      setError(t('project.permissions.validation.privateNeedsOrganization'))
      return
    }

    try {
      setSaving(true)
      setError(null)

      const data = {
        is_public: isPublic,
        organization_ids: selectedOrganizationIds,
      }

      await projectsAPI.update(projectId, data)
      toast.success(t('project.permissions.saveSuccess'))

      if (onSave) {
        onSave(data)
      }
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : 'Failed to save permissions'
      setError(errorMessage)
      toast.error(errorMessage)
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setIsPublic(initialIsPublic)
    setSelectedOrganizationIds(initialOrganizations.map((org) => org.id))
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
        <div className="mt-4 space-y-3">
          <div>
            <Label>{t('project.permissions.visibility')}</Label>
            <div className="mt-2 flex items-center space-x-2">
              {isPublic ? (
                <>
                  <GlobeAltIcon className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-sm text-zinc-900 dark:text-white">
                    {t('project.permissions.public')}
                  </span>
                </>
              ) : (
                <>
                  <LockClosedIcon className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  <span className="text-sm text-zinc-900 dark:text-white">
                    {t('project.permissions.private')}
                  </span>
                </>
              )}
            </div>
          </div>
          {!isPublic && initialOrganizations.length > 0 && (
            <div>
              <Label>{t('project.permissions.organizations')}</Label>
              <div className="mt-2 flex flex-wrap gap-2">
                {initialOrganizations.map((org) => (
                  <span
                    key={org.id}
                    className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-400"
                  >
                    {org.name}
                  </span>
                ))}
              </div>
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

      {/* Visibility Toggle */}
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
            data-testid="public-option"
          >
            <input
              type="radio"
              name="visibility"
              checked={isPublic}
              onChange={() => setIsPublic(true)}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="public-radio"
            />
            <div className="flex-1">
              <div className="flex items-center space-x-2">
                <GlobeAltIcon className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                <span className="font-medium text-zinc-900 dark:text-white">
                  {t('project.permissions.public')}
                </span>
              </div>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('project.permissions.publicDescription')}
              </p>
            </div>
          </label>

          <label
            className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
            data-testid="private-option"
          >
            <input
              type="radio"
              name="visibility"
              checked={!isPublic}
              onChange={() => setIsPublic(false)}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="private-radio"
            />
            <div className="flex-1">
              <div className="flex items-center space-x-2">
                <LockClosedIcon className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                <span className="font-medium text-zinc-900 dark:text-white">
                  {t('project.permissions.private')}
                </span>
              </div>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('project.permissions.privateDescription')}
              </p>
            </div>
          </label>
        </div>
      </div>

      {/* Organization Assignment */}
      {!isPublic && (
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

          {loading ? (
            <div className="mt-3 text-center">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('project.permissions.loadingOrganizations')}
              </p>
            </div>
          ) : availableOrganizations.length === 0 ? (
            <div className="mt-3 text-center">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('project.permissions.noOrganizationsAvailable')}
              </p>
            </div>
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
                    checked={selectedOrganizationIds.includes(org.id)}
                    onChange={() => handleOrganizationToggle(org.id)}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                    data-testid={`organization-checkbox-${org.id}`}
                  />
                  <UserGroupIcon className="h-5 w-5 text-zinc-400" />
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

      {/* Action Buttons */}
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
          disabled={saving || loading}
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
