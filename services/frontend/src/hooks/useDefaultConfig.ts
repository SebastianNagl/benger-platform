/**
 * Hook for managing default configurations
 * Issue #204: Centralized temperature configuration system
 */

import {
  DefaultConfig,
  getAllDefaultConfigs,
  getDefaultConfig,
} from '@/lib/api/admin-defaults'
import { useCallback, useEffect, useState } from 'react'

interface UseDefaultConfigReturn {
  config: DefaultConfig | null
  loading: boolean
  error: string | null
  refresh: () => void
}

/**
 * Hook to get default configuration for a specific task type
 */
export function useDefaultConfig(taskType: string): UseDefaultConfigReturn {
  const [config, setConfig] = useState<DefaultConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const configData = await getDefaultConfig(taskType)
      setConfig(configData)
    } catch (err) {
      console.error('Failed to fetch default config:', err)
      setError(
        err instanceof Error ? err.message : 'Failed to fetch default config'
      )
      // Provide fallback values
      setConfig({
        task_type: taskType,
        temperature: 0,
        max_tokens: 500,
        generation_config: { temperature: 0, max_tokens: 500 },
      })
    } finally {
      setLoading(false)
    }
  }, [taskType])

  useEffect(() => {
    if (taskType) {
      fetchConfig()
    }
  }, [taskType, fetchConfig])

  return {
    config,
    loading,
    error,
    refresh: fetchConfig,
  }
}

interface UseAllDefaultConfigsReturn {
  configs: Record<string, DefaultConfig>
  loading: boolean
  error: string | null
  refresh: () => void
}

/**
 * Hook to get default configurations for all task types
 */
export function useAllDefaultConfigs(): UseAllDefaultConfigsReturn {
  const [configs, setConfigs] = useState<Record<string, DefaultConfig>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAllConfigs = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const configData = await getAllDefaultConfigs()
      setConfigs(configData)
    } catch (err) {
      console.error('Failed to fetch all default configs:', err)
      setError(
        err instanceof Error ? err.message : 'Failed to fetch default configs'
      )
      // Provide fallback values
      setConfigs({
        qa: {
          task_type: 'qa',
          temperature: 0,
          max_tokens: 500,
          generation_config: { temperature: 0, max_tokens: 500 },
        },
        qa_reasoning: {
          task_type: 'qa_reasoning',
          temperature: 0,
          max_tokens: 1000,
          generation_config: { temperature: 0, max_tokens: 1000 },
        },
        multiple_choice: {
          task_type: 'multiple_choice',
          temperature: 0,
          max_tokens: 200,
          generation_config: { temperature: 0, max_tokens: 200 },
        },
        generation: {
          task_type: 'generation',
          temperature: 0,
          max_tokens: 2000,
          generation_config: { temperature: 0, max_tokens: 2000 },
        },
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAllConfigs()
  }, [fetchAllConfigs])

  return {
    configs,
    loading,
    error,
    refresh: fetchAllConfigs,
  }
}

/**
 * Helper function to get temperature default for a task type
 */
export function getDefaultTemperature(taskType: string): number {
  // Centralized temperature defaults
  return 0
}

/**
 * Helper function to get max tokens default for a task type
 */
export function getDefaultMaxTokens(taskType: string): number {
  // Centralized max tokens defaults
  const defaults = {
    qa: 500,
    qa_reasoning: 1000,
    multiple_choice: 200,
    generation: 2000,
  }
  return defaults[taskType as keyof typeof defaults] || 500
}
