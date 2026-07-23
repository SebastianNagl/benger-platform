'use client'

/**
 * Custom-model (BYOM) management: register button + "my models" and
 * "shared & public" lists + the register/edit form modal.
 *
 * Lifted from the former /settings/models page so the catalog page
 * (/models) can host the full management experience next to the official
 * catalog — one place to see, register, edit, and key custom models.
 * Access scoping comes from the backend list (visibility-filtered);
 * can_edit drives the edit/delete affordances per row.
 */

import { CustomModelFormModal } from '@/components/models/CustomModelFormModal'
import { CustomModelList } from '@/components/models/CustomModelList'
import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { customModelsAPI } from '@/lib/api/customModels'
import type { CustomModel } from '@/lib/api/types'
import { ArrowPathIcon, PlusIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useRef, useState } from 'react'

export function CustomModelsManager({
  onModelsLoaded,
  onVisibleCountChange,
  filterQuery = '',
}: {
  /** Optional: surfaces the loaded models (e.g. for a count badge). */
  onModelsLoaded?: (models: CustomModel[]) => void
  /** Optional: fires with the post-filter row count so a page-level badge
   *  can track the filtered view (matching the official groups' counts). */
  onVisibleCountChange?: (count: number) => void
  /** Optional page-level search: filters both lists by name, id, endpoint
   *  model, owner, or description (case-insensitive). */
  filterQuery?: string
}) {
  const { user } = useAuth()
  const { t } = useI18n()

  const [models, setModels] = useState<CustomModel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<CustomModel | null>(null)

  // Latest callbacks/translations behind a ref so loadModels can stay
  // identity-stable (empty deps). Otherwise a caller passing a fresh `t`
  // or `onModelsLoaded` each render would re-fire the load effect forever.
  const cbRef = useRef({ t, onModelsLoaded })
  cbRef.current = { t, onModelsLoaded }

  const loadModels = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await customModelsAPI.list()
      const list = Array.isArray(data) ? data : []
      setModels(list)
      cbRef.current.onModelsLoaded?.(list)
    } catch (err) {
      console.error('Failed to load custom models:', err)
      setError(cbRef.current.t('customModels.page.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [])

  // Key on the stable user id, not the user object — a context provider may
  // hand back a fresh object each render, which would loop the load.
  const userId = user?.id
  useEffect(() => {
    if (userId) {
      loadModels()
    }
  }, [userId, loadModels])

  // Page-level search applies to both lists (name / id / endpoint model /
  // owner / description), mirroring the official-catalog search fields.
  const q = filterQuery.trim().toLowerCase()
  const visibleModels = q
    ? models.filter((m) =>
        [
          m.name,
          m.id,
          m.endpoint_model_name,
          m.created_by_username ?? '',
          m.description ?? '',
        ].some((field) => field.toLowerCase().includes(q))
      )
    : models

  // Own models: created by me (superadmins additionally get can_edit on
  // foreign models, so match on created_by first and only fall back to
  // can_edit when created_by is missing).
  const ownModels = visibleModels.filter((m) =>
    m.created_by != null && user
      ? String(m.created_by) === String(user.id)
      : m.can_edit
  )
  const sharedModels = visibleModels.filter((m) => !ownModels.includes(m))

  useEffect(() => {
    onVisibleCountChange?.(visibleModels.length)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleModels.length])

  const openCreate = () => {
    setEditTarget(null)
    setFormOpen(true)
  }

  const openEdit = (model: CustomModel) => {
    setEditTarget(model)
    setFormOpen(true)
  }

  return (
    <div data-testid="custom-models-manager">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('customModels.page.subtitle')}
        </p>
        <Button
          variant="filled"
          onClick={openCreate}
          data-testid="custom-model-register-button"
        >
          <PlusIcon className="mr-1.5 h-4 w-4" />
          {t('customModels.page.register')}
        </Button>
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-lg bg-white p-8 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          <div className="flex items-center justify-center">
            <ArrowPathIcon className="h-8 w-8 animate-spin text-zinc-400" />
            <span className="ml-2 text-zinc-600 dark:text-zinc-400">
              {t('customModels.page.loading')}
            </span>
          </div>
        </div>
      ) : (
        <div className="space-y-10">
          {/* Own models */}
          <section data-testid="custom-models-own-section">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {t('customModels.page.myModels')}
            </h3>
            <p className="mb-4 mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {t('customModels.page.myModelsDescription')}
            </p>
            <CustomModelList
              models={ownModels}
              emptyMessage={t('customModels.page.myModelsEmpty')}
              onEdit={openEdit}
              onChanged={loadModels}
            />
          </section>

          {/* Shared & public models */}
          <section data-testid="custom-models-shared-section">
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {t('customModels.page.sharedModels')}
            </h3>
            <p className="mb-4 mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {t('customModels.page.sharedModelsDescription')}
            </p>
            <CustomModelList
              models={sharedModels}
              emptyMessage={t('customModels.page.sharedModelsEmpty')}
              onEdit={openEdit}
              onChanged={loadModels}
            />
          </section>
        </div>
      )}

      <CustomModelFormModal
        isOpen={formOpen}
        model={editTarget}
        onClose={() => {
          setFormOpen(false)
          setEditTarget(null)
          loadModels()
        }}
        onSaved={() => {
          loadModels()
        }}
      />
    </div>
  )
}
