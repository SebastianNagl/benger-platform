'use client'

import { useI18n } from '@/contexts/I18nContext'
import { useModelScope } from '@/contexts/ModelScopeContext'
import { api } from '@/lib/api'
import { ParameterConstraints } from '@/lib/api/types'
import type { RecommendedParameters } from '@/lib/modelConstraints'
import { useCallback, useEffect, useState } from 'react'

export interface ModelError {
  type:
    'NO_API_KEYS' | 'AUTH_FAILED' | 'SERVER_ERROR' | 'NETWORK_ERROR' | 'UNKNOWN'
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
  recommended_parameters?: RecommendedParameters | null
  // BYOM: custom models arrive in the same flat array with
  // is_official: false; officials carry true or omit the field.
  is_official?: boolean
  requires_api_key?: boolean
  has_credential?: boolean
  base_url?: string
  created_by?: string | null
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
  // The scope decides whose keys are listed: the project's dispatch org
  // (project pages), the wizard's creation target, else personal keys.
  const { projectId, organizationId } = useModelScope()
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ModelError | null>(null)

  const fetchModels = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      // The endpoint resolves the providers through the org key of the
      // scope or the user's own keys, exactly as the worker will.
      const data = await api.getAvailableModels({
        projectId: projectId ?? undefined,
        organizationId: organizationId ?? undefined,
      })
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
  }, [t, projectId, organizationId])

  const refetch = useCallback(async () => {
    await fetchModels()
  }, [fetchModels])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  // Refetch when API keys or custom-model credentials change elsewhere
  // (UserApiKeys and CustomModelCredentialRow dispatch 'apiKeysChanged'),
  // so pickers pick up newly runnable models without a page reload.
  useEffect(() => {
    const handleApiKeysChanged = () => {
      fetchModels()
    }
    window.addEventListener('apiKeysChanged', handleApiKeysChanged)
    return () => {
      window.removeEventListener('apiKeysChanged', handleApiKeysChanged)
    }
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
