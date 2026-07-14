'use client'

/**
 * CustomModelCredentialRow - per-user API key management for one custom
 * model (BYOM). Cloned from the per-provider card in UserApiKeys, backed by
 * the /custom-models/{id}/credential endpoints.
 *
 * Every user stores their OWN key for a custom model. When the model was
 * registered with requires_api_key: false, the row collapses to an
 * informational "no key required" state with only a Test button.
 */

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { customModelsAPI } from '@/lib/api/customModels'
import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface TestResult {
  type: 'success' | 'error'
  message: string
}

interface CustomModelCredentialRowProps {
  modelId: string
  baseUrl: string
  requiresApiKey: boolean
  /** Initial credential state (from the list payload); refreshed via GET. */
  initialHasCredential?: boolean
  /** Called after a successful save/remove (in addition to apiKeysChanged). */
  onChanged?: () => void
}

export function CustomModelCredentialRow({
  modelId,
  baseUrl,
  requiresApiKey,
  initialHasCredential = false,
  onChanged,
}: CustomModelCredentialRowProps) {
  const { t } = useI18n()

  const [hasCredential, setHasCredential] = useState(initialHasCredential)
  const [newApiKey, setNewApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [loading, setLoading] = useState(false)
  const [testLoading, setTestLoading] = useState(false)
  const [validationError, setValidationError] = useState('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [message, setMessage] = useState<TestResult | null>(null)

  useEffect(() => {
    if (!requiresApiKey) return
    let cancelled = false
    customModelsAPI
      .getCredentialStatus(modelId)
      .then((status) => {
        if (!cancelled) setHasCredential(status.has_credential)
      })
      .catch(() => {
        // Keep the initial state on failure - the row stays usable.
      })
    return () => {
      cancelled = true
    }
  }, [modelId, requiresApiKey])

  const notifyKeysChanged = (action: 'add' | 'remove') => {
    window.dispatchEvent(
      new CustomEvent('apiKeysChanged', {
        detail: { provider: 'custom', modelId, action },
      })
    )
  }

  const saveCredential = async () => {
    const apiKey = newApiKey.trim()
    if (!apiKey) {
      setValidationError(t('customModels.credential.keyRequired'))
      return
    }

    setLoading(true)
    setValidationError('')
    setMessage(null)

    try {
      await customModelsAPI.setCredential(modelId, apiKey)
      setMessage({
        type: 'success',
        message: t('customModels.credential.saveSuccess'),
      })
      setNewApiKey('')
      setShowApiKey(false)
      setHasCredential(true)
      setTestResult(null)
      notifyKeysChanged('add')
      onChanged?.()
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail ||
        t('customModels.credential.saveFailed')
      setMessage({ type: 'error', message: errorMessage })
    } finally {
      setLoading(false)
    }
  }

  const removeCredential = async () => {
    setLoading(true)
    setMessage(null)

    try {
      await customModelsAPI.deleteCredential(modelId)
      setMessage({
        type: 'success',
        message: t('customModels.credential.removeSuccess'),
      })
      setHasCredential(false)
      setTestResult(null)
      notifyKeysChanged('remove')
      onChanged?.()
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail ||
        t('customModels.credential.removeFailed')
      setMessage({ type: 'error', message: errorMessage })
    } finally {
      setLoading(false)
    }
  }

  /**
   * Test the connection. With an unsaved key in the input, the key is sent
   * along (tested without saving); otherwise the stored credential (or no
   * key for keyless models) is used.
   */
  const testConnection = async () => {
    setTestLoading(true)
    setTestResult(null)

    try {
      const key = newApiKey.trim()
      const result = await customModelsAPI.testConnection(
        modelId,
        key ? { api_key: key } : {}
      )
      setTestResult({ type: result.status, message: result.message })
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail ||
        t('customModels.credential.testFailed')
      setTestResult({ type: 'error', message: errorMessage })
    } finally {
      setTestLoading(false)
    }
  }

  const resultBox = (result: TestResult | null, testId: string) =>
    result && (
      <div
        className={`rounded-md p-3 text-sm ${
          result.type === 'success'
            ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'
            : 'border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400'
        }`}
        data-testid={testId}
      >
        <div className="whitespace-pre-wrap">{result.message}</div>
      </div>
    )

  return (
    <div
      className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800"
      data-testid={`custom-model-credential-row-${modelId}`}
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h4 className="font-medium text-zinc-900 dark:text-white">
            {t('customModels.credential.title')}
          </h4>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {t('customModels.credential.endpointNotice')}{' '}
            <span className="font-mono">{baseUrl}</span>
          </p>
        </div>
        {requiresApiKey && (
          <span
            className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
              hasCredential
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400'
            }`}
            data-testid="credential-status-pill"
          >
            {hasCredential
              ? t('customModels.credential.configured')
              : t('customModels.credential.notConfigured')}
          </span>
        )}
      </div>

      {message && resultBox(message, 'credential-message')}

      {!requiresApiKey ? (
        <div className="space-y-3">
          <div
            className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-400"
            data-testid="credential-no-key-required"
          >
            {t('customModels.credential.noKeyRequired')}
          </div>

          {resultBox(testResult, 'credential-test-result')}

          <div className="flex justify-end">
            <Button
              variant="outline"
              onClick={testConnection}
              disabled={testLoading}
              className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
              data-testid="credential-test-button"
            >
              {testLoading
                ? t('customModels.credential.testing')
                : t('customModels.credential.testConnection')}
            </Button>
          </div>
        </div>
      ) : hasCredential ? (
        <div className="space-y-3">
          {resultBox(testResult, 'credential-test-result')}

          <div className="flex justify-end space-x-2">
            <Button
              variant="outline"
              onClick={testConnection}
              disabled={testLoading || loading}
              className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
              data-testid="credential-test-button"
            >
              {testLoading
                ? t('customModels.credential.testing')
                : t('customModels.credential.testConnection')}
            </Button>
            <Button
              variant="outline"
              onClick={removeCredential}
              disabled={loading || testLoading}
              className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
              data-testid="credential-remove-button"
            >
              {loading
                ? t('customModels.credential.removing')
                : t('customModels.credential.remove')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="relative">
            <input
              type={showApiKey ? 'text' : 'password'}
              placeholder={t('customModels.credential.placeholder')}
              value={newApiKey}
              onChange={(e) => {
                setNewApiKey(e.target.value)
                if (validationError) setValidationError('')
              }}
              className="w-full rounded-full bg-white px-4 py-2 pr-10 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
              data-testid="credential-key-input"
            />
            <button
              type="button"
              onClick={() => setShowApiKey((prev) => !prev)}
              className="absolute inset-y-0 right-0 flex items-center pr-3 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
              data-testid="credential-toggle-visibility"
            >
              {showApiKey ? (
                <EyeSlashIcon className="h-4 w-4" />
              ) : (
                <EyeIcon className="h-4 w-4" />
              )}
            </button>
          </div>

          {validationError && (
            <p
              className="text-sm text-red-600 dark:text-red-400"
              data-testid="credential-validation-error"
            >
              {validationError}
            </p>
          )}

          {resultBox(testResult, 'credential-test-result')}

          <div className="flex justify-end space-x-2">
            <Button
              variant="outline"
              onClick={testConnection}
              disabled={testLoading || loading || !newApiKey.trim()}
              className="text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/50"
              data-testid="credential-test-button"
            >
              {testLoading
                ? t('customModels.credential.testing')
                : t('customModels.credential.testConnection')}
            </Button>
            <Button
              variant="filled"
              onClick={saveCredential}
              disabled={loading || testLoading || !newApiKey.trim()}
              data-testid="credential-save-button"
            >
              {loading
                ? t('customModels.credential.saving')
                : t('customModels.credential.save')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
