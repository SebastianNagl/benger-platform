/**
 * @jest-environment jsdom
 */

/**
 * Comprehensive tests for useDefaultConfig hook
 * Tests both useDefaultConfig and useAllDefaultConfigs hooks
 * Following the established 8-part hook testing pattern
 */

import { renderHook, waitFor } from '@testing-library/react'
import {
  getDefaultMaxTokens,
  getDefaultTemperature,
  useAllDefaultConfigs,
  useDefaultConfig,
} from '../useDefaultConfig'

jest.mock('@/lib/api/admin-defaults', () => ({
  getDefaultConfig: jest.fn(),
  getAllDefaultConfigs: jest.fn(),
}))

import {
  getAllDefaultConfigs,
  getDefaultConfig,
} from '@/lib/api/admin-defaults'

const mockGetDefaultConfig = getDefaultConfig as jest.MockedFunction<
  typeof getDefaultConfig
>
const mockGetAllDefaultConfigs = getAllDefaultConfigs as jest.MockedFunction<
  typeof getAllDefaultConfigs
>

// Mock data
const mockQaConfig = {
  task_type: 'qa',
  temperature: 0,
  max_tokens: 500,
  generation_config: { temperature: 0, max_tokens: 500 },
}

const mockQaReasoningConfig = {
  task_type: 'qa_reasoning',
  temperature: 0,
  max_tokens: 1000,
  generation_config: { temperature: 0, max_tokens: 1000 },
}

const mockMultipleChoiceConfig = {
  task_type: 'multiple_choice',
  temperature: 0,
  max_tokens: 200,
  generation_config: { temperature: 0, max_tokens: 200 },
}

const mockGenerationConfig = {
  task_type: 'generation',
  temperature: 0,
  max_tokens: 2000,
  generation_config: { temperature: 0, max_tokens: 2000 },
}

const mockAllConfigs = {
  qa: mockQaConfig,
  qa_reasoning: mockQaReasoningConfig,
  multiple_choice: mockMultipleChoiceConfig,
  generation: mockGenerationConfig,
}

