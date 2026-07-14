'use client'

/**
 * CustomModelList - card list of custom models (BYOM).
 *
 * Owner rows (can_edit) get Edit / Visibility / Delete actions; the
 * visibility action expands an inline ModelPermissionsPanel. All rows can
 * be expanded to a read-only detail section containing the per-user
 * CustomModelCredentialRow (every user stores their OWN key per model).
 */

import { Button } from '@/components/shared/Button'
import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { customModelsAPI } from '@/lib/api/customModels'
import type { CustomModel } from '@/lib/api/types'
import { ChevronRightIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'
import { CustomBadge, VisibilityBadge } from './ModelBadges'
import { CustomModelCredentialRow } from './CustomModelCredentialRow'
import { ModelPermissionsPanel } from './ModelPermissionsPanel'

interface CustomModelListProps {
  models: CustomModel[]
  /** Message shown when the list is empty. */
  emptyMessage?: string
  /** Owner action: open the edit form for this model. */
  onEdit?: (model: CustomModel) => void
  /** Called after delete or a visibility change so the parent can refetch. */
  onChanged?: () => void
}

function modelVisibility(
  model: CustomModel
): 'private' | 'organization' | 'public' {
  if (model.is_public) return 'public'
  if (model.is_private) return 'private'
  return 'organization'
}

export function CustomModelList({
  models,
  emptyMessage,
  onEdit,
  onChanged,
}: CustomModelListProps) {
  const { t } = useI18n()
  const { addToast } = useToast()

  const [expandedIds, setExpandedIds] = useState<string[]>([])
  const [visibilityOpenFor, setVisibilityOpenFor] = useState<string | null>(
    null
  )
  const [deleteTarget, setDeleteTarget] = useState<CustomModel | null>(null)
  const [deleting, setDeleting] = useState(false)

  const toggleExpanded = (modelId: string) => {
    setExpandedIds((prev) =>
      prev.includes(modelId)
        ? prev.filter((id) => id !== modelId)
        : [...prev, modelId]
    )
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      setDeleting(true)
      await customModelsAPI.remove(deleteTarget.id)
      addToast(t('customModels.list.deleteSuccess'), 'success')
      onChanged?.()
    } catch (error: any) {
      const detail =
        error?.response?.data?.detail ||
        (error instanceof Error ? error.message : null)
      addToast(detail || t('customModels.list.deleteFailed'), 'error')
    } finally {
      setDeleting(false)
      setDeleteTarget(null)
    }
  }

  if (models.length === 0) {
    return (
      <div
        className="rounded-lg border border-dashed border-zinc-300 py-8 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400"
        data-testid="custom-model-list-empty"
      >
        {emptyMessage ?? t('customModels.list.empty')}
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="custom-model-list">
      {models.map((model) => {
        const expanded = expandedIds.includes(model.id)
        const visibilityOpen = visibilityOpenFor === model.id

        return (
          <div
            key={model.id}
            className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900"
            data-testid={`custom-model-row-${model.id}`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3 p-4">
              <button
                type="button"
                onClick={() => toggleExpanded(model.id)}
                className="flex min-w-0 flex-1 items-center gap-3 text-left"
                data-testid={`custom-model-expand-${model.id}`}
              >
                <ChevronRightIcon
                  className={`h-4 w-4 flex-shrink-0 text-zinc-400 transition-transform ${
                    expanded ? 'rotate-90' : ''
                  }`}
                />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium text-zinc-900 dark:text-white">
                      {model.name}
                    </span>
                    <CustomBadge
                      ownerName={
                        model.can_edit ? undefined : model.created_by_username
                      }
                    />
                    <VisibilityBadge visibility={modelVisibility(model)} />
                    {model.requires_api_key && (
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          model.has_credential
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                            : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400'
                        }`}
                        data-testid={`credential-pill-${model.id}`}
                      >
                        {model.has_credential
                          ? t('customModels.badges.keyConfigured')
                          : t('customModels.badges.keyMissing')}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">
                    {model.base_url} · {model.endpoint_model_name}
                  </div>
                </div>
              </button>

              <div className="flex flex-shrink-0 items-center gap-3">
                <div className="text-right text-xs text-zinc-500 dark:text-zinc-400">
                  {model.input_cost_per_million != null &&
                  model.output_cost_per_million != null ? (
                    <span>
                      ${model.input_cost_per_million.toFixed(2)} / $
                      {model.output_cost_per_million.toFixed(2)}{' '}
                      {t('customModels.list.perMillion')}
                    </span>
                  ) : (
                    <span>-</span>
                  )}
                </div>

                {model.can_edit && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      className="text-xs"
                      onClick={() => onEdit?.(model)}
                      data-testid={`custom-model-edit-${model.id}`}
                    >
                      {t('customModels.list.edit')}
                    </Button>
                    <Button
                      variant="outline"
                      className="text-xs"
                      onClick={() => {
                        setVisibilityOpenFor(visibilityOpen ? null : model.id)
                        if (!expanded) toggleExpanded(model.id)
                      }}
                      data-testid={`custom-model-visibility-${model.id}`}
                    >
                      {t('customModels.list.editVisibility')}
                    </Button>
                    <Button
                      variant="outline"
                      className="text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                      onClick={() => setDeleteTarget(model)}
                      data-testid={`custom-model-delete-${model.id}`}
                    >
                      {t('customModels.list.delete')}
                    </Button>
                  </div>
                )}
              </div>
            </div>

            {expanded && (
              <div
                className="space-y-4 border-t border-zinc-200 p-4 dark:border-zinc-700"
                data-testid={`custom-model-detail-${model.id}`}
              >
                {model.description && (
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {model.description}
                  </p>
                )}

                {!model.can_edit && model.created_by_username && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t('customModels.list.owner')}: {model.created_by_username}
                  </p>
                )}

                {visibilityOpen && model.can_edit && (
                  <div
                    className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                    data-testid={`custom-model-visibility-panel-${model.id}`}
                  >
                    <ModelPermissionsPanel
                      modelId={model.id}
                      canEdit={model.can_edit}
                      initialVisibility={modelVisibility(model)}
                      initialOrganizationIds={model.organization_ids}
                      onSaved={() => {
                        setVisibilityOpenFor(null)
                        onChanged?.()
                      }}
                      onCancel={() => setVisibilityOpenFor(null)}
                    />
                  </div>
                )}

                <CustomModelCredentialRow
                  modelId={model.id}
                  baseUrl={model.base_url}
                  requiresApiKey={model.requires_api_key}
                  initialHasCredential={model.has_credential}
                  onChanged={onChanged}
                />
              </div>
            )}
          </div>
        )
      })}

      <ConfirmationDialog
        isOpen={deleteTarget !== null}
        onClose={() => {
          if (!deleting) setDeleteTarget(null)
        }}
        onConfirm={handleDelete}
        title={t('customModels.list.deleteTitle')}
        message={t('customModels.list.deleteMessage', {
          name: deleteTarget?.name ?? '',
        })}
        confirmText={t('customModels.list.deleteConfirm')}
        variant="danger"
      />
    </div>
  )
}
