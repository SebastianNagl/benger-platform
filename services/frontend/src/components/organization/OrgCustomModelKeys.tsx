'use client'

import { useI18n } from '@/contexts/I18nContext'
import { Button } from '@/components/shared/Button'
import {
  organizationsAPI,
  type OrgSharedCustomModel,
} from '@/lib/api/organizations'
import { EyeIcon, EyeSlashIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { Dialog } from '@headlessui/react'
import { useCallback, useEffect, useState } from 'react'

interface OrgCustomModelKeysProps {
  organizationId: string
  isAdmin: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Org admin surface for org-owned (shared) BYOM custom-model credentials.
 *
 * Mirrors OrgApiKeys but keyed by custom model instead of provider: an admin
 * provisions ONE shared key per custom model shared with the org, so members
 * do not each have to enter their own. The shared key is only USED when the
 * org runs shared-billing mode (require_private_keys false) — surfaced here
 * as an informational banner. Key material is never fetched or shown.
 */
export function OrgCustomModelKeys({
  organizationId,
  isAdmin,
  open,
  onOpenChange,
}: OrgCustomModelKeysProps) {
  const { t } = useI18n()

  const [models, setModels] = useState<OrgSharedCustomModel[]>([])
  const [requirePrivateKeys, setRequirePrivateKeys] = useState(true)
  const [newKeys, setNewKeys] = useState<Record<string, string>>({})
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const [listLoading, setListLoading] = useState(false)
  const [message, setMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  const fetchSettings = useCallback(async () => {
    try {
      const data = await organizationsAPI.getOrgApiKeySettings(organizationId)
      setRequirePrivateKeys(data.require_private_keys)
    } catch {
      setRequirePrivateKeys(true)
    }
  }, [organizationId])

  const fetchModels = useCallback(async () => {
    setListLoading(true)
    try {
      const data = await organizationsAPI.listOrgCustomModels(organizationId)
      setModels(data || [])
    } catch {
      setModels([])
    } finally {
      setListLoading(false)
    }
  }, [organizationId])

  useEffect(() => {
    if (open) {
      setMessage(null)
      fetchSettings()
      fetchModels()
    }
  }, [open, fetchSettings, fetchModels])

  const setKey = async (modelId: string, modelName: string) => {
    const apiKey = newKeys[modelId]
    if (!apiKey || !apiKey.trim()) return

    setLoading((prev) => ({ ...prev, [modelId]: true }))
    setMessage(null)
    try {
      await organizationsAPI.setOrgCustomModelCredential(
        organizationId,
        modelId,
        apiKey
      )
      setMessage({
        type: 'success',
        text: t('organization.customModelKeys.keySaved', { model: modelName }),
      })
      setNewKeys((prev) => ({ ...prev, [modelId]: '' }))
      setShowKeys((prev) => ({ ...prev, [modelId]: false }))
      await fetchModels()
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('organization.customModelKeys.saveFailed'),
      })
    } finally {
      setLoading((prev) => ({ ...prev, [modelId]: false }))
    }
  }

  const removeKey = async (modelId: string, modelName: string) => {
    setLoading((prev) => ({ ...prev, [modelId]: true }))
    setMessage(null)
    try {
      await organizationsAPI.removeOrgCustomModelCredential(
        organizationId,
        modelId
      )
      setMessage({
        type: 'success',
        text: t('organization.customModelKeys.keyRemoved', { model: modelName }),
      })
      await fetchModels()
    } catch (error: any) {
      setMessage({
        type: 'error',
        text:
          error.response?.data?.detail ||
          t('organization.customModelKeys.removeFailed'),
      })
    } finally {
      setLoading((prev) => ({ ...prev, [modelId]: false }))
    }
  }

  const configuredCount = models.filter((m) => m.has_org_credential).length

  return (
    <Dialog open={open} onClose={() => onOpenChange(false)} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('organization.customModelKeys.dialogTitle')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('organization.customModelKeys.dialogDescription')}
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
                  className={`rounded-md border p-4 text-sm ${
                    message.type === 'success'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                      : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                  }`}
                >
                  {message.text}
                </div>
              )}

              {!isAdmin ? (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('organization.customModelKeys.adminOnly')}
                  </p>
                </div>
              ) : (
                <>
                  {/* Shared-billing mode note */}
                  {requirePrivateKeys ? (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
                      <p className="text-sm text-amber-700 dark:text-amber-400">
                        {t('organization.customModelKeys.sharedModeInactive')}
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-900/20">
                      <p className="text-sm text-emerald-700 dark:text-emerald-400">
                        {t('organization.customModelKeys.sharedModeActive')}
                      </p>
                    </div>
                  )}

                  <div className="text-sm text-zinc-600 dark:text-zinc-400">
                    <p>
                      {t('organization.customModelKeys.configuredCount', {
                        configured: configuredCount,
                        total: models.length,
                      })}
                    </p>
                  </div>

                  {/* Model cards */}
                  {listLoading ? (
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      {t('organization.customModelKeys.loading')}
                    </p>
                  ) : models.length === 0 ? (
                    <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                      <p className="text-sm text-zinc-600 dark:text-zinc-400">
                        {t('organization.customModelKeys.noModels')}
                      </p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 gap-6">
                      {models.map((model) => {
                        const hasKey = model.has_org_credential
                        const isLoading = loading[model.id] || false
                        const newKey = newKeys[model.id] || ''
                        const showKey = showKeys[model.id] || false

                        return (
                          <div
                            key={model.id}
                            className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800"
                          >
                            <div className="mb-3 flex items-center justify-between">
                              <div>
                                <h3 className="font-medium text-zinc-900 dark:text-white">
                                  {model.name}
                                </h3>
                                {model.base_url && (
                                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                                    {model.base_url}
                                  </p>
                                )}
                              </div>
                              <span
                                className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                                  hasKey
                                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                                    : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400'
                                }`}
                              >
                                {hasKey
                                  ? t('organization.customModelKeys.configured')
                                  : t('organization.customModelKeys.notConfigured')}
                              </span>
                            </div>

                            {hasKey ? (
                              <div className="flex justify-end">
                                <Button
                                  variant="outline"
                                  onClick={() => removeKey(model.id, model.name)}
                                  disabled={isLoading}
                                  className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                                >
                                  {isLoading
                                    ? t('organization.customModelKeys.removing')
                                    : t('organization.customModelKeys.removeKey')}
                                </Button>
                              </div>
                            ) : (
                              <div className="space-y-3">
                                <div className="relative">
                                  <input
                                    type={showKey ? 'text' : 'password'}
                                    placeholder={t(
                                      'organization.customModelKeys.keyPlaceholder'
                                    )}
                                    value={newKey}
                                    onChange={(e) =>
                                      setNewKeys((prev) => ({
                                        ...prev,
                                        [model.id]: e.target.value,
                                      }))
                                    }
                                    className="w-full rounded-full bg-white px-4 py-2 pr-10 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                  />
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setShowKeys((prev) => ({
                                        ...prev,
                                        [model.id]: !prev[model.id],
                                      }))
                                    }
                                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                                  >
                                    {showKey ? (
                                      <EyeSlashIcon className="h-4 w-4" />
                                    ) : (
                                      <EyeIcon className="h-4 w-4" />
                                    )}
                                  </button>
                                </div>

                                <div className="flex justify-end">
                                  <Button
                                    variant="filled"
                                    onClick={() => setKey(model.id, model.name)}
                                    disabled={isLoading || !newKey}
                                  >
                                    {isLoading
                                      ? t('organization.customModelKeys.saving')
                                      : t('organization.customModelKeys.saveKey')}
                                  </Button>
                                </div>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}

                  <div className="space-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                    <p>{t('organization.customModelKeys.encryptedInfo')}</p>
                    <p>{t('organization.customModelKeys.sharedInfo')}</p>
                  </div>
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
