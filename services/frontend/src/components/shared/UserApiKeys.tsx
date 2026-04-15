'use client'

import apiClient from '@/lib/api'
import { useI18n } from '@/contexts/I18nContext'
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'
import { Button } from './Button'

interface UserApiKeysProps {
  disabled?: boolean
  disabledMessage?: string
}

interface ApiKeyStatus {
  openai: boolean
  anthropic: boolean
  google: boolean
  deepinfra: boolean
  grok: boolean
  mistral: boolean
  cohere: boolean
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
    description: 'shared.userApiKeys.descOpenai',
    placeholder: 'sk-...',
    validation: /^sk-[a-zA-Z0-9_-]{20,}$/,
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'shared.userApiKeys.descAnthropic',
    placeholder: 'sk-ant-...',
    validation: /^sk-ant-[a-zA-Z0-9-_]{30,}$/,
  },
  {
    id: 'google',
    name: 'Google',
    description: 'shared.userApiKeys.descGoogle',
    placeholder: 'AI...',
    validation: /^[a-zA-Z0-9_-]{20,}$/,
  },
  {
    id: 'deepinfra',
    name: 'DeepInfra',
    description: 'shared.userApiKeys.descDeepinfra',
    placeholder: 'Your DeepInfra API key',
    validation: /^[a-zA-Z0-9]{20,}$/,
  },
  {
    id: 'grok',
    name: 'Grok (xAI)',
    description: 'shared.userApiKeys.descGrok',
    placeholder: 'xai-...',
    validation: /^xai-[a-zA-Z0-9_-]{10,}$/,
  },
  {
    id: 'mistral',
    name: 'Mistral AI',
    description: 'shared.userApiKeys.descMistral',
    placeholder: 'Your Mistral API key',
    validation: /^[a-zA-Z0-9]{20,}$/,
  },
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'shared.userApiKeys.descCohere',
    placeholder: 'Your Cohere API key',
    validation: /^[a-zA-Z0-9]{20,}$/,
  },
]