describe('useDefaultConfig', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    jest.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('1. Basic Hook Behavior', () => {
    it('should return expected interface', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current).toHaveProperty('config')
      expect(result.current).toHaveProperty('loading')
      expect(result.current).toHaveProperty('error')
      expect(result.current).toHaveProperty('refresh')
      expect(typeof result.current.refresh).toBe('function')
    })

    it('should initialize with loading state', () => {
      mockGetDefaultConfig.mockImplementation(() => new Promise(() => {}))

      const { result } = renderHook(() => useDefaultConfig('qa'))

      expect(result.current.loading).toBe(true)
      expect(result.current.config).toBeNull()
      expect(result.current.error).toBeNull()
    })

    it('should fetch data automatically on mount', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(mockGetDefaultConfig).toHaveBeenCalledTimes(1)
        expect(mockGetDefaultConfig).toHaveBeenCalledWith('qa')
      })
    })

    it('should not fetch data if taskType is empty', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig(''))

      await waitFor(() => {
        expect(result.current.loading).toBe(true)
      })

      expect(mockGetDefaultConfig).not.toHaveBeenCalled()
      expect(result.current.config).toBeNull()
    })
  })

  describe('2. Data Fetching/State Management', () => {
    it('should successfully fetch config for qa task type', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toEqual(mockQaConfig)
      expect(result.current.error).toBeNull()
      expect(mockGetDefaultConfig).toHaveBeenCalledWith('qa')
    })

    it('should successfully fetch config for qa_reasoning task type', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaReasoningConfig)

      const { result } = renderHook(() => useDefaultConfig('qa_reasoning'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toEqual(mockQaReasoningConfig)
      expect(result.current.config?.max_tokens).toBe(1000)
    })

    it('should successfully fetch config for multiple_choice task type', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockMultipleChoiceConfig)

      const { result } = renderHook(() => useDefaultConfig('multiple_choice'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toEqual(mockMultipleChoiceConfig)
      expect(result.current.config?.max_tokens).toBe(200)
    })

    it('should successfully fetch config for generation task type', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockGenerationConfig)

      const { result } = renderHook(() => useDefaultConfig('generation'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toEqual(mockGenerationConfig)
      expect(result.current.config?.max_tokens).toBe(2000)
    })

    it('should refetch when taskType changes', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result, rerender } = renderHook(
        ({ taskType }) => useDefaultConfig(taskType),
        {
          initialProps: { taskType: 'qa' },
        }
      )

      await waitFor(() => {
        expect(result.current.config?.task_type).toBe('qa')
      })

      mockGetDefaultConfig.mockResolvedValue(mockGenerationConfig)

      rerender({ taskType: 'generation' })

      await waitFor(() => {
        expect(result.current.config?.task_type).toBe('generation')
      })

      expect(mockGetDefaultConfig).toHaveBeenCalledTimes(2)
      expect(mockGetDefaultConfig).toHaveBeenNthCalledWith(1, 'qa')
      expect(mockGetDefaultConfig).toHaveBeenNthCalledWith(2, 'generation')
    })

    it('should preserve generation_config structure', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.generation_config).toBeDefined()
      expect(result.current.config?.generation_config.temperature).toBe(0)
      expect(result.current.config?.generation_config.max_tokens).toBe(500)
    })
  })

  describe('3. Loading States', () => {
    it('should set loading to true while fetching', async () => {
      let resolveConfig: any
      mockGetDefaultConfig.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveConfig = resolve
          })
      )

      const { result } = renderHook(() => useDefaultConfig('qa'))

      expect(result.current.loading).toBe(true)

      resolveConfig(mockQaConfig)

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })
    })

    it('should set loading to false after successful fetch', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toEqual(mockQaConfig)
    })

    it('should set loading to false after error', async () => {
      mockGetDefaultConfig.mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).not.toBeNull()
    })

    it('should set loading during manual refresh', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      let resolveRefresh: any
      mockGetDefaultConfig.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve
          })
      )

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.loading).toBe(true)
      })

      resolveRefresh(mockQaConfig)

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })
    })
  })

  describe('4. Error Handling', () => {
    it('should handle network errors and provide fallback config', async () => {
      mockGetDefaultConfig.mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).toBe('Network error')
      expect(result.current.config).toEqual({
        task_type: 'qa',
        temperature: 0,
        max_tokens: 500,
        generation_config: { temperature: 0, max_tokens: 500 },
      })
    })

    it('should handle non-Error objects in catch block', async () => {
      mockGetDefaultConfig.mockRejectedValue('String error')

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).toBe('Failed to fetch default config')
      expect(result.current.config).toBeDefined()
    })

    it('should provide fallback config with correct task_type on error', async () => {
      mockGetDefaultConfig.mockRejectedValue(new Error('API error'))

      const { result } = renderHook(() => useDefaultConfig('generation'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.task_type).toBe('generation')
      expect(result.current.config?.temperature).toBe(0)
      expect(result.current.config?.max_tokens).toBe(500)
    })

    it('should log errors to console', async () => {
      const error = new Error('Test error')
      mockGetDefaultConfig.mockRejectedValue(error)

      renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(console.error).toHaveBeenCalledWith(
          'Failed to fetch default config:',
          error
        )
      })
    })

    it('should clear error state on successful refresh after error', async () => {
      mockGetDefaultConfig.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.error).not.toBeNull()
      })

      mockGetDefaultConfig.mockResolvedValueOnce(mockQaConfig)

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.error).toBeNull()
        expect(result.current.config).toEqual(mockQaConfig)
      })
    })

    it('should handle API error with status code', async () => {
      const apiError = new Error('Server Error')
      Object.assign(apiError, { status: 500 })
      mockGetDefaultConfig.mockRejectedValue(apiError)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).toBe('Server Error')
      expect(result.current.config).toBeDefined()
    })
  })

  describe('5. Data Transformation/Callbacks', () => {
    it('should preserve all config fields', async () => {
      const fullConfig = {
        task_type: 'qa',
        temperature: 0.7,
        max_tokens: 800,
        generation_config: {
          temperature: 0.7,
          max_tokens: 800,
          top_p: 0.9,
          frequency_penalty: 0.5,
        },
      }
      mockGetDefaultConfig.mockResolvedValue(fullConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toEqual(fullConfig)
      expect(result.current.config?.generation_config.top_p).toBe(0.9)
      expect(result.current.config?.generation_config.frequency_penalty).toBe(
        0.5
      )
    })

    it('should handle config with additional fields in generation_config', async () => {
      const extendedConfig = {
        task_type: 'qa',
        temperature: 0,
        max_tokens: 500,
        generation_config: {
          temperature: 0,
          max_tokens: 500,
          extra_field: 'extra_value',
          nested: { field: 'value' },
        },
      }
      mockGetDefaultConfig.mockResolvedValue(extendedConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.generation_config.extra_field).toBe(
        'extra_value'
      )
      expect(result.current.config?.generation_config.nested).toEqual({
        field: 'value',
      })
    })

    it('should handle refresh callback correctly', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      mockGetDefaultConfig.mockResolvedValue({
        ...mockQaConfig,
        temperature: 0.5,
      })

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.config?.temperature).toBe(0.5)
      })

      expect(mockGetDefaultConfig).toHaveBeenCalledTimes(2)
    })
  })

  describe('6. Refetch/Invalidation', () => {
    it('should allow manual refetch via refresh function', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(mockGetDefaultConfig).toHaveBeenCalledTimes(1)

      result.current.refresh()

      await waitFor(() => {
        expect(mockGetDefaultConfig).toHaveBeenCalledTimes(2)
      })
    })

    it('should update config after refresh with new data', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.config?.max_tokens).toBe(500)
      })

      mockGetDefaultConfig.mockResolvedValue({
        ...mockQaConfig,
        max_tokens: 1000,
      })

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.config?.max_tokens).toBe(1000)
      })
    })

    it('should set loading state during refresh', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      let resolveRefresh: any
      mockGetDefaultConfig.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve
          })
      )

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.loading).toBe(true)
      })

      resolveRefresh(mockQaConfig)

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })
    })

    it('should handle rapid consecutive refresh calls', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      result.current.refresh()
      result.current.refresh()
      result.current.refresh()

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toEqual(mockQaConfig)
    })
  })

  describe('7. Edge Cases', () => {
    it('should handle config with zero values', async () => {
      const zeroConfig = {
        task_type: 'qa',
        temperature: 0,
        max_tokens: 0,
        generation_config: { temperature: 0, max_tokens: 0 },
      }
      mockGetDefaultConfig.mockResolvedValue(zeroConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.temperature).toBe(0)
      expect(result.current.config?.max_tokens).toBe(0)
    })

    it('should handle config with very large max_tokens', async () => {
      const largeConfig = {
        task_type: 'qa',
        temperature: 0,
        max_tokens: 100000,
        generation_config: { temperature: 0, max_tokens: 100000 },
      }
      mockGetDefaultConfig.mockResolvedValue(largeConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.max_tokens).toBe(100000)
    })

    it('should handle config with decimal temperature values', async () => {
      const decimalConfig = {
        task_type: 'qa',
        temperature: 0.7234567,
        max_tokens: 500,
        generation_config: { temperature: 0.7234567, max_tokens: 500 },
      }
      mockGetDefaultConfig.mockResolvedValue(decimalConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.temperature).toBe(0.7234567)
    })

    it('should handle unknown task types', async () => {
      mockGetDefaultConfig.mockResolvedValue({
        task_type: 'unknown_type',
        temperature: 0,
        max_tokens: 500,
        generation_config: { temperature: 0, max_tokens: 500 },
      })

      const { result } = renderHook(() => useDefaultConfig('unknown_type'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.task_type).toBe('unknown_type')
    })

    it('should handle task type with special characters', async () => {
      mockGetDefaultConfig.mockResolvedValue({
        task_type: 'qa-test_v2',
        temperature: 0,
        max_tokens: 500,
        generation_config: { temperature: 0, max_tokens: 500 },
      })

      const { result } = renderHook(() => useDefaultConfig('qa-test_v2'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.task_type).toBe('qa-test_v2')
    })

    it('should handle empty generation_config object', async () => {
      const emptyGenConfig = {
        task_type: 'qa',
        temperature: 0,
        max_tokens: 500,
        generation_config: {},
      }
      mockGetDefaultConfig.mockResolvedValue(emptyGenConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config?.generation_config).toEqual({})
    })

    it('should not refetch when taskType changes to empty string', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result, rerender } = renderHook(
        ({ taskType }) => useDefaultConfig(taskType),
        {
          initialProps: { taskType: 'qa' },
        }
      )

      await waitFor(() => {
        expect(result.current.config).toEqual(mockQaConfig)
      })

      expect(mockGetDefaultConfig).toHaveBeenCalledTimes(1)

      rerender({ taskType: '' })

      await waitFor(() => {
        expect(mockGetDefaultConfig).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('8. API Integration/Cleanup', () => {
    it('should call getDefaultConfig with correct parameters', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(mockGetDefaultConfig).toHaveBeenCalledWith('qa')
      })
    })

    it('should handle API response structure', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toMatchObject({
        task_type: expect.any(String),
        temperature: expect.any(Number),
        max_tokens: expect.any(Number),
        generation_config: expect.any(Object),
      })
    })

    it('should not retry failed API calls automatically', async () => {
      mockGetDefaultConfig.mockRejectedValue(new Error('Network error'))

      renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(mockGetDefaultConfig).toHaveBeenCalledTimes(1)
      })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(mockGetDefaultConfig).toHaveBeenCalledTimes(1)
    })

    it('should handle API response with extra fields gracefully', async () => {
      const configWithExtraFields = {
        ...mockQaConfig,
        extra_field: 'extra_value',
        another_field: 123,
      }
      mockGetDefaultConfig.mockResolvedValue(configWithExtraFields)

      const { result } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.config).toMatchObject(mockQaConfig)
    })

    it('should cleanup properly on unmount', async () => {
      mockGetDefaultConfig.mockResolvedValue(mockQaConfig)

      const { unmount } = renderHook(() => useDefaultConfig('qa'))

      await waitFor(() => {
        expect(mockGetDefaultConfig).toHaveBeenCalled()
      })

      unmount()

      expect(mockGetDefaultConfig).toHaveBeenCalledTimes(1)
    })
  })
})

