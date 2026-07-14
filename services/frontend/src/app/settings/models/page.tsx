'use client'

/**
 * Settings page for custom models (BYOM - bring your own model).
 *
 * Two sections:
 * - "Meine Modelle": the user's own custom models (full CRUD + register)
 * - "Geteilt & öffentlich": other users' customs visible via org-sharing
 *   or public visibility (usage only - store a key, use in pickers)
 */

import { AuthGuard } from '@/components/auth/AuthGuard'
import { CustomModelFormModal } from '@/components/models/CustomModelFormModal'
import { CustomModelList } from '@/components/models/CustomModelList'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { customModelsAPI } from '@/lib/api/customModels'
import type { CustomModel } from '@/lib/api/types'
import { ArrowPathIcon, PlusIcon } from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

function ModelSettingsContent() {
  const { user } = useAuth()
  const { t } = useI18n()

  const [models, setModels] = useState<CustomModel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<CustomModel | null>(null)

  const loadModels = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await customModelsAPI.list()
      setModels(data)
    } catch (err) {
      console.error('Failed to load custom models:', err)
      setError(t('customModels.page.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    if (user) {
      loadModels()
    }
  }, [user, loadModels])

  // Own models: created by me (superadmins additionally get can_edit on
  // foreign models, so match on created_by first and only fall back to
  // can_edit when created_by is missing).
  const ownModels = models.filter((m) =>
    m.created_by != null && user
      ? String(m.created_by) === String(user.id)
      : m.can_edit
  )
  const sharedModels = models.filter((m) => !ownModels.includes(m))

  const openCreate = () => {
    setEditTarget(null)
    setFormOpen(true)
  }

  const openEdit = (model: CustomModel) => {
    setEditTarget(model)
    setFormOpen(true)
  }

  return (
    <div className="mx-auto max-w-7xl py-8">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[
            {
              label: t('customModels.page.breadcrumbSettings'),
              href: '/settings',
            },
            {
              label: t('customModels.page.breadcrumbModels'),
              href: '/settings/models',
            },
          ]}
        />
      </div>

      {/* Header */}
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('customModels.page.title')}
          </h1>
          <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
            {t('customModels.page.subtitle')}
          </p>
        </div>
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
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {t('customModels.page.myModels')}
            </h2>
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
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {t('customModels.page.sharedModels')}
            </h2>
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

export default function ModelSettingsPage() {
  return (
    <AuthGuard>
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        <ModelSettingsContent />
      </ResponsiveContainer>
    </AuthGuard>
  )
}
