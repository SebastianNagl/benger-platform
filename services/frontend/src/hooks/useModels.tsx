'use client'

import { api } from '@/lib/api'
import { ParameterConstraints } from '@/lib/api/types'
import { useI18n } from '@/contexts/I18nContext'
import { useCallback, useEffect, useState } from 'react'

export interface ModelError {
  type:
    | 'NO_API_KEYS'
    | 'AUTH_FAILED'
    | 'SERVER_ERROR'
    | 'NETWORK_ERROR'
    | 'UNKNOWN'
  message: string
  details?: string
}

export interface Model {
  id: string
  name: string
  description?: string
  provider: string
  model_type: string
  capabilities: string[]
  is_active: boolean
  created_at: string | null
  updated_at?: string | null
  default_config?: {
    reasoning_config?: {
      parameter: string
      type: string
      values?: string[]
      min?: number
      max?: number
      default: string | number | boolean
      label?: string
    }
  }
  parameter_constraints?: ParameterConstraints | null
}

export interface UseModelsReturn {
  models: Model[]
  loading: boolean
  error: ModelError | null
  refetch: () => Promise<void>
  hasApiKeys: boolean
  apiKeyStatus: Record<string, boolean> | null
}

export function useModels(): UseModelsReturn {
  const { t } = useI18n()
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ModelError | null>(null)

  const fetchModels = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch available models directly - the /available-models endpoint
      // already handles org context (via X-Organization-Context header) and
      // resolves providers through org or user API keys as appropriate.
      const data = await api.getAvailableModels()
      setModels(data)

      if (data.length === 0) {
        setError({
          type: 'NO_API_KEYS',
          message: t('models.errors.noApiKeys'),
          details: t('models.errors.noApiKeysDetails'),
        })
      }
    } catch (err: any) {
      console.error('Failed to fetch models:', err)

      let errorType: ModelError['type'] = 'UNKNOWN'
      let message = t('models.errors.loadFailed')
      let details = err?.message || t('models.errors.unexpected')

      if (
        err?.status === 401 ||
        err?.message?.includes('Unauthorized') ||
        err?.message?.includes('credentials')
      ) {
        errorType = 'AUTH_FAILED'
        message = t('models.errors.authFailed')
        details = t('models.errors.authFailedDetails')
      } else if (
        err?.status >= 500 ||
        err?.message?.includes('Internal server error')
      ) {
        errorType = 'SERVER_ERROR'
        message = t('models.errors.serverError')
        details = t('models.errors.serverErrorDetails')
      } else if (err?.name === 'TypeError' && err?.message?.includes('fetch')) {
        errorType = 'NETWORK_ERROR'
        message = t('models.errors.networkError')
        details = t('models.errors.networkErrorDetails')
      }

      setError({ type: errorType, message, details })
      setModels([])
    } finally {
      setLoading(false)
    }
  }, [t])

  const refetch = useCallback(async () => {
    await fetchModels()
  }, [fetchModels])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  return {
    models,
    loading,
    error,
    refetch,
    hasApiKeys: models.length > 0,
    apiKeyStatus: null,
  }
}

export default useModels
