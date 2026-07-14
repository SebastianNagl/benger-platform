/**
 * ModelPermissionsPanel - visibility control for a custom model (BYOM).
 *
 * Three switchable tiers (cloned from ProjectPermissionsPanel, minus the
 * public sub-role — sharing a model only ever grants USAGE, never editing):
 *   - private:      only the creator (and superadmins)
 *   - organization: members of one or more selected organizations
 *   - public:       every authenticated user across all orgs
 *
 * Edit/delete stays with the creator + superadmins regardless of visibility.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Label } from '@/components/shared/Label'
import { useI18n } from '@/contexts/I18nContext'
import { customModelsAPI } from '@/lib/api/customModels'
import { organizationsAPI } from '@/lib/api/organizations'
import { useEffect, useState } from 'react'
import { useToast } from '@/components/shared/Toast'

interface Organization {
  id: string
  name: string
  slug?: string
}

export type ModelVisibility = 'private' | 'organization' | 'public'

interface ModelPermissionsPanelProps {
  modelId: string
  canEdit: boolean
  initialVisibility?: ModelVisibility
  initialOrganizationIds?: string[]
  onSaved?: (data: {
    visibility: ModelVisibility
    organization_ids: string[]
  }) => void
  onCancel?: () => void
}

export function ModelPermissionsPanel({
  modelId,
  canEdit,
  initialVisibility = 'private',
  initialOrganizationIds = [],
  onSaved,
  onCancel,
}: ModelPermissionsPanelProps) {
  const { t } = useI18n()
  const { addToast } = useToast()

  const [visibility, setVisibility] =
    useState<ModelVisibility>(initialVisibility)
  const [selectedOrgIds, setSelectedOrgIds] = useState<string[]>(
    initialOrganizationIds
  )
  const [availableOrganizations, setAvailableOrganizations] = useState<
    Organization[]
  >([])
  const [loadingOrgs, setLoadingOrgs] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    if (!canEdit) {
      addToast(t('customModels.permissions.noPermission'), 'error')
      return
    }

    if (visibility === 'organization' && selectedOrgIds.length === 0) {
      setError(t('customModels.permissions.validation.needsOrganization'))
      return
    }

    try {
      setSaving(true)
      setError(null)

      const payload =
        visibility === 'private'
          ? ({ is_private: true } as const)
          : visibility === 'public'
            ? ({ is_public: true } as const)
            : ({
                is_private: false,
                organization_ids: selectedOrgIds,
              } as const)

      await customModelsAPI.updateVisibility(modelId, payload)
      addToast(t('customModels.permissions.saveSuccess'), 'success')

      if (onSaved) {
        onSaved({
          visibility,
          organization_ids: visibility === 'organization' ? selectedOrgIds : [],
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
    setSelectedOrgIds(initialOrganizationIds)
    setError(null)
    if (onCancel) {
      onCancel()
    }
  }

  if (!canEdit) {
    const initialOrgNames = initialOrganizationIds.map(
      (id) => availableOrganizations.find((o) => o.id === id)?.name ?? id
    )
    return (
      <div
        className="rounded-lg bg-zinc-50 p-6 dark:bg-zinc-800/50"
        data-testid="model-permissions-readonly"
      >
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('customModels.permissions.viewOnly')}
        </p>
        <div className="mt-4">
          <Label>{t('customModels.permissions.visibility')}</Label>
          <div className="mt-2 text-sm text-zinc-900 dark:text-white">
            {visibility === 'public'
              ? t('customModels.permissions.public')
              : visibility === 'private'
                ? t('customModels.permissions.private')
                : t('customModels.permissions.organization')}
          </div>
          {visibility === 'organization' && initialOrgNames.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {initialOrgNames.map((name) => (
                <span
                  key={name}
                  className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                >
                  {name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6" data-testid="model-permissions-panel">
      {error && (
        <div
          className="rounded-md bg-red-50 p-4 dark:bg-red-900/20"
          data-testid="model-permissions-error"
        >
          <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
        </div>
      )}

      <div>
        <Label htmlFor="model-visibility-toggle">
          {t('customModels.permissions.visibility')}
        </Label>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t('customModels.permissions.visibilityDescription')}
        </p>
        <div className="mt-3 space-y-3">
          <label
            className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
            data-testid="model-visibility-private-option"
          >
            <input
              type="radio"
              name="model-visibility"
              checked={visibility === 'private'}
              onChange={() => setVisibility('private')}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="model-visibility-private-radio"
            />
            <div className="flex-1">
              <span className="font-medium text-zinc-900 dark:text-white">
                {t('customModels.permissions.private')}
              </span>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('customModels.permissions.privateDescription')}
              </p>
            </div>
          </label>

          <label
            className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
            data-testid="model-visibility-organization-option"
          >
            <input
              type="radio"
              name="model-visibility"
              checked={visibility === 'organization'}
              onChange={() => setVisibility('organization')}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="model-visibility-organization-radio"
            />
            <div className="flex-1">
              <span className="font-medium text-zinc-900 dark:text-white">
                {t('customModels.permissions.organization')}
              </span>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('customModels.permissions.organizationDescription')}
              </p>
            </div>
          </label>

          <label
            className="flex cursor-pointer items-start space-x-3 rounded-lg border border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
            data-testid="model-visibility-public-option"
          >
            <input
              type="radio"
              name="model-visibility"
              checked={visibility === 'public'}
              onChange={() => setVisibility('public')}
              className="mt-0.5 h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
              data-testid="model-visibility-public-radio"
            />
            <div className="flex-1">
              <span className="font-medium text-zinc-900 dark:text-white">
                {t('customModels.permissions.public')}
              </span>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {t('customModels.permissions.publicDescription')}
              </p>
            </div>
          </label>
        </div>
      </div>

      {visibility === 'organization' && (
        <div data-testid="model-permissions-organization-section">
          <Label>
            {t('customModels.permissions.organizations')}
            <span className="ml-2 text-sm text-red-600 dark:text-red-400">
              *
            </span>
          </Label>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {t('customModels.permissions.organizationsDescription')}
          </p>
          {loadingOrgs ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              {t('customModels.permissions.loadingOrganizations')}
            </p>
          ) : availableOrganizations.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              {t('customModels.permissions.noOrganizationsAvailable')}
            </p>
          ) : (
            <div
              className="mt-3 space-y-2"
              data-testid="model-permissions-organization-list"
            >
              {availableOrganizations.map((org) => (
                <label
                  key={org.id}
                  className="flex cursor-pointer items-center space-x-3 rounded-lg border border-zinc-200 p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
                  data-testid={`model-permissions-organization-item-${org.id}`}
                >
                  <input
                    type="checkbox"
                    checked={selectedOrgIds.includes(org.id)}
                    onChange={() => toggleOrg(org.id)}
                    className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                    data-testid={`model-permissions-organization-checkbox-${org.id}`}
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

      <div className="flex items-center justify-end space-x-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
        <Button
          onClick={handleCancel}
          variant="outline"
          disabled={saving}
          data-testid="model-permissions-cancel-button"
        >
          {t('customModels.permissions.cancel')}
        </Button>
        <Button
          onClick={handleSave}
          disabled={saving}
          data-testid="model-permissions-save-button"
        >
          {saving
            ? t('customModels.permissions.saving')
            : t('customModels.permissions.save')}
        </Button>
      </div>
    </div>
  )
}