describe('useAllDefaultConfigs', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    jest.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('1. Basic Hook Behavior', () => {
    it('should return expected interface', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current).toHaveProperty('configs')
      expect(result.current).toHaveProperty('loading')
      expect(result.current).toHaveProperty('error')
      expect(result.current).toHaveProperty('refresh')
      expect(typeof result.current.refresh).toBe('function')
    })

    it('should initialize with loading state', () => {
      mockGetAllDefaultConfigs.mockImplementation(() => new Promise(() => {}))

      const { result } = renderHook(() => useAllDefaultConfigs())

      expect(result.current.loading).toBe(true)
      expect(result.current.configs).toEqual({})
      expect(result.current.error).toBeNull()
    })

    it('should fetch data automatically on mount', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(mockGetAllDefaultConfigs).toHaveBeenCalledTimes(1)
      })
    })
  })

  describe('2. Data Fetching/State Management', () => {
    it('should successfully fetch all configs', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs).toEqual(mockAllConfigs)
      expect(result.current.error).toBeNull()
    })

    it('should return configs as object with task types as keys', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs).toHaveProperty('qa')
      expect(result.current.configs).toHaveProperty('qa_reasoning')
      expect(result.current.configs).toHaveProperty('multiple_choice')
      expect(result.current.configs).toHaveProperty('generation')
    })

    it('should preserve all config details for each task type', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs.qa).toEqual(mockQaConfig)
      expect(result.current.configs.generation.max_tokens).toBe(2000)
      expect(result.current.configs.multiple_choice.max_tokens).toBe(200)
    })
  })

  describe('3. Loading States', () => {
    it('should set loading to true while fetching', async () => {
      let resolveConfigs: any
      mockGetAllDefaultConfigs.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveConfigs = resolve
          })
      )

      const { result } = renderHook(() => useAllDefaultConfigs())

      expect(result.current.loading).toBe(true)

      resolveConfigs(mockAllConfigs)

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })
    })

    it('should set loading to false after successful fetch', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs).toEqual(mockAllConfigs)
    })

    it('should set loading to false after error', async () => {
      mockGetAllDefaultConfigs.mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).not.toBeNull()
    })
  })

  describe('4. Error Handling', () => {
    it('should handle network errors and provide fallback configs', async () => {
      mockGetAllDefaultConfigs.mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).toBe('Network error')
      expect(result.current.configs).toEqual(mockAllConfigs)
    })

    it('should handle non-Error objects in catch block', async () => {
      mockGetAllDefaultConfigs.mockRejectedValue('String error')

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.error).toBe('Failed to fetch default configs')
      expect(result.current.configs).toBeDefined()
    })

    it('should log errors to console', async () => {
      const error = new Error('Test error')
      mockGetAllDefaultConfigs.mockRejectedValue(error)

      renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(console.error).toHaveBeenCalledWith(
          'Failed to fetch all default configs:',
          error
        )
      })
    })

    it('should clear error state on successful refresh after error', async () => {
      mockGetAllDefaultConfigs.mockRejectedValueOnce(new Error('Network error'))

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.error).not.toBeNull()
      })

      mockGetAllDefaultConfigs.mockResolvedValueOnce(mockAllConfigs)

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.error).toBeNull()
        expect(result.current.configs).toEqual(mockAllConfigs)
      })
    })

    it('should provide complete fallback configs on error', async () => {
      mockGetAllDefaultConfigs.mockRejectedValue(new Error('API error'))

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs.qa).toBeDefined()
      expect(result.current.configs.qa_reasoning).toBeDefined()
      expect(result.current.configs.multiple_choice).toBeDefined()
      expect(result.current.configs.generation).toBeDefined()
    })
  })

  describe('5. Data Transformation/Callbacks', () => {
    it('should preserve all config fields for all task types', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      Object.values(result.current.configs).forEach((config) => {
        expect(config).toHaveProperty('task_type')
        expect(config).toHaveProperty('temperature')
        expect(config).toHaveProperty('max_tokens')
        expect(config).toHaveProperty('generation_config')
      })
    })

    it('should handle refresh callback correctly', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      const updatedConfigs = {
        ...mockAllConfigs,
        qa: { ...mockQaConfig, temperature: 0.5 },
      }
      mockGetAllDefaultConfigs.mockResolvedValue(updatedConfigs)

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.configs.qa.temperature).toBe(0.5)
      })

      expect(mockGetAllDefaultConfigs).toHaveBeenCalledTimes(2)
    })
  })

  describe('6. Refetch/Invalidation', () => {
    it('should allow manual refetch via refresh function', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(mockGetAllDefaultConfigs).toHaveBeenCalledTimes(1)

      result.current.refresh()

      await waitFor(() => {
        expect(mockGetAllDefaultConfigs).toHaveBeenCalledTimes(2)
      })
    })

    it('should update configs after refresh with new data', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.configs.qa.max_tokens).toBe(500)
      })

      const updatedConfigs = {
        ...mockAllConfigs,
        qa: { ...mockQaConfig, max_tokens: 1000 },
      }
      mockGetAllDefaultConfigs.mockResolvedValue(updatedConfigs)

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.configs.qa.max_tokens).toBe(1000)
      })
    })

    it('should set loading state during refresh', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      let resolveRefresh: any
      mockGetAllDefaultConfigs.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve
          })
      )

      result.current.refresh()

      await waitFor(() => {
        expect(result.current.loading).toBe(true)
      })

      resolveRefresh(mockAllConfigs)

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })
    })
  })

  describe('7. Edge Cases', () => {
    it('should handle empty configs object', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue({})

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs).toEqual({})
    })

    it('should handle configs with only subset of task types', async () => {
      const partialConfigs = {
        qa: mockQaConfig,
        generation: mockGenerationConfig,
      }
      mockGetAllDefaultConfigs.mockResolvedValue(partialConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(Object.keys(result.current.configs)).toHaveLength(2)
      expect(result.current.configs.qa).toBeDefined()
      expect(result.current.configs.generation).toBeDefined()
    })

    it('should handle configs with additional task types', async () => {
      const extendedConfigs = {
        ...mockAllConfigs,
        custom_type: {
          task_type: 'custom_type',
          temperature: 0.8,
          max_tokens: 3000,
          generation_config: { temperature: 0.8, max_tokens: 3000 },
        },
      }
      mockGetAllDefaultConfigs.mockResolvedValue(extendedConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs.custom_type).toBeDefined()
      expect(result.current.configs.custom_type.max_tokens).toBe(3000)
    })

    it('should handle null response', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(null)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs).toBeNull()
    })
  })

  describe('8. API Integration/Cleanup', () => {
    it('should call getAllDefaultConfigs with no parameters', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(mockGetAllDefaultConfigs).toHaveBeenCalledWith()
      })
    })

    it('should handle API response structure', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { result } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(result.current.loading).toBe(false)
      })

      expect(result.current.configs).toMatchObject({
        qa: expect.objectContaining({
          task_type: expect.any(String),
          temperature: expect.any(Number),
          max_tokens: expect.any(Number),
        }),
      })
    })

    it('should not retry failed API calls automatically', async () => {
      mockGetAllDefaultConfigs.mockRejectedValue(new Error('Network error'))

      renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(mockGetAllDefaultConfigs).toHaveBeenCalledTimes(1)
      })

      await new Promise((resolve) => setTimeout(resolve, 100))

      expect(mockGetAllDefaultConfigs).toHaveBeenCalledTimes(1)
    })

    it('should cleanup properly on unmount', async () => {
      mockGetAllDefaultConfigs.mockResolvedValue(mockAllConfigs)

      const { unmount } = renderHook(() => useAllDefaultConfigs())

      await waitFor(() => {
        expect(mockGetAllDefaultConfigs).toHaveBeenCalled()
      })

      unmount()

      expect(mockGetAllDefaultConfigs).toHaveBeenCalledTimes(1)
    })
  })
})