export default function UserApiKeys({ disabled = false, disabledMessage }: UserApiKeysProps = {}) {
  const { t } = useI18n()

  const getErrorHelpText = (
    errorType: string | undefined,
    provider: string
  ): string => {
    switch (errorType) {
      case 'auth':
        return t('shared.userApiKeys.errorAuth', { provider })
      case 'network':
        return t('shared.userApiKeys.errorNetwork')
      case 'timeout':
        return t('shared.userApiKeys.errorTimeout')
      case 'quota':
        return t('shared.userApiKeys.errorQuota')
      default:
        return t('shared.userApiKeys.errorDefault')
    }
  }

  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus>({
    openai: false,
    anthropic: false,
    google: false,
    deepinfra: false,
    grok: false,
    mistral: false,
    cohere: false,
  })
  const [newApiKeys, setNewApiKeys] = useState<Record<string, string>>({})
  const [showApiKeys, setShowApiKeys] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const [testLoading, setTestLoading] = useState<Record<string, boolean>>({})
  const [validationErrors, setValidationErrors] = useState<
    Record<string, string>
  >({})
  const [testResults, setTestResults] = useState<
    Record<string, TestResult | null>
  >({})
  const [message, setMessage] = useState<{
    type: 'success' | 'error'
    text: string
  } | null>(null)

  useEffect(() => {
    fetchApiKeyStatus()
  }, [])

  const fetchApiKeyStatus = async () => {
    try {
      const data = await apiClient.getUserApiKeys()
      const status: ApiKeyStatus = {
        openai: data.api_key_status?.openai || false,
        anthropic: data.api_key_status?.anthropic || false,
        google: data.api_key_status?.google || false,
        deepinfra: data.api_key_status?.deepinfra || false,
        grok: data.api_key_status?.grok || false,
        mistral: data.api_key_status?.mistral || false,
        cohere: data.api_key_status?.cohere || false,
      }

      setApiKeyStatus(status)
    } catch (error) {
      console.error('Error fetching API key status:', error)
      setMessage({ type: 'error', text: t('shared.userApiKeys.failedLoadStatus') })
    }
  }

  const validateApiKey = (provider: string, apiKey: string): string | null => {
    const providerConfig = providers.find((p) => p.id === provider)
    if (!providerConfig) return t('shared.userApiKeys.invalidProvider')

    if (!apiKey.trim()) return t('shared.userApiKeys.apiKeyRequired')

    if (!providerConfig.validation.test(apiKey.trim())) {
      return t('shared.userApiKeys.invalidKeyFormat', { provider: providerConfig.name })
    }

    return null
  }

  const setApiKey = async (provider: string) => {
    const apiKey = newApiKeys[provider]
    if (!apiKey) return

    // Validate API key format
    const validationError = validateApiKey(provider, apiKey)
    if (validationError) {
      setValidationErrors((prev) => ({ ...prev, [provider]: validationError }))
      return
    }

    setLoading((prev) => ({ ...prev, [provider]: true }))
    setValidationErrors((prev) => ({ ...prev, [provider]: '' }))
    setMessage(null)

    try {
      await apiClient.setUserApiKey(provider, apiKey)
      setMessage({
        type: 'success',
        text: t('shared.userApiKeys.keySaved', { provider: providers.find((p) => p.id === provider)?.name }),
      })
      setNewApiKeys((prev) => ({ ...prev, [provider]: '' }))
      setShowApiKeys((prev) => ({ ...prev, [provider]: false }))
      await fetchApiKeyStatus()
      setTestResults((prev) => ({ ...prev, [provider]: null }))

      // Notify other components that API keys have changed
      window.dispatchEvent(
        new CustomEvent('apiKeysChanged', {
          detail: { provider, action: 'add' },
        })
      )
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail || t('shared.userApiKeys.failedSave')
      setMessage({ type: 'error', text: errorMessage })
    } finally {
      setLoading((prev) => ({ ...prev, [provider]: false }))
    }
  }

  const removeApiKey = async (provider: string) => {
    setLoading((prev) => ({ ...prev, [provider]: true }))
    setMessage(null)

    try {
      await apiClient.removeUserApiKey(provider)
      setMessage({
        type: 'success',
        text: t('shared.userApiKeys.keyRemoved', { provider: providers.find((p) => p.id === provider)?.name }),
      })
      await fetchApiKeyStatus()
      setTestResults((prev) => ({ ...prev, [provider]: null }))

      // Notify other components that API keys have changed
      window.dispatchEvent(
        new CustomEvent('apiKeysChanged', {
          detail: { provider, action: 'remove' },
        })
      )
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail || t('shared.userApiKeys.failedRemove')
      setMessage({ type: 'error', text: errorMessage })
    } finally {
      setLoading((prev) => ({ ...prev, [provider]: false }))
    }
  }

  const handleApiKeyChange = (provider: string, value: string) => {
    setNewApiKeys((prev) => ({ ...prev, [provider]: value }))
    // Clear validation error when user starts typing
    if (validationErrors[provider]) {
      setValidationErrors((prev) => ({ ...prev, [provider]: '' }))
    }
  }

  const toggleShowApiKey = (provider: string) => {
    setShowApiKeys((prev) => ({ ...prev, [provider]: !prev[provider] }))
  }

  const testApiKeyConnection = async (provider: string) => {
    const apiKey = newApiKeys[provider]
    if (!apiKey) return

    // Validate API key format first
    const validationError = validateApiKey(provider, apiKey)
    if (validationError) {
      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: 'error',
          message: `${validationError}\n\n${getErrorHelpText('auth', provider)}`,
        },
      }))
      return
    }

    setTestLoading((prev) => ({ ...prev, [provider]: true }))
    setTestResults((prev) => ({ ...prev, [provider]: null }))

    try {
      const result = await apiClient.testUserApiKey(provider, apiKey)
      const displayMessage =
        result.status === 'success'
          ? result.message
          : `${result.message}\n\n${getErrorHelpText(undefined, provider)}`

      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: result.status,
          message: displayMessage,
        },
      }))
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail || t('shared.userApiKeys.connectionTestFailed')
      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: 'error',
          message: `${errorMessage}\n\n${getErrorHelpText(undefined, provider)}`,
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
      const result = await apiClient.testSavedUserApiKey(provider)
      const displayMessage =
        result.status === 'success'
          ? result.message
          : `${result.message}\n\n${getErrorHelpText(undefined, provider)}`

      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: result.status,
          message: displayMessage,
        },
      }))
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail || t('shared.userApiKeys.connectionTestFailed')
      setTestResults((prev) => ({
        ...prev,
        [provider]: {
          type: 'error',
          message: `${errorMessage}\n\n${getErrorHelpText(undefined, provider)}`,
        },
      }))
    } finally {
      setTestLoading((prev) => ({ ...prev, [provider]: false }))
    }
  }

  return (
    <div className="space-y-6">
      {disabled && disabledMessage ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950/30">
          <p className="text-sm text-blue-700 dark:text-blue-400">
            {disabledMessage}
          </p>
        </div>
      ) : (
        <div className="text-sm text-zinc-600 dark:text-zinc-400">
          <p>
            {t('shared.userApiKeys.introText')}
          </p>
        </div>
      )}

      {message && (
        <div
          className={`rounded-md border p-4 ${
            message.type === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
              : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
          }`}
        >
          {message.text}
        </div>
      )}

      <div className={`grid grid-cols-1 gap-6 ${disabled ? 'pointer-events-none opacity-60' : ''}`}
        title={disabled ? disabledMessage : undefined}
      >
        {providers.map((provider) => (
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
                    {t(provider.description)}
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                    apiKeyStatus[provider.id as keyof ApiKeyStatus]
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                      : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400'
                  }`}
                >
                  {apiKeyStatus[provider.id as keyof ApiKeyStatus]
                    ? t('shared.userApiKeys.configured')
                    : t('shared.userApiKeys.notConfigured')}
                </span>
              </div>
            </div>

            {apiKeyStatus[provider.id as keyof ApiKeyStatus] ? (
              <div className="space-y-3">
                {testResults[provider.id] && (
                  <div
                    className={`rounded-md p-3 text-sm ${
                      testResults[provider.id]?.type === 'success'
                        ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                        : 'border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                    }`}
                  >
                    <div className="whitespace-pre-wrap">
                      {testResults[provider.id]?.message}
                    </div>
                  </div>
                )}

                <div className="flex justify-end space-x-2">
                  <Button
                    variant="outline"
                    onClick={() => testSavedApiKey(provider.id)}
                    disabled={testLoading[provider.id] || loading[provider.id]}
                    className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
                  >
                    {testLoading[provider.id]
                      ? t('shared.userApiKeys.testing')
                      : t('shared.userApiKeys.testConnection')}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => removeApiKey(provider.id)}
                    disabled={loading[provider.id] || testLoading[provider.id]}
                    className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
                  >
                    {loading[provider.id] ? t('shared.userApiKeys.removing') : t('shared.userApiKeys.removeApiKey')}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="relative">
                  <input
                    type={showApiKeys[provider.id] ? 'text' : 'password'}
                    placeholder={provider.placeholder}
                    value={newApiKeys[provider.id] || ''}
                    onChange={(e) =>
                      handleApiKeyChange(provider.id, e.target.value)
                    }
                    className="w-full rounded-full bg-white px-4 py-2 pr-10 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                  />
                  <button
                    type="button"
                    onClick={() => toggleShowApiKey(provider.id)}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                  >
                    {showApiKeys[provider.id] ? (
                      <EyeSlashIcon className="h-4 w-4" />
                    ) : (
                      <EyeIcon className="h-4 w-4" />
                    )}
                  </button>
                </div>

                {validationErrors[provider.id] && (
                  <p className="text-sm text-red-600 dark:text-red-400">
                    {validationErrors[provider.id]}
                  </p>
                )}

                {testResults[provider.id] && (
                  <div
                    className={`rounded-md p-3 text-sm ${
                      testResults[provider.id]?.type === 'success'
                        ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
                        : 'border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
                    }`}
                  >
                    <div className="whitespace-pre-wrap">
                      {testResults[provider.id]?.message}
                    </div>
                  </div>
                )}

                <div className="flex justify-end space-x-2">
                  <Button
                    variant="outline"
                    onClick={() => testApiKeyConnection(provider.id)}
                    disabled={
                      testLoading[provider.id] ||
                      loading[provider.id] ||
                      !newApiKeys[provider.id]
                    }
                    className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
                  >
                    {testLoading[provider.id]
                      ? t('shared.userApiKeys.testing')
                      : t('shared.userApiKeys.testConnection')}
                  </Button>
                  <Button
                    variant="filled"
                    onClick={() => setApiKey(provider.id)}
                    disabled={
                      loading[provider.id] ||
                      testLoading[provider.id] ||
                      !newApiKeys[provider.id]
                    }
                  >
                    {loading[provider.id] ? t('shared.userApiKeys.saving') : t('shared.userApiKeys.saveApiKey')}
                  </Button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-1 text-xs text-zinc-500 dark:text-zinc-400">
        <p>{t('shared.userApiKeys.helpEncrypted')}</p>
        <p>
          {t('shared.userApiKeys.helpProviderAccess')}
        </p>
        <p>{t('shared.userApiKeys.helpNeverShared')}</p>
      </div>
    </div>
  )
}
