'use client'

import { useI18n } from '@/contexts/I18nContext'
import { Button } from '@/components/shared/Button'
import { organizationsAPI } from '@/lib/api/organizations'
import {
  EyeIcon,
  EyeSlashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { Dialog } from '@headlessui/react'
import { useCallback, useEffect, useState } from 'react'

interface OrgApiKeysProps {
  organizationId: string
  isAdmin: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface TestResult {
  type: 'success' | 'error'
  message: string
}

interface Provider {
  id: string
  name: string
  description: string
  placeholder: string
  validation: RegExp
}

const providers: Provider[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'GPT-4, GPT-3.5 Turbo models',
    placeholder: 'sk-...',
    validation: /^sk-[a-zA-Z0-9_-]{20,}$/,
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Claude models',
    placeholder: 'sk-ant-...',
    validation: /^sk-ant-[a-zA-Z0-9-_]{30,}$/,
  },
  {
    id: 'google',
    name: 'Google',
    description: 'Gemini models',
    placeholder: 'AI...',
    validation: /^[a-zA-Z0-9_-]{20,}$/,
  },
  {
    id: 'deepinfra',
    name: 'DeepInfra',
    description: 'Llama, Qwen, DeepSeek models',
    placeholder: 'Your DeepInfra API key',
    validation: /^[a-zA-Z0-9]{20,}$/,
  },
  {
    id: 'grok',
    name: 'Grok (xAI)',
    description: 'Grok models',
    placeholder: 'xai-...',
    validation: /^xai-[a-zA-Z0-9_-]{10,}$/,
  },
  {
    id: 'mistral',
    name: 'Mistral AI',
    description: 'Mistral models',
    placeholder: 'Your Mistral API key',
    validation: /^[a-zA-Z0-9]{20,}$/,
  },
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'Command models',
    placeholder: 'Your Cohere API key',
    validation: /^[a-zA-Z0-9]{20,}$/,
  },
]