describe('Helper Functions', () => {
  describe('getDefaultTemperature', () => {
    it('should return 0 for any task type', () => {
      expect(getDefaultTemperature('qa')).toBe(0)
      expect(getDefaultTemperature('qa_reasoning')).toBe(0)
      expect(getDefaultTemperature('multiple_choice')).toBe(0)
      expect(getDefaultTemperature('generation')).toBe(0)
      expect(getDefaultTemperature('unknown')).toBe(0)
    })
  })

  describe('getDefaultMaxTokens', () => {
    it('should return correct max_tokens for qa', () => {
      expect(getDefaultMaxTokens('qa')).toBe(500)
    })

    it('should return correct max_tokens for qa_reasoning', () => {
      expect(getDefaultMaxTokens('qa_reasoning')).toBe(1000)
    })

    it('should return correct max_tokens for multiple_choice', () => {
      expect(getDefaultMaxTokens('multiple_choice')).toBe(200)
    })

    it('should return correct max_tokens for generation', () => {
      expect(getDefaultMaxTokens('generation')).toBe(2000)
    })

    it('should return default 500 for unknown task types', () => {
      expect(getDefaultMaxTokens('unknown')).toBe(500)
      expect(getDefaultMaxTokens('custom')).toBe(500)
      expect(getDefaultMaxTokens('')).toBe(500)
    })
  })
})