export function OrgApiKeys({ organizationId, isAdmin, open, onOpenChange }: OrgApiKeysProps) {
  const { t } = useI18n()

  const getProviderDescription = (id: string) => {
    const descriptions: Record<string, string> = {
      openai: t('organization.apiKeys.providers.openai.description'),
      anthropic: t('organization.apiKeys.providers.anthropic.description'),
      google: t('organization.apiKeys.providers.google.description'),
      deepinfra: t('organization.apiKeys.providers.deepinfra.description'),
      grok: t('organization.apiKeys.providers.grok.description'),
      mistral: t('organization.apiKeys.providers.mistral.description'),
      cohere: t('organization.apiKeys.providers.cohere.description'),
    }
    return descriptions[id] || providers.find((p) => p.id === id)?.description || ''
  }
  const [requirePrivateKeys, setRequirePrivateKeys] = useState(true)
  const [apiKeyStatus, setApiKeyStatus] = useState<Record<string, boolean>>({})
  const [newApiKeys, setNewApiKeys] = useState<Record<string, string>>({})
  const [showApiKeys, setShowApiKeys] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const [testLoading, setTestLoading] = useState<Record<string, boolean>>({})
  const [testResults, setTestResults] = useState<
    Record<string, TestResult | null>
  >({})
  const [settingsLoading, setSettingsLoading] = useState(false)
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

  const fetchKeyStatus = useCallback(async () => {
    try {
      const data = await organizationsAPI.getOrgApiKeyStatus(organizationId)
      setApiKeyStatus(data.api_key_status || {})
    } catch {
      setApiKeyStatus({})
    }
  }, [organizationId])

  useEffect(() => {
    if (open) {
      setMessage(null)
      fetchSettings()
      fetchKeyStatus()
    }
  }, [open, fetchSettings, fetchKeyStatus])

  const toggleRequirePrivateKeys = async () => {
    if (!isAdmin) return
    setSettingsLoading(true)
    setMessage(null)

    try {
      const newValue = !requirePrivateKeys
      await organizationsAPI.updateOrgApiKeySettings(organizationId, newValue)
      setRequirePrivateKeys(newValue)
      setMessage({
        type: 'success',
        text: newValue
          ? t('organization.apiKeys.membersUseOwnKeys')
          : t('organization.apiKeys.orgProvidesKeys'),
      })
      if (!newValue) {
        await fetchKeyStatus()
      }
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || t('organization.apiKeys.updateFailed'),
      })
    } finally {
      setSettingsLoading(false)
    }
  }

  const setApiKey = async (provider: string) => {
    const apiKey = newApiKeys[provider]
    if (!apiKey) return

    const providerConfig = providers.find((p) => p.id === provider)
    if (providerConfig && !providerConfig.validation.test(apiKey.trim())) {
      setMessage({
        type: 'error',
        text: t('organization.apiKeys.invalidKeyFormat', { provider: providerConfig.name }),
      })
      return
    }

    setLoading((prev) => ({ ...prev, [provider]: true }))
    setMessage(null)

    try {
      await organizationsAPI.setOrgApiKey(organizationId, provider, apiKey)
      setMessage({
        type: 'success',
        text: t('organization.apiKeys.keySaved', { provider: providers.find((p) => p.id === provider)?.name }),
      })
      setNewApiKeys((prev) => ({ ...prev, [provider]: '' }))
      setShowApiKeys((prev) => ({ ...prev, [provider]: false }))
      await fetchKeyStatus()
      setTestResults((prev) => ({ ...prev, [provider]: null }))
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || t('organization.apiKeys.saveFailed'),
      })
    } finally {
      setLoading((prev) => ({ ...prev, [provider]: false }))
    }
  }

  const removeApiKey = async (provider: string) => {
    setLoading((prev) => ({ ...prev, [provider]: true }))
    setMessage(null)

    try {
      await organizationsAPI.removeOrgApiKey(organizationId, provider)
      setMessage({
        type: 'success',
        text: t('organization.apiKeys.keyRemoved', { provider: providers.find((p) => p.id === provider)?.name }),
      })
      await fetchKeyStatus()
      setTestResults((prev) => ({ ...prev, [provider]: null }))
    } catch (error: any) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || t('organization.apiKeys.removeFailed'),
      })
    } finally {
      setLoading((prev) => ({ ...prev, [provider]: false }))
    }
  }

  const testApiKey = async (provider: string) => {
    const apiKey = newApiKeys[provider]
    if (!apiKey) return

    setTestLoading((prev) => ({ ...prev, [provider]: true }))
    setTestResults((prev) => ({ ...prev, [provider]: null }))

    try {
      const result = await organizationsAPI.testOrgApiKey(
        organizationId,
        provider,
        apiKey
      )
      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: result.status === 'success' ? 'success' : 'error',
          message: result.message,
        },
      }))
    } catch (error: any) {
      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: 'error',
          message: error.response?.data?.detail || t('organization.apiKeys.testFailed'),
        },
      }))
    } finally {
      setTestLoading((prev) => ({ ...prev, [provider]: false }))
    }
  }

  const testSavedApiKey = async (provider: string) => {
    setTestLoading((prev) => ({ ...prev, [provider]: true }))
    setTestResults((prev) => ({ ...prev, [provider]: null }))

    try {
      const result = await organizationsAPI.testSavedOrgApiKey(
        organizationId,
        provider
      )
      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: result.status === 'success' ? 'success' : 'error',
          message: result.message,
        },
      }))
    } catch (error: any) {
      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: 'error',
          message: error.response?.data?.detail || t('organization.apiKeys.testFailed'),
        },
      }))
    } finally {
      setTestLoading((prev) => ({ ...prev, [provider]: false }))
    }
  }

  const configuredCount = Object.values(apiKeyStatus).filter(Boolean).length

  return (
    <Dialog open={open} onClose={() => onOpenChange(false)} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-2xl rounded-lg bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('organization.apiKeys.dialogTitle')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('organization.apiKeys.dialogDescription')}
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

              {/* Mode toggle (admin only) */}
              {isAdmin && (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {t('organization.apiKeys.orgProvidesToggle')}
                      </p>
                      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {!requirePrivateKeys
                          ? t('organization.apiKeys.sharedKeysActive')
                          : t('organization.apiKeys.enableSharedKeys')}
                      </p>
                    </div>
                    <button
                      onClick={toggleRequirePrivateKeys}
                      disabled={settingsLoading}
                      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 ${
                        !requirePrivateKeys
                          ? 'bg-emerald-600'
                          : 'bg-zinc-200 dark:bg-zinc-600'
                      } ${settingsLoading ? 'opacity-50' : ''}`}
                      role="switch"
                      aria-checked={!requirePrivateKeys}
                      aria-label={t('organization.apiKeys.orgProvidesToggle')}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          !requirePrivateKeys ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              )}

              {/* Non-admin info when members-pay mode */}
              {!isAdmin && requirePrivateKeys && (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    {t('organization.apiKeys.membersConfigureOwn')}
                  </p>
                </div>
              )}

              {/* Non-admin info when org-pays mode */}
              {!isAdmin && !requirePrivateKeys && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-800 dark:bg-emerald-900/20">
                  <p className="text-sm text-emerald-700 dark:text-emerald-400">
                    {t('organization.apiKeys.orgProvidesSharedKeys')}
                  </p>
                </div>
              )}

              {/* Provider cards (admin only) */}
              {isAdmin && (
                <>
                  <div className="text-sm text-zinc-600 dark:text-zinc-400">
                    <p>
                      {t('organization.apiKeys.configuredCount', { configured: configuredCount, total: providers.length })}
                    </p>
                    {requirePrivateKeys && (
                      <p className="mt-1 text-amber-600 dark:text-amber-400">
                        {t('organization.apiKeys.membersPersonalNote')}
                      </p>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-6">
                    {providers.map((provider) => {
                      const hasKey = apiKeyStatus[provider.id] || false
                      const isLoading = loading[provider.id] || false
                      const isTestLoading = testLoading[provider.id] || false
                      const testResult = testResults[provider.id]
                      const newKey = newApiKeys[provider.id] || ''
                      const showKey = showApiKeys[provider.id] || false

                      return (
                        <div
                          key={provider.id}
                          className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800"
                        >
                          <div className="mb-3 flex items-center justify-between">
                            <div className="flex items-center space-x-3">
                              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-700">
                                <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">
                                  {provider.name[0]}
                                </span>
                              </div>
                              <div>
                                <h3 className="font-medium text-zinc-900 dark:text-white">
                                  {provider.name}
                                </h3>
                                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                                  {getProviderDescription(provider.id)}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center space-x-2">
                              <span
                                className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                                  hasKey
                                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                                    : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400'
                                }`}
                              >
                                {hasKey ? t('organization.apiKeys.configured') : t('organization.apiKeys.notConfigured')}
                              </span>
                            </div>
                          </div>

                          {hasKey ? (
                            <div className="space-y-3">
                              {testResult && (
                                <div
                                  className={`rounded-md p-3 text-sm ${
                                    testResult.type === 'success'
                                      ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                                      : 'border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                                  }`}
                                >
                                  <div className="whitespace-pre-wrap">
                                    {testResult.message}
                                  </div>
                                </div>
                              )}

                              <div className="flex justify-end space-x-2">
                                <Button
                                  variant="outline"
                                  onClick={() => testSavedApiKey(provider.id)}
                                  disabled={isTestLoading || isLoading}
                                  className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
                                >
                                  {isTestLoading ? t('organization.apiKeys.testing') : t('organization.apiKeys.testConnection')}
                                </Button>
                                <Button
                                  variant="outline"
                                  onClick={() => removeApiKey(provider.id)}
                                  disabled={isLoading || isTestLoading}
                                  className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                                >
                                  {isLoading ? t('organization.apiKeys.removing') : t('organization.apiKeys.removeKey')}
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="space-y-3">
                              <div className="relative">
                                <input
                                  type={showKey ? 'text' : 'password'}
                                  placeholder={provider.placeholder}
                                  value={newKey}
                                  onChange={(e) =>
                                    setNewApiKeys((prev) => ({
                                      ...prev,
                                      [provider.id]: e.target.value,
                                    }))
                                  }
                                  className="w-full rounded-full bg-white px-4 py-2 pr-10 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                />
                                <button
                                  type="button"
                                  onClick={() =>
                                    setShowApiKeys((prev) => ({
                                      ...prev,
                                      [provider.id]: !prev[provider.id],
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

                              {testResult && (
                                <div
                                  className={`rounded-md p-3 text-sm ${
                                    testResult.type === 'success'
                                      ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                                      : 'border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                                  }`}
                                >
                                  <div className="whitespace-pre-wrap">
                                    {testResult.message}
                                  </div>
                                </div>
                              )}

                              <div className="flex justify-end space-x-2">
                                <Button
                                  variant="outline"
                                  onClick={() => testApiKey(provider.id)}
                                  disabled={isTestLoading || isLoading || !newKey}
                                  className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
                                >
                                  {isTestLoading ? t('organization.apiKeys.testing') : t('organization.apiKeys.testConnection')}
                                </Button>
                                <Button
                                  variant="filled"
                                  onClick={() => setApiKey(provider.id)}
                                  disabled={isLoading || isTestLoading || !newKey}
                                >
                                  {isLoading ? t('organization.apiKeys.saving') : t('organization.apiKeys.saveKey')}
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>

                  <div className="space-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                    <p>{t('organization.apiKeys.encryptedInfo')}</p>
                    <p>{t('organization.apiKeys.sharedInfo')}</p>
                    <p>{t('organization.apiKeys.adminOnlyInfo')}</p>
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
